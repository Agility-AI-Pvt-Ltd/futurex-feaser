"""add project reviewer tables

Revision ID: 20260526_01
Revises: 20260514_01
Create Date: 2026-05-26 16:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_01"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_review_submissions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("author_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("github_url", sa.Text(), nullable=True),
        sa.Column("selected_repo", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(), nullable=True),
        sa.Column("storage_bucket", sa.String(), nullable=True),
        sa.Column("storage_object_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_project_review_submissions_id", "project_review_submissions", ["id"])
    op.create_index("ix_project_review_submissions_author_id", "project_review_submissions", ["author_id"])
    op.create_index("ix_project_review_submissions_status", "project_review_submissions", ["status"])

    op.create_table(
        "project_review_code_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("project_review_submissions.id"), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False, server_default="source_archive"),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("bucket_name", sa.String(), nullable=True),
        sa.Column("object_path", sa.Text(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_project_review_code_artifacts_id", "project_review_code_artifacts", ["id"])
    op.create_index(
        "ix_project_review_code_artifacts_submission_id",
        "project_review_code_artifacts",
        ["submission_id"],
    )

    op.create_table(
        "project_review_reports",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("project_review_submissions.id"), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("readiness_level", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("seniority_estimate", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("would_pass_strong_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("improvement_roadmap", sa.JSON(), nullable=False),
        sa.Column("static_analysis", sa.JSON(), nullable=False),
        sa.Column("llm_analysis", sa.JSON(), nullable=False),
        sa.Column("graph_trace", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_project_review_reports_id", "project_review_reports", ["id"])
    op.create_index("ix_project_review_reports_submission_id", "project_review_reports", ["submission_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_project_review_reports_submission_id", table_name="project_review_reports")
    op.drop_index("ix_project_review_reports_id", table_name="project_review_reports")
    op.drop_table("project_review_reports")
    op.drop_index("ix_project_review_code_artifacts_submission_id", table_name="project_review_code_artifacts")
    op.drop_index("ix_project_review_code_artifacts_id", table_name="project_review_code_artifacts")
    op.drop_table("project_review_code_artifacts")
    op.drop_index("ix_project_review_submissions_status", table_name="project_review_submissions")
    op.drop_index("ix_project_review_submissions_author_id", table_name="project_review_submissions")
    op.drop_index("ix_project_review_submissions_id", table_name="project_review_submissions")
    op.drop_table("project_review_submissions")
