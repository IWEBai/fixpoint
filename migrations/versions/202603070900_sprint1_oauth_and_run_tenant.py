"""Sprint 1: add github_users, oauth_states, Run.installation_id FK, Run.github_user_id

Revision ID: 202603070900
Revises: 202602261400
Create Date: 2026-03-07 09:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202603070900"
down_revision = "202602261400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- github_users: one row per GitHub account that has ever logged in ---
    op.create_table(
        "github_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id", name="uq_github_users_github_id"),
    )

    # --- oauth_states: CSRF protection for the OAuth dance ---
    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", name="uq_oauth_states_state"),
    )
    op.create_index("ix_oauth_states_state", "oauth_states", ["state"])

    # --- installation_members: maps GitHub users → their installations ---
    op.create_table(
        "installation_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.installation_id"],
            name="fk_instmembers_installation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_user_id",
            "installation_id",
            name="uq_installation_members",
        ),
    )

    # --- Add github_user_id to runs (who triggered the run) ---
    op.add_column(
        "runs",
        sa.Column("github_user_id", sa.BigInteger(), nullable=True),
    )

    # --- Add installation_id FK to runs ---
    op.add_column(
        "runs",
        sa.Column(
            "run_installation_id",
            sa.Integer(),
            sa.ForeignKey(
                "installations.installation_id",
                name="fk_runs_installation_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_runs_run_installation_id", "runs", ["run_installation_id"])

    # Backfill: join runs → repositories → installations to populate run_installation_id
    op.execute(
        """
        UPDATE runs r
        SET run_installation_id = repos.installation_id
        FROM repositories repos
        WHERE repos.repo_owner = r.repo_owner
          AND repos.repo_name  = r.repo_name
          AND repos.installation_id IS NOT NULL
          AND r.run_installation_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_runs_run_installation_id", table_name="runs")
    op.drop_column("runs", "run_installation_id")
    op.drop_column("runs", "github_user_id")
    op.drop_table("installation_members")
    op.drop_index("ix_oauth_states_state", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_table("github_users")
