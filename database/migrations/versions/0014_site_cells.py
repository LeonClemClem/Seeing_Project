"""sites.cells: AROME orography of the 5 x 5 grid cells around each site

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("cells", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "cells")
