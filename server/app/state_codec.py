from __future__ import annotations

from dataclasses import replace

from engine.models import CollapseRecord, FinalRecord, RunState, WeekHistoryRecord
from server.app.models import Run, RunWeekLog


def run_to_engine_state(run: Run, week_logs: list[RunWeekLog]) -> RunState:
    history: list[WeekHistoryRecord] = []
    for item in sorted(week_logs, key=lambda x: x.week_number):
        if item.chosen_option_id is None:
            continue
        history.append(
            WeekHistoryRecord(
                week_num=item.week_number,
                week_id=item.week_id,
                presented_option_ids=list(item.presented_option_ids),
                chosen_id=item.chosen_option_id,
                resolved_rolls=dict(item.resolved_rolls or {}),
                applied_deltas=dict(item.applied_deltas or {}),
            )
        )

    final_record = None
    if run.final_tactic_id:
        final_record = FinalRecord(
            tactic_id=run.final_tactic_id,
            requirements_met=bool(run.final_requirements_met),
            win_rate=float(run.final_win_rate or 0.0),
            roll_int=run.final_roll_int,
            final_result=run.final_result or "失利",
            final_tier=run.final_tier,
            applied_deltas=dict(run.final_applied_deltas or {}),
        )

    collapse_record = None
    if run.collapse_ending_id:
        collapse_record = CollapseRecord(
            week_num=int(run.collapse_week or 0),
            attr=str(run.collapse_attr),
            ending_id=run.collapse_ending_id,
        )

    pending_presented = []
    pending = next((w for w in week_logs if w.week_number == run.week and w.chosen_option_id is None), None)
    if pending is not None:
        pending_presented = list(pending.presented_option_ids)

    return RunState(
        seed=run.seed,
        ruleset_version=run.ruleset_version,
        status=run.status,
        week=run.week,
        attributes=dict(run.attributes),
        min_attributes=dict(run.min_attributes),
        attributes_start=dict(run.attributes_start) if run.attributes_start else None,
        personality_start=run.personality_start,
        personality_end=run.personality_end,
        presented_options=pending_presented,
        history=history,
        final_record=final_record,
        collapse_record=collapse_record,
        warning_attrs=list(run.warning_attrs or []),
        score=run.score,
        grade_id=run.grade_id,
        grade_label=run.grade_label,
        achievements=list(run.achievements or []),
        report=dict(run.report) if run.report else None,
    )


def apply_engine_state_to_run(run: Run, state: RunState) -> Run:
    run.ruleset_version = state.ruleset_version
    run.status = state.status
    run.week = state.week
    run.attributes = dict(state.attributes)
    run.min_attributes = dict(state.min_attributes)
    run.attributes_start = dict(state.attributes_start) if state.attributes_start else None
    run.personality_start = state.personality_start
    run.personality_end = state.personality_end
    run.warning_attrs = list(state.warning_attrs)

    if state.final_record is not None:
        run.final_tactic_id = state.final_record.tactic_id
        run.final_requirements_met = state.final_record.requirements_met
        run.final_win_rate = state.final_record.win_rate
        run.final_roll_int = state.final_record.roll_int
        run.final_result = state.final_record.final_result
        run.final_tier = state.final_record.final_tier
        run.final_applied_deltas = dict(state.final_record.applied_deltas)

    if state.collapse_record is not None:
        run.collapse_week = state.collapse_record.week_num
        run.collapse_attr = state.collapse_record.attr
        run.collapse_ending_id = state.collapse_record.ending_id

    run.score = state.score
    run.grade_id = state.grade_id
    run.grade_label = state.grade_label
    run.achievements = list(state.achievements)
    run.report = dict(state.report) if state.report else None
    return run
