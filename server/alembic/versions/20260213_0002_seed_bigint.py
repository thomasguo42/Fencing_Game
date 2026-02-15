"""seed to bigint

Revision ID: 20260213_0002
Revises: 20260213_0001
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260213_0002"
down_revision = "20260213_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("runs") as batch:
            batch.alter_column("seed", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)
    else:
        op.alter_column("runs", "seed", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("runs") as batch:
            batch.alter_column("seed", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
    else:
        op.alter_column("runs", "seed", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
