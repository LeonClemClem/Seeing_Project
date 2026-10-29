"""CosmoDrôme altitude: 1364 m (was unknown)

Display only (the physics uses the AROME orography of the site's cell).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

sites = sa.table("sites", sa.column("slug", sa.String), sa.column("altitude_m", sa.Float))


def upgrade() -> None:
    op.execute(sites.update().where(sites.c.slug == "cosmodrome").values(altitude_m=1364.0))


def downgrade() -> None:
    op.execute(sites.update().where(sites.c.slug == "cosmodrome").values(altitude_m=None))
