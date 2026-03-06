"""Add installations and repositories tables

Revision ID: 202602211100
Revises: 202602201200
Create Date: 2026-02-21 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202602211100"
down_revision = "202602201200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=True),
        sa.Column("account_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", name="uq_installation_id"),
    )

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=True),
        sa.Column("repo_owner", sa.String(length=255), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("installation_id", sa.Integer(), sa.ForeignKey("installations.installation_id"), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("mode", sa.String(length=32), server_default="warn", nullable=False),
        sa.Column("baseline_ref", sa.String(length=255), nullable=True),
        sa.Column("rails_preset", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_id", name="uq_repo_id"),
        sa.UniqueConstraint("repo_owner", "repo_name", name="uq_repo_owner_name"),
    )


def downgrade() -> None:
    op.drop_table("repositories")
    op.drop_table("installations")
