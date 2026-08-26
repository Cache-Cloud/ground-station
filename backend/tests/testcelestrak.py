"""CelesTrak synchronization safety regression coverage."""

import copy
import logging
import uuid

import pytest
import requests

from db.models import OrbitalSources, OrbitalSourceSyncState
from tlesync import logic


class _Response:
    """Minimal response object for the exact-200 CelesTrak request helper."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = "CelesTrak request rejected for regression test"


def _celestrak_source(name: str, url: str, priority: int) -> OrbitalSources:
    return OrbitalSources(
        id=uuid.uuid4(),
        name=name,
        identifier=f"{name.lower().replace(' ', '-')}-{priority}",
        url=url,
        format="omm",
        provider="generic_http",
        adapter="http_omm",
        enabled=True,
        priority=priority,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [301, 403, 404, 500])
async def test_non_200_celestrak_response_suspends_source_and_stops_later_requests(
    db_session, monkeypatch, status_code
):
    """The sync-run circuit breaker must allow only its first CelesTrak request."""
    first_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=CSV"
    later_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=CSV"
    first_source = _celestrak_source("First CelesTrak source", first_url, priority=1)
    later_source = _celestrak_source("Later CelesTrak source", later_url, priority=2)
    db_session.add_all([first_source, later_source])
    await db_session.commit()

    requests_seen = []

    def fake_get(url, **kwargs):
        requests_seen.append((url, kwargs))
        return _Response(status_code)

    emitted_states = []

    async def emit_callback(state):
        emitted_states.append(copy.deepcopy(state))

    monkeypatch.setattr(requests, "get", fake_get)

    result = await logic.synchronize_satellite_data_internal(
        db_session, logging.getLogger(__name__), emit_callback
    )

    assert result is False
    assert [url for url, _kwargs in requests_seen] == [first_url]
    assert requests_seen[0][1]["allow_redirects"] is False

    state = await db_session.get(OrbitalSourceSyncState, first_source.id)
    assert state is not None
    assert state.last_http_status == status_code
    assert state.suspended_at is not None
    assert state.last_error is not None
    assert f"HTTP {status_code}" in state.last_error

    suspended_source = await db_session.get(OrbitalSources, first_source.id)
    assert suspended_source.enabled is False
    assert await db_session.get(OrbitalSourceSyncState, later_source.id) is None
    assert emitted_states[-1]["success"] is False
    assert "requires human review" in emitted_states[-1]["message"].lower()
