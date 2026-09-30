"""Add explicit satellite orbit lifecycle timestamps.

Revision ID: d8b4f2a6c1e9
Revises: c7a1e9d4b2f6
Create Date: 2026-09-30 08:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d8b4f2a6c1e9"
down_revision: Union[str, None] = "c7a1e9d4b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("satellite_orbits", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fetched_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("changed_at", sa.DateTime(), nullable=True))

    # Older databases cannot reconstruct these events precisely. Preserve their
    # best available row timestamps, then let future syncs maintain exact values.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE satellite_orbits
            SET fetched_at = COALESCE(updated, added),
                first_seen_at = added,
                changed_at = COALESCE(updated, added)
            """
        )
    )

    with op.batch_alter_table("satellite_orbits", schema=None) as batch_op:
        batch_op.alter_column("first_seen_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column("changed_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("satellite_orbits", schema=None) as batch_op:
        batch_op.drop_column("changed_at")
        batch_op.drop_column("first_seen_at")
        batch_op.drop_column("fetched_at")
