from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.constants import RULESET_VERSION


@dataclass
class ContentBundle:
    base_dir: Path
    rules: dict[str, Any]
    personality: dict[str, Any]
    weeks: dict[str, Any]
    finals: dict[str, Any]
    achievements: dict[str, Any]
    endings: dict[str, Any]
    intro: dict[str, Any]
    report_templates: dict[str, Any]
    report_reference: dict[str, Any]
    ui: dict[str, Any]
    experience: dict[str, Any]
    changelog: dict[str, Any]


_CACHE: ContentBundle | None = None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_content(base_dir: str | Path | None = None, refresh: bool = False) -> ContentBundle:
    global _CACHE

    if _CACHE and not refresh and base_dir is None:
        return _CACHE

    if base_dir is None:
        root = Path(__file__).resolve().parents[1]
        base = root / "content" / RULESET_VERSION
    else:
        base = Path(base_dir)

    bundle = ContentBundle(
        base_dir=base,
        rules=_load_json(base / "rules.json"),
        personality=_load_json(base / "personality.json"),
        weeks=_load_json(base / "weeks.json"),
        finals=_load_json(base / "finals.json"),
        achievements=_load_json(base / "achievements.json"),
        endings=_load_json(base / "endings.json"),
        intro=_load_json(base / "intro.json"),
        report_templates=_load_json(base / "report_templates.json"),
        report_reference=_load_json(base / "report_reference.json"),
        ui=_load_json(base / "ui.json"),
        experience=_load_json(base / "experience.json"),
        changelog=_load_json(base / "changelog.json"),
    )

    if base_dir is None:
        _CACHE = bundle
    return bundle


def week_by_num(content: ContentBundle, week_num: int) -> dict[str, Any]:
    week_id = f"week_{week_num:02d}"
    for item in content.weeks["weeks"]:
        if item["id"] == week_id:
            return item
    raise KeyError(f"Unknown week: {week_num}")


def option_by_id(content: ContentBundle, week_num: int, option_id: str) -> dict[str, Any]:
    week = week_by_num(content, week_num)
    for opt in week.get("options", []):
        if opt["id"] == option_id:
            return opt
    raise KeyError(f"Unknown option {option_id} in week {week_num}")


def tactic_by_id(content: ContentBundle, tactic_id: str) -> dict[str, Any]:
    for tactic in content.finals["tactics"]:
        if tactic["id"] == tactic_id:
            return tactic
    raise KeyError(f"Unknown tactic: {tactic_id}")


def personality_by_id(content: ContentBundle, personality_id: str) -> dict[str, Any]:
    for item in content.personality["types"]:
        if item["id"] == personality_id:
            return item
    raise KeyError(f"Unknown personality: {personality_id}")


def collapse_ending_by_id(content: ContentBundle, ending_id: str) -> dict[str, Any]:
    for item in content.endings["collapse_endings"]:
        if item["id"] == ending_id:
            return item
    raise KeyError(f"Unknown ending: {ending_id}")
