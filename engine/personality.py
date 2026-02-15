from __future__ import annotations

from collections import Counter

from engine.constants import ATTRS
from engine.content import ContentBundle


def _all_between(attrs: dict[str, int], low: int, high: int) -> bool:
    return all(low <= attrs[a] <= high for a in ATTRS)


def _lead_over_second(attrs: dict[str, int], target_attr: str, gap: int) -> bool:
    sorted_items = sorted(attrs.items(), key=lambda kv: kv[1], reverse=True)
    if not sorted_items or sorted_items[0][0] != target_attr:
        return False
    second = sorted_items[1][1] if len(sorted_items) > 1 else sorted_items[0][1]
    return attrs[target_attr] - second >= gap


def _at_least_two_pairs_ge55_le35(attrs: dict[str, int]) -> bool:
    counts = Counter()
    for value in attrs.values():
        if value >= 55:
            counts["high"] += 1
        if value <= 35:
            counts["low"] += 1
    return counts["high"] >= 2 and counts["low"] >= 2


def _matches_conditions(attrs: dict[str, int], conditions: dict[str, object]) -> bool:
    for key, value in conditions.items():
        if key == "all_between_inclusive":
            low = int(value["min"])
            high = int(value["max"])
            if not _all_between(attrs, low, high):
                return False
        elif key == "lead_over_second_gte":
            if not _lead_over_second(attrs, "skill", int(value)):
                return False
        elif key.endswith("_gte") and key.split("_gte")[0] in ATTRS:
            attr = key.split("_gte")[0]
            if attrs[attr] < int(value):
                return False
        elif key == "either_skill_or_mind_gte":
            n = int(value)
            if attrs["skill"] < n and attrs["mind"] < n:
                return False
        elif key == "the_other_lte":
            n = int(value)
            if attrs["skill"] >= attrs["mind"]:
                if attrs["mind"] > n:
                    return False
            else:
                if attrs["skill"] > n:
                    return False
        elif key == "at_least_two_pairs_ge55_le35":
            if bool(value) and not _at_least_two_pairs_ge55_le35(attrs):
                return False
        else:
            raise ValueError(f"Unsupported personality condition key: {key}")
    return True


def classify_personality(content: ContentBundle, attrs: dict[str, int]) -> str:
    types_by_id = {t["id"]: t for t in content.personality["types"]}
    default_id = next(t["id"] for t in content.personality["types"] if t.get("is_default") is True)

    for pid in content.personality["priority_order"]:
        if pid == default_id:
            continue
        entry = types_by_id[pid]
        if _matches_conditions(attrs, entry.get("conditions", {})):
            return pid

    return default_id
