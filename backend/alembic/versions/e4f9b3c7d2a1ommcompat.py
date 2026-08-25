"""allow OMM-only satellite compatibility rows

Revision ID: e4f9b3c7d2a1
Revises: d3e8a2c4b6f1
Create Date: 2026-08-25 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f9b3c7d2a1"
down_revision: Union[str, None] = "d3e8a2c4b6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A five-character TLE catalogue field cannot encode new six-digit NORAD
    # catalogue numbers.  The canonical satellite_orbits row retains the OMM
    # payload; satellites.tle* becomes an optional legacy compatibility cache.
    with op.batch_alter_table("satellites", schema=None) as batch_op:
        batch_op.alter_column("tle1", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("tle2", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    missing_tle_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM satellites WHERE tle1 IS NULL OR tle2 IS NULL")
    ).scalar_one()
    if missing_tle_count:
        raise RuntimeError(
            "Cannot restore required TLE columns while OMM-only satellites exist. "
            "Remove or convert those rows before downgrading."
        )

    with op.batch_alter_table("satellites", schema=None) as batch_op:
        batch_op.alter_column("tle1", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("tle2", existing_type=sa.String(), nullable=False)
