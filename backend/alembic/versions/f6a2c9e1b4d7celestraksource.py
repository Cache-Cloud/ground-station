"""mark canonical CelesTrak feeds as constrained sources

Revision ID: f6a2c9e1b4d7
Revises: e5a1c9d2b4f6
Create Date: 2026-08-26 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union
from urllib.parse import parse_qs, urlparse

import sqlalchemy as sa

from alembic import op

revision: str = "f6a2c9e1b4d7"
down_revision: Union[str, None] = "e5a1c9d2b4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CELESTRAK_GROUPS = {
    "amateur",
    "cubesat",
    "gnss",
    "iridium-next",
    "orbcomm",
    "stations",
    "weather",
}


def _is_constrained_celestrak_url(url: str) -> bool:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "celestrak.org"
        or parsed.path != "/NORAD/elements/gp.php"
    ):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    group = (query.get("GROUP") or [""])[0].strip().lower()
    return group in CELESTRAK_GROUPS and (query.get("FORMAT") or [""])[0].upper() == "CSV"


def upgrade() -> None:
    bind = op.get_bind()
    if "orbital_sources" not in sa.inspect(bind).get_table_names():
        return

    sources = sa.Table("orbital_sources", sa.MetaData(), autoload_with=bind)
    # SQLite can reflect legacy UUID values as numerics, so compare their text
    # representation just like the preceding CelesTrak remediation migration.
    rows = bind.execute(
        sa.text("SELECT CAST(id AS TEXT) AS id, url FROM orbital_sources")
    ).mappings()
    for row in rows:
        if _is_constrained_celestrak_url(str(row["url"] or "")):
            bind.execute(
                sources.update()
                .where(sa.cast(sources.c.id, sa.String()) == str(row["id"]))
                .values(provider="celestrak")
            )


def downgrade() -> None:
    bind = op.get_bind()
    if "orbital_sources" not in sa.inspect(bind).get_table_names():
        return
    sources = sa.Table("orbital_sources", sa.MetaData(), autoload_with=bind)
    bind.execute(
        sources.update().where(sources.c.provider == "celestrak").values(provider="generic_http")
    )
