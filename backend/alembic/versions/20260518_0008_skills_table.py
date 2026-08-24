"""add skills table

Revision ID: 20260518_0008
Revises: 20260517_0007
Create Date: 2026-05-18

User-defined Skill workflow (DSL JSON) — schema disimpan di JSONB
``definition``, divalidasi via ``app.domain.skills.parse_skill`` di repository
sebelum INSERT.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0008"
down_revision: str | None = "20260517_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("definition", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_skills_project_name"),
    )
    op.create_index("ix_skills_project_id", "skills", ["project_id"])
    op.create_index("ix_skills_project", "skills", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_skills_project", table_name="skills")
    op.drop_index("ix_skills_project_id", table_name="skills")
    op.drop_table("skills")
