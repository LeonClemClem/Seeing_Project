"""short site names

OHP, Saint-Véran, Pic du Midi, Copernic and Drôme instead of the long official names.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

sites = sa.table("sites", sa.column("slug", sa.String), sa.column("name", sa.String))

NAMES = {
    # slug: (short name, previous name)
    "ohp": ("OHP", "Observatoire de Haute-Provence"),
    "saint-veran": ("Saint-Véran", "Observatoire de Saint-Véran"),
    "pic-du-midi": ("Pic du Midi", "Observatoire du Pic du Midi"),
    "copernic-gap": ("Copernic", "Association Copernic (Gap)"),
    "verclause": ("Drôme", "Verclause (Drôme)"),
}


def upgrade() -> None:
    for slug, (short, _) in NAMES.items():
        op.execute(sites.update().where(sites.c.slug == slug).values(name=short))


def downgrade() -> None:
    for slug, (_, previous) in NAMES.items():
        op.execute(sites.update().where(sites.c.slug == slug).values(name=previous))
