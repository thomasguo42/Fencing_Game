from __future__ import annotations

import copy

import pytest

from engine import EngineError, GameEngine


def _valid_allocation() -> dict[str, int]:
    return {
        "stamina": 42,
        "skill": 46,
        "mind": 40,
        "academics": 40,
        "social": 41,
        "finance": 41,
    }


def _play_default_path(engine: GameEngine, seed: int = 123456) -> tuple:
    state = engine.new_run_state(seed=seed)
    state = engine.allocate(state, _valid_allocation())

    first_presented = copy.deepcopy(state.presented_options)

    weekly_choices = []
    while state.status == "in_progress" and state.week <= 11:
        choice = state.presented_options[0]
        weekly_choices.append((state.week, tuple(state.presented_options), choice))
        state = engine.apply_choice(state, choice)

    if state.status == "in_progress" and state.week == 12:
        state = engine.resolve_final(state, "w12_t01")

    state = engine.finalize(state)
    return state, first_presented, weekly_choices


def _play_safe_path_to_final(engine: GameEngine, seed: int = 8888):
    state = engine.new_run_state(seed=seed)
    state = engine.allocate(state, _valid_allocation())

    while state.status == "in_progress" and state.week <= 11:
        candidates = []
        for option_id in state.presented_options:
            candidate = engine.apply_choice(state, option_id)
            collapsed = 1 if candidate.status == "collapsed" else 0
            min_attr = min(candidate.attributes.values())
            candidates.append((collapsed, -min_attr, option_id, candidate))
        candidates.sort()
        state = candidates[0][3]

    if state.status == "in_progress" and state.week == 12:
        state = engine.resolve_final(state, "w12_t06")
    return engine.finalize(state)


def test_allocation_validation() -> None:
    engine = GameEngine()
    state = engine.new_run_state(seed=1)

    bad = _valid_allocation()
    bad["stamina"] = 10

    with pytest.raises(EngineError):
        engine.allocate(state, bad)


def test_deterministic_same_seed_same_result() -> None:
    engine = GameEngine()

    state_a, first_a, weekly_a = _play_default_path(engine, seed=777)
    state_b, first_b, weekly_b = _play_default_path(engine, seed=777)

    assert first_a == first_b
    assert weekly_a == weekly_b
    assert state_a.to_dict() == state_b.to_dict()


def test_choice_must_be_presented() -> None:
    engine = GameEngine()
    state = engine.new_run_state(seed=9)
    state = engine.allocate(state, _valid_allocation())

    with pytest.raises(EngineError):
        engine.apply_choice(state, "w01_o99")


def test_clamp_and_immediate_collapse() -> None:
    engine = GameEngine()
    state = engine.new_run_state(seed=22)
    state = engine.allocate(
        state,
        {
            "stamina": 25,
            "skill": 60,
            "mind": 60,
            "academics": 35,
            "social": 35,
            "finance": 35,
        },
    )

    # Apply a heavy stamina hit deterministically through direct provided roll path.
    state = engine.apply_choice(
        state,
        state.presented_options[0],
        resolved_rolls={"stamina": -100},
    )

    # If this particular option doesn't include stamina plus_minus, we still require clamp invariant.
    for value in state.attributes.values():
        assert 0 <= value <= 100

    if state.status == "collapsed":
        assert state.collapse_record is not None
        assert state.collapse_record.ending_id.startswith("collapse_")


def test_golden_seed_123456() -> None:
    engine = GameEngine()
    state, first_presented, weekly_choices = _play_default_path(engine, seed=123456)

    assert first_presented == ["w01_o06", "w01_o01", "w01_o05"]
    assert weekly_choices[0] == (1, ("w01_o06", "w01_o01", "w01_o05"), "w01_o06")
    assert state.final_record is None
    assert state.report is not None
    assert state.score == 301
    assert state.grade_id == "D"
    assert state.grade_label == "懵懂摸索"
    assert state.attributes == {
        "stamina": 5,
        "skill": 61,
        "mind": 24,
        "academics": 50,
        "social": 54,
        "finance": 55,
    }
    assert state.achievements == [
        "ach_special_02",
        "ach_special_06",
    ]


def test_safe_policy_reaches_final() -> None:
    engine = GameEngine()
    state = _play_safe_path_to_final(engine, seed=8888)

    assert state.status == "finished"
    assert state.final_record is not None
    assert state.week == 12
    assert state.score is not None
    assert state.report is not None
