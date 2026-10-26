"""map_frames.extra: low / high turbulence split of each map frame (fisheye)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("map_frames", sa.Column("extra", sa.LargeBinary, nullable=True))


def downgrade() -> None:
    op.drop_column("map_frames", "extra")
