# Copyright (c) 2026 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Unit tests for scheduled-observation CRUD helpers."""

import uuid
from datetime import datetime, timezone

import pytest

from crud.scheduledobservations import (
    add_scheduled_observation,
    delete_scheduled_observations,
    edit_scheduled_observation,
    fetch_observations_by_satellite,
    fetch_observations_by_status,
    fetch_observations_by_time_range,
    fetch_scheduled_observations,
    log_observation_event,
    toggle_scheduled_observation_enabled,
    update_scheduled_observation_status,
)
from db.models import Satellites
from observations.constants import STATUS_COMPLETED, STATUS_FAILED


async def _add_satellite(db_session, norad_id):
    db_session.add(Satellites(norad_id=norad_id, name=f"Satellite {norad_id}"))
    await db_session.commit()


def _observation_data(
    norad_id, *, name="Observation", observation_id=None, start="2026-02-01T12:00:00Z"
):
    return {
        "id": observation_id or str(uuid.uuid4()),
        "name": name,
        "enabled": True,
        "satellite": {"norad_id": norad_id, "name": f"Satellite {norad_id}", "group_id": "group-a"},
        "pass": {
            "event_start": start,
            "event_end": "2026-02-01T12:10:00Z",
            "peak_altitude": 47.5,
        },
        "task_start": "2026-02-01T12:02:00Z",
        "task_end": "2026-02-01T12:09:00Z",
        "task_start_elevation": 15,
        "rotator": {"name": "Rotator", "tracker_id": "runtime-only"},
        "rig": {"name": "Rig"},
        "transmitter": {"id": "tx-1"},
        "sessions": [],
    }


@pytest.mark.asyncio
class TestScheduledObservationsCrud:
    async def test_add_preserves_configuration_and_fetches_by_queries(self, db_session):
        await _add_satellite(db_session, 43001)
        await _add_satellite(db_session, 43002)
        first = await add_scheduled_observation(
            db_session,
            _observation_data(43001, name="Later", start="2026-02-01T14:00:00Z"),
        )
        second = await add_scheduled_observation(
            db_session,
            _observation_data(43002, name="Earlier", start="2026-02-01T10:00:00Z"),
        )

        all_observations = await fetch_scheduled_observations(db_session)
        time_range = await fetch_observations_by_time_range(
            db_session,
            datetime(2026, 2, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 2, 1, 11, tzinfo=timezone.utc),
        )
        by_satellite = await fetch_observations_by_satellite(db_session, 43001)
        by_status = await fetch_observations_by_status(db_session, "scheduled")

        assert first["success"] is True
        assert "tracker_id" not in first["data"]["rotator"]
        assert first["data"]["transmitter"] == {"id": "tx-1"}
        assert [item["name"] for item in all_observations["data"]] == ["Earlier", "Later"]
        assert [item["id"] for item in time_range["data"]] == [second["data"]["id"]]
        assert [item["id"] for item in by_satellite["data"]] == [first["data"]["id"]]
        assert len(by_status["data"]) == 2

    async def test_edit_toggle_status_and_execution_log(self, db_session):
        await _add_satellite(db_session, 43003)
        added = await add_scheduled_observation(db_session, _observation_data(43003))
        observation_id = added["data"]["id"]

        edit_data = _observation_data(43003, name="Updated", observation_id=observation_id)
        edit_data["enabled"] = False
        edited = await edit_scheduled_observation(db_session, edit_data)
        toggled = await toggle_scheduled_observation_enabled(db_session, observation_id, True)
        failed = await update_scheduled_observation_status(
            db_session, observation_id, STATUS_FAILED, error_message="receiver unavailable"
        )
        completed = await update_scheduled_observation_status(
            db_session, observation_id, STATUS_COMPLETED
        )
        logged = await log_observation_event(
            db_session, observation_id, "Recorder stopped", "warning"
        )
        fetched = await fetch_scheduled_observations(db_session, observation_id)

        assert edited["data"]["name"] == "Updated"
        assert toggled["data"] == {"id": observation_id, "enabled": True}
        assert failed["data"]["status"] == STATUS_FAILED
        assert completed["data"]["status"] == STATUS_COMPLETED
        assert logged == {"success": True}
        assert fetched["data"]["error_count"] == 1
        assert fetched["data"]["error_message"] == "receiver unavailable"
        assert fetched["data"]["execution_log"][0]["event"] == "Recorder stopped"
        assert fetched["data"]["execution_log"][0]["level"] == "warning"

    async def test_missing_records_and_deletion_are_reported(self, db_session):
        await _add_satellite(db_session, 43004)
        added = await add_scheduled_observation(db_session, _observation_data(43004))

        missing_edit = await edit_scheduled_observation(db_session, {"name": "No id"})
        missing_toggle = await toggle_scheduled_observation_enabled(db_session, "missing", False)
        missing_status = await update_scheduled_observation_status(db_session, "", STATUS_FAILED)
        deleted = await delete_scheduled_observations(db_session, [added["data"]["id"]])
        fetched = await fetch_scheduled_observations(db_session, added["data"]["id"])

        assert missing_edit["error"] == "Observation ID is required"
        assert missing_toggle["error"] == "Observation not found: missing"
        assert missing_status["error"] == "Observation ID is required"
        assert deleted["data"]["deleted"] == 1
        assert fetched["data"] is None
