"""Initial runs table

Revision ID: 202602201200
Revises: 
Create Date: 2026-02-20 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202602201200"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("repo_owner", sa.String(length=255), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("base_ref", sa.String(length=255), nullable=True),
        sa.Column("head_ref", sa.String(length=255), nullable=True),
        sa.Column("head_sha", sa.String(length=255), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("engine_version", sa.String(length=255), nullable=True),
        sa.Column("job_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("fingerprint", sa.String(length=255), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_summary", sa.String(length=1000), nullable=True),
        sa.Column("artifact_paths", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("runs")
