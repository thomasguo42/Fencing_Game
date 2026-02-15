from __future__ import annotations

from engine.constants import ATTRS
from engine.content import ContentBundle
from engine.models import RunState


def _check_conditions(state: RunState, score: int, conditions: dict) -> bool:
    for key, value in conditions.items():
        if key == "completed_weeks_eq":
            if state.completed_weeks != int(value):
                return False
        elif key == "all_attrs_between_inclusive":
            low = int(value["min"])
            high = int(value["max"])
            if not all(low <= state.attributes[a] <= high for a in ATTRS):
                return False
        elif key == "attr_gte":
            for attr, threshold in value.items():
                if state.attributes[attr] < int(threshold):
                    return False
        elif key == "total_score_gte":
            if score < int(value):
                return False
        elif key == "personality_end_not_equal_start":
            if bool(value) and state.personality_end == state.personality_start:
                return False
        elif key == "at_least_k_of_attrs_gte":
            needed = int(value["k"])
            threshold = int(value["value"])
            attrs = value["attrs"]
            count = sum(1 for attr in attrs if state.attributes[attr] >= threshold)
            if count < needed:
                return False
        elif key == "no_attr_below":
            threshold = int(value)
            if any(state.attributes[a] < threshold for a in ATTRS):
                return False
        elif key == "attr_never_below":
            for attr, threshold in value.items():
                if state.min_attributes[attr] < int(threshold):
                    return False
        elif key == "final_win_with_requirements_met":
            final = state.final_record
            if not (final and final.requirements_met and final.final_result == "胜利"):
                return False
        elif key == "not_collapsed":
            if bool(value) and state.status == "collapsed":
                return False
        else:
            raise ValueError(f"Unsupported achievement condition: {key}")
    return True


def evaluate_achievements(content: ContentBundle, state: RunState, score: int) -> list[str]:
    unlocked: list[str] = []
    for group in ("core", "special", "legend"):
        for ach in content.achievements[group]:
            if _check_conditions(state, score, ach.get("conditions", {})):
                unlocked.append(ach["id"])
    return unlocked
