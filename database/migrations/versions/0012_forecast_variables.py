"""forecasts.variables: model variables of every forecast hour

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("variables", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("forecasts", "variables")
