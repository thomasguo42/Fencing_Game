#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content" / "v3.3.0"

ATTRS = ["stamina", "skill", "mind", "academics", "social", "finance"]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Failed to load JSON {path}: {e}")


def require(condition: bool, msg: str) -> None:
    if not condition:
        die(msg)


def validate_rules(rules: dict) -> None:
    require(rules.get("ruleset_version") == "v3.3.0", "rules.json ruleset_version must be v3.3.0")
    require(rules.get("attributes") == ATTRS, "rules.json attributes must match canonical attr list")

    alloc = rules.get("allocation", {})
    require(alloc.get("total_points") == 250, "allocation.total_points must be 250")
    require(alloc.get("min_per_attr") == 25, "allocation.min_per_attr must be 25")
    require(alloc.get("max_per_attr") == 60, "allocation.max_per_attr must be 60")

    clamp = rules.get("clamp", {})
    require(clamp.get("min") == 0 and clamp.get("max") == 100, "clamp must be [0,100]")

    redlines = rules.get("redlines", {})
    for a in ATTRS:
        v = redlines.get(a)
        require(isinstance(v, int), f"redlines.{a} must be int")
        require(v > 0, f"redlines.{a} must be > 0")

    require(rules.get("warning_offset") == 5, "warning_offset must be 5")

    scoring = rules.get("scoring", {})
    weights = scoring.get("weights", {})
    for a in ATTRS:
        require(isinstance(weights.get(a), (int, float)), f"scoring.weights.{a} must be number")

    rounding = scoring.get("rounding", {})
    require(rounding.get("score") == "half_up", "scoring.rounding.score must be half_up")

    factors = scoring.get("factors", {})
    required_factors = [
        "final_win_fancy",
        "final_win_normal",
        "final_win_close",
        "final_lose_close",
        "final_lose",
        "collapse",
    ]
    for k in required_factors:
        require(isinstance(factors.get(k), (int, float)), f"scoring.factors.{k} must be number")
    require(factors.get("collapse") == 0.80, "scoring.factors.collapse must be 0.80")


def validate_personality(personality: dict) -> None:
    require(personality.get("ruleset_version") == "v3.3.0", "personality.json ruleset_version must be v3.3.0")
    types = personality.get("types", [])
    require(len(types) == 8, "personality.types must have 8 entries")

    ids = [t.get("id") for t in types]
    require(len(set(ids)) == 8, "personality.types ids must be unique")

    default_types = [t for t in types if t.get("is_default") is True]
    require(len(default_types) == 1, "personality must have exactly one is_default=true type")
    default_id = default_types[0].get("id")

    priority = personality.get("priority_order", [])
    require(isinstance(priority, list) and len(priority) == 8, "personality.priority_order must list 8 ids")
    require(set(priority) == set(ids), "personality.priority_order must include exactly the same ids as types")
    require(priority[-1] == default_id, "default personality must be last in priority_order")

    for t in types:
        tid = t.get("id")
        require(isinstance(tid, str) and tid, "personality.type.id required")
        require(isinstance(t.get("name_cn"), str) and t.get("name_cn"), f"{tid}: name_cn required")
        copy = (t.get("copy_cn") or {})
        require(isinstance(copy.get("short"), str) and copy.get("short"), f"personality {tid} copy_cn.short required")
        require(isinstance(copy.get("long"), str) and copy.get("long"), f"personality {tid} copy_cn.long required")


def validate_delta_value(v, ctx: str) -> None:
    if isinstance(v, int):
        return
    if isinstance(v, dict) and "plus_minus" in v:
        n = v.get("plus_minus")
        require(isinstance(n, int) and n > 0, f"{ctx}: plus_minus must be positive int")
        return
    die(f"{ctx}: delta must be int or {{plus_minus:int}}")


