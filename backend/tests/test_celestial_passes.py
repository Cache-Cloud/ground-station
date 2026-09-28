from datetime import datetime, timedelta, timezone

from celestial import passes, trajectory
from celestial.passes import _build_pass_events_from_samples


def test_position_interpolation_rejects_times_outside_sample_interval():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    samples = [
        (start, [1.0, 2.0, 3.0]),
        (start + timedelta(hours=1), [2.0, 3.0, 4.0]),
    ]

    assert (
        trajectory._interpolate_position_from_samples(samples, start - timedelta(seconds=1)) is None
    )
    assert (
        trajectory._interpolate_position_from_samples(
            samples, start + timedelta(hours=1, seconds=1)
        )
        is None
    )
    assert trajectory._interpolate_position_from_samples(samples, start) == [1.0, 2.0, 3.0]
    assert trajectory._interpolate_position_from_samples(samples, start + timedelta(hours=1)) == [
        2.0,
        3.0,
        4.0,
    ]


def test_build_pass_events_extracts_crossing_window():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    samples = [
        {"time": start + timedelta(minutes=0), "az_deg": 10.0, "el_deg": -4.0},
        {"time": start + timedelta(minutes=1), "az_deg": 12.0, "el_deg": 2.0},
        {"time": start + timedelta(minutes=2), "az_deg": 18.0, "el_deg": 8.0},
        {"time": start + timedelta(minutes=3), "az_deg": 26.0, "el_deg": -1.0},
    ]
    row = {
        "target_key": "mission:voyager_1",
        "target_type": "mission",
        "name": "Voyager 1",
        "command": "Voyager 1",
        "color": "#06D6A0",
        "source": "horizons",
        "cache": "db-hit",
        "stale": False,
    }

    events = _build_pass_events_from_samples(row=row, samples=samples, horizon_deg=0.0)

    assert len(events) == 1
    event = events[0]
    assert event["target_key"] == "mission:voyager_1"
    assert event["peak_elevation_deg"] == 8.0
    assert event["peak_altitude"] == event["peak_elevation_deg"]
    assert event["start_azimuth"] == event["start_azimuth_deg"]
    assert event["end_azimuth"] == event["end_azimuth_deg"]
    assert event["peak_azimuth"] == event["peak_azimuth_deg"]
    assert event["estimated_start"] is False
    assert event["estimated_end"] is False
    assert len(event["elevation_curve"]) >= 3
    assert event["elevation_curve"][0]["elevation"] == 0.0
    assert event["elevation_curve"][-1]["elevation"] == 0.0
    assert event["duration_seconds"] > 0


def test_build_pass_events_handles_open_ended_pass():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    samples = [
        {"time": start + timedelta(minutes=0), "az_deg": 90.0, "el_deg": 3.0},
        {"time": start + timedelta(minutes=1), "az_deg": 95.0, "el_deg": 4.0},
        {"time": start + timedelta(minutes=2), "az_deg": 100.0, "el_deg": 2.0},
    ]
    row = {
        "target_key": "body:mars",
        "target_type": "body",
        "name": "Mars",
        "body_id": "mars",
        "source": "offline-solar-system",
        "cache": "offline",
        "stale": False,
    }

    events = _build_pass_events_from_samples(row=row, samples=samples, horizon_deg=0.0)

    assert len(events) == 1
    event = events[0]
    assert event["target_key"] == "body:mars"
    assert event["estimated_start"] is True
    assert event["estimated_end"] is True
    assert event["id"] == "body:mars_projection-open"
    assert event["projection_start"] == start.isoformat()
    assert event["projection_end"] == (start + timedelta(minutes=2)).isoformat()
    assert event["peak_elevation_deg"] == 4.0
    assert [point["elevation"] for point in event["elevation_curve"]] == [3.0, 4.0, 2.0]


