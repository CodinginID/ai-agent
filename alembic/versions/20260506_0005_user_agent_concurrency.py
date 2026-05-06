"""add concurrency column to user_agent_configs

Revision ID: 20260506_0005
Revises: 20260506_0004
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_0005"
down_revision: str | None = "20260506_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_agent_configs",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("user_agent_configs", "concurrency")
