"""Personal places never calibrated: from the old default K (2, 57, 0.1) to the K of the map (1, 30, 0.1), the new
default, so that the map, the one-off forecast, the fisheye and the place's forecast agree until it is calibrated.
Only places whose K history has nothing but its "initial" entry and whose K are still the old default; the change is
added to their K history (source "carte"), so the old K stay restorable.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

OLD = (2.0, 57.0, 0.1)
NEW = (1.0, 30.0, 0.1)


def upgrade() -> None:
    conn = op.get_bind()
    ids = conn.execute(
        sa.text(
            """
            SELECT s.id FROM sites s
            WHERE s.owner_id IS NOT NULL AND s.k_tke = :t AND s.k_cis = :c AND abs(s.k_tke_conv - :v) < 1e-9
              AND NOT EXISTS (SELECT 1 FROM site_k_history h WHERE h.site_id = s.id AND h.source <> 'initial')
            """
        ),
        {"t": OLD[0], "c": OLD[1], "v": OLD[2]},
    ).scalars().all()
    for site_id in ids:
        conn.execute(
            sa.text("UPDATE sites SET k_tke = :t, k_cis = :c, k_tke_conv = :v WHERE id = :id"),
            {"t": NEW[0], "c": NEW[1], "v": NEW[2], "id": site_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO site_k_history (site_id, k_tke, k_cis, k_conv, source) VALUES (:id, :t, :c, :v, 'carte')"
            ),
            {"t": NEW[0], "c": NEW[1], "v": NEW[2], "id": site_id},
        )


def downgrade() -> None:
    # nothing undone: the old K stay in the K history (restorable from the place's K history)
    pass
