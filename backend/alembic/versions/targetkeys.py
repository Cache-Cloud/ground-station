"""Canonicalize mission and body target ownership keys.

Revision ID: e8c4a1d7b2f9
Revises: d7e5a9c2b4f1
Create Date: 2026-09-22 12:00:00.000000
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e8c4a1d7b2f9"
down_revision: Union[str, None] = "d7e5a9c2b4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEPARATORS = re.compile(r"[\s_]+", flags=re.UNICODE)
_LEGACY_MISSION_ID_COMMANDS = {
    "bepicolombo": "BepiColombo",
    "cassini": "Cassini",
    "chandrayaan2orbiter": "-152",
    "chandrayaan3": "Chandrayaan-3",
    "curiosity": "-76",
    "dart": "DART",
    "dawn": "Dawn",
    "deepimpact": "Deep Impact",
    "euclid": "Euclid",
    "exomars": "ExoMars",
    "galileo": "Galileo",
    "hayabusa2": "Hayabusa 2",
    "insight": "InSight",
    "juice": "JUICE",
    "juno": "-61",
    "lunarreconnaissanceorbiter": "LRO",
    "lucy": "-49",
    "marsodyssey": "-53",
    "maven": "MAVEN",
    "mro": "Mars Reconnaissance Orbiter",
    "newhorizons": "-98",
    "osirisrex": "-64",
    "parkersolarprobe": "Parker Solar Probe",
    "perseverance": "Mars 2020",
    "psyche": "-255",
    "rosetta": "Rosetta",
    "solarorbiter": "Solar Orbiter",
    "stereoa": "STEREO-A",
    "stereob": "STEREO-B",
    "tianwen1": "Tianwen-1",
    "voyager1": "Voyager 1",
    "voyager2": "Voyager 2",
}


def _identifier(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return _SEPARATORS.sub("_", text).strip("_")


def _key_from_parts(target_type: Any, *, command: Any = None, body_id: Any = None) -> str:
    normalized_type = str(target_type or "").strip().lower()
    source = command if normalized_type == "mission" else body_id
    suffix = _identifier(source)
    if normalized_type not in {"mission", "body"} or not suffix:
        return ""
    return f"{normalized_type}:{suffix}"


def _canonical_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if ":" not in text:
        return ""
    prefix, suffix = text.split(":", 1)
    normalized_prefix = prefix.strip().lower()
    # Legacy command-scoped owners become ordinary mission owners during this
    # migration. Runtime code intentionally has no compatibility branch.
    if normalized_prefix == "missioncmd":
        normalized_prefix = "mission"
    normalized_suffix = _identifier(suffix)
    if normalized_prefix not in {"mission", "body"} or not normalized_suffix:
        return ""
    return f"{normalized_prefix}:{normalized_suffix}"


def _legacy_mission_id_key(value: str) -> str:
    """Map catalog IDs used by the retired key builder to command-based keys."""
    if not value.startswith("mission:"):
        return ""
    legacy_id = value.split(":", 1)[1]
    command = _LEGACY_MISSION_ID_COMMANDS.get(legacy_id)
    return _key_from_parts("mission", command=command) if command else ""


def _register_alias(aliases: dict[str, str], original: str, canonical: str) -> None:
    if not original or original == canonical:
        return
    existing = aliases.get(original)
    if existing and existing != canonical:
        raise RuntimeError(
            f"Ambiguous legacy target key {original!r}: {existing!r} or {canonical!r}"
        )
    aliases[original] = canonical


def _assert_unique(mapping: dict[str, str], label: str) -> None:
    by_canonical: dict[str, list[str]] = {}
    for original, canonical in mapping.items():
        by_canonical.setdefault(canonical, []).append(original)
    collisions = {key: values for key, values in by_canonical.items() if len(values) > 1}
    if collisions:
        details = "; ".join(
            f"{key} <- {', '.join(sorted(values))}" for key, values in sorted(collisions.items())
        )
        raise RuntimeError(f"Canonical target-key collision in {label}: {details}")


def _decode_json(value: Any) -> Any:
    decoded = value
    for _ in range(3):
        if not isinstance(decoded, str):
            return decoded
        try:
            decoded = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Invalid tracking_state JSON encountered during target-key migration"
            ) from exc
    return decoded


def _registry_row(
    target_key: str,
    *,
    display_name: Any = None,
    command: Any = None,
    body_id: Any = None,
) -> dict[str, Any]:
    target_type = target_key.split(":", 1)[0]
    body_value = str(body_id or "").strip().lower() or None
    command_value = str(command or "").strip() or None
    return {
        "id": target_key,
        "target_type": target_type,
        "body_class": None,
        "display_name": str(display_name or target_key).strip() or target_key,
        "horizons_command": command_value if target_type == "mission" else body_value,
        "body_id": body_value if target_type == "body" else None,
        "parent_body_id": None,
        "always_in_scene": False,
        "enabled": True,
    }


def upgrade() -> None:
    bind = op.get_bind()

    target_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, target_type, body_class, display_name, horizons_command, "
                "body_id, parent_body_id, always_in_scene, enabled FROM celestial_targets"
            )
        ).mappings()
    )
    target_mapping: dict[str, str] = {}
    registry: dict[str, dict[str, Any]] = {}
    for row in target_rows:
        original = str(row["id"])
        canonical = _canonical_key(original)
        target_type = str(row["target_type"] or "").strip().lower()
        if not canonical or not canonical.startswith(f"{target_type}:"):
            raise RuntimeError(f"Invalid celestial target identity: {original!r}")
        target_mapping[original] = canonical
        registry[canonical] = dict(row) | {"id": canonical, "target_type": target_type}
    _assert_unique(target_mapping, "celestial_targets")

    monitored_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, display_name, target_type, command, body_id " "FROM monitored_celestial"
            )
        ).mappings()
    )
    monitored_mapping: dict[str, str] = {}
    for row in monitored_rows:
        target_key = _key_from_parts(
            row["target_type"], command=row["command"], body_id=row["body_id"]
        )
        if not target_key:
            raise RuntimeError(f"Cannot derive target_key for monitored target {row['id']!r}")
        monitored_mapping[str(row["id"])] = target_key
        registry.setdefault(
            target_key,
            _registry_row(
                target_key,
                display_name=row["display_name"],
                command=row["command"],
                body_id=row["body_id"],
            ),
        )
    _assert_unique(monitored_mapping, "monitored_celestial")

    tracking_rows = list(bind.execute(sa.text("SELECT id, value FROM tracking_state")).mappings())
    tracking_updates: dict[str, dict[str, Any]] = {}
    key_aliases: dict[str, str] = {}
    for row in tracking_rows:
        value = _decode_json(row["value"])
        if not isinstance(value, dict):
            continue
        target_type = str(value.get("target_type") or "").strip().lower()
        if target_type not in {"mission", "body"}:
            if str(value.get("body_id") or "").strip():
                target_type = "body"
            elif str(value.get("command") or "").strip():
                target_type = "mission"
            else:
                continue
        stored_target_key = _canonical_key(value.get("target_key"))
        metadata_target_key = _key_from_parts(
            target_type,
            command=value.get("command"),
            body_id=value.get("body_id"),
        )
        # Keep an existing registry identity opaque. Otherwise, tracking metadata
        # provides the missing link from retired mission-ID keys to command keys.
        target_key = (
            stored_target_key
            if stored_target_key in registry
            else metadata_target_key or stored_target_key
        )
        if not target_key or not target_key.startswith(f"{target_type}:"):
            raise RuntimeError(f"Cannot canonicalize tracking_state row {row['id']!r}")
        _register_alias(key_aliases, stored_target_key, target_key)
        updated = dict(value)
        updated["target_type"] = target_type
        updated["target_key"] = target_key
        tracking_updates[str(row["id"])] = updated
        registry.setdefault(
            target_key,
            _registry_row(
                target_key,
                display_name=value.get("target_name"),
                command=value.get("command"),
                body_id=value.get("body_id"),
            ),
        )

    transmitter_rows = list(
        bind.execute(
            sa.text("SELECT id, target_key FROM transmitters WHERE target_key IS NOT NULL")
        ).mappings()
    )
    transmitter_mapping: dict[str, str] = {}
    for row in transmitter_rows:
        stored_target_key = _canonical_key(row["target_key"])
        if not stored_target_key:
            raise RuntimeError(
                f"Invalid transmitter target_key on transmitter {row['id']!r}: {row['target_key']!r}"
            )
        canonical = stored_target_key
        if stored_target_key not in registry:
            canonical = (
                key_aliases.get(stored_target_key)
                or _legacy_mission_id_key(stored_target_key)
                or stored_target_key
            )
        transmitter_mapping[str(row["id"])] = canonical
        registry.setdefault(canonical, _registry_row(canonical))

    # Mutate the schema only after every legacy identity has been validated and
    # collision-checked, so an ambiguous installation remains untouched.
    op.add_column("monitored_celestial", sa.Column("target_key", sa.String(), nullable=True))

    # Defer FK checks while parent primary keys and snapshot references move
    # through temporary values. The completed graph is checked below.
    bind.execute(sa.text("PRAGMA defer_foreign_keys = ON"))
    temporary_ids: dict[str, str] = {}
    for original, canonical in target_mapping.items():
        if original == canonical:
            continue
        temporary = f"__target_key_migration__:{uuid.uuid4().hex}"
        temporary_ids[original] = temporary
        bind.execute(
            sa.text("UPDATE celestial_targets SET id = :temporary WHERE id = :original"),
            {"temporary": temporary, "original": original},
        )
        bind.execute(
            sa.text(
                "UPDATE celestial_vector_snapshots SET target_id = :canonical "
                "WHERE target_id = :original"
            ),
            {"canonical": canonical, "original": original},
        )
    for original, temporary in temporary_ids.items():
        bind.execute(
            sa.text("UPDATE celestial_targets SET id = :canonical WHERE id = :temporary"),
            {"canonical": target_mapping[original], "temporary": temporary},
        )

    now_utc = datetime.now(timezone.utc)
    existing_keys = set(target_mapping.values())
    for target_key, row in registry.items():
        if target_key in existing_keys:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO celestial_targets "
                "(id, target_type, body_class, display_name, horizons_command, body_id, "
                "parent_body_id, always_in_scene, enabled, created_at, updated_at) "
                "VALUES (:id, :target_type, :body_class, :display_name, :horizons_command, "
                ":body_id, :parent_body_id, :always_in_scene, :enabled, :created_at, :updated_at)"
            ),
            dict(row) | {"created_at": now_utc, "updated_at": now_utc},
        )

    for monitored_id, target_key in monitored_mapping.items():
        bind.execute(
            sa.text("UPDATE monitored_celestial SET target_key = :target_key WHERE id = :id"),
            {"target_key": target_key, "id": monitored_id},
        )
    for transmitter_id, target_key in transmitter_mapping.items():
        bind.execute(
            sa.text("UPDATE transmitters SET target_key = :target_key WHERE id = :id"),
            {"target_key": target_key, "id": transmitter_id},
        )
    for tracking_id, value in tracking_updates.items():
        bind.execute(
            sa.text("UPDATE tracking_state SET value = :value WHERE id = :id"),
            {"value": json.dumps(value, separators=(",", ":")), "id": tracking_id},
        )

    with op.batch_alter_table("celestial_targets") as batch_op:
        batch_op.create_check_constraint(
            "ck_celestial_targets_target_type",
            "target_type IN ('mission', 'body')",
        )
        batch_op.create_check_constraint(
            "ck_celestial_targets_id_namespace",
            "((target_type = 'mission' AND substr(id, 1, 8) = 'mission:') OR "
            "(target_type = 'body' AND substr(id, 1, 5) = 'body:')) AND "
            "id = lower(id) AND instr(id, ' ') = 0",
        )
    with op.batch_alter_table("monitored_celestial") as batch_op:
        batch_op.alter_column("target_key", existing_type=sa.String(), nullable=False)
        batch_op.create_unique_constraint("uq_monitored_celestial_target_key", ["target_key"])
        batch_op.create_foreign_key(
            "fk_monitored_celestial_target_key",
            "celestial_targets",
            ["target_key"],
            ["id"],
        )
        batch_op.create_index("ix_monitored_celestial_target_key", ["target_key"])
    with op.batch_alter_table("transmitters") as batch_op:
        batch_op.create_foreign_key(
            "fk_transmitters_target_key",
            "celestial_targets",
            ["target_key"],
            ["id"],
        )

    invalid_keys: list[str] = []
    for table, column in (
        ("celestial_targets", "id"),
        ("monitored_celestial", "target_key"),
        ("transmitters", "target_key"),
    ):
        rows = bind.execute(
            sa.text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL")
        ).scalars()
        invalid_keys.extend(
            f"{table}.{column}={value!r}" for value in rows if _canonical_key(value) != value
        )
    if invalid_keys:
        raise RuntimeError("Non-canonical target keys remain: " + ", ".join(invalid_keys))
    orphan_checks = {
        "monitored_celestial": (
            "SELECT m.target_key FROM monitored_celestial m "
            "LEFT JOIN celestial_targets c ON c.id = m.target_key WHERE c.id IS NULL"
        ),
        "transmitters": (
            "SELECT t.target_key FROM transmitters t "
            "LEFT JOIN celestial_targets c ON c.id = t.target_key "
            "WHERE t.target_key IS NOT NULL AND c.id IS NULL"
        ),
        "celestial_vector_snapshots": (
            "SELECT s.target_id FROM celestial_vector_snapshots s "
            "LEFT JOIN celestial_targets c ON c.id = s.target_id WHERE c.id IS NULL"
        ),
    }
    target_orphans = {
        table: list(bind.execute(sa.text(statement)).scalars())
        for table, statement in orphan_checks.items()
    }
    target_orphans = {table: rows for table, rows in target_orphans.items() if rows}
    if target_orphans:
        raise RuntimeError(f"Target-key migration left orphan references: {target_orphans}")


def downgrade() -> None:
    with op.batch_alter_table("transmitters") as batch_op:
        batch_op.drop_constraint("fk_transmitters_target_key", type_="foreignkey")
    with op.batch_alter_table("monitored_celestial") as batch_op:
        batch_op.drop_index("ix_monitored_celestial_target_key")
        batch_op.drop_constraint("fk_monitored_celestial_target_key", type_="foreignkey")
        batch_op.drop_constraint("uq_monitored_celestial_target_key", type_="unique")
        batch_op.drop_column("target_key")
    with op.batch_alter_table("celestial_targets") as batch_op:
        batch_op.drop_constraint("ck_celestial_targets_id_namespace", type_="check")
        batch_op.drop_constraint("ck_celestial_targets_target_type", type_="check")
