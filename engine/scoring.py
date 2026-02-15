from __future__ import annotations

import math

from engine.constants import ATTRS
from engine.content import ContentBundle
from engine.models import RunState
from engine.rng import deterministic_rng


def round_half_up(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _score_factor(content: ContentBundle, state: RunState) -> float:
    factors = content.rules["scoring"]["factors"]

    if state.status == "collapsed":
        return float(factors["collapse"])

    final = state.final_record
    if final is None:
        return float(factors["no_final"])

    if final.final_result == "胜利":
        if final.final_tier == "fancy":
            return float(factors["final_win_fancy"])
        if final.final_tier == "normal":
            return float(factors["final_win_normal"])
        return float(factors["final_win_close"])

    if final.final_result == "惜败":
        return float(factors["final_lose_close"])

    return float(factors["final_lose"])


def compute_score_and_grade(content: ContentBundle, state: RunState) -> tuple[int, str, str, dict[str, float | int]]:
    weights = content.rules["scoring"]["weights"]
    base_score = sum(state.attributes[a] * float(weights[a]) for a in ATTRS)
    factor = _score_factor(content, state)

    rng = deterministic_rng(state.seed, state.ruleset_version, "score_micro")
    magnitude_choices = [int(x) for x in content.rules["scoring"]["micro_tweak_pct_choices"]]
    sign_choices = [int(x) for x in content.rules["scoring"]["micro_tweak_sign_choices"]]
    magnitude = magnitude_choices[rng.randint(0, len(magnitude_choices) - 1)]
    sign = sign_choices[rng.randint(0, len(sign_choices) - 1)]

    micro_multiplier = 1.0 + sign * (magnitude / 100.0)
    final_score = round_half_up(base_score * factor * micro_multiplier)

    grade_id = "D"
    grade_label = ""
    for band in content.rules["scoring"]["grades"]:
        if int(band["min_score"]) <= final_score <= int(band["max_score"]):
            grade_id = str(band["id"])
            grade_label = str(band["label"])
            break

    details = {
        "base_score": base_score,
        "factor": factor,
        "micro_magnitude_pct": magnitude,
        "micro_sign": sign,
        "micro_multiplier": micro_multiplier,
    }
    return final_score, grade_id, grade_label, details
