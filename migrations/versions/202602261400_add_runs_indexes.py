"""Add indexes on runs table for production query performance

Revision ID: 202602261400
Revises: 202602211100
Create Date: 2026-02-26 14:00:00

"""
from __future__ import annotations

from alembic import op

revision = "202602261400"
down_revision = "202602211100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Supports list_runs ORDER BY created_at DESC (most common query)
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    # Supports filtering runs by repo
    op.create_index("ix_runs_repo", "runs", ["repo_owner", "repo_name"])
    # Supports filtering by status (e.g. queued/running dashboards)
    op.create_index("ix_runs_status", "runs", ["status"])
    # Supports debugging/correlation lookups
    op.create_index("ix_runs_correlation_id", "runs", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_correlation_id", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_repo", table_name="runs")
    op.drop_index("ix_runs_created_at", table_name="runs")
