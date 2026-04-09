#!/usr/bin/env python3
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from engine import GameEngine
from server.app.config import settings
from server.app.db import SessionLocal
from server.app.models import Run, User
from server.app.security import hash_password


PREFIX = "leaderboard_demo_"
PASSWORD = "secret123"
DISPLAY_NAMES = [
    "陈一鸣",
    "林若舟",
    "周启明",
    "许临风",
    "唐知遥",
    "沈观澜",
    "顾南星",
    "秦书禾",
    "宋修远",
    "谢闻笙",
    "陆承言",
    "何见山",
]


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=9, minute=0, second=0, microsecond=0)


def _week_start(now: datetime) -> datetime:
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=9, minute=0, second=0, microsecond=0)


def _report_sections(index: int) -> dict[str, str]:
    return {
        "trajectory_summary_cn": f"测试数据 {index + 1}：这是一条用于排行榜验收的轨迹摘要。",
        "coach_note_cn": f"测试数据 {index + 1}：教练评语占位。",
        "teammate_note_cn": f"测试数据 {index + 1}：队友评语占位。",
        "final_moment_cn": f"测试数据 {index + 1}：最后一剑定格。",
    }


def _timestamps(now: datetime, index: int) -> tuple[datetime, datetime]:
    month_start = _month_start(now)
    week_start = _week_start(now)

    if index < 6:
        stamp = week_start + timedelta(hours=index * 3)
    else:
        month_gap = (week_start.date() - month_start.date()).days
        if month_gap > 0:
            day_offset = min(index - 6, month_gap - 1)
            stamp = month_start + timedelta(days=day_offset, hours=index)
        else:
            stamp = week_start + timedelta(days=index - 5, hours=index)
    return stamp, stamp


def _cleanup_demo_users() -> None:
    with SessionLocal() as db:
        users = list(db.execute(select(User).where(User.username.like(f"{PREFIX}%"))).scalars().all())
        for user in users:
            runs = list(db.execute(select(Run).where(Run.user_id == user.id)).scalars().all())
            for run in runs:
                db.delete(run)
            db.delete(user)
        db.commit()


def main() -> None:
    _cleanup_demo_users()

    content = GameEngine().content
    achievement_ids = [
        item["id"]
        for group in ("core", "special", "legend")
        for item in content.achievements[group]
    ]
    now = datetime.now(UTC)

    with SessionLocal() as db:
        for index, display_name in enumerate(DISPLAY_NAMES):
            user = User(
                username=f"{PREFIX}{index + 1:02d}",
                password_hash=hash_password(PASSWORD),
                display_name=display_name,
                phone_number=f"1380000{index + 100:04d}",
                external_user_id=f"{PREFIX}{uuid.uuid4().hex[:12]}",
            )
            db.add(user)
            db.flush()

            created_at, updated_at = _timestamps(now, index)
            score = 620 - index * 24
            base_attr = 68 - index
            unlocked_count = max(1, min(len(achievement_ids), 8 - index // 2))

            run = Run(
                ruleset_version=settings.ruleset_version,
                seed=70_000 + index,
                status="finished",
                week=12,
                owner_type="user",
                user_id=user.id,
                guest_id=None,
                is_active_guest_run=False,
                attributes={
                    "stamina": base_attr,
                    "skill": base_attr + 4,
                    "mind": base_attr - 2,
                    "academics": 55 + index % 5,
                    "social": 48 + index % 7,
                    "finance": 46 + index % 6,
                },
                min_attributes={
                    "stamina": 32,
                    "skill": 34,
                    "mind": 31,
                    "academics": 30,
                    "social": 30,
                    "finance": 30,
                },
                attributes_start={
                    "stamina": 42,
                    "skill": 46,
                    "mind": 40,
                    "academics": 40,
                    "social": 41,
                    "finance": 41,
                },
                personality_start="white_paper",
                personality_end="white_paper",
                personality_reveal_ack=True,
                warning_attrs=[],
                final_tactic_id="w12_t06",
                final_requirements_met=True,
                final_win_rate=0.75,
                final_roll_int=80 - index,
                final_result="胜利",
                final_tier="normal",
                final_applied_deltas={"skill": 3, "mind": 2},
                score=score,
                grade_id="G1",
                grade_label="稳定成长",
                achievements=achievement_ids[:unlocked_count],
                report={"report_sections": _report_sections(index)},
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(run)
        db.commit()

    print("Leaderboard demo data created.")
    print(f"Users: {len(DISPLAY_NAMES)}")
    print(f"Username prefix: {PREFIX}")
    print(f"Password for all demo users: {PASSWORD}")


if __name__ == "__main__":
    main()
