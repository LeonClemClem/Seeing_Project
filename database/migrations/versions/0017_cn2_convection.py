"""cn2_profiles.conv: levels filled by the convective closure (hatched on the Cn² panel)

Display only; NULL for the profiles stored before.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cn2_profiles", sa.Column("conv", ARRAY(sa.Boolean()), nullable=True))


def downgrade() -> None:
    op.drop_column("cn2_profiles", "conv")
