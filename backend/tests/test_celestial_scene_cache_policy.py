from datetime import datetime, timezone

import pytest

from celestial import horizons, scene


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def debug(self, *_args, **_kwargs):
        return None


@pytest.fixture(autouse=True)
def _reset_horizons_availability():
    horizons.reset_horizons_circuit()
    yield
    horizons.reset_horizons_circuit()


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
