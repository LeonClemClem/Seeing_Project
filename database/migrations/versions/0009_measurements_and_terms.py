"""measurements, and the V2bd terms of every forecast hour

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in ("i_tke", "i_conv", "i_cis"):
        op.add_column("forecasts", sa.Column(col, sa.Float, nullable=True))
    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seeing_arcsec", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("site_id", "time"),
    )
    op.create_index("ix_measurements_site_id", "measurements", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_measurements_site_id", table_name="measurements")
    op.drop_table("measurements")
    for col in ("i_tke", "i_conv", "i_cis"):
        op.drop_column("forecasts", col)