def validate_weeks(weeks: dict) -> None:
    require(weeks.get("ruleset_version") == "v3.3.0", "weeks.json ruleset_version must be v3.3.0")
    ws = weeks.get("weeks", [])
    require(len(ws) == 12, "weeks.weeks must have 12 entries")

    seen_week_ids = set()
    seen_option_ids = set()

    for week in ws:
        wid = week.get("id")
        require(isinstance(wid, str) and wid, "week.id required")
        require(wid not in seen_week_ids, f"duplicate week id: {wid}")
        seen_week_ids.add(wid)

        require(isinstance(week.get("title_cn"), str) and week.get("title_cn"), f"{wid}: title_cn required")
        require(isinstance(week.get("narrative_cn"), str) and week.get("narrative_cn"), f"{wid}: narrative_cn required")

        m = re.match(r"week_(\d{2})$", wid)
        require(m is not None, f"{wid}: week id must match week_XX")
        wk_num = int(m.group(1))

        opts = week.get("options", [])
        if wk_num == 12:
            require(opts == [] or len(opts) == 0, "week_12 options must be empty (final tactics live in finals.json)")
            continue

        require(len(opts) == 6, f"{wid}: must have exactly 6 options")
        for opt in opts:
            oid = opt.get("id")
            require(isinstance(oid, str) and oid, f"{wid}: option.id required")
            require(oid not in seen_option_ids, f"duplicate option id: {oid}")
            seen_option_ids.add(oid)

            require(isinstance(opt.get("title_cn"), str) and opt.get("title_cn"), f"{oid}: title_cn required")
            require(isinstance(opt.get("desc_cn"), str) and opt.get("desc_cn"), f"{oid}: desc_cn required")
            require(isinstance(opt.get("result_cn"), str) and opt.get("result_cn"), f"{oid}: result_cn required")

            deltas = opt.get("deltas", {})
            require(isinstance(deltas, dict) and deltas, f"{oid}: deltas must be non-empty object")
            for k, v in deltas.items():
                require(k in ATTRS, f"{oid}: delta attr {k} not in canonical attr list")
                validate_delta_value(v, f"{oid}.deltas.{k}")


def validate_finals(finals: dict) -> None:
    require(finals.get("ruleset_version") == "v3.3.0", "finals.json ruleset_version must be v3.3.0")
    tactics = finals.get("tactics", [])
    require(len(tactics) == 6, "finals.tactics must have 6 entries")
    ids = [t.get("id") for t in tactics]
    require(len(set(ids)) == 6, "finals.tactics ids must be unique")

    for t in tactics:
        tid = t.get("id")
        require(isinstance(tid, str) and tid, "tactic.id required")
        require(isinstance(t.get("name_cn"), str) and t.get("name_cn"), f"{tid}: name_cn required")
        require(isinstance(t.get("desc_cn"), str) and t.get("desc_cn"), f"{tid}: desc_cn required")

        req = t.get("requirements", {})
        require(isinstance(req, dict) and req, f"{tid}: requirements required")
        for a, v in req.items():
            require(a in ATTRS, f"{tid}: requirement attr {a} invalid")
            require(isinstance(v, int), f"{tid}: requirement value for {a} must be int")

        for fld in ("on_meet_apply", "on_fail_apply"):
            d = t.get(fld, {})
            require(isinstance(d, dict) and d, f"{tid}: {fld} required")
            for a, v in d.items():
                require(a in ATTRS, f"{tid}: {fld} attr {a} invalid")
                require(isinstance(v, int), f"{tid}: {fld} value for {a} must be int")


def validate_achievements(ach: dict) -> None:
    require(ach.get("ruleset_version") == "v3.3.0", "achievements.json ruleset_version must be v3.3.0")
    for group in ("core", "special", "legend"):
        items = ach.get(group, [])
        require(isinstance(items, list), f"achievements.{group} must be a list")
        for it in items:
            aid = it.get("id")
            require(isinstance(aid, str) and aid, f"achievement in {group} missing id")
            require(isinstance(it.get("name_cn"), str) and it.get("name_cn"), f"{aid}: name_cn required")
            require(isinstance(it.get("desc_cn"), str) and it.get("desc_cn"), f"{aid}: desc_cn required")


def validate_endings(endings: dict) -> None:
    require(endings.get("ruleset_version") == "v3.3.0", "endings.json ruleset_version must be v3.3.0")
    ce = endings.get("collapse_endings", [])
    require(len(ce) == 6, "collapse_endings must have 6 entries")
    ids = [e.get("id") for e in ce]
    require(len(set(ids)) == 6, "collapse_endings ids must be unique")
    for e in ce:
        eid = e.get("id")
        require(isinstance(eid, str) and eid, "collapse ending id required")
        require(isinstance(e.get("name_cn"), str) and e.get("name_cn"), f"{eid}: name_cn required")
        require(isinstance(e.get("copy_cn"), str) and e.get("copy_cn"), f"{eid}: copy_cn required")