def test_observer_samples_keep_fixed_snapshot_boundaries_when_epoch_moves(monkeypatch):
    snapshot_start = datetime(2026, 1, 1, 10, 12, tzinfo=timezone.utc)
    snapshot_end = snapshot_start + timedelta(hours=2)
    row = {
        "target_type": "body",
        "target_key": "body:io",
        "body_id": "io",
        "orbit_samples_xyz_au": [[1.0, 0.001, 0.0], [1.0, 0.002, 0.0]],
        "orbit_sample_times_utc": [snapshot_start.isoformat(), snapshot_end.isoformat()],
    }
    earth_samples = [
        (snapshot_start, [0.999, 0.0, 0.0]),
        (snapshot_end, [0.999, 0.0005, 0.0]),
    ]
    monkeypatch.setattr(
        passes,
        "compute_observer_sky_position",
        lambda **_kwargs: {"sky_position": {"az_deg": 180.0, "el_deg": 30.0}},
    )

    def extract(epoch):
        return passes._extract_row_observer_samples(
            row=row,
            epoch=epoch,
            past_hours=1,
            future_hours=1,
            step_minutes=10,
            observer_location={"lat": 40.0, "lon": 22.0},
            earth_position_xyz_au=None,
            earth_orbit_samples=earth_samples,
            logger=type("_DummyLogger", (), {"debug": lambda *_args, **_kwargs: None})(),
        )

    first = extract(snapshot_start + timedelta(hours=1))
    second = extract(snapshot_start + timedelta(hours=1, seconds=5))

    assert [sample["time"] for sample in first] == [sample["time"] for sample in second]
    assert first[0]["time"] == snapshot_start
    assert first[-1]["time"] == snapshot_end
    first_event = passes._build_pass_events_from_samples(row, first, horizon_deg=0.0)[0]
    second_event = passes._build_pass_events_from_samples(row, second, horizon_deg=0.0)[0]
    assert first_event["id"] == second_event["id"] == "body:io_projection-open"
    assert first_event["event_end"] == second_event["event_end"] == snapshot_end.isoformat()


def test_build_pass_events_densifies_sparse_curve_segments():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    samples = [
        {"time": start + timedelta(minutes=0), "az_deg": 10.0, "el_deg": -1.0},
        {"time": start + timedelta(minutes=30), "az_deg": 40.0, "el_deg": 8.0},
        {"time": start + timedelta(minutes=60), "az_deg": 70.0, "el_deg": 5.0},
        {"time": start + timedelta(minutes=90), "az_deg": 100.0, "el_deg": -2.0},
    ]
    row = {
        "target_key": "mission:cassini",
        "target_type": "mission",
        "name": "CASSINI",
        "command": "CASSINI",
        "source": "horizons",
        "cache": "db-hit",
        "stale": False,
    }

    events = _build_pass_events_from_samples(row=row, samples=samples, horizon_deg=0.0)

    assert len(events) == 1
    curve = events[0]["elevation_curve"]
    # Sparse 30-minute samples should be densified so the frontend receives a smoother path.
    assert len(curve) > 4
    assert curve[0]["elevation"] == 0.0
    assert curve[-1]["elevation"] == 0.0


