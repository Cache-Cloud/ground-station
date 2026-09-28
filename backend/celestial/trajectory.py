# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pure trajectory sampling and interpolation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from celestial.settings import _parse_iso_utc


def _extract_orbit_samples(
    payload: Dict[str, Any],
    *,
    epoch_fallback: datetime,
    past_hours: int,
    future_hours: int,
) -> List[Tuple[datetime, List[float]]]:
    positions_obj = payload.get("orbit_samples_xyz_au")
    positions: List[List[float]] = []
    if isinstance(positions_obj, list):
        for sample in positions_obj:
            if not isinstance(sample, list) or len(sample) < 3:
                continue
            try:
                position = [float(sample[0]), float(sample[1]), float(sample[2])]
            except (TypeError, ValueError):
                continue
            positions.append(position)

    if len(positions) < 2:
        return []

    raw_times_obj = payload.get("orbit_sample_times_utc")
    sample_times: List[datetime] = []
    if isinstance(raw_times_obj, list) and len(raw_times_obj) == len(positions):
        parsed_times = [_parse_iso_utc(item) for item in raw_times_obj]
        if all(item is not None for item in parsed_times):
            sample_times = [item for item in parsed_times if item is not None]

    if len(sample_times) != len(positions):
        start = epoch_fallback - timedelta(hours=int(past_hours))
        span_seconds = max(1.0, float((int(past_hours) + int(future_hours)) * 3600))
        if len(positions) == 1:
            sample_times = [epoch_fallback]
        else:
            sample_times = [
                start + timedelta(seconds=(span_seconds * idx / max(1, len(positions) - 1)))
                for idx in range(len(positions))
            ]

    return list(zip(sample_times, positions))


def _interpolate_position_from_samples(
    samples: List[Tuple[datetime, List[float]]],
    at_time: datetime,
) -> Optional[List[float]]:
    if not samples:
        return None
    ordered = sorted(samples, key=lambda item: item[0])
    first_time, first_pos = ordered[0]
    last_time, last_pos = ordered[-1]
    # A position can only be interpolated inside the sampled interval. Reusing
    # an endpoint outside that interval freezes one body while the other keeps
    # moving, which creates false observer-relative motion in sky paths.
    if at_time < first_time or at_time > last_time:
        return None
    if at_time == first_time:
        return [float(first_pos[0]), float(first_pos[1]), float(first_pos[2])]
    if at_time == last_time:
        return [float(last_pos[0]), float(last_pos[1]), float(last_pos[2])]

    cursor = 0
    for sample_time, _sample_position in ordered[1:]:
        if sample_time >= at_time:
            break
        cursor += 1
    left_time, left_pos = ordered[cursor]
    right_time, right_pos = ordered[cursor + 1]
    span_seconds = (right_time - left_time).total_seconds()
    if span_seconds <= 1e-9:
        return [float(left_pos[0]), float(left_pos[1]), float(left_pos[2])]
    ratio = max(0.0, min(1.0, (at_time - left_time).total_seconds() / span_seconds))
    return [
        float(left_pos[0]) + ((float(right_pos[0]) - float(left_pos[0])) * ratio),
        float(left_pos[1]) + ((float(right_pos[1]) - float(left_pos[1])) * ratio),
        float(left_pos[2]) + ((float(right_pos[2]) - float(left_pos[2])) * ratio),
    ]


