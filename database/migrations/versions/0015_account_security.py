"""account security: e-mail confirmation and rate limits

users.email_verified_at (existing accounts count as confirmed), email_tokens (single-use links, stored
as SHA-256) and auth_events (failed logins, sign-ups and confirmation e-mails, for the rate limits).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET email_verified_at = created_at")
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_tokens_user_id"), "email_tokens", ["user_id"], unique=False)
    op.create_table(
        "auth_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_events_at"), "auth_events", ["at"], unique=False)
    op.create_index(op.f("ix_auth_events_email"), "auth_events", ["email"], unique=False)
    op.create_index(op.f("ix_auth_events_ip"), "auth_events", ["ip"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_events_ip"), table_name="auth_events")
    op.drop_index(op.f("ix_auth_events_email"), table_name="auth_events")
    op.drop_index(op.f("ix_auth_events_at"), table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_index(op.f("ix_email_tokens_user_id"), table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_column("users", "email_verified_at")
