# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Earth-relative metrics derived from heliocentric celestial vectors."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from celestial.trajectory import _interpolate_position_from_samples

AU_IN_KM = 149597870.7
SECONDS_PER_DAY = 86400.0
SPEED_OF_LIGHT_KM_PER_S = 299792.458

Vector = List[float]
TimedVector = Tuple[datetime, Vector]


def _vector3(value: Any) -> Optional[Vector]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        vector = [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None
    return vector if all(math.isfinite(component) for component in vector) else None


def _subtract(left: Vector, right: Vector) -> Vector:
    return [left[index] - right[index] for index in range(3)]


def _magnitude(vector: Vector) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _velocity_from_samples(samples: List[TimedVector], epoch: datetime) -> Optional[Vector]:
    if len(samples) < 2:
        return None
    ordered = sorted(samples, key=lambda item: item[0])
    left_time, left_position = ordered[0]
    right_time, right_position = ordered[1]

    if epoch >= ordered[-1][0]:
        left_time, left_position = ordered[-2]
        right_time, right_position = ordered[-1]
    elif epoch > ordered[0][0]:
        for index in range(1, len(ordered)):
            if epoch <= ordered[index][0]:
                left_time, left_position = ordered[index - 1]
                right_time, right_position = ordered[index]
                break

    span_days = (right_time - left_time).total_seconds() / SECONDS_PER_DAY
    left_vector = _vector3(left_position)
    right_vector = _vector3(right_position)
    if span_days <= 1e-12 or left_vector is None or right_vector is None:
        return None
    return [(right_vector[index] - left_vector[index]) / span_days for index in range(3)]


def _projected_closest_approach(
    target_samples: List[TimedVector],
    earth_samples: List[TimedVector],
) -> Optional[Tuple[float, datetime]]:
    """Find the closest point on piecewise-linear Earth-relative trajectory segments."""
    relative_samples: List[TimedVector] = []
    for sample_time, target_position_value in sorted(target_samples, key=lambda item: item[0]):
        target_position = _vector3(target_position_value)
        earth_position = _interpolate_position_from_samples(earth_samples, sample_time)
        earth_vector = _vector3(earth_position)
        if target_position is None or earth_vector is None:
            continue
        relative_samples.append((sample_time, _subtract(target_position, earth_vector)))

    if not relative_samples:
        return None
    closest_distance_au = _magnitude(relative_samples[0][1])
    closest_time = relative_samples[0][0]

    for index in range(1, len(relative_samples)):
        left_time, left_vector = relative_samples[index - 1]
        right_time, right_vector = relative_samples[index]
        delta = _subtract(right_vector, left_vector)
        delta_squared = sum(component * component for component in delta)
        ratio = 0.0
        if delta_squared > 1e-18:
            ratio = max(
                0.0,
                min(1.0, -sum(left_vector[i] * delta[i] for i in range(3)) / delta_squared),
            )
        candidate = [left_vector[i] + ratio * delta[i] for i in range(3)]
        candidate_distance_au = _magnitude(candidate)
        if candidate_distance_au < closest_distance_au:
            closest_distance_au = candidate_distance_au
            closest_time = left_time + timedelta(
                seconds=(right_time - left_time).total_seconds() * ratio
            )

    return closest_distance_au, closest_time


def build_earth_relative_metrics(
    *,
    target_position_xyz_au: Any,
    target_velocity_xyz_au_per_day: Any,
    earth_position_xyz_au: Any,
    epoch: datetime,
    target_samples: List[TimedVector],
    earth_samples: List[TimedVector],
) -> Optional[Dict[str, Any]]:
    """Build geocentric distance, motion, signal-delay, and closest-approach metrics."""
    target_position = _vector3(target_position_xyz_au)
    earth_position = _vector3(earth_position_xyz_au)
    if target_position is None or earth_position is None:
        return None

    relative_position = _subtract(target_position, earth_position)
    distance_au = _magnitude(relative_position)
    distance_km = distance_au * AU_IN_KM
    metrics: Dict[str, Any] = {
        "distance_au": distance_au,
        "distance_km": distance_km,
        "one_way_light_time_seconds": distance_km / SPEED_OF_LIGHT_KM_PER_S,
        "round_trip_light_time_seconds": 2.0 * distance_km / SPEED_OF_LIGHT_KM_PER_S,
    }

    target_velocity = _vector3(target_velocity_xyz_au_per_day) or _velocity_from_samples(
        target_samples, epoch
    )
    earth_velocity = _velocity_from_samples(earth_samples, epoch)
    if target_velocity is not None and earth_velocity is not None:
        relative_velocity_au_per_day = _subtract(target_velocity, earth_velocity)
        velocity_scale = AU_IN_KM / SECONDS_PER_DAY
        relative_speed_km_s = _magnitude(relative_velocity_au_per_day) * velocity_scale
        metrics["relative_speed_km_s"] = relative_speed_km_s

        if distance_au > 1e-15:
            range_rate_au_per_day = (
                sum(
                    relative_position[index] * relative_velocity_au_per_day[index]
                    for index in range(3)
                )
                / distance_au
            )
            range_rate_km_s = range_rate_au_per_day * velocity_scale
            metrics["range_rate_km_s"] = range_rate_km_s
            metrics["motion"] = (
                "approaching"
                if range_rate_km_s < -1e-9
                else "receding" if range_rate_km_s > 1e-9 else "steady"
            )
            metrics["doppler_shift_hz_per_ghz"] = (
                -range_rate_km_s / SPEED_OF_LIGHT_KM_PER_S * 1_000_000_000.0
            )

    closest_approach = _projected_closest_approach(target_samples, earth_samples)
    if closest_approach is not None:
        closest_distance_au, closest_time = closest_approach
        metrics["closest_approach_distance_au"] = closest_distance_au
        metrics["closest_approach_distance_km"] = closest_distance_au * AU_IN_KM
        metrics["closest_approach_at_utc"] = closest_time.astimezone(timezone.utc).isoformat()

    return metrics
