"""site name: CosmoDrôme (the right spelling)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

sites = sa.table("sites", sa.column("slug", sa.String), sa.column("name", sa.String))


def upgrade() -> None:
    op.execute(sites.update().where(sites.c.slug == "cosmodrome").values(name="CosmoDrôme"))


def downgrade() -> None:
    op.execute(sites.update().where(sites.c.slug == "cosmodrome").values(name="Cosmodrome"))
