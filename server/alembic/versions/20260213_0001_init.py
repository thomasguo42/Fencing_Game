"""initial schema

Revision ID: 20260213_0001
Revises: 
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260213_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guests",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("ruleset_version", sa.String(length=16), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=True),
        sa.Column("is_active_guest_run", sa.Boolean(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("min_attributes", sa.JSON(), nullable=False),
        sa.Column("attributes_start", sa.JSON(), nullable=True),
        sa.Column("personality_start", sa.String(length=64), nullable=True),
        sa.Column("personality_end", sa.String(length=64), nullable=True),
        sa.Column("warning_attrs", sa.JSON(), nullable=False),
        sa.Column("final_tactic_id", sa.String(length=32), nullable=True),
        sa.Column("final_requirements_met", sa.Boolean(), nullable=True),
        sa.Column("final_win_rate", sa.Float(), nullable=True),
        sa.Column("final_roll_int", sa.Integer(), nullable=True),
        sa.Column("final_result", sa.String(length=16), nullable=True),
        sa.Column("final_tier", sa.String(length=16), nullable=True),
        sa.Column("final_applied_deltas", sa.JSON(), nullable=True),
        sa.Column("collapse_week", sa.Integer(), nullable=True),
        sa.Column("collapse_attr", sa.String(length=16), nullable=True),
        sa.Column("collapse_ending_id", sa.String(length=64), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("grade_id", sa.String(length=8), nullable=True),
        sa.Column("grade_label", sa.String(length=32), nullable=True),
        sa.Column("achievements", sa.JSON(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "run_week_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("week_id", sa.String(length=16), nullable=False),
        sa.Column("presented_option_ids", sa.JSON(), nullable=False),
        sa.Column("chosen_option_id", sa.String(length=32), nullable=True),
        sa.Column("resolved_rolls", sa.JSON(), nullable=False),
        sa.Column("applied_deltas", sa.JSON(), nullable=False),
        sa.Column("result_cn", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_id", "week_number", name="uq_run_week"),
    )


def downgrade() -> None:
    op.drop_table("run_week_logs")
    op.drop_table("runs")
    op.drop_table("users")
    op.drop_table("guests")
