"""add idea refinement versions

Revision ID: 20260529_01
Revises: 20260514_01
Create Date: 2026-05-29 16:25:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260529_01"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idea_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("startup_idea", sa.Text(), nullable=False),
        sa.Column("problem_solved", sa.Text(), nullable=False),
        sa.Column("ideal_customer", sa.Text(), nullable=False),
        sa.Column("refinement_text", sa.Text(), nullable=False),
        sa.Column("refinement_query", sa.Text(), nullable=True),
        sa.Column("report_score_before", sa.String(), nullable=True),
        sa.Column("score_after", sa.String(), nullable=True),
        sa.Column("score_delta", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "version_number",
            name="uq_idea_versions_conversation_version",
        ),
    )
    op.create_index(op.f("ix_idea_versions_id"), "idea_versions", ["id"], unique=False)
    op.create_index(
        op.f("ix_idea_versions_conversation_id"),
        "idea_versions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_idea_versions_conversation_created",
        "idea_versions",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idea_versions_conversation_created", table_name="idea_versions")
    op.drop_index(op.f("ix_idea_versions_conversation_id"), table_name="idea_versions")
    op.drop_index(op.f("ix_idea_versions_id"), table_name="idea_versions")
    op.drop_table("idea_versions")
