"""seed the curated observing sites

Coordinates and K coefficients come from research/SeeingAromeV2_correction_conv_tke.py.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

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
)

SITES = [
    # slug, name, lat, lon, altitude_m, k_tke_conv, k_tke, k_cis
    ("copernic-gap", "Association Copernic (Gap)", 44.5828, 5.9868, None, 0.3, 3.0, 30.0),
    ("saint-veran", "Observatoire de Saint-Véran", 44.6988, 6.9083, 2930.0, 0.3, 3.0, 30.0),
    ("verclause", "Verclause (Drôme)", 44.3814, 5.4286, None, 0.3, 4.0, 40.0),
    ("cosmodrome", "Cosmodrome", 44.1952, 5.4716, None, 0.3, 3.0, 30.0),
    ("pic-du-midi", "Observatoire du Pic du Midi", 42.93642, 0.14122, 2877.0, 0.3, 3.0, 30.0),
]


def upgrade() -> None:
    op.bulk_insert(
        sites,
        [
            dict(zip(("slug", "name", "lat", "lon", "altitude_m", "k_tke_conv", "k_tke", "k_cis"), row), active=True)
            for row in SITES
        ],
    )


def downgrade() -> None:
    op.execute(sites.delete().where(sites.c.slug.in_([row[0] for row in SITES])))
