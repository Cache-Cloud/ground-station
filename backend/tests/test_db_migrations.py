# Copyright (c) 2026 Efstratios Goudelis

import json
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from alembic import command
from db import migrations


def test_backup_rotation_keeps_latest_five(tmp_path):
    db_path = tmp_path / "gs.db"
    db_path.write_bytes(b"db")

    for index in range(6):
        old_backup = tmp_path / f"gs.db.pre-migration-20260101-00000{index}.bak"
        old_backup.write_bytes(f"old-{index}".encode("ascii"))
        os.utime(old_backup, (1 + index, 1 + index))

    created_backup = migrations._backup_db_before_migration(db_path)

    assert created_backup is not None
    backups = sorted(tmp_path.glob("gs.db.pre-migration-*.bak"))
    assert len(backups) == 5
    assert created_backup in backups


def test_run_migrations_creates_backup_only_when_pending(monkeypatch, tmp_path):
    db_path = tmp_path / "gs.db"
    db_path.write_bytes(b"db")

    calls = {"backup": 0, "upgrade": 0}

    monkeypatch.setattr(migrations, "get_alembic_config", lambda: object())
    monkeypatch.setattr(migrations, "_resolve_db_path", lambda: db_path)

    def _mock_backup(_db_path: Path):
        calls["backup"] += 1
        return _db_path.with_suffix(".bak")

    monkeypatch.setattr(migrations, "_backup_db_before_migration", _mock_backup)

    def _mock_upgrade(_cfg, _head):
        calls["upgrade"] += 1

    monkeypatch.setattr(migrations.command, "upgrade", _mock_upgrade)

    monkeypatch.setattr(migrations, "_has_pending_migrations", lambda _cfg, _db_path: False)
    migrations.run_migrations()
    assert calls["backup"] == 0
    assert calls["upgrade"] == 1

    monkeypatch.setattr(migrations, "_has_pending_migrations", lambda _cfg, _db_path: True)
    migrations.run_migrations()
    assert calls["backup"] == 1
    assert calls["upgrade"] == 2


def _insert_legacy_orbital_source(connection, name: str, url: str) -> str:
    """Insert a pre-remediation source row at the migration's parent revision."""
    source_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO orbital_sources (id, name, identifier, url, format, added, updated)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (source_id, name, f"legacy-{name.lower().replace(' ', '-')}", url, "3le"),
    )
    return source_id


def test_celestrak_migration_converts_known_sources_and_suspends_unknown_ones(
    monkeypatch, tmp_path
):
    """Upgrade an affected database shape through the CelesTrak remediation revision."""
    db_path = tmp_path / "legacy-gs.db"
    monkeypatch.setenv("GS_DB", str(db_path))
    monkeypatch.setenv("ALEMBIC_CONTEXT", "1")
    alembic_config = migrations.get_alembic_config()

    # Create the exact schema immediately before the remediation migration.
    command.upgrade(alembic_config, "e6c1b4d2a9f3")
    connection = sqlite3.connect(db_path)
    try:
        source_ids = {
            "old_default": _insert_legacy_orbital_source(
                connection,
                "Old default",
                "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=omm",
            ),
            "static": _insert_legacy_orbital_source(
                connection,
                "Static Cubesats",
                "https://www.celestrak.com/NORAD/elements/cubesat.txt",
            ),
            "tle": _insert_legacy_orbital_source(
                connection,
                "Legacy TLE Weather",
                "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
            ),
            "legacy_host": _insert_legacy_orbital_source(
                connection,
                "Legacy host",
                "https://www.celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=CSV",
            ),
            "valid_group": _insert_legacy_orbital_source(
                connection,
                "Valid group",
                "https://celestrak.org/NORAD/elements/gp.php?GROUP=gnss&FORMAT=CSV",
            ),
            "unknown": _insert_legacy_orbital_source(
                connection,
                "Unknown custom query",
                "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS*&FORMAT=CSV",
            ),
        }
        connection.commit()
    finally:
        connection.close()

    command.upgrade(alembic_config, "head")

    connection = sqlite3.connect(db_path)
    try:
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT id, url, provider, format, adapter, enabled FROM orbital_sources"
            )
        }
        states = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT source_id, suspension_reason FROM orbital_source_sync_states"
            )
        }
    finally:
        connection.close()

    expected_urls = {
        "old_default": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=CSV",
        "static": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cubesat&FORMAT=CSV",
        "tle": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=CSV",
        "legacy_host": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=CSV",
        "valid_group": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gnss&FORMAT=CSV",
    }
    for source_name, expected_url in expected_urls.items():
        url, provider, source_format, adapter, enabled = rows[source_ids[source_name]]
        assert url == expected_url
        assert provider == "celestrak"
        assert source_format == "omm"
        assert adapter == "http_omm"
        assert enabled == 1
        assert source_ids[source_name] not in states

    unknown_url, _provider, _format, _adapter, unknown_enabled = rows[source_ids["unknown"]]
    assert unknown_url == "https://celestrak.org/NORAD/elements/gp.php?NAME=ISS*&FORMAT=CSV"
    assert unknown_enabled == 0
    assert "requires review" in states[source_ids["unknown"]]


