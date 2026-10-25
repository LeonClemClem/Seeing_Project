"""site visibility and the OHP site

Public sites are the observatories (Pic du Midi, OHP, Saint-Véran); the CosmoDrôme is shared by its
team with the community; Copernic and Verclause stay computed by the batch (research data) but are
no longer offered on the website. Adds the OHP (Observatoire de Haute-Provence).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

VISIBILITIES = ("public", "shared", "hidden")

sites = sa.table(
    "sites",
    sa.column("slug", sa.String),
    sa.column("name", sa.String),
    sa.column("lat", sa.Float),
    sa.column("lon", sa.Float),
    sa.column("altitude_m", sa.Float),
    sa.column("k_tke_conv", sa.Float),
    sa.column("k_tke", sa.Float),
    sa.column("k_cis", sa.Float),
    sa.column("active", sa.Boolean),
    sa.column("visibility", sa.String),
)


def upgrade() -> None:
    op.add_column("sites", sa.Column("visibility", sa.String(16), nullable=False, server_default="public"))
    op.create_check_constraint("ck_sites_visibility", "sites", "visibility IN ('public', 'shared', 'hidden')")
    op.execute(sites.update().where(sites.c.slug.in_(["copernic-gap", "verclause"])).values(visibility="hidden"))
    op.execute(sites.update().where(sites.c.slug == "cosmodrome").values(visibility="shared"))
    # Same placeholder K as the other seeded sites (0002); the calibrated K are set separately.
    op.bulk_insert(
        sites,
        [
            dict(slug="ohp", name="Observatoire de Haute-Provence", lat=43.9317, lon=5.7128, altitude_m=650.0,
                 k_tke_conv=0.3, k_tke=3.0, k_cis=30.0, active=True, visibility="public"),
        ],
    )


def downgrade() -> None:
    for table in ("cn2_profiles", "forecasts"):
        op.execute(f"DELETE FROM {table} WHERE site_id IN (SELECT id FROM sites WHERE slug = 'ohp')")
    op.execute(sites.delete().where(sites.c.slug == "ohp"))
    op.drop_constraint("ck_sites_visibility", "sites", type_="check")
    op.drop_column("sites", "visibility")
