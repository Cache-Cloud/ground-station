# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import pytest

from celestial import status as celestial_status
from celestial import syncstate
from celestial.syncstate import (
    get_celestial_sync_state,
    hydrate_celestial_sync_state,
    load_celestial_sync_state,
    reset_celestial_sync_state,
    save_celestial_sync_state,
    start_celestial_sync,
    update_celestial_sync_progress,
)
from handlers.entities import celestial as celestial_handlers


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    reset_celestial_sync_state()
    yield
    reset_celestial_sync_state()


@pytest.mark.asyncio
async def test_terminal_celestial_sync_state_round_trips_through_database(db_session):
    state = {
        "status": "complete",
        "progress": 100,
        "success": True,
        "message": "Celestial ephemeris synchronization completed.",
        "trigger": "scheduled",
        "started_at": "2026-09-22T08:00:00+00:00",
        "completed_at": "2026-09-22T08:01:00+00:00",
        "last_update": "2026-09-22T08:01:00+00:00",
        "count": 4,
        "refreshed": 4,
        "failed": 0,
        "errors": [],
    }

    assert await save_celestial_sync_state(db_session, state) is True
    assert await load_celestial_sync_state(db_session) == state


@pytest.mark.asyncio
async def test_completed_sync_state_is_hydrated_after_runtime_reset(db_session, monkeypatch):
    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(syncstate, "AsyncSessionLocal", lambda: _SessionContext())

    start_celestial_sync("manual")
    terminal_state = await syncstate.finish_celestial_sync(
        {
            "success": True,
            "count": 4,
            "refreshed": 4,
            "failed": 0,
            "errors": [],
        }
    )
    assert terminal_state["status"] == "complete"
    assert terminal_state["success"] is True

    # A new backend process begins with idle runtime state and restores this row.
    reset_celestial_sync_state()
    hydrated_state = await hydrate_celestial_sync_state()

    assert hydrated_state == terminal_state
    assert get_celestial_sync_state() == terminal_state


def test_runtime_celestial_sync_state_tracks_progress():
    started = start_celestial_sync("manual")
    assert started["status"] == "inprogress"
    assert started["trigger"] == "manual"

    update_celestial_sync_progress(
        {
            "processed": 2,
            "total": 5,
            "percent": 40,
            "refreshed": 2,
            "failed": 0,
            "phase": "processed",
            "current_target": {"key": "body:mars", "name": "Mars"},
        }
    )

    state = get_celestial_sync_state()
    assert state["status"] == "inprogress"
    assert state["progress"] == 40
    assert state["processed"] == 2
    assert state["count"] == 5
    assert state["current_target"]["name"] == "Mars"


@pytest.mark.asyncio
async def test_ephemeris_status_returns_shared_sync_state(monkeypatch):
    terminal_state = {
        "status": "complete",
        "success": True,
        "progress": 100,
        "trigger": "scheduled",
    }

    class _SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    class _Logger:
        def exception(self, *_args, **_kwargs):
            return None

    async def hydrate():
        return terminal_state

    async def cache_stats(_session):
        return {"success": True, "data": {"total_snapshots": 2}}

    monkeypatch.setattr(celestial_status, "hydrate_celestial_sync_state", hydrate)
    monkeypatch.setattr(
        celestial_status.crud_vectors,
        "fetch_celestial_vector_snapshot_stats",
        cache_stats,
    )
    monkeypatch.setattr(
        celestial_status,
        "AsyncSessionLocal",
        lambda: _SessionContext(),
    )

    response = await celestial_handlers.get_celestial_ephemeris_status(
        sio=None,
        data=None,
        logger=_Logger(),
        sid="client",
    )

    assert response["success"] is True
    assert response["data"]["sync"]["state"] == terminal_state
