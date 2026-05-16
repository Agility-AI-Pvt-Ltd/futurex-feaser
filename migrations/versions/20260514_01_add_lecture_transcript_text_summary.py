"""add lecture transcript text and summary cache

Revision ID: 20260514_01
Revises: 843ff5581461
Create Date: 2026-05-14 17:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260514_01"
down_revision = "843ff5581461"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lecture_transcript_metadata",
        sa.Column("transcript_text", sa.Text(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "lecture_transcript_metadata",
        sa.Column("transcript_summary", sa.Text(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "lecture_transcript_metadata",
        sa.Column("summary_generated_at", sa.DateTime(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("lecture_transcript_metadata", "summary_generated_at")
    op.drop_column("lecture_transcript_metadata", "transcript_summary")
    op.drop_column("lecture_transcript_metadata", "transcript_text")
