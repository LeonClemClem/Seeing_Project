"""site_history (research history of the monitored sites) and the Seeing monitor 5 site

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

sites = sa.table(
    "sites",
    sa.column("slug", sa.String), sa.column("name", sa.String), sa.column("lat", sa.Float), sa.column("lon", sa.Float),
    sa.column("altitude_m", sa.Float), sa.column("k_tke_conv", sa.Float), sa.column("k_tke", sa.Float),
    sa.column("k_cis", sa.Float), sa.column("active", sa.Boolean), sa.column("visibility", sa.String),
)


def upgrade() -> None:
    op.create_table(
        "site_history",
        sa.Column("site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("data", JSONB, nullable=False),
    )
    # Research seeing monitor (Miratlas SM5), administrator only, with its calibrated V2bd K.
    op.bulk_insert(sites, [dict(slug="seeing-monitor-5", name="Seeing monitor 5", lat=43.9015, lon=5.8659,
                                altitude_m=None, k_tke_conv=0.002, k_tke=5.08, k_cis=80.5, active=True,
                                visibility="hidden")])


def downgrade() -> None:
    for table in ("measurements", "cn2_profiles", "forecasts"):
        op.execute(f"DELETE FROM {table} WHERE site_id IN (SELECT id FROM sites WHERE slug = 'seeing-monitor-5')")  # noqa: S608
    op.execute(sites.delete().where(sites.c.slug == "seeing-monitor-5"))
    op.drop_table("site_history")