def test_target_key_migration_rewrites_all_persisted_owners(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy-target-keys.db"
    monkeypatch.setenv("GS_DB", str(db_path))
    monkeypatch.setenv("ALEMBIC_CONTEXT", "1")
    alembic_config = migrations.get_alembic_config()
    command.upgrade(alembic_config, "d7e5a9c2b4f1")

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO celestial_targets
                (id, target_type, display_name, horizons_command, always_in_scene,
                 enabled, created_at, updated_at)
            VALUES
                ('mission:Voyager  1', 'mission', 'Voyager 1', 'Voyager 1', 0, 1,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            """
            INSERT INTO celestial_vector_snapshots
                (id, target_id, epoch_bucket_utc, past_hours, future_hours, step_minutes,
                 frame, center, position_xyz_au, velocity_xyz_au_per_day,
                 orbit_samples_xyz_au, orbit_sample_times_utc, source, fetched_at,
                 expires_at, created_at, updated_at)
            VALUES
                ('snapshot-1', 'mission:Voyager  1', CURRENT_TIMESTAMP, 1, 24, 60,
                 'heliocentric-ecliptic', 'sun', '[]', '[]', '[]', '[]', 'horizons',
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            """
            INSERT INTO monitored_celestial
                (id, display_name, command, enabled, created_at, updated_at, target_type)
            VALUES
                ('monitored-1', 'ExoMars', 'ExoMars', 1, CURRENT_TIMESTAMP,
                 CURRENT_TIMESTAMP, 'mission')
            """
        )
        connection.execute(
            "INSERT INTO transmitters (id, target_key, status) "
            "VALUES ('tx-legacy', 'missioncmd:Legacy  Mission', 'active')"
        )
        connection.execute(
            "INSERT INTO transmitters (id, target_key, status) "
            "VALUES ('tx-voyager', 'mission:Voyager 1', 'active')"
        )
        connection.execute(
            "INSERT INTO transmitters (id, target_key, status) "
            "VALUES ('tx-voyager-id', 'mission:voyager1', 'active')"
        )
        connection.execute(
            "INSERT INTO tracking_state (id, name, value, added) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (
                uuid.uuid4().hex,
                "tracking-state-target-1",
                json.dumps(
                    {
                        "target_type": "mission",
                        "command": "Parker Solar Probe",
                        "target_key": "missioncmd:Parker Solar Probe",
                    }
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(alembic_config, "head")

    connection = sqlite3.connect(db_path)
    try:
        target_ids = {row[0] for row in connection.execute("SELECT id FROM celestial_targets")}
        snapshot_target = connection.execute(
            "SELECT target_id FROM celestial_vector_snapshots WHERE id = 'snapshot-1'"
        ).fetchone()[0]
        monitored_key = connection.execute(
            "SELECT target_key FROM monitored_celestial WHERE id = 'monitored-1'"
        ).fetchone()[0]
        transmitter_keys = dict(
            connection.execute(
                "SELECT id, target_key FROM transmitters WHERE target_key IS NOT NULL"
            )
        )
        tracking_value = json.loads(
            connection.execute(
                "SELECT value FROM tracking_state WHERE name = 'tracking-state-target-1'"
            ).fetchone()[0]
        )
    finally:
        connection.close()

    assert {
        "mission:voyager_1",
        "mission:exomars",
        "mission:legacy_mission",
        "mission:parker_solar_probe",
    }.issubset(target_ids)
    assert snapshot_target == "mission:voyager_1"
    assert monitored_key == "mission:exomars"
    assert transmitter_keys == {
        "tx-legacy": "mission:legacy_mission",
        "tx-voyager": "mission:voyager_1",
        "tx-voyager-id": "mission:voyager_1",
    }
    assert tracking_value["target_key"] == "mission:parker_solar_probe"


def test_target_key_migration_aborts_before_schema_changes_on_collision(monkeypatch, tmp_path):
    db_path = tmp_path / "colliding-target-keys.db"
    monkeypatch.setenv("GS_DB", str(db_path))
    monkeypatch.setenv("ALEMBIC_CONTEXT", "1")
    alembic_config = migrations.get_alembic_config()
    command.upgrade(alembic_config, "d7e5a9c2b4f1")

    connection = sqlite3.connect(db_path)
    try:
        connection.executemany(
            """
            INSERT INTO celestial_targets
                (id, target_type, display_name, horizons_command, always_in_scene,
                 enabled, created_at, updated_at)
            VALUES (?, 'mission', ?, ?, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                ("mission:Voyager 1", "Voyager 1", "Voyager 1"),
                ("mission:voyager_1", "Voyager One", "Voyager One"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="Canonical target-key collision"):
        command.upgrade(alembic_config, "head")

    connection = sqlite3.connect(db_path)
    try:
        monitored_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(monitored_celestial)")
        }
        target_ids = {row[0] for row in connection.execute("SELECT id FROM celestial_targets")}
    finally:
        connection.close()

    assert "target_key" not in monitored_columns
    assert target_ids == {"mission:Voyager 1", "mission:voyager_1"}
