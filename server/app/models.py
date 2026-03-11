from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    runs: Mapped[list[Run]] = relationship(back_populates="user")


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    runs: Mapped[list[Run]] = relationship(back_populates="guest")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ruleset_version: Mapped[str] = mapped_column(String(16), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)
    week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    guest_id: Mapped[str | None] = mapped_column(ForeignKey("guests.id"), nullable=True)
    is_active_guest_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)
    min_attributes: Mapped[dict] = mapped_column(JSON, nullable=False)
    attributes_start: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    personality_start: Mapped[str | None] = mapped_column(String(64), nullable=True)
    personality_end: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Personality reveal is a required, resumable step right after allocation.
    # Default True so existing rows (pre-migration behavior) are not blocked.
    personality_reveal_ack: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    warning_attrs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    final_tactic_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    final_requirements_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_roll_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    final_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    final_applied_deltas: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    collapse_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collapse_attr: Mapped[str | None] = mapped_column(String(16), nullable=True)
    collapse_ending_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    grade_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    achievements: Mapped[list | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="runs")
    guest: Mapped[Guest | None] = relationship(back_populates="runs")
    week_logs: Mapped[list[RunWeekLog]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunWeekLog(Base):
    __tablename__ = "run_week_logs"
    __table_args__ = (UniqueConstraint("run_id", "week_number", name="uq_run_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    week_id: Mapped[str] = mapped_column(String(16), nullable=False)
    presented_option_ids: Mapped[list] = mapped_column(JSON, nullable=False)

    chosen_option_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_rolls: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    applied_deltas: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result_cn: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    run: Mapped[Run] = relationship(back_populates="week_logs")
