from __future__ import annotations

from typing import Any

from engine.content import ContentBundle, collapse_ending_by_id, option_by_id, personality_by_id, tactic_by_id, week_by_num
from engine.models import RunState


def _personality_meta(content: ContentBundle, personality_id: str | None) -> dict[str, Any] | None:
    if not personality_id:
        return None
    personality = personality_by_id(content, personality_id)
    return {
        "id": personality.get("id"),
        "name_cn": personality.get("name_cn"),
        "copy_cn": personality.get("copy_cn"),
    }


def build_allocation_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "allocation",
        "payload": {
            "intro": content.intro,
            "ui": content.ui.get("allocation_cn", {}),
        },
    }


def build_personality_reveal_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    reveal = content.intro.get("personality_reveal", {}) if isinstance(content.intro, dict) else {}
    template = str(reveal.get("template_cn", ""))
    p = personality_by_id(content, state.personality_start or "white_paper")
    name_cn = str(p.get("name_cn", ""))
    desc_cn = str((p.get("copy_cn") or {}).get("long", ""))
    if template.strip():
        reveal_cn = template.replace("[人格名称]", name_cn).replace("[人格描述]", desc_cn)
    else:
        reveal_cn = f"【你的初形】\n{name_cn}\n{desc_cn}".strip()

    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "personality_reveal",
        "payload": {
            "title_cn": reveal.get("title_cn") or "人格觉醒：你的初貌",
            "cta_cn": reveal.get("cta_cn") or "继续",
            "reveal_cn": reveal_cn,
            "personality": {
                "id": p.get("id"),
                "name_cn": p.get("name_cn"),
                "copy_cn": p.get("copy_cn"),
            },
        },
    }


def build_week_screen(
    content: ContentBundle,
    run_id: str,
    state: RunState,
    presented_options: list[str],
) -> dict[str, Any]:
    week = week_by_num(content, state.week)
    options = []
    for option_id in presented_options:
        opt = option_by_id(content, state.week, option_id)
        options.append(
            {
                "id": opt["id"],
                "title_cn": opt["title_cn"],
                "desc_cn": opt["desc_cn"],
            }
        )

    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "week",
        "payload": {
            "week_id": week["id"],
            "title_cn": week["title_cn"],
            "narrative_cn": week["narrative_cn"],
            "options": options,
            "warning_attrs": list(state.warning_attrs),
            "ui": content.ui.get("week_cn", {}),
        },
    }


def build_finals_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    week = week_by_num(content, 12)
    tactics_public = []
    for tactic in content.finals["tactics"]:
        tactics_public.append(
            {
                "id": tactic["id"],
                "name_cn": tactic["name_cn"],
                "desc_cn": tactic["desc_cn"],
            }
        )
    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "finals",
        "payload": {
            "week_id": week["id"],
            "title_cn": week["title_cn"],
            "narrative_cn": week["narrative_cn"],
            "tactics": tactics_public,
            "ui": content.ui.get("final_cn", {}),
        },
    }


def build_collapse_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    if state.collapse_record is None:
        raise ValueError("collapse record missing")
    ending = collapse_ending_by_id(content, state.collapse_record.ending_id)
    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "collapse",
        "payload": {
            "ending": ending,
            "collapse_week": state.collapse_record.week_num,
            "collapse_attr": state.collapse_record.attr,
            "personality_start_meta": _personality_meta(content, state.personality_start),
            "personality_end_meta": _personality_meta(content, state.personality_end),
            "warning_attrs": list(state.warning_attrs),
        },
    }


def build_final_outcome_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    if state.final_record is None:
        raise ValueError("final record missing")
    tactic = tactic_by_id(content, state.final_record.tactic_id)
    final_tier_cn = None
    if state.final_record.final_result == "胜利":
        tier_map = {
            "fancy": "华丽胜利",
            "normal": "一般胜利",
            "close": "险胜",
        }
        final_tier_cn = tier_map.get(state.final_record.final_tier or "", "险胜")
    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "final_outcome",
        "payload": {
            "result": {
                "tactic_id": state.final_record.tactic_id,
                "tactic_name_cn": tactic["name_cn"],
                "requirements_met": state.final_record.requirements_met,
                "final_result": state.final_record.final_result,
                "final_tier_cn": final_tier_cn,
            },
            "warning_attrs": state.warning_attrs,
        },
    }


def build_report_screen(content: ContentBundle, run_id: str, state: RunState) -> dict[str, Any]:
    if state.report is None:
        raise ValueError("report missing")

    achievement_meta = {}
    for group in ("core", "special", "legend"):
        for item in content.achievements[group]:
            achievement_meta[item["id"]] = item

    detailed_achievements = [achievement_meta[aid] for aid in state.achievements if aid in achievement_meta]

    return {
        "run_id": run_id,
        "status": state.status,
        "week": state.week,
        "screen": "report",
        "payload": {
            "score": state.score,
            "grade": {"id": state.grade_id, "label": state.grade_label},
            "attributes_start": state.attributes_start,
            "attributes_end": state.attributes,
            "min_attributes": state.min_attributes,
            "personality_start": state.personality_start,
            "personality_end": state.personality_end,
            "personality_start_meta": _personality_meta(content, state.personality_start),
            "personality_end_meta": _personality_meta(content, state.personality_end),
            "achievements": detailed_achievements,
            "achievement_ids": state.achievements,
            "report_sections": state.report["report_sections"],
            "ui": content.ui.get("report_cn", {}),
            "reference": content.report_reference,
        },
    }
