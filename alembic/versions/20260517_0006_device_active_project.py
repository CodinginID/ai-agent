"""add active_project_id column to devices

Revision ID: 20260517_0006
Revises: 20260506_0005
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_0006"
down_revision: str | None = "20260506_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("active_project_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_devices_active_project",
        "devices",
        "projects",
        ["active_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_devices_active_project_id",
        "devices",
        ["active_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_devices_active_project_id", table_name="devices")
    op.drop_constraint("fk_devices_active_project", "devices", type_="foreignkey")
    op.drop_column("devices", "active_project_id")
