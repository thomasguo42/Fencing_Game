"""share quotas, profile fields, and leaderboard support

Revision ID: 20260322_0001
Revises: 20260215_0001
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260322_0001"
down_revision = "20260215_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    existing_user_cols = {c["name"] for c in inspector.get_columns("users")}
    user_columns = [
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("external_user_id", sa.String(length=128), nullable=True),
    ]

    if dialect == "sqlite":
        with op.batch_alter_table("users") as batch:
            for column in user_columns:
                if column.name not in existing_user_cols:
                    batch.add_column(column)
    else:
        for column in user_columns:
            if column.name not in existing_user_cols:
                op.add_column("users", column)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    if "ix_users_external_user_id" not in existing_indexes:
        op.create_index("ix_users_external_user_id", "users", ["external_user_id"], unique=True)

    existing_tables = set(inspector.get_table_names())

    if "daily_play_quotas" not in existing_tables:
        op.create_table(
            "daily_play_quotas",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("actor_type", sa.String(length=16), nullable=False),
            sa.Column("actor_key", sa.String(length=64), nullable=False),
            sa.Column("quota_date", sa.Date(), nullable=False),
            sa.Column("used_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bonus_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("actor_type", "actor_key", "quota_date", name="uq_daily_play_quota"),
        )

    if "share_invites" not in existing_tables:
        op.create_table(
            "share_invites",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("invite_token", sa.String(length=64), nullable=False, unique=True),
            sa.Column("actor_type", sa.String(length=16), nullable=False),
            sa.Column("actor_key", sa.String(length=64), nullable=False),
            sa.Column("source_run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=True),
            sa.Column("page_path", sa.String(length=255), nullable=False),
            sa.Column("redeem_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "share_redeems" not in existing_tables:
        op.create_table(
            "share_redeems",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("invite_id", sa.String(length=36), sa.ForeignKey("share_invites.id"), nullable=False),
            sa.Column("scanner_actor_type", sa.String(length=16), nullable=False),
            sa.Column("scanner_actor_key", sa.String(length=64), nullable=False),
            sa.Column("granted_bonus", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("invite_id", "scanner_actor_type", "scanner_actor_key", name="uq_share_redeem_actor"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "share_redeems" in existing_tables:
        op.drop_table("share_redeems")
    if "share_invites" in existing_tables:
        op.drop_table("share_invites")
    if "daily_play_quotas" in existing_tables:
        op.drop_table("daily_play_quotas")

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    if "ix_users_external_user_id" in existing_indexes:
        op.drop_index("ix_users_external_user_id", table_name="users")

    existing_user_cols = {c["name"] for c in inspector.get_columns("users")}
    cols_to_drop = [name for name in ("display_name", "phone_number", "external_user_id") if name in existing_user_cols]
    if not cols_to_drop:
        return

    if dialect == "sqlite":
        with op.batch_alter_table("users") as batch:
            for name in cols_to_drop:
                batch.drop_column(name)
    else:
        for name in cols_to_drop:
            op.drop_column("users", name)
