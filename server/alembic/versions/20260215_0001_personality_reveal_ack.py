"""add personality_reveal_ack

Revision ID: 20260215_0001
Revises: 20260213_0002
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260215_0001"
down_revision = "20260213_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("runs")}
    if "personality_reveal_ack" in existing_cols:
        return

    col = sa.Column("personality_reveal_ack", sa.Boolean(), server_default=sa.true(), nullable=False)
    if dialect == "sqlite":
        with op.batch_alter_table("runs") as batch:
            batch.add_column(col)
    else:
        op.add_column("runs", col)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("runs") as batch:
            batch.drop_column("personality_reveal_ack")
    else:
        op.drop_column("runs", "personality_reveal_ack")
