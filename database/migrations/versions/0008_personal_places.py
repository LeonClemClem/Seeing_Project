"""personal places

Personal places are `sites` rows owned by an account (`owner_id`), visibility `private` or `shared`.
Deleting a site (or its owner) now deletes its forecasts and Cn2 profiles.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _site_fks(ondelete: str | None) -> None:
    for table in ("forecasts", "cn2_profiles"):
        op.drop_constraint(f"{table}_site_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(f"{table}_site_id_fkey", table, "sites", ["site_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    op.add_column("sites", sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_sites_owner_id", "sites", ["owner_id"])
    op.drop_constraint("ck_sites_visibility", "sites", type_="check")
    op.create_check_constraint("ck_sites_visibility", "sites", "visibility IN ('public', 'shared', 'hidden', 'private')")
    _site_fks("CASCADE")


def downgrade() -> None:
    _site_fks(None)
    op.execute("DELETE FROM sites WHERE owner_id IS NOT NULL")
    op.drop_constraint("ck_sites_visibility", "sites", type_="check")
    op.create_check_constraint("ck_sites_visibility", "sites", "visibility IN ('public', 'shared', 'hidden')")
    op.drop_index("ix_sites_owner_id", table_name="sites")
    op.drop_column("sites", "owner_id")