def test_extract_row_observer_samples_prefers_supplied_earth_orbit_samples(monkeypatch):
    """Observer sampling should use provided Earth Horizons samples before local ephemeris fallback."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    row = {
        "target_type": "body",
        "target_key": "body:moon",
        "body_id": "moon",
        "orbit_samples_xyz_au": [
            [0.999, 0.001, 0.0],
            [0.999, 0.002, 0.0],
        ],
        "orbit_sample_times_utc": [
            start.isoformat(),
            (start + timedelta(minutes=30)).isoformat(),
        ],
    }

    earth_orbit_samples = [
        (start, [0.998, 0.0, 0.0]),
        (start + timedelta(minutes=30), [0.998, 0.0005, 0.0]),
    ]

    def _unexpected_earth_fallback(_body_id, _sample_time):
        raise AssertionError(
            "Local Earth ephemeris fallback should not run when Horizons samples exist"
        )

    monkeypatch.setattr(
        passes,
        "compute_body_position_heliocentric_au",
        _unexpected_earth_fallback,
        raising=False,
    )

    samples = passes._extract_row_observer_samples(
        row=row,
        epoch=start,
        past_hours=0,
        future_hours=1,
        step_minutes=30,
        observer_location={"lat": 40.0, "lon": 22.0},
        earth_position_xyz_au=None,
        earth_orbit_samples=earth_orbit_samples,
        logger=type("_DummyLogger", (), {"debug": lambda *_args, **_kwargs: None})(),
    )

    assert len(samples) > 2
    assert samples[0]["time"] == start
    assert samples[1]["time"] == start + timedelta(minutes=5)
    assert all("el_deg" in sample and "az_deg" in sample for sample in samples)


def test_extract_row_observer_samples_requires_horizons_target_samples_for_bodies():
    """Body rows without Horizons orbit samples should not fall back to local ephemeris."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    row = {
        "target_type": "body",
        "target_key": "body:moon",
        "body_id": "moon",
        "orbit_samples_xyz_au": [],
        "orbit_sample_times_utc": [],
    }

    samples = passes._extract_row_observer_samples(
        row=row,
        epoch=start,
        past_hours=0,
        future_hours=1,
        step_minutes=30,
        observer_location={"lat": 40.0, "lon": 22.0},
        earth_position_xyz_au=None,
        earth_orbit_samples=[],
        logger=type("_DummyLogger", (), {"debug": lambda *_args, **_kwargs: None})(),
    )

    assert samples == []


def test_extract_row_observer_samples_does_not_call_local_earth_fallback(monkeypatch):
    """Observer sampling should skip rows when Earth Horizons vectors are unavailable."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    row = {
        "target_type": "mission",
        "target_key": "mission:voyager_1",
        "command": "Voyager 1",
        "orbit_samples_xyz_au": [
            [0.999, 0.001, 0.0],
            [0.999, 0.002, 0.0],
        ],
        "orbit_sample_times_utc": [
            start.isoformat(),
            (start + timedelta(minutes=30)).isoformat(),
        ],
    }

    def _unexpected_earth_fallback(_body_id, _sample_time):
        raise AssertionError("Local Earth ephemeris fallback should not be called")

    monkeypatch.setattr(
        passes,
        "compute_body_position_heliocentric_au",
        _unexpected_earth_fallback,
        raising=False,
    )

    samples = passes._extract_row_observer_samples(
        row=row,
        epoch=start,
        past_hours=0,
        future_hours=1,
        step_minutes=30,
        observer_location={"lat": 40.0, "lon": 22.0},
        earth_position_xyz_au=None,
        earth_orbit_samples=[],
        logger=type("_DummyLogger", (), {"debug": lambda *_args, **_kwargs: None})(),
    )

    assert samples == []


def test_extract_row_observer_samples_stops_when_earth_samples_end(monkeypatch):
    """A current Earth position must not be reused beyond its trajectory samples."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    row = {
        "target_type": "body",
        "target_key": "body:moon",
        "body_id": "moon",
        "orbit_samples_xyz_au": [
            [1.0, 0.001, 0.0],
            [1.0, 0.002, 0.0],
        ],
        "orbit_sample_times_utc": [
            start.isoformat(),
            (start + timedelta(hours=1)).isoformat(),
        ],
    }
    earth_orbit_samples = [
        (start, [0.999, 0.0, 0.0]),
        (start + timedelta(minutes=30), [0.999, 0.0005, 0.0]),
    ]

    monkeypatch.setattr(
        passes,
        "compute_observer_sky_position",
        lambda **_kwargs: {"sky_position": {"az_deg": 180.0, "el_deg": 30.0}},
    )

    samples = passes._extract_row_observer_samples(
        row=row,
        epoch=start,
        past_hours=0,
        future_hours=1,
        step_minutes=30,
        observer_location={"lat": 40.0, "lon": 22.0},
        earth_position_xyz_au=[0.999, 0.0, 0.0],
        earth_orbit_samples=earth_orbit_samples,
        logger=type("_DummyLogger", (), {"debug": lambda *_args, **_kwargs: None})(),
    )

    assert len(samples) == 7
    assert samples[-1]["time"] == start + timedelta(minutes=30)
