"""suspend unsafe CelesTrak sources and store source sync state

Revision ID: d3e8a2c4b6f1
Revises: e6c1b4d2a9f3
Create Date: 2026-08-25 10:00:00.000000

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e8a2c4b6f1"
down_revision: Union[str, None] = "e6c1b4d2a9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CELESTRAK_HOSTS = {
    "celestrak.org",
    "www.celestrak.org",
    "celestrak.com",
    "www.celestrak.com",
}
# These are the historical Ground Station defaults and currently supported
# groups we can migrate without changing a user's intended data set.
MIGRATABLE_GROUPS = {
    "amateur",
    "cubesat",
    "gnss",
    "iridium-next",
    "orbcomm",
    "stations",
    "weather",
}
STATIC_DEFAULT_GROUPS = {"/norad/elements/cubesat.txt": "cubesat"}


def _canonical_gp_url(group: str) -> str:
    return urlunparse(
        (
            "https",
            "celestrak.org",
            "/NORAD/elements/gp.php",
            "",
            urlencode({"GROUP": group, "FORMAT": "CSV"}),
            "",
        )
    )


def _migration_target(url: str) -> tuple[str | None, str | None]:
    """Return a safe replacement URL or a reason to suspend this source."""
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if host not in CELESTRAK_HOSTS:
        return None, None

    static_group = STATIC_DEFAULT_GROUPS.get(parsed.path.lower())
    if static_group:
        return _canonical_gp_url(static_group), None

    if parsed.path.lower() == "/norad/elements/gp.php":
        query = parse_qs(parsed.query, keep_blank_values=True)
        group = (query.get("GROUP") or query.get("group") or [""])[0].strip().lower()
        if group in MIGRATABLE_GROUPS:
            return _canonical_gp_url(group), None

    return (
        None,
        "CelesTrak source requires review: it was not a known safe Ground Station GP query.",
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "orbital_sources" not in table_names:
        return

    if "orbital_source_sync_states" not in table_names:
        op.create_table(
            "orbital_source_sync_states",
            sa.Column("source_id", sa.UUID(), nullable=False),
            sa.Column("last_success_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("last_http_status", sa.Integer(), nullable=True),
            sa.Column("suspended_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("suspension_reason", sa.String(), nullable=True),
            sa.Column("updated", sa.DateTime(timezone=False), nullable=False),
            sa.ForeignKeyConstraint(["source_id"], ["orbital_sources.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("source_id"),
        )

    metadata = sa.MetaData()
    sources = sa.Table("orbital_sources", metadata, autoload_with=bind)
    # SQLite reflects UUID columns with NUMERIC affinity. Define the table
    # explicitly so suspended source IDs retain their UUID bind processor.
    states = sa.table(
        "orbital_source_sync_states",
        sa.column("source_id", sa.UUID(as_uuid=True)),
        sa.column("suspended_at", sa.DateTime(timezone=False)),
        sa.column("suspension_reason", sa.String()),
        sa.column("updated", sa.DateTime(timezone=False)),
    )
    state_insert = sqlite_insert(states)
    state_upsert = state_insert.on_conflict_do_update(
        index_elements=["source_id"],
        set_={
            "suspended_at": state_insert.excluded.suspended_at,
            "suspension_reason": state_insert.excluded.suspension_reason,
            "updated": state_insert.excluded.updated,
        },
    )
    now = datetime.now(timezone.utc)

    # Reading legacy UUIDs as text avoids Decimal coercion failures on SQLite.
    source_rows = bind.execute(
        sa.text("SELECT CAST(id AS TEXT) AS id, url FROM orbital_sources")
    ).mappings()
    for row in source_rows:
        replacement_url, suspension_reason = _migration_target(str(row["url"] or ""))
        if replacement_url:
            bind.execute(
                sources.update()
                .where(sa.cast(sources.c.id, sa.String()) == str(row["id"]))
                .values(
                    url=replacement_url,
                    provider="generic_http",
                    format="omm",
                    adapter="http_omm",
                    enabled=True,
                )
            )
        elif suspension_reason:
            bind.execute(
                sources.update()
                .where(sa.cast(sources.c.id, sa.String()) == str(row["id"]))
                .values(enabled=False)
            )
            bind.execute(
                state_upsert.values(
                    source_id=uuid.UUID(str(row["id"])),
                    suspended_at=now,
                    suspension_reason=suspension_reason,
                    updated=now,
                )
            )


def downgrade() -> None:
    op.drop_table("orbital_source_sync_states")
