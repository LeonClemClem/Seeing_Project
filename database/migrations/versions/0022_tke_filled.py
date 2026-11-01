"""forecasts.tke_filled, cn2_profiles.tke_filled: lead 0 whose missing TKE (not published by Meteo-France) was taken
from lead 1 of the same run. NULL on the rows stored before: their lead 0 lacks the TKE and stays left out.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("tke_filled", sa.Boolean, nullable=True))
    op.add_column("cn2_profiles", sa.Column("tke_filled", sa.Boolean, nullable=True))


def downgrade() -> None:
    op.drop_column("cn2_profiles", "tke_filled")
    op.drop_column("forecasts", "tke_filled")