def _interpolate_position_xyz_au_at_epoch(
    *,
    payload: Dict[str, Any],
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> Optional[List[float]]:
    """Interpolate a mission position at the requested epoch using cached orbit samples."""
    samples = _extract_orbit_samples(
        payload,
        epoch_fallback=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    if not samples:
        return None

    ordered = sorted(samples, key=lambda item: item[0])
    first_time, first_pos = ordered[0]
    last_time, last_pos = ordered[-1]
    if epoch <= first_time:
        return [float(first_pos[0]), float(first_pos[1]), float(first_pos[2])]
    if epoch >= last_time:
        return [float(last_pos[0]), float(last_pos[1]), float(last_pos[2])]

    for index in range(1, len(ordered)):
        left_time, left_pos = ordered[index - 1]
        right_time, right_pos = ordered[index]
        if epoch > right_time:
            continue

        span_seconds = (right_time - left_time).total_seconds()
        if span_seconds <= 1e-9:
            return [float(left_pos[0]), float(left_pos[1]), float(left_pos[2])]
        ratio = max(0.0, min(1.0, (epoch - left_time).total_seconds() / span_seconds))
        return [
            float(left_pos[0]) + ((float(right_pos[0]) - float(left_pos[0])) * ratio),
            float(left_pos[1]) + ((float(right_pos[1]) - float(left_pos[1])) * ratio),
            float(left_pos[2]) + ((float(right_pos[2]) - float(left_pos[2])) * ratio),
        ]

    return [float(last_pos[0]), float(last_pos[1]), float(last_pos[2])]


def _derive_velocity_xyz_au_per_day_at_epoch(
    *,
    payload: Dict[str, Any],
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> Optional[List[float]]:
    """Estimate current velocity from adjacent cached orbit samples."""
    samples = _extract_orbit_samples(
        payload,
        epoch_fallback=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    if len(samples) < 2:
        return None

    ordered = sorted(samples, key=lambda item: item[0])
    left_time, left_pos = ordered[0]
    right_time, right_pos = ordered[1]

    if epoch >= ordered[-1][0]:
        left_time, left_pos = ordered[-2]
        right_time, right_pos = ordered[-1]
    else:
        for index in range(1, len(ordered)):
            candidate_time, _candidate_pos = ordered[index]
            if epoch <= candidate_time:
                left_time, left_pos = ordered[index - 1]
                right_time, right_pos = ordered[index]
                break

    span_days = (right_time - left_time).total_seconds() / 86400.0
    if abs(span_days) <= 1e-12:
        return None

    return [
        (float(right_pos[0]) - float(left_pos[0])) / span_days,
        (float(right_pos[1]) - float(left_pos[1])) / span_days,
        (float(right_pos[2]) - float(left_pos[2])) / span_days,
    ]


def _refresh_payload_dynamics_at_epoch(
    *,
    payload: Dict[str, Any],
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> None:
    """Refresh current position and velocity from cached trajectory samples."""
    interpolated_position = _interpolate_position_xyz_au_at_epoch(
        payload=payload,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    if interpolated_position:
        payload["position_xyz_au"] = interpolated_position

    derived_velocity = _derive_velocity_xyz_au_per_day_at_epoch(
        payload=payload,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    if derived_velocity:
        payload["velocity_xyz_au_per_day"] = derived_velocity


def _trim_payload_to_projection_window(
    *,
    payload: Dict[str, Any],
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> bool:
    """Trim a wider cached trajectory to the exact requested window."""
    samples = _extract_orbit_samples(
        payload,
        epoch_fallback=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    if len(samples) < 2:
        return False

    ordered = sorted(samples, key=lambda item: item[0])
    window_start = epoch - timedelta(hours=int(past_hours))
    window_end = epoch + timedelta(hours=int(future_hours))
    start_position = _interpolate_position_from_samples(ordered, window_start)
    end_position = _interpolate_position_from_samples(ordered, window_end)
    if start_position is None or end_position is None:
        return False

    # Interpolated boundary samples prevent a coarse cached interval from
    # visibly shortening or extending the requested path.
    trimmed = [(window_start, start_position)]
    trimmed.extend(
        (sample_time, position)
        for sample_time, position in ordered
        if window_start < sample_time < window_end
    )
    trimmed.append((window_end, end_position))
    payload["orbit_sample_times_utc"] = [
        sample_time.astimezone(timezone.utc).isoformat() for sample_time, _position in trimmed
    ]
    payload["orbit_samples_xyz_au"] = [position for _sample_time, position in trimmed]
    return True


def _payload_covers_projection_window(
    payload: Dict[str, Any],
    *,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> bool:
    """Return whether explicit Horizons samples cover the requested calculation window."""
    raw_times = payload.get("orbit_sample_times_utc")
    if not isinstance(raw_times, list) or len(raw_times) < 2:
        return False
    parsed_times = [_parse_iso_utc(value) for value in raw_times]
    valid_times = sorted(value for value in parsed_times if value is not None)
    if len(valid_times) < 2:
        return False
    window_start = epoch - timedelta(hours=int(past_hours))
    window_end = epoch + timedelta(hours=int(future_hours))
    return bool(valid_times[0] <= window_start and valid_times[-1] >= window_end)


def _payload_covers_current_epoch(payload: Dict[str, Any], *, epoch: datetime) -> bool:
    """Return whether explicit Horizons samples bracket the current scene epoch."""
    raw_times = payload.get("orbit_sample_times_utc")
    if not isinstance(raw_times, list) or len(raw_times) < 2:
        return False
    parsed_times = [_parse_iso_utc(value) for value in raw_times]
    valid_times = sorted(value for value in parsed_times if value is not None)
    if len(valid_times) < 2:
        return False
    return bool(valid_times[0] <= epoch <= valid_times[-1])


def _snapshot_projection_is_compatible(
    snapshot: Dict[str, Any],
    *,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
) -> bool:
    """Return whether a differently keyed snapshot can satisfy this projection."""
    try:
        cached_past_hours = int(snapshot["past_hours"])
        cached_future_hours = int(snapshot["future_hours"])
        cached_step_minutes = int(snapshot["step_minutes"])
    except (KeyError, TypeError, ValueError):
        return False

    return (
        cached_past_hours >= int(past_hours)
        and cached_future_hours >= int(future_hours)
        and cached_step_minutes <= int(step_minutes)
    )


def _extract_earth_position_xyz_au(planets: List[Dict[str, Any]]) -> Optional[List[float]]:
    for body in planets:
        if str(body.get("id") or "").lower() == "earth":
            # Offline analytic vectors are suitable for the canvas, but must not
            # silently become the precision source for passes or tracking.
            if (
                str(body.get("source") or "") != "horizons"
                or body.get("current_position_usable", body.get("calculation_usable", True))
                is False
            ):
                return None
            position = body.get("position_xyz_au")
            if isinstance(position, list) and len(position) >= 3:
                try:
                    return [float(position[0]), float(position[1]), float(position[2])]
                except (TypeError, ValueError):
                    return None
    return None


def _extract_earth_orbit_samples(
    rows: List[Dict[str, Any]],
    *,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
) -> List[Tuple[datetime, List[float]]]:
    """Extract Earth heliocentric orbit samples from scene rows when available."""
    for row in rows:
        if str(row.get("id") or "").strip().lower() != "earth":
            continue
        if str(row.get("source") or "") != "horizons" or row.get("calculation_usable") is False:
            return []
        samples = _extract_orbit_samples(
            row,
            epoch_fallback=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
        )
        if samples:
            return samples
        break
    return []
