from datetime import datetime, timedelta, timezone

import pytest

from celestial.relative import AU_IN_KM, build_earth_relative_metrics


def test_builds_earth_relative_motion_and_signal_metrics():
    epoch = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    earth_samples = [
        (epoch - timedelta(hours=1), [1.0, -0.01, 0.0]),
        (epoch + timedelta(hours=1), [1.0, 0.01, 0.0]),
    ]

    metrics = build_earth_relative_metrics(
        target_position_xyz_au=[2.0, 0.0, 0.0],
        target_velocity_xyz_au_per_day=[0.01, 0.12, 0.0],
        earth_position_xyz_au=[1.0, 0.0, 0.0],
        epoch=epoch,
        target_samples=[],
        earth_samples=earth_samples,
    )

    assert metrics is not None
    assert metrics["distance_au"] == pytest.approx(1.0)
    assert metrics["distance_km"] == pytest.approx(AU_IN_KM)
    assert metrics["relative_speed_km_s"] > abs(metrics["range_rate_km_s"])
    assert metrics["range_rate_km_s"] > 0
    assert metrics["motion"] == "receding"
    assert metrics["doppler_shift_hz_per_ghz"] < 0
    assert metrics["round_trip_light_time_seconds"] == pytest.approx(
        2 * metrics["one_way_light_time_seconds"]
    )


def test_finds_closest_point_between_projected_samples():
    epoch = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    start = epoch - timedelta(hours=1)
    end = epoch + timedelta(hours=1)
    earth_samples = [(start, [0.0, 0.0, 0.0]), (end, [0.0, 0.0, 0.0])]
    target_samples = [(start, [1.0, 1.0, 0.0]), (end, [1.0, -1.0, 0.0])]

    metrics = build_earth_relative_metrics(
        target_position_xyz_au=[1.0, 0.0, 0.0],
        target_velocity_xyz_au_per_day=None,
        earth_position_xyz_au=[0.0, 0.0, 0.0],
        epoch=epoch,
        target_samples=target_samples,
        earth_samples=earth_samples,
    )

    assert metrics is not None
    assert metrics["closest_approach_distance_au"] == pytest.approx(1.0)
    assert metrics["closest_approach_at_utc"] == epoch.isoformat()
