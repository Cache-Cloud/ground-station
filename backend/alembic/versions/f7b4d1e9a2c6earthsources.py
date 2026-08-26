"""fix orbital sources to Earth until non-Earth propagation exists

Revision ID: f7b4d1e9a2c6
Revises: f6a2c9e1b4d7
Create Date: 2026-08-26 13:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f7b4d1e9a2c6"
down_revision: Union[str, None] = "f6a2c9e1b4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "orbital_sources" not in sa.inspect(bind).get_table_names():
        return
    op.execute(sa.text("UPDATE orbital_sources SET central_body = 'earth'"))


def downgrade() -> None:
    # The original non-Earth selection was not usable and cannot be inferred.
    pass
