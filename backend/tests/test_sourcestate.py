"""Tests for persistent per-provider orbital source status."""

import uuid

import pytest

from db.models import OrbitalSources, OrbitalSourceSyncState
from tlesync.sourcestate import (
    CELESTRAK_RATE_LIMIT_NOOP_MESSAGE,
    all_enabled_sources_are_rate_limited,
    mark_source_failure,
    mark_source_success,
)


@pytest.mark.asyncio
async def test_generic_source_status_records_failures_and_recovery(db_session):
    """Generic providers expose their latest result without being suspended."""
    source = OrbitalSources(
        id=uuid.uuid4(),
        name="Space-Track test",
        identifier="space-track-test",
        url="https://www.space-track.org/basicspacedata/query/class/gp",
        format="omm",
        provider="space_track",
        adapter="space_track_gp",
        enabled=True,
    )
    db_session.add(source)
    await db_session.commit()

    await mark_source_failure(db_session, source.id, "HTTP 401", 401)
    state = await db_session.get(OrbitalSourceSyncState, source.id)
    assert state.last_success_at is None
    assert state.last_attempt_at is not None
    assert state.last_http_status == 401
    assert state.last_error == "HTTP 401"
    assert state.suspended_at is None

    await mark_source_success(db_session, source.id)
    state = await db_session.get(OrbitalSourceSyncState, source.id)
    assert state.last_success_at is not None
    assert state.last_http_status == 200
    assert state.last_error is None
    assert state.suspended_at is None


def test_rate_limited_celestrak_noop_message_is_explicit():
    assert all_enabled_sources_are_rate_limited(2, 2) is True
    assert all_enabled_sources_are_rate_limited(0, 0) is False
    assert all_enabled_sources_are_rate_limited(1, 2) is False
    assert "No download was needed" in CELESTRAK_RATE_LIMIT_NOOP_MESSAGE
    assert "Existing orbital data remains active" in CELESTRAK_RATE_LIMIT_NOOP_MESSAGE
