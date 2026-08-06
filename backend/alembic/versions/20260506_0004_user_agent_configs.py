"""add user_agent_configs table

Revision ID: 20260506_0004
Revises: 20260503_0003
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_0004"
down_revision: str | None = "20260503_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_agent_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "agent_id", name="uq_user_agent_configs_user_agent"
        ),
    )
    op.create_index(
        "ix_user_agent_configs_user_id", "user_agent_configs", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_agent_configs_user_id", table_name="user_agent_configs")
    op.drop_table("user_agent_configs")
