from __future__ import annotations

from dataclasses import replace
from typing import Any

from engine.achievements import evaluate_achievements
from engine.constants import ATTRS, COLLAPSE_ENDING_ID, RULESET_VERSION
from engine.content import ContentBundle, load_content, option_by_id, tactic_by_id, week_by_num
from engine.models import CollapseRecord, FinalRecord, RunState, WeekHistoryRecord
from engine.personality import classify_final_personality, classify_initial_personality
from engine.report import build_report
from engine.rng import deterministic_rng
from engine.scoring import compute_score_and_grade


class EngineError(ValueError):
    pass


class GameEngine:
    def __init__(self, content: ContentBundle | None = None):
        self.content = content or load_content()
        if self.content.rules["ruleset_version"] != RULESET_VERSION:
            raise EngineError("Unsupported ruleset version")

    def new_run_state(self, seed: int) -> RunState:
        return RunState(seed=int(seed), ruleset_version=RULESET_VERSION)

    def allocate(self, state: RunState, attributes_initial: dict[str, int]) -> RunState:
        self._ensure_state_in_progress(state)
        if state.week != 0:
            raise EngineError("Allocation can only happen at week 0")

        alloc = self.content.rules["allocation"]
        required_total = int(alloc["total_points"])
        min_per_attr = int(alloc["min_per_attr"])
        max_per_attr = int(alloc["max_per_attr"])

        if set(attributes_initial.keys()) != set(ATTRS):
            raise EngineError("Allocation must include all six attributes")

        total = sum(int(attributes_initial[a]) for a in ATTRS)
        if total != required_total:
            raise EngineError(f"Allocation total must be {required_total}")

        for attr in ATTRS:
            value = int(attributes_initial[attr])
            if value < min_per_attr or value > max_per_attr:
                raise EngineError(f"{attr} must be in [{min_per_attr}, {max_per_attr}]")

        attrs = {a: int(attributes_initial[a]) for a in ATTRS}
        personality_start = classify_initial_personality(self.content, attrs)
        presented = self.present_week(state.seed, week=1)

        return replace(
            state,
            week=1,
            attributes=attrs,
            min_attributes=dict(attrs),
            attributes_start=dict(attrs),
            personality_start=personality_start,
            presented_options=presented,
            warning_attrs=self._warning_attrs(attrs),
        )

    def present_week(self, seed: int, week: int) -> list[str]:
        if week < 1 or week > 11:
            raise EngineError("Week option presentation is only valid for weeks 1..11")

        week_data = week_by_num(self.content, week)
        options = week_data["options"]
        original_ids = [opt["id"] for opt in options if opt.get("option_type") != "custom"]
        custom_ids = [opt["id"] for opt in options if opt.get("option_type") == "custom"]

        if len(original_ids) >= 2 and len(custom_ids) >= 1:
            selected = self._deterministic_sample(original_ids, seed, week, "present_original", 2)
            selected += self._deterministic_sample(custom_ids, seed, week, "present_custom", 1)
            return self._deterministic_sample(selected, seed, week, "present_mix", len(selected))

        option_ids = [opt["id"] for opt in options]
        return self._deterministic_sample(option_ids, seed, week, "present", 3)

    def apply_choice(
        self,
        state: RunState,
        option_id: str,
        presented_option_ids: list[str] | None = None,
        resolved_rolls: dict[str, int] | None = None,
    ) -> RunState:
        self._ensure_state_in_progress(state)
        if state.week < 1 or state.week > 11:
            raise EngineError("Choices can only be applied for weeks 1..11")

        presented = presented_option_ids or state.presented_options
        if option_id not in presented:
            raise EngineError("Chosen option was not presented")

        option = option_by_id(self.content, state.week, option_id)
        applied, rolls = self._resolve_deltas(
            week=state.week,
            choice_id=option_id,
            deltas=option["deltas"],
            seed=state.seed,
            provided_rolls=resolved_rolls,
        )

        new_attrs = self._apply_attr_deltas(state.attributes, applied)
        warning_attrs = self._warning_attrs(new_attrs)

        history = list(state.history)
        history.append(
            WeekHistoryRecord(
                week_num=state.week,
                week_id=f"week_{state.week:02d}",
                presented_option_ids=list(presented),
                chosen_id=option_id,
                resolved_rolls=rolls,
                applied_deltas=applied,
            )
        )

        collapse_attr = self._collapse_attr(new_attrs)
        if collapse_attr is not None:
            collapse = CollapseRecord(
                week_num=state.week,
                attr=collapse_attr,
                ending_id=COLLAPSE_ENDING_ID[collapse_attr],
            )
            personality_end = classify_final_personality(self.content, new_attrs)
            return replace(
                state,
                attributes=new_attrs,
                min_attributes=self._min_update(state.min_attributes, new_attrs),
                history=history,
                status="collapsed",
                warning_attrs=warning_attrs,
                collapse_record=collapse,
                personality_end=personality_end,
            )

        next_week = state.week + 1
        next_presented: list[str] = []
        if next_week <= 11:
            next_presented = self.present_week(state.seed, next_week)

        return replace(
            state,
            week=next_week,
            attributes=new_attrs,
            min_attributes=self._min_update(state.min_attributes, new_attrs),
            history=history,
            presented_options=next_presented,
            warning_attrs=warning_attrs,
        )

    def resolve_final(self, state: RunState, tactic_id: str) -> RunState:
        self._ensure_state_in_progress(state)
        if state.week != 12:
            raise EngineError("Final can only be resolved at week 12")

        tactic = tactic_by_id(self.content, tactic_id)
        requirements = tactic["requirements"]
        requirements_mode = tactic.get("requirements_mode", "all")

        checks = [state.attributes[attr] >= int(req) for attr, req in requirements.items()]
        requirements_met = all(checks) if requirements_mode == "all" else any(checks)

        win_rate = 0.0
        roll_int = None
        final_tier = None

        if requirements_met:
            applied = {a: int(v) for a, v in tactic["on_meet_apply"].items()}
            excess = self._final_excess(state.attributes, requirements)

            cfg = self.content.rules["rng"]["final_win"]
            base = float(cfg["base_win_rate"])
            step = int(cfg["step_excess"])
            bonus = float(cfg["step_bonus"])
            cap = float(cfg["max_win_rate"])
            win_rate = min(max(base + (excess // step) * bonus, 0.0), cap)

            rng = deterministic_rng(state.seed, state.ruleset_version, "final_win", tactic_id)
            roll_int = rng.randint(0, 9999)
            wins = roll_int < int(win_rate * 10000)

            if wins:
                final_result = "胜利"
                final_tier = self._final_tier(excess)
            else:
                final_result = "惜败"
        else:
            applied = {a: int(v) for a, v in tactic["on_fail_apply"].items()}
            final_result = "失利"

        new_attrs = self._apply_attr_deltas(state.attributes, applied)

        final_record = FinalRecord(
            tactic_id=tactic_id,
            requirements_met=requirements_met,
            win_rate=win_rate,
            roll_int=roll_int,
            final_result=final_result,
            final_tier=final_tier,
            applied_deltas=applied,
        )

        personality_end = classify_final_personality(self.content, new_attrs)

        return replace(
            state,
            status="finished",
            attributes=new_attrs,
            min_attributes=self._min_update(state.min_attributes, new_attrs),
            final_record=final_record,
            personality_end=personality_end,
            warning_attrs=self._warning_attrs(new_attrs),
        )

    def finalize(self, state: RunState) -> RunState:
        if state.status not in {"finished", "collapsed"}:
            raise EngineError("Run can only be finalized when finished or collapsed")

        score, grade_id, grade_label, score_details = compute_score_and_grade(self.content, state)
        achievements = evaluate_achievements(self.content, state, score)
        report = build_report(self.content, state)

        payload = {
            "attrs_start": state.attributes_start,
            "attrs_end": state.attributes,
            "attrs_min": state.min_attributes,
            "personality_start": state.personality_start,
            "personality_end": state.personality_end,
            "final": state.final_record.__dict__ if state.final_record else None,
            "score": score,
            "score_details": score_details,
            "grade": {"id": grade_id, "label": grade_label},
            "achievements": achievements,
            "report_sections": report,
        }

        return replace(
            state,
            score=score,
            grade_id=grade_id,
            grade_label=grade_label,
            achievements=achievements,
            report=payload,
        )

    def _ensure_state_in_progress(self, state: RunState) -> None:
        if state.status != "in_progress":
            raise EngineError("Run is not in progress")

    def _resolve_deltas(
        self,
        week: int,
        choice_id: str,
        deltas: dict[str, Any],
        seed: int,
        provided_rolls: dict[str, int] | None,
    ) -> tuple[dict[str, int], dict[str, int]]:
        applied: dict[str, int] = {}
        rolls: dict[str, int] = {}

        for attr, raw in deltas.items():
            if isinstance(raw, int):
                applied[attr] = raw
                continue

            if isinstance(raw, dict) and "plus_minus" in raw:
                n = int(raw["plus_minus"])
                if provided_rolls and attr in provided_rolls:
                    delta = int(provided_rolls[attr])
                else:
                    rng = deterministic_rng(seed, RULESET_VERSION, week, choice_id, attr, "plus_minus")
                    heads = sum(rng.coin_flip() for _ in range(2 * n))
                    delta = heads - n
                applied[attr] = delta
                rolls[attr] = delta
                continue

            raise EngineError(f"Unsupported delta format for {attr}: {raw}")

        return applied, rolls

    def _deterministic_sample(self, option_ids: list[str], seed: int, week: int, namespace: str, count: int) -> list[str]:
        rng = deterministic_rng(seed, RULESET_VERSION, week, namespace)
        shuffled = list(option_ids)
        for i in range(len(shuffled) - 1, 0, -1):
            j = rng.randint(0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled[:count]

    def _apply_attr_deltas(self, attrs: dict[str, int], deltas: dict[str, int]) -> dict[str, int]:
        clamp_min = int(self.content.rules["clamp"]["min"])
        clamp_max = int(self.content.rules["clamp"]["max"])

        out = dict(attrs)
        for attr in ATTRS:
            out[attr] = int(out[attr] + deltas.get(attr, 0))
            out[attr] = max(clamp_min, min(clamp_max, out[attr]))
        return out

    def _collapse_attr(self, attrs: dict[str, int]) -> str | None:
        redlines = self.content.rules["redlines"]
        for attr in ATTRS:
            if attrs[attr] <= int(redlines[attr]):
                return attr
        return None

    def _warning_attrs(self, attrs: dict[str, int]) -> list[str]:
        redlines = self.content.rules["redlines"]
        warning_offset = int(self.content.rules["warning_offset"])
        return [a for a in ATTRS if attrs[a] <= int(redlines[a]) + warning_offset]

    @staticmethod
    def _min_update(min_attrs: dict[str, int], attrs: dict[str, int]) -> dict[str, int]:
        return {a: min(min_attrs[a], attrs[a]) for a in ATTRS}

    @staticmethod
    def _final_excess(attrs: dict[str, int], requirements: dict[str, int]) -> int:
        if len(requirements) == 1:
            (attr, req), = requirements.items()
            return attrs[attr] - int(req)

        if set(requirements.keys()) == {"skill", "mind"}:
            return min(attrs["skill"] - int(requirements["skill"]), attrs["mind"] - int(requirements["mind"]))

        excesses = [attrs[attr] - int(req) for attr, req in requirements.items()]
        return min(excesses)

    @staticmethod
    def _final_tier(excess: int) -> str:
        if excess >= 10:
            return "fancy"
        if excess >= 5:
            return "normal"
        return "close"
