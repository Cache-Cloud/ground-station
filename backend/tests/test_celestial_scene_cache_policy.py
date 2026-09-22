from datetime import datetime, timedelta, timezone

import pytest

from celestial import horizons, scene, syncstate
from crud.celestialvectors import fetch_celestial_vector_snapshot_stats
from db.models import CelestialTargets, CelestialVectorSnapshots
from handlers.entities import celestial as celestial_handlers


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def debug(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_earth_cannot_be_created_as_a_monitored_target():
    result = await celestial_handlers._validate_monitored_target_payload(
        {
            "target_type": "body",
            "body_id": "earth",
            "display_name": "Earth",
        }
    )

    assert result == {
        "success": False,
        "error": "Body 'Earth' cannot be monitored",
    }


@pytest.fixture(autouse=True)
def _reset_horizons_availability():
    horizons.reset_horizons_circuit()
    syncstate.reset_celestial_sync_state()
    yield
    horizons.reset_horizons_circuit()
    syncstate.reset_celestial_sync_state()


@pytest.mark.asyncio
async def test_get_vectors_snapshot_returns_exact_cache_hit(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    payload = {"command": "Voyager 1", "position_xyz_au": [1.0, 0.0, 0.0]}

    async def _stub_load_vectors_from_db(*_args, **_kwargs):
        return {"payload": payload}

    def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("Network fetch should not run on exact cache hit")

    monkeypatch.setattr(scene, "_load_vectors_from_db", _stub_load_vectors_from_db)
    monkeypatch.setattr(scene, "fetch_celestial_vectors", _unexpected_fetch)

    result = await scene._get_vectors_snapshot(
        command="Voyager 1",
        epoch=epoch,
        past_hours=1,
        future_hours=24,
        step_minutes=60,
        observer_location={"lat": 40.0, "lon": 22.0},
        force_refresh=False,
        logger=_DummyLogger(),
        allow_network_fetch=True,
    )

    assert result["cache"] == "db-hit"
    assert result["stale"] is False
    assert result["payload"]["command"] == "Voyager 1"


async def test_get_vectors_snapshot_cache_only_returns_miss_without_exact_cache(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    async def _stub_load_vectors_from_db(*_args, **_kwargs):
        return None

    monkeypatch.setattr(scene, "_load_vectors_from_db", _stub_load_vectors_from_db)
    # Cache-only mode falls back to the newest stale snapshot after its exact
    # lookup. Stub both database lookups so this test does not observe data
    # created by another test or an already-running temporary database.
    monkeypatch.setattr(scene, "_load_latest_vectors_from_db", _stub_load_vectors_from_db)

    result = await scene._get_vectors_snapshot(
        command="Voyager 1",
        epoch=epoch,
        past_hours=1,
        future_hours=24,
        step_minutes=60,
        observer_location={"lat": 40.0, "lon": 22.0},
        force_refresh=True,
        logger=_DummyLogger(),
        allow_network_fetch=False,
    )

    assert result["cache"] == "cache-only-miss"
    assert result["stale"] is True
    assert result["payload"] is None
    assert "No cached vectors available" in str(result["error"])


@pytest.mark.asyncio
async def test_get_vectors_snapshot_uses_fresh_snapshot_with_different_projection(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    compatible_payload = {
        "command": "Venus",
        "position_xyz_au": [0.0, 0.0, 0.0],
        "orbit_samples_xyz_au": [[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        "orbit_sample_times_utc": [
            datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc).isoformat(),
        ],
    }

    async def _no_projection_match(*_args, **_kwargs):
        return None

    async def _fresh_compatible_snapshot(*_args, **_kwargs):
        return {"payload": compatible_payload}

    monkeypatch.setattr(scene, "_load_vectors_from_db", _no_projection_match)
    monkeypatch.setattr(scene, "_load_latest_vectors_from_db", _no_projection_match)
    monkeypatch.setattr(
        scene,
        "_load_latest_vectors_for_target_from_db",
        _fresh_compatible_snapshot,
    )

    result = await scene._get_vectors_snapshot(
        command="Venus",
        target_key="body:venus",
        epoch=epoch,
        past_hours=0,
        future_hours=24,
        step_minutes=60,
        observer_location={"lat": 40.0, "lon": 22.0},
        force_refresh=False,
        logger=_DummyLogger(),
        allow_network_fetch=False,
    )

    assert result["cache"] == "db-compatible-hit"
    assert result["stale"] is False
    assert result["payload"]["position_xyz_au"] == [2.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_get_vectors_snapshot_fetches_and_stores_on_cache_miss(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    calls = {"fetch": 0, "store": 0}
    fetched_payload = {
        "command": "Voyager 1",
        "position_xyz_au": [1.0, 0.0, 0.0],
        "orbit_samples_xyz_au": [[1.0, 0.0, 0.0], [1.0, 0.1, 0.0]],
        "orbit_sample_times_utc": [
            datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc).isoformat(),
            datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc).isoformat(),
        ],
    }

    async def _stub_load_vectors_from_db(*_args, **_kwargs):
        return None

    def _stub_fetch_celestial_vectors(*_args, **_kwargs):
        calls["fetch"] += 1
        return dict(fetched_payload)

    async def _stub_store_vectors_in_db(*_args, **_kwargs):
        calls["store"] += 1
        return None

    monkeypatch.setattr(scene, "_load_vectors_from_db", _stub_load_vectors_from_db)
    monkeypatch.setattr(
        scene,
        "_load_latest_vectors_for_target_from_db",
        _stub_load_vectors_from_db,
    )
    monkeypatch.setattr(scene, "fetch_celestial_vectors", _stub_fetch_celestial_vectors)
    monkeypatch.setattr(scene, "_store_vectors_in_db", _stub_store_vectors_in_db)

    result = await scene._get_vectors_snapshot(
        command="Voyager 1",
        epoch=epoch,
        past_hours=1,
        future_hours=24,
        step_minutes=60,
        observer_location={"lat": 40.0, "lon": 22.0},
        force_refresh=False,
        logger=_DummyLogger(),
        allow_network_fetch=True,
    )

    assert result["cache"] == "db-miss"
    assert result["stale"] is False
    assert result["payload"]["command"] == "Voyager 1"
    assert calls["fetch"] == 1
    assert calls["store"] == 1


@pytest.mark.asyncio
async def test_get_vectors_snapshot_returns_miss_on_fetch_error_without_fallback(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    async def _stub_load_vectors_from_db(*_args, **_kwargs):
        return None

    def _failing_fetch(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(scene, "_load_vectors_from_db", _stub_load_vectors_from_db)
    monkeypatch.setattr(scene, "_load_latest_vectors_from_db", _stub_load_vectors_from_db)
    monkeypatch.setattr(
        scene,
        "_load_latest_vectors_for_target_from_db",
        _stub_load_vectors_from_db,
    )
    monkeypatch.setattr(scene, "fetch_celestial_vectors", _failing_fetch)

    result = await scene._get_vectors_snapshot(
        command="Voyager 1",
        epoch=epoch,
        past_hours=1,
        future_hours=24,
        step_minutes=60,
        observer_location={"lat": 40.0, "lon": 22.0},
        force_refresh=True,
        logger=_DummyLogger(),
        allow_network_fetch=True,
    )

    assert result["cache"] == "miss"
    assert result["stale"] is True
    assert result["payload"] is None
    assert "network down" in str(result["error"])


@pytest.mark.asyncio
async def test_get_vectors_snapshot_uses_expired_snapshot_after_fetch_error(monkeypatch):
    epoch = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    stale_payload = {
        "position_xyz_au": [1.0, 2.0, 3.0],
        "orbit_samples_xyz_au": [],
        "orbit_sample_times_utc": [],
        "source": "horizons",
        "fetched_at_utc": "2025-12-31T12:00:00+00:00",
    }

    async def _no_cache(*_args, **_kwargs):
        return None

    async def _stale_target_cache(*_args, **kwargs):
        return {"payload": stale_payload} if kwargs.get("valid_only") is False else None

    def _failing_fetch(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(scene, "_load_vectors_from_db", _no_cache)
    monkeypatch.setattr(scene, "_load_latest_vectors_from_db", _no_cache)
    monkeypatch.setattr(
        scene,
        "_load_latest_vectors_for_target_from_db",
        _stale_target_cache,
    )
    monkeypatch.setattr(scene, "fetch_celestial_vectors", _failing_fetch)

    result = await scene._get_vectors_snapshot(
        command="Voyager 1",
        epoch=epoch,
        past_hours=1,
        future_hours=24,
        step_minutes=60,
        observer_location=None,
        force_refresh=True,
        logger=_DummyLogger(),
        allow_network_fetch=True,
    )

    assert result["cache"] == "db-stale-fallback"
    assert result["stale"] is True
    assert result["payload"]["position_xyz_au"] == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
async def test_build_horizons_solar_system_bodies_keeps_missing_rows_without_origin_vectors(
    monkeypatch,
):
    epoch = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)

    def _stub_build_builtin_body_targets():
        return [
            {
                "body_id": "pluto",
                "target_key": "body:pluto",
                "horizons_command": "999",
                "name": "Pluto",
                "body_class": "dwarf",
                "parent_body_id": "sun",
            }
        ]

    async def _stub_ensure_scene_targets_registered(*_args, **_kwargs):
        return None

    async def _stub_get_vectors_snapshot(*_args, **_kwargs):
        return {
            "payload": None,
            "cache": "cache-only-miss",
            "stale": True,
            "error": "No data returned",
        }

    monkeypatch.setattr(scene, "_build_builtin_body_targets", _stub_build_builtin_body_targets)
    monkeypatch.setattr(
        scene, "_ensure_scene_targets_registered", _stub_ensure_scene_targets_registered
    )
    monkeypatch.setattr(scene, "_get_vectors_snapshot", _stub_get_vectors_snapshot)

    solar_meta, planets = await scene._build_horizons_solar_system_bodies(
        epoch=epoch,
        past_hours=6,
        future_hours=6,
        step_minutes=60,
        observer_location=None,
        force_refresh=True,
        allow_network_fetch=False,
        logger=_DummyLogger(),
    )

    assert solar_meta["cache"]["missing_count"] == 1
    assert len(planets) == 1
    row = planets[0]
    assert row["id"] == "pluto"
    assert row["stale"] is True
    assert row["position_xyz_au"] is None
    assert row["velocity_xyz_au_per_day"] is None


@pytest.mark.asyncio
async def test_build_horizons_solar_system_bodies_uses_offline_visual_fallback(monkeypatch):
    epoch = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        scene,
        "_build_builtin_body_targets",
        lambda: [
            {
                "body_id": "saturn",
                "target_key": "body:saturn",
                "horizons_command": "699",
                "name": "Saturn",
                "body_class": "planet",
                "parent_body_id": "sun",
            }
        ],
    )

    async def _noop(*_args, **_kwargs):
        return None

    async def _missing(*_args, **_kwargs):
        return {
            "payload": None,
            "cache": "miss",
            "stale": True,
            "error": "NASA JPL Horizons could not be reached",
            "error_code": "connect_timeout",
        }

    monkeypatch.setattr(scene, "_ensure_scene_targets_registered", _noop)
    monkeypatch.setattr(scene, "_get_vectors_snapshot", _missing)

    solar_meta, planets = await scene._build_horizons_solar_system_bodies(
        epoch=epoch,
        past_hours=6,
        future_hours=6,
        step_minutes=60,
        observer_location=None,
        force_refresh=False,
        allow_network_fetch=True,
        logger=_DummyLogger(),
    )

    assert solar_meta["cache"]["offline_count"] == 1
    assert solar_meta["cache"]["missing_count"] == 0
    assert planets[0]["source"] == "offline-analytic-kepler"
    assert planets[0]["approximate"] is True
    assert len(planets[0]["position_xyz_au"]) == 3


def test_horizons_circuit_skips_requests_during_backoff(monkeypatch):
    calls = []

    def _timeout(*_args, **kwargs):
        calls.append(kwargs)
        raise horizons.requests.exceptions.ConnectTimeout("blocked")

    monkeypatch.setattr(horizons.requests, "get", _timeout)

    with pytest.raises(horizons.HorizonsUnavailableError) as first_error:
        horizons._request_horizons_json(params={}, timeout_seconds=10.0, force_probe=False)
    with pytest.raises(horizons.HorizonsUnavailableError):
        horizons._request_horizons_json(params={}, timeout_seconds=10.0, force_probe=False)

    assert first_error.value.reason == "connect_timeout"
    assert len(calls) == 1
    assert calls[0]["timeout"] == (2.0, 10.0)
    status = horizons.get_horizons_status()
    assert status["circuit"] == "open"
    assert status["retry_at_utc"]


def test_manual_horizons_probe_closes_open_circuit(monkeypatch):
    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": "ok"}

    responses = [horizons.requests.exceptions.ConnectTimeout("blocked"), _Response()]

    def _request(*_args, **_kwargs):
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(horizons.requests, "get", _request)

    with pytest.raises(horizons.HorizonsUnavailableError):
        horizons._request_horizons_json(params={}, timeout_seconds=10.0, force_probe=False)
    payload, status_code = horizons._request_horizons_json(
        params={}, timeout_seconds=10.0, force_probe=True
    )

    assert payload == {"result": "ok"}
    assert status_code == 200
    assert horizons.get_horizons_status()["availability"] == "available"


@pytest.mark.asyncio
async def test_vector_snapshot_stats_report_cache_health(db_session):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    db_session.add(
        CelestialTargets(
            id="mission:voyager-1",
            target_type="mission",
            display_name="Voyager 1",
            horizons_command="Voyager 1",
        )
    )
    common = {
        "target_id": "mission:voyager-1",
        "epoch_bucket_utc": now,
        "past_hours": 1,
        "future_hours": 24,
        "step_minutes": 60,
        "frame": "heliocentric-ecliptic",
        "center": "sun",
        "position_xyz_au": [1, 2, 3],
        "velocity_xyz_au_per_day": [0, 0, 0],
        "orbit_samples_xyz_au": [],
        "orbit_sample_times_utc": [],
        "source": "horizons",
        "fetched_at": now - timedelta(minutes=5),
    }
    db_session.add_all(
        [
            CelestialVectorSnapshots(
                id="fresh",
                expires_at=now + timedelta(hours=1),
                **common,
            ),
            CelestialVectorSnapshots(
                id="expired",
                epoch_bucket_utc=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=1),
                error="old response",
                **{key: value for key, value in common.items() if key != "epoch_bucket_utc"},
            ),
        ]
    )
    await db_session.commit()

    result = await fetch_celestial_vector_snapshot_stats(db_session, as_of=now)

    assert result["success"] is True
    assert result["data"]["total_snapshots"] == 2
    assert result["data"]["distinct_targets"] == 1
    assert result["data"]["fresh_snapshots"] == 1
    assert result["data"]["expired_snapshots"] == 1
    assert result["data"]["error_snapshots"] == 1


@pytest.mark.asyncio
async def test_cache_refresh_reports_per_target_progress(monkeypatch):
    class _SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    async def fetch_monitored(*_args, **_kwargs):
        return {"success": True, "data": []}

    async def fetch_settings(*_args, **_kwargs):
        return {"success": True, "data": {"value": {}}}

    async def noop(*_args, **_kwargs):
        return None

    async def snapshot(*_args, **kwargs):
        if kwargs["target_key"] == "body:mars":
            return {
                "payload": None,
                "error": "NASA JPL Horizons could not be reached",
                "error_code": "connection_failure",
            }
        return {"payload": {"position_xyz_au": [1, 0, 0]}, "error": None}

    targets = [
        {"target_key": "body:earth", "name": "Earth", "horizons_command": "399"},
        {"target_key": "body:mars", "name": "Mars", "horizons_command": "499"},
    ]
    progress = []

    async def collect_progress(event):
        progress.append(event)

    async def finish_without_database(result):
        return result

    monkeypatch.setattr(scene, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(scene.crud_monitored, "fetch_monitored_celestial", fetch_monitored)
    monkeypatch.setattr(scene.crud_preferences, "get_map_settings", fetch_settings)
    monkeypatch.setattr(scene, "_build_builtin_body_targets", lambda: targets)
    monkeypatch.setattr(scene, "_ensure_scene_targets_registered", noop)
    monkeypatch.setattr(scene, "_get_vectors_snapshot", snapshot)
    monkeypatch.setattr(scene, "finish_celestial_sync", finish_without_database)

    result = await scene.refresh_celestial_vector_snapshots_cache(
        _DummyLogger(),
        progress_callback=collect_progress,
    )

    assert result["refreshed"] == 1
    assert result["failed"] == 1
    assert result["errors"] == [
        {
            "target_key": "body:mars",
            "target_name": "Mars",
            "error_code": "connection_failure",
            "error": "NASA JPL Horizons could not be reached",
        }
    ]
    assert [event["phase"] for event in progress] == [
        "starting",
        "processing",
        "processed",
        "processing",
        "processed",
    ]
    assert progress[-1]["processed"] == 2
    assert progress[-1]["percent"] == 100.0
    assert progress[-1]["failed"] == 1


@pytest.mark.asyncio
async def test_cache_refresh_progress_is_sent_only_to_requesting_client(monkeypatch):
    emitted = []

    class _Sio:
        async def emit(self, event, payload, to=None):
            emitted.append((event, payload, to))

    async def refresh(_logger, *, progress_callback=None, trigger="manual"):
        assert trigger == "manual"
        await progress_callback({"processed": 1, "total": 2, "percent": 50.0})
        return {"success": True, "count": 2, "refreshed": 2, "failed": 0}

    monkeypatch.setattr(
        celestial_handlers,
        "refresh_celestial_vector_snapshots_cache",
        refresh,
    )

    async def emit_status(sio, _logger):
        payload = {"success": True, "data": {"sync": {"state": {"status": "complete"}}}}
        await sio.emit("celestial-ephemeris-status-update", payload)

    monkeypatch.setattr(celestial_handlers, "emit_celestial_ephemeris_status", emit_status)

    async def build_empty_payload(_data, _logger):
        return {"celestial": []}

    monkeypatch.setattr(
        celestial_handlers,
        "_build_scene_payload",
        build_empty_payload,
    )

    result = await celestial_handlers.refresh_celestial_cache_now(
        sio=_Sio(),
        data=None,
        logger=_DummyLogger(),
        sid="requesting-client",
    )

    assert result["success"] is True
    assert emitted == [
        (
            "celestial-cache-refresh-progress",
            {"processed": 1, "total": 2, "percent": 50.0},
            "requesting-client",
        ),
        (
            "celestial-ephemeris-status-update",
            {"success": True, "data": {"sync": {"state": {"status": "complete"}}}},
            None,
        ),
        (
            "celestial-tracks-update",
            {
                "timestamp_utc": emitted[2][1]["timestamp_utc"],
                "frame": "heliocentric-ecliptic",
                "center": "sun",
                "units": {"position": "au", "velocity": "au/day"},
                "celestial": [],
                "celestial_passes": [],
                "observer_bodies": [],
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_successful_cache_refresh_broadcasts_rebuilt_cached_tracks(monkeypatch):
    emitted = []
    build_calls = []

    class _Sio:
        async def emit(self, event, payload, to=None):
            emitted.append((event, payload, to))

    async def refresh(_logger, *, progress_callback=None, trigger="manual"):
        assert trigger == "manual"
        return {"success": True, "count": 1, "refreshed": 1, "failed": 0}

    async def build_payload(_data, _logger):
        return {
            "celestial": [
                {
                    "target_type": "mission",
                    "command": "Voyager 1",
                    "name": "Voyager 1",
                }
            ]
        }

    async def build_tracks(**kwargs):
        build_calls.append(kwargs)
        return {
            "success": True,
            "data": {
                "celestial": [
                    {
                        "name": "Voyager 1",
                        "sky_position": {"az_deg": 120.0, "el_deg": 30.0},
                    }
                ]
            },
        }

    monkeypatch.setattr(
        celestial_handlers,
        "refresh_celestial_vector_snapshots_cache",
        refresh,
    )

    async def emit_status(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        celestial_handlers,
        "emit_celestial_ephemeris_status",
        emit_status,
    )
    monkeypatch.setattr(celestial_handlers, "_build_scene_payload", build_payload)
    monkeypatch.setattr(celestial_handlers, "build_celestial_tracks", build_tracks)

    result = await celestial_handlers.refresh_celestial_cache_now(
        sio=_Sio(),
        data=None,
        logger=_DummyLogger(),
        sid="requesting-client",
    )

    assert result["success"] is True
    assert len(build_calls) == 1
    assert build_calls[0]["force_refresh"] is False
    assert build_calls[0]["allow_network_fetch"] is False
    assert build_calls[0]["register_targets"] is False
    assert build_calls[0]["use_computed_cache"] is False
    assert emitted == [
        (
            "celestial-tracks-update",
            {
                "celestial": [
                    {
                        "name": "Voyager 1",
                        "sky_position": {"az_deg": 120.0, "el_deg": 30.0},
                    }
                ]
            },
            None,
        )
    ]


@pytest.mark.asyncio
async def test_failed_cache_refresh_does_not_broadcast_tracks(monkeypatch):
    emitted = []

    class _Sio:
        async def emit(self, event, payload, to=None):
            emitted.append((event, payload, to))

    async def refresh(_logger, *, progress_callback=None, trigger="manual"):
        assert trigger == "manual"
        return {
            "success": False,
            "count": 1,
            "refreshed": 0,
            "failed": 1,
            "error": "Horizons unavailable",
        }

    async def unexpected_payload(*_args, **_kwargs):
        raise AssertionError("Tracks must not be rebuilt after a failed refresh")

    monkeypatch.setattr(
        celestial_handlers,
        "refresh_celestial_vector_snapshots_cache",
        refresh,
    )
    monkeypatch.setattr(
        celestial_handlers,
        "_build_scene_payload",
        unexpected_payload,
    )
    monkeypatch.setattr(
        celestial_handlers,
        "get_horizons_status",
        lambda: {
            "availability": "unavailable",
            "circuit": "open",
            "reason": "connection_failure",
            "retry_at_utc": "2026-09-22T08:45:00+00:00",
        },
    )

    async def emit_status(sio, _logger):
        payload = {"success": True, "data": {"sync": {"state": {"success": False}}}}
        await sio.emit("celestial-ephemeris-status-update", payload)

    monkeypatch.setattr(celestial_handlers, "emit_celestial_ephemeris_status", emit_status)

    result = await celestial_handlers.refresh_celestial_cache_now(
        sio=_Sio(),
        data=None,
        logger=_DummyLogger(),
        sid="requesting-client",
    )

    assert result["success"] is False
    assert result["data"]["provider_status"] == {
        "availability": "unavailable",
        "circuit": "open",
        "reason": "connection_failure",
        "retry_at_utc": "2026-09-22T08:45:00+00:00",
    }
    assert emitted == [
        (
            "celestial-ephemeris-status-update",
            {"success": True, "data": {"sync": {"state": {"success": False}}}},
            None,
        )
    ]


@pytest.mark.asyncio
async def test_delete_monitored_target_broadcasts_current_cached_tracks(monkeypatch):
    broadcasts = []

    class _SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    async def delete_target(_session, ids):
        return {
            "success": True,
            "data": {"deleted": len(ids), "ids": ids},
            "error": None,
        }

    async def broadcast(sio, logger, projection=None):
        broadcasts.append((sio, logger, projection))

    sio = object()
    logger = _DummyLogger()
    monkeypatch.setattr(celestial_handlers, "AsyncSessionLocal", _SessionContext)
    monkeypatch.setattr(
        celestial_handlers.crud_monitored,
        "delete_monitored_celestial",
        delete_target,
    )
    monkeypatch.setattr(
        celestial_handlers,
        "_broadcast_current_cached_celestial_tracks",
        broadcast,
    )

    result = await celestial_handlers.delete_monitored_celestial(
        sio=sio,
        data={"ids": ["target-1"]},
        logger=logger,
        sid="requesting-client",
    )

    assert result["success"] is True
    assert broadcasts == [(sio, logger, None)]
