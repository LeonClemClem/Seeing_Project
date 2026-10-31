"""K_conv = 0.1 for every site

The user's choice (2026-10-31): the same K_conv = 0.1 everywhere, curated sites and personal places, as
Calibrer already saves it. Only K_conv changes; K_TKE and K_CIS stay as calibrated.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

sites = sa.table("sites", sa.column("slug", sa.String), sa.column("k_tke_conv", sa.Float))

# K_conv before this migration where it was not 0.1 (migrations 0006 and 0010)
PREVIOUS = {"ohp": 0.01, "saint-veran": 0.086, "seeing-monitor-5": 0.002}


def upgrade() -> None:
    op.execute(sites.update().values(k_tke_conv=0.1))


def downgrade() -> None:
    for slug, k in PREVIOUS.items():
        op.execute(sites.update().where(sites.c.slug == slug).values(k_tke_conv=k))
