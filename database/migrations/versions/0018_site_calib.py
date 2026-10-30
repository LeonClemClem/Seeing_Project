"""sites.calib: calibration settings of a place (filters and nights left out), remembered on the server

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("calib", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "calib")
