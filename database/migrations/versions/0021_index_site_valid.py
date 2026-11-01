"""Indexes (site_id, valid_time) on forecasts and cn2_profiles: the history, calibration and week Cn2 queries read
one site's hours in time order (the first /verif of a site took ~28 s without it)

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-01
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_forecasts_site_valid", "forecasts", ["site_id", "valid_time"])
    op.create_index("ix_cn2_profiles_site_valid", "cn2_profiles", ["site_id", "valid_time"])


def downgrade() -> None:
    op.drop_index("ix_cn2_profiles_site_valid", table_name="cn2_profiles")
    op.drop_index("ix_forecasts_site_valid", table_name="forecasts")
