from __future__ import annotations

from engine.constants import ATTRS
from engine.content import ContentBundle


INITIAL_HIGH_PRIORITY = ("mind", "skill", "stamina", "academics", "social", "finance")
FINAL_LOW_PRIORITY = tuple(reversed(INITIAL_HIGH_PRIORITY))


def _ordered_extreme(attrs: dict[str, int], order: tuple[str, ...], *, highest: bool) -> str:
    attr_set = set(ATTRS)
    values = {attr: int(attrs[attr]) for attr in ATTRS if attr in attrs}
    if set(values) != attr_set:
        missing = ", ".join(sorted(attr_set - set(values)))
        raise ValueError(f"Personality classification missing attrs: {missing}")

    target = max(values.values()) if highest else min(values.values())
    for attr in order:
        if values[attr] == target:
            return attr
    raise ValueError("Unable to resolve personality attribute")


def classify_initial_personality(content: ContentBundle, attrs: dict[str, int]) -> str:
    """Classify the allocation persona by highest attr with the required tie order."""
    attr = _ordered_extreme(attrs, INITIAL_HIGH_PRIORITY, highest=True)
    attr_map = content.personality.get("initial_attr_map", {})
    pid = attr_map.get(attr)
    if not isinstance(pid, str) or not pid:
        raise ValueError(f"Missing initial personality mapping for attr: {attr}")
    return pid


def classify_final_personality(content: ContentBundle, attrs: dict[str, int]) -> str:
    """Classify the report persona by highest and lowest ending attrs.

    The document defines the high-attribute priority. It does not define low-attr
    ties, so we keep them deterministic by using the reverse high priority.
    """
    high = _ordered_extreme(attrs, INITIAL_HIGH_PRIORITY, highest=True)
    low = _ordered_extreme(attrs, FINAL_LOW_PRIORITY, highest=False)
    rules = content.personality.get("final_rules", {})
    attr_rules = rules.get(high, {})
    pid = attr_rules.get(low)
    if not isinstance(pid, str) or not pid:
        raise ValueError(f"Missing final personality mapping for high={high}, low={low}")
    return pid


def classify_personality(content: ContentBundle, attrs: dict[str, int]) -> str:
    return classify_initial_personality(content, attrs)
