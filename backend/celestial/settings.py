# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Configuration and projection helpers for celestial scene building."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from common.arguments import arguments


def _config_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(getattr(arguments, name, default))
    except (TypeError, ValueError):
        value = int(default)
    return max(minimum, value)


# Celestial cache policy is fixed by code, not by app config.
CACHE_TTL_SECONDS = 120
VECTOR_DB_TTL_SECONDS = 2 * 60 * 60
VECTOR_EPOCH_BUCKET_MINUTES = 60
VECTOR_FETCH_PADDING_HOURS = 1
COMPUTED_EPOCH_BUCKET_SECONDS = 60
SCHEDULED_SYNC_PAST_HOURS = _config_int("celestial_sync_past_hours", 1, 1)
SCHEDULED_SYNC_FUTURE_HOURS = 24
SCHEDULED_SYNC_STEP_MINUTES = 60
CELESTIAL_MAP_SETTINGS_NAME = "celestial-map-settings"
MAX_CELESTIAL_PAST_HOURS = 168
MAX_CELESTIAL_FUTURE_HOURS = 720
MAX_SAMPLES_PER_TARGET = 1500
DEFAULT_CELESTIAL_TARGETS: List[Dict[str, str]] = []
CELESTIAL_PASS_HORIZON_DEG = 0.0
CURVE_DENSIFY_TARGET_STEP_SECONDS = 5 * 60
CURVE_DENSIFY_MAX_INSERTS_PER_SEGMENT = 8
OBSERVER_SKY_TARGET_STEP_MINUTES = 5
MAX_OBSERVER_SKY_SAMPLES_PER_TARGET = 1500
DEFAULT_FRAME = "heliocentric-ecliptic"
DEFAULT_CENTER = "sun"


