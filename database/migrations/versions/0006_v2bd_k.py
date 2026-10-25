"""calibrated V2bd K

K_TKE, K_CIS and K_conv of the V2bd model (soft transition at H_COULIM), fitted on the seeing
monitor measurements of each site (research/historique_sites.py, K_new). They replace the
placeholders of migrations 0002 and 0004.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

sites = sa.table(
    "sites",
    sa.column("slug", sa.String),
    sa.column("k_tke_conv", sa.Float),
    sa.column("k_tke", sa.Float),
    sa.column("k_cis", sa.Float),
)

K = {
    # slug: ((k_tke, k_cis, k_tke_conv) V2bd, previous placeholders)
    "ohp": ((0.767, 48.4, 0.01), (3.0, 30.0, 0.3)),
    "saint-veran": ((5.17, 41.1, 0.086), (3.0, 30.0, 0.3)),
    "pic-du-midi": ((1.8, 22.6, 0.1), (3.0, 30.0, 0.3)),
    "cosmodrome": ((1.03, 18.0, 0.1), (3.0, 30.0, 0.3)),
    "verclause": ((3.94, 49.7, 0.1), (4.0, 40.0, 0.3)),
    "copernic-gap": ((11.2, 112.0, 0.1), (3.0, 30.0, 0.3)),
}


def _set(which: int) -> None:
    for slug, values in K.items():
        k_tke, k_cis, k_conv = values[which]
        op.execute(sites.update().where(sites.c.slug == slug).values(k_tke=k_tke, k_cis=k_cis, k_tke_conv=k_conv))


def upgrade() -> None:
    _set(0)


def downgrade() -> None:
    _set(1)
