"""add chat_sessions author and conversation composite index

Revision ID: 20260505_01
Revises:
Create Date: 2026-05-05 00:00:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260505_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS '
            'ix_chat_sessions_author_conversation '
            'ON chat_sessions ("authorId", conversation_id)'
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_chat_sessions_author_conversation"
        )
