"""map_frames: global seeing map of every night lead hour of a run

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_frames",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_hour", sa.Integer, nullable=False),
        sa.Column("ny", sa.Integer, nullable=False),
        sa.Column("nx", sa.Integer, nullable=False),
        sa.Column("lat0", sa.Float, nullable=False),
        sa.Column("lon0", sa.Float, nullable=False),
        sa.Column("dlat", sa.Float, nullable=False),
        sa.Column("dlon", sa.Float, nullable=False),
        sa.Column("k_tke", sa.Float, nullable=False),
        sa.Column("k_cis", sa.Float, nullable=False),
        sa.Column("k_conv", sa.Float, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("run_id", "lead_hour"),
    )
    op.create_index("ix_map_frames_run_id", "map_frames", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_map_frames_run_id", table_name="map_frames")
    op.drop_table("map_frames")
