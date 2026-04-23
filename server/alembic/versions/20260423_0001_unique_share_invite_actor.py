"""unique share invite per actor

Revision ID: 20260423_0001
Revises: 20260322_0001
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260423_0001"
down_revision = "20260322_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "share_invites" not in inspector.get_table_names():
        return

    ranked_sql = """
        WITH ranked AS (
            SELECT
                id,
                FIRST_VALUE(id) OVER (
                    PARTITION BY actor_type, actor_key
                    ORDER BY created_at ASC, id ASC
                ) AS keep_id,
                ROW_NUMBER() OVER (
                    PARTITION BY actor_type, actor_key
                    ORDER BY created_at ASC, id ASC
                ) AS rn
            FROM share_invites
        )
    """

    if "share_redeems" in inspector.get_table_names():
        bind.execute(
            sa.text(
                ranked_sql
                + """
                UPDATE share_redeems
                SET invite_id = (
                    SELECT keep_id FROM ranked WHERE ranked.id = share_redeems.invite_id
                )
                WHERE invite_id IN (SELECT id FROM ranked WHERE rn > 1)
                """
            )
        )

    bind.execute(
        sa.text(
            ranked_sql
            + """
            DELETE FROM share_invites
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        )
    )

    existing = {constraint["name"] for constraint in inspector.get_unique_constraints("share_invites")}
    if "uq_share_invite_actor" in existing:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("share_invites") as batch:
            batch.create_unique_constraint("uq_share_invite_actor", ["actor_type", "actor_key"])
    else:
        op.create_unique_constraint("uq_share_invite_actor", "share_invites", ["actor_type", "actor_key"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "share_invites" not in inspector.get_table_names():
        return

    existing = {constraint["name"] for constraint in inspector.get_unique_constraints("share_invites")}
    if "uq_share_invite_actor" not in existing:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("share_invites") as batch:
            batch.drop_constraint("uq_share_invite_actor", type_="unique")
    else:
        op.drop_constraint("uq_share_invite_actor", "share_invites", type_="unique")
