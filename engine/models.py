from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from engine.constants import ATTRS, RULESET_VERSION


AttrMap = dict[str, int]


@dataclass
class WeekHistoryRecord:
    week_num: int
    week_id: str
    presented_option_ids: list[str]
    chosen_id: str
    resolved_rolls: dict[str, int]
    applied_deltas: AttrMap


@dataclass
class FinalRecord:
    tactic_id: str
    requirements_met: bool
    win_rate: float
    roll_int: int | None
    final_result: str
    final_tier: str | None
    applied_deltas: AttrMap


@dataclass
class CollapseRecord:
    week_num: int
    attr: str
    ending_id: str


@dataclass
class RunState:
    seed: int
    ruleset_version: str = RULESET_VERSION
    status: str = "in_progress"
    week: int = 0
    attributes: AttrMap = field(default_factory=lambda: {a: 0 for a in ATTRS})
    min_attributes: AttrMap = field(default_factory=lambda: {a: 0 for a in ATTRS})
    attributes_start: AttrMap | None = None
    personality_start: str | None = None
    personality_end: str | None = None
    presented_options: list[str] = field(default_factory=list)
    history: list[WeekHistoryRecord] = field(default_factory=list)
    final_record: FinalRecord | None = None
    collapse_record: CollapseRecord | None = None
    warning_attrs: list[str] = field(default_factory=list)
    score: int | None = None
    grade_id: str | None = None
    grade_label: str | None = None
    achievements: list[str] = field(default_factory=list)
    report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["history"] = [asdict(item) for item in self.history]
        return payload

    @property
    def completed_weeks(self) -> int:
        if self.final_record is not None:
            return 12
        return len(self.history)