def _parse_epoch(data: Optional[Dict[str, Any]]) -> datetime:
    if not data:
        return datetime.now(timezone.utc)

    epoch_raw = data.get("epoch")
    if not epoch_raw:
        return datetime.now(timezone.utc)

    try:
        epoch_str = str(epoch_raw).strip()
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        parsed = datetime.fromisoformat(epoch_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _parse_projection_options(data: Optional[Dict[str, Any]]) -> Tuple[int, int, int]:
    if not data:
        return 1, 24, 60

    def parse_int(name: str, default: int, low: int, high: int) -> int:
        try:
            value = int(data.get(name, default))
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    past_hours = parse_int("past_hours", 1, 1, MAX_CELESTIAL_PAST_HOURS)
    future_hours = parse_int("future_hours", 24, 1, MAX_CELESTIAL_FUTURE_HOURS)
    step_minutes = parse_int("step_minutes", 60, 5, 24 * 60)
    adaptive_step_minutes = _compute_adaptive_step_minutes(
        past_hours=past_hours,
        future_hours=future_hours,
        requested_step_minutes=step_minutes,
        max_samples=MAX_SAMPLES_PER_TARGET,
    )
    return past_hours, future_hours, adaptive_step_minutes


def _coerce_projection_setting(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return int(fallback)
    return max(int(minimum), min(parsed, int(maximum)))


def _projection_payload_from_map_settings(settings: Dict[str, Any]) -> Dict[str, int]:
    """Translate saved celestial UI settings into scene projection options."""
    return {
        "past_hours": _coerce_projection_setting(
            settings.get("pastHours", settings.get("past_hours")),
            SCHEDULED_SYNC_PAST_HOURS,
            1,
            MAX_CELESTIAL_PAST_HOURS,
        ),
        "future_hours": _coerce_projection_setting(
            settings.get("futureHours", settings.get("future_hours")),
            SCHEDULED_SYNC_FUTURE_HOURS,
            1,
            MAX_CELESTIAL_FUTURE_HOURS,
        ),
        "step_minutes": _coerce_projection_setting(
            settings.get("stepMinutes", settings.get("step_minutes")),
            SCHEDULED_SYNC_STEP_MINUTES,
            1,
            24 * 60,
        ),
    }


def _parse_iso_utc(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _build_window_timestamps(
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
) -> List[datetime]:
    start = epoch - timedelta(hours=int(past_hours))
    end = epoch + timedelta(hours=int(future_hours))
    step = timedelta(minutes=max(1, int(step_minutes)))
    timestamps: List[datetime] = []
    current = start
    while current <= end:
        timestamps.append(current)
        current = current + step
    if not timestamps or timestamps[-1] < end:
        timestamps.append(end)
    return timestamps


def _build_interval_timestamps(
    start: datetime,
    end: datetime,
    step_minutes: int,
) -> List[datetime]:
    """Build a stable sample grid for an already-fetched vector interval."""
    if end < start:
        return []

    step = timedelta(minutes=max(1, int(step_minutes)))
    timestamps = [start]
    current = start + step
    while current < end:
        timestamps.append(current)
        current += step
    if timestamps[-1] < end:
        # The exact snapshot boundary is meaningful: it is the point through
        # which projection coverage is known, even when it is not a LOS.
        timestamps.append(end)
    return timestamps


def _round_up(value: int, base: int) -> int:
    if base <= 1:
        return max(1, value)
    return int(math.ceil(value / base) * base)


def _compute_adaptive_step_minutes(
    past_hours: int,
    future_hours: int,
    requested_step_minutes: int,
    max_samples: int,
) -> int:
    span_hours = max(1, int(past_hours) + int(future_hours))
    # Honor the target's requested density unless it would exceed the hard
    # sample cap. This makes the per-target interval an actual precision choice.
    effective_step = max(5, int(requested_step_minutes))

    # Enforce hard sample cap per target by raising step if needed.
    span_minutes = span_hours * 60
    estimated_samples = int(span_minutes / effective_step) + 1
    if estimated_samples > max_samples:
        required_step = _round_up(
            int(math.ceil(span_minutes / max(1, max_samples - 1))),
            5,
        )
        effective_step = max(effective_step, required_step)

    return min(max(5, effective_step), 24 * 60)


def _compute_observer_sample_step_minutes(
    past_hours: int,
    future_hours: int,
    source_step_minutes: int,
) -> int:
    """Choose local sky sampling density without requiring extra Horizons calls."""
    span_hours = max(1, int(past_hours) + int(future_hours))
    span_minutes = span_hours * 60

    # Short planetarium windows need real az/el samples, otherwise each sparse
    # vector sample becomes a visible kink in the projected sky path.
    if span_hours <= 72:
        desired_step = OBSERVER_SKY_TARGET_STEP_MINUTES
    elif span_hours <= 14 * 24:
        desired_step = 15
    elif span_hours <= 60 * 24:
        desired_step = 60
    elif span_hours <= 180 * 24:
        desired_step = 180
    else:
        desired_step = 360

    source_step = max(OBSERVER_SKY_TARGET_STEP_MINUTES, int(source_step_minutes))
    effective_step = min(source_step, desired_step)
    estimated_samples = int(span_minutes / effective_step) + 1
    if estimated_samples > MAX_OBSERVER_SKY_SAMPLES_PER_TARGET:
        required_step = _round_up(
            int(math.ceil(span_minutes / max(1, MAX_OBSERVER_SKY_SAMPLES_PER_TARGET - 1))),
            OBSERVER_SKY_TARGET_STEP_MINUTES,
        )
        effective_step = max(effective_step, required_step)

    return min(max(OBSERVER_SKY_TARGET_STEP_MINUTES, effective_step), 24 * 60)


def _bucket_epoch(epoch: datetime, bucket_seconds: int) -> datetime:
    utc_epoch = epoch.astimezone(timezone.utc)
    timestamp = int(utc_epoch.timestamp())
    bucketed = timestamp - (timestamp % max(1, int(bucket_seconds)))
    return datetime.fromtimestamp(bucketed, tz=timezone.utc)
