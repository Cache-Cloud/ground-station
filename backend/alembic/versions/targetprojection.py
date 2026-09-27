"""Add per-target monitored celestial projection settings.

Revision ID: c7a1e9d4b2f6
Revises: b6f2d8a4c1e7
Create Date: 2026-09-27 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c7a1e9d4b2f6"
down_revision: Union[str, None] = "b6f2d8a4c1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitored_celestial",
        sa.Column("projection_past_hours", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "monitored_celestial",
        sa.Column("projection_future_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.add_column(
        "monitored_celestial",
        sa.Column("projection_step_minutes", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("monitored_celestial", "projection_step_minutes")
    op.drop_column("monitored_celestial", "projection_future_hours")
    op.drop_column("monitored_celestial", "projection_past_hours")
