# Copyright (c) 2026 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests for observation conflict and regeneration decisions."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from observations.conflicts import should_update_observation


@pytest.mark.parametrize(
    ("status", "start_offset", "expected"),
    [
        ("scheduled", timedelta(minutes=10), True),
        ("scheduled", timedelta(minutes=-10), False),
        ("running", timedelta(minutes=10), False),
        ("failed", timedelta(minutes=10), False),
        ("completed", timedelta(minutes=10), False),
        ("cancelled", timedelta(minutes=10), False),
        ("missed", timedelta(minutes=10), False),
    ],
)
def test_generation_only_updates_future_scheduled_observations(status, start_offset, expected):
    observation = SimpleNamespace(
        status=status,
        event_start=datetime.now(timezone.utc) + start_offset,
    )

    assert should_update_observation(observation) is expected