def validate_intro(intro: dict) -> None:
    require(intro.get("ruleset_version") == "v3.3.0", "intro.json ruleset_version must be v3.3.0")
    opening = intro.get("opening", {})
    require(isinstance(opening.get("scene_cn"), str) and opening.get("scene_cn"), "intro.opening.scene_cn required")
    lines = opening.get("voiceover_lines_cn", [])
    require(isinstance(lines, list) and len(lines) >= 5, "intro.opening.voiceover_lines_cn must be list with >=5 lines")

    alloc = intro.get("allocation", {})
    attrs = alloc.get("attributes", [])
    require(isinstance(attrs, list) and len(attrs) == 6, "intro.allocation.attributes must have 6 entries")
    ids = [a.get("id") for a in attrs]
    require(set(ids) == set(ATTRS), "intro.allocation.attributes ids must match canonical attr list")


def validate_report_templates(rpt: dict) -> None:
    require(rpt.get("ruleset_version") == "v3.3.0", "report_templates.json ruleset_version must be v3.3.0")
    tpl = rpt.get("templates", {})
    for k in ("trajectory_summary_cn", "coach_note_cn", "teammate_note_cn", "final_moment_cn"):
        require(isinstance(tpl.get(k), str) and tpl.get(k), f"report_templates.templates.{k} required")


def validate_report_reference(rref: dict) -> None:
    require(rref.get("ruleset_version") == "v3.3.0", "report_reference.json ruleset_version must be v3.3.0")
    require(isinstance(rref.get("annual_report_template_cn"), str) and rref.get("annual_report_template_cn"), "report_reference.annual_report_template_cn required")
    require(isinstance(rref.get("annual_report_sample_win_cn"), str) and rref.get("annual_report_sample_win_cn"), "report_reference.annual_report_sample_win_cn required")


def validate_ui(ui: dict) -> None:
    require(ui.get("ruleset_version") == "v3.3.0", "ui.json ruleset_version must be v3.3.0")
    nav = ui.get("nav_cn", {})
    require(isinstance(nav.get("start_new"), str) and nav.get("start_new"), "ui.nav_cn.start_new required")
    require(isinstance(nav.get("restart"), str) and nav.get("restart"), "ui.nav_cn.restart required")


def validate_experience(exp: dict) -> None:
    require(exp.get("ruleset_version") == "v3.3.0", "experience.json ruleset_version must be v3.3.0")
    journey = exp.get("single_run_journey_cn", [])
    require(isinstance(journey, list) and len(journey) >= 5, "experience.single_run_journey_cn must have >=5 steps")
    closing = exp.get("closing_message_cn", [])
    require(isinstance(closing, list) and len(closing) >= 3, "experience.closing_message_cn must have >=3 lines")

def validate_changelog(chg: dict) -> None:
    require(chg.get("ruleset_version") == "v3.3.0", "changelog.json ruleset_version must be v3.3.0")
    require(isinstance(chg.get("items_cn"), list) and len(chg.get("items_cn")) == 7, "changelog.items_cn must have 7 items")
    require(isinstance(chg.get("summary_cn"), str) and chg.get("summary_cn"), "changelog.summary_cn required")


def main() -> None:
    require(CONTENT_DIR.exists(), f"Content dir not found: {CONTENT_DIR}")

    rules = load_json(CONTENT_DIR / "rules.json")
    personality = load_json(CONTENT_DIR / "personality.json")
    weeks = load_json(CONTENT_DIR / "weeks.json")
    finals = load_json(CONTENT_DIR / "finals.json")
    achievements = load_json(CONTENT_DIR / "achievements.json")
    endings = load_json(CONTENT_DIR / "endings.json")
    intro = load_json(CONTENT_DIR / "intro.json")
    rpt = load_json(CONTENT_DIR / "report_templates.json")
    ui = load_json(CONTENT_DIR / "ui.json")
    exp = load_json(CONTENT_DIR / "experience.json")
    rref = load_json(CONTENT_DIR / "report_reference.json")
    chg = load_json(CONTENT_DIR / "changelog.json")

    validate_rules(rules)
    validate_personality(personality)
    validate_weeks(weeks)
    validate_finals(finals)
    validate_achievements(achievements)
    validate_endings(endings)
    validate_intro(intro)
    validate_report_templates(rpt)
    validate_report_reference(rref)
    validate_ui(ui)
    validate_experience(exp)
    validate_changelog(chg)

    print("OK: content v3.3.0 validated")


if __name__ == "__main__":
    main()
