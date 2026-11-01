"""site_k_history: every set of K saved for a site, never deleted, so that the K can be restored

The K in service of every site are recorded as the first entry ("initial").

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_k_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("k_tke", sa.Float, nullable=False),
        sa.Column("k_cis", sa.Float, nullable=False),
        sa.Column("k_conv", sa.Float, nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
    )
    op.create_index("ix_site_k_history_site_id", "site_k_history", ["site_id"])
    op.execute(
        "INSERT INTO site_k_history (site_id, k_tke, k_cis, k_conv, source) "
        "SELECT id, k_tke, k_cis, k_tke_conv, 'initial' FROM sites"
    )


def downgrade() -> None:
    op.drop_index("ix_site_k_history_site_id", table_name="site_k_history")
    op.drop_table("site_k_history")
