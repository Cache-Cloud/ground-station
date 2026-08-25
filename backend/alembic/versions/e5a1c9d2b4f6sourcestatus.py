"""record generic orbital-source fetch errors

Revision ID: e5a1c9d2b4f6
Revises: e4f9b3c7d2a1
Create Date: 2026-08-25 16:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a1c9d2b4f6"
down_revision: Union[str, None] = "e4f9b3c7d2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Suspension remains CelesTrak-only; all providers use last_error for the
    # most recent failed fetch shown in the Sources UI.
    with op.batch_alter_table("orbital_source_sync_states", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_error", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orbital_source_sync_states", schema=None) as batch_op:
        batch_op.drop_column("last_error")
