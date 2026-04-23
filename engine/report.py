from __future__ import annotations

from typing import Any

from engine.constants import (
    ATTRS,
    ATTR_CN,
    COACH_MOTTO,
    COACH_OPEN,
    FINAL_ACTION,
    RISK_LESSON,
    TEAMMATE_LINE_BANDS,
)
from engine.content import ContentBundle, personality_by_id, tactic_by_id, week_by_num
from engine.models import RunState


def _strengths_and_weaknesses(state: RunState) -> tuple[list[str], str, dict[str, int]]:
    attrs_start = state.attributes_start or {a: 0 for a in ATTRS}
    delta = {a: state.attributes[a] - attrs_start[a] for a in ATTRS}

    strengths_sorted = sorted(
        ATTRS,
        key=lambda a: (state.attributes[a], delta[a]),
        reverse=True,
    )
    strengths = strengths_sorted[:2]

    weaknesses_sorted = sorted(
        ATTRS,
        key=lambda a: (state.attributes[a], -state.min_attributes[a]),
    )
    weakness = weaknesses_sorted[0]
    return strengths, weakness, delta


def _risk_attr(state: RunState) -> str:
    if state.collapse_record is not None:
        return state.collapse_record.attr
    return min(ATTRS, key=lambda a: state.min_attributes[a])


def _turning_point(content: ContentBundle, state: RunState) -> str:
    if state.collapse_record is not None:
        ending = next(
            e for e in content.endings["collapse_endings"] if e["id"] == state.collapse_record.ending_id
        )
        return f"阶段{state.collapse_record.week_num}《{ending['name_cn']}》"

    warning_offset = int(content.rules["warning_offset"])
    redlines = content.rules["redlines"]

    attrs = dict(state.attributes_start or {a: 0 for a in ATTRS})
    for rec in state.history:
        for attr in ATTRS:
            attrs[attr] += rec.applied_deltas.get(attr, 0)
            attrs[attr] = max(0, min(100, attrs[attr]))
        if any(attrs[a] <= int(redlines[a]) + warning_offset for a in ATTRS):
            title = week_by_num(content, rec.week_num)["title_cn"]
            return f"阶段{rec.week_num}《{title}》"

    max_impact = -1
    target = state.history[0] if state.history else None
    for rec in state.history:
        impact = sum(abs(v) for v in rec.applied_deltas.values())
        if impact > max_impact:
            max_impact = impact
            target = rec

    if target is None:
        return "阶段1《入队适应期 · 镜中的笨拙》"

    title = week_by_num(content, target.week_num)["title_cn"]
    return f"阶段{target.week_num}《{title}》"


def build_report(content: ContentBundle, state: RunState) -> dict[str, Any]:
    templates = content.report_templates["templates"]

    p_start = personality_by_id(content, state.personality_start or "white_paper")
    p_end = personality_by_id(content, state.personality_end or state.personality_start or "white_paper")

    strengths, weakness, delta = _strengths_and_weaknesses(state)
    risk_attr = _risk_attr(state)
    turning_point = _turning_point(content, state)

    strengths_cn = "与".join(ATTR_CN[s] for s in strengths)
    weakness_cn = ATTR_CN[weakness]

    notable_growth_attr = max(ATTRS, key=lambda a: delta[a])
    if all(delta[a] <= 0 for a in ATTRS):
        notable_growth_attr = strengths[0]

    teammate_line = ""
    social = state.attributes["social"]
    for threshold, line in TEAMMATE_LINE_BANDS:
        if social >= threshold:
            teammate_line = line
            break

    tactic_name = ""
    final_action = ""
    final_moment = None
    if state.final_record is not None:
        tactic = tactic_by_id(content, state.final_record.tactic_id)
        tactic_name = tactic["name_cn"]
        final_action = FINAL_ACTION[state.final_record.tactic_id]
        final_moment = templates["final_moment_cn"].format(
            tactic_name=tactic_name,
            final_action=final_action,
        )

    trajectory_summary = templates["trajectory_summary_cn"].format(
        start_tone=p_start["copy_cn"]["short"],
        end_tone=p_end["copy_cn"]["short"],
        strengths=strengths_cn,
        weaknesses=weakness_cn,
        turning_point=turning_point,
        lesson=RISK_LESSON[risk_attr],
    )

    coach_note = templates["coach_note_cn"].format(
        coach_open=COACH_OPEN.get(state.personality_start or "", COACH_OPEN["white_paper"]),
        notable_growth=ATTR_CN[notable_growth_attr],
        risk_area=ATTR_CN[risk_attr],
        coach_motto=COACH_MOTTO[risk_attr],
    )

    teammate_note = templates["teammate_note_cn"].format(teammate_line=teammate_line)

    return {
        "trajectory_summary_cn": trajectory_summary,
        "coach_note_cn": coach_note,
        "teammate_note_cn": teammate_note,
        "final_moment_cn": final_moment,
        "fields": {
            "start_tone": p_start["copy_cn"]["short"],
            "end_tone": p_end["copy_cn"]["short"],
            "strengths": strengths_cn,
            "weaknesses": weakness_cn,
            "turning_point": turning_point,
            "lesson": RISK_LESSON[risk_attr],
            "notable_growth": ATTR_CN[notable_growth_attr],
            "risk_area": ATTR_CN[risk_attr],
            "teammate_line": teammate_line,
            "tactic_name": tactic_name,
            "final_action": final_action,
        },
    }
