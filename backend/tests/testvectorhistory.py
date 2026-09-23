# Copyright (c) 2026 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests for the compact celestial vector-history inspection API."""

from datetime import datetime, timedelta, timezone

import pytest

from crud.celestialvectors import fetch_celestial_vector_snapshot_history
from db.models import CelestialTargets, CelestialVectorSnapshots
from handlers.entities.celestial import get_celestial_vector_snapshot_history


@pytest.mark.asyncio
async def test_vector_history_reports_cache_and_sample_validity(db_session):
    now = datetime(2026, 9, 23, 3, 30, tzinfo=timezone.utc)
    epoch = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)
    sample_times = [
        (now - timedelta(hours=24)).isoformat(),
        now.isoformat(),
        (now + timedelta(hours=24)).isoformat(),
    ]
    db_session.add(
        CelestialTargets(
            id="mission:-61",
            target_type="mission",
            display_name="Juno",
            horizons_command="-61",
        )
    )
    db_session.add_all(
        [
            CelestialVectorSnapshots(
                id="fresh",
                target_id="mission:-61",
                epoch_bucket_utc=epoch,
                past_hours=24,
                future_hours=24,
                step_minutes=60,
                position_xyz_au=[1, 2, 3],
                velocity_xyz_au_per_day=[0.1, 0.2, 0.3],
                orbit_samples_xyz_au=[[1, 2, 3]] * 3,
                orbit_sample_times_utc=sample_times,
                fetched_at=now - timedelta(minutes=30),
                expires_at=now + timedelta(minutes=90),
            ),
            CelestialVectorSnapshots(
                id="expired",
                target_id="mission:-61",
                epoch_bucket_utc=epoch - timedelta(hours=1),
                past_hours=24,
                future_hours=24,
                step_minutes=60,
                position_xyz_au=[1, 2, 3],
                velocity_xyz_au_per_day=[0.1, 0.2, 0.3],
                orbit_samples_xyz_au=[[1, 2, 3]] * 2,
                orbit_sample_times_utc=[
                    (epoch - timedelta(hours=2)).isoformat(),
                    (epoch + timedelta(hours=2)).isoformat(),
                ],
                fetched_at=now - timedelta(hours=3),
                expires_at=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()

    result = await fetch_celestial_vector_snapshot_history(
        db_session,
        "mission:-61",
        as_of=now,
    )

    assert result["success"] is True
    assert result["data"]["target_key"] == "mission:-61"
    assert result["data"]["now_utc"] == now.isoformat()
    fresh, expired = result["data"]["snapshots"]
    assert fresh == {
        "id": "fresh",
        "epoch_bucket_utc": epoch.isoformat(),
        "fetched_at": (now - timedelta(minutes=30)).isoformat(),
        "expires_at": (now + timedelta(minutes=90)).isoformat(),
        "sample_start_utc": (now - timedelta(hours=24)).isoformat(),
        "sample_end_utc": (now + timedelta(hours=24)).isoformat(),
        "requested_start_utc": (now - timedelta(hours=24)).isoformat(),
        "requested_end_utc": (now + timedelta(hours=24)).isoformat(),
        "sample_count": 3,
        "past_hours": 24,
        "future_hours": 24,
        "step_minutes": 60,
        "frame": "heliocentric-ecliptic",
        "center": "sun",
        "source": "horizons",
        "error": None,
        "cache_fresh": True,
        "vector_available": True,
        "covers_now": True,
        "covers_projection_window": True,
    }
    assert expired["cache_fresh"] is False
    assert expired["covers_now"] is True
    assert expired["covers_projection_window"] is False


@pytest.mark.asyncio
async def test_vector_history_handler_rejects_noncanonical_target_key():
    result = await get_celestial_vector_snapshot_history(
        None,
        {"target_key": "Mission:Juno Probe"},
        None,
        "sid",
    )

    assert result == {
        "success": False,
        "data": None,
        "error": "target_key must be a canonical mission: or body: key",
    }
