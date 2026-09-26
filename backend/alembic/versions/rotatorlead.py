"""Add persisted satellite tracking lead to rotators.

Revision ID: b6f2d8a4c1e7
Revises: e8c4a1d7b2f9
Create Date: 2026-09-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b6f2d8a4c1e7"
down_revision: Union[str, None] = "e8c4a1d7b2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rotators",
        sa.Column(
            "tracking_lead_seconds",
            sa.Float(),
            nullable=False,
            server_default="2.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("rotators", "tracking_lead_seconds")
