# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Observer pass detection and elevation-curve construction."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from celestial.observermath import compute_observer_sky_position
from celestial.settings import (
    CELESTIAL_PASS_HORIZON_DEG,
    CURVE_DENSIFY_MAX_INSERTS_PER_SEGMENT,
    CURVE_DENSIFY_TARGET_STEP_SECONDS,
    _build_interval_timestamps,
    _compute_observer_sample_step_minutes,
    _parse_iso_utc,
)
from celestial.trajectory import _interpolate_position_from_samples


def _interpolate_crossing_point(
    previous: Dict[str, Any],
    current: Dict[str, Any],
    horizon_deg: float,
) -> Dict[str, Any]:
    prev_el = float(previous["el_deg"])
    curr_el = float(current["el_deg"])
    prev_time = previous["time"]
    curr_time = current["time"]
    denominator = curr_el - prev_el
    if abs(denominator) < 1e-9:
        ratio = 0.0
    else:
        ratio = (float(horizon_deg) - prev_el) / denominator
    ratio = max(0.0, min(1.0, ratio))

    crossing_time = prev_time + timedelta(seconds=(curr_time - prev_time).total_seconds() * ratio)
    prev_az = float(previous["az_deg"])
    curr_az = float(current["az_deg"])
    delta_az = ((curr_az - prev_az + 540.0) % 360.0) - 180.0
    crossing_az = (prev_az + (delta_az * ratio)) % 360.0

    return {
        "time": crossing_time,
        "az_deg": crossing_az,
        "el_deg": float(horizon_deg),
    }


def _serialize_pass_curve_point(
    point: Dict[str, Any],
    *,
    elevation_deg: Optional[float] = None,
) -> Dict[str, Any]:
    point_time = point["time"]
    point_elevation = float(elevation_deg) if elevation_deg is not None else float(point["el_deg"])
    return {
        "time": point_time.astimezone(timezone.utc).isoformat(),
        "azimuth": float(point["az_deg"]),
        "elevation": point_elevation,
    }


def _deduplicate_curve_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduplicated: List[Dict[str, Any]] = []
    for point in points:
        point_time = str(point.get("time") or "").strip()
        if deduplicated and deduplicated[-1].get("time") == point_time:
            if float(point.get("elevation", -math.inf)) >= float(
                deduplicated[-1].get("elevation", -math.inf)
            ):
                deduplicated[-1] = point
            continue
        deduplicated.append(point)
    return deduplicated


def _interpolate_serialized_curve_point(
    previous: Dict[str, Any],
    current: Dict[str, Any],
    ratio: float,
) -> Optional[Dict[str, Any]]:
    prev_time = _parse_iso_utc(previous.get("time"))
    curr_time = _parse_iso_utc(current.get("time"))
    if not prev_time or not curr_time:
        return None

    ratio = max(0.0, min(1.0, float(ratio)))
    point_time = prev_time + timedelta(seconds=(curr_time - prev_time).total_seconds() * ratio)

    prev_az = float(previous.get("azimuth", 0.0))
    curr_az = float(current.get("azimuth", prev_az))
    # Interpolate azimuth using the shortest angular delta to avoid wrap jumps near 0°/360°.
    delta_az = ((curr_az - prev_az + 540.0) % 360.0) - 180.0
    azimuth = (prev_az + (delta_az * ratio)) % 360.0

    prev_el = float(previous.get("elevation", 0.0))
    curr_el = float(current.get("elevation", prev_el))
    elevation = prev_el + ((curr_el - prev_el) * ratio)

    return {
        "time": point_time.astimezone(timezone.utc).isoformat(),
        "azimuth": azimuth,
        "elevation": elevation,
    }


def _densify_curve_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(points) < 2:
        return points

    densified: List[Dict[str, Any]] = [points[0]]
    for index in range(1, len(points)):
        previous = points[index - 1]
        current = points[index]
        prev_time = _parse_iso_utc(previous.get("time"))
        curr_time = _parse_iso_utc(current.get("time"))
        if prev_time and curr_time:
            delta_seconds = max(0.0, (curr_time - prev_time).total_seconds())
            if delta_seconds > float(CURVE_DENSIFY_TARGET_STEP_SECONDS):
                desired_segments = int(
                    math.ceil(delta_seconds / float(CURVE_DENSIFY_TARGET_STEP_SECONDS))
                )
                # Keep growth bounded on very large windows while still smoothing sparse segments.
                insert_count = max(
                    0,
                    min(CURVE_DENSIFY_MAX_INSERTS_PER_SEGMENT, desired_segments - 1),
                )
                for insert_index in range(1, insert_count + 1):
                    ratio = insert_index / float(insert_count + 1)
                    interpolated = _interpolate_serialized_curve_point(previous, current, ratio)
                    if interpolated:
                        densified.append(interpolated)
        densified.append(current)
    return _deduplicate_curve_points(densified)


def _build_pass_elevation_curve(
    *,
    ordered_samples: List[Dict[str, Any]],
    start_index: int,
    end_index: int,
    start_crossing: Optional[Dict[str, Any]],
    end_crossing: Optional[Dict[str, Any]],
    horizon_deg: float,
) -> List[Dict[str, Any]]:
    if not ordered_samples:
        return []

    clamped_start = max(0, min(start_index, len(ordered_samples) - 1))
    clamped_end = max(clamped_start, min(end_index, len(ordered_samples) - 1))
    curve_points: List[Dict[str, Any]] = []

    if start_crossing:
        curve_points.append(
            _serialize_pass_curve_point(start_crossing, elevation_deg=float(horizon_deg))
        )

    for sample in ordered_samples[clamped_start : clamped_end + 1]:
        if float(sample["el_deg"]) < float(horizon_deg):
            continue
        curve_points.append(_serialize_pass_curve_point(sample))

    if end_crossing:
        curve_points.append(
            _serialize_pass_curve_point(end_crossing, elevation_deg=float(horizon_deg))
        )

    deduplicated = _deduplicate_curve_points(curve_points)
    if len(deduplicated) < 2:
        return []
    return _densify_curve_points(deduplicated)


def _build_pass_events_from_samples(
    row: Dict[str, Any],
    samples: List[Dict[str, Any]],
    horizon_deg: float,
) -> List[Dict[str, Any]]:
    if len(samples) < 2:
        return []

    ordered_samples = sorted(samples, key=lambda item: item["time"])
    events: List[Dict[str, Any]] = []
    active_pass: Optional[Dict[str, Any]] = None

    for index, sample in enumerate(ordered_samples):
        is_above = float(sample["el_deg"]) > float(horizon_deg)
        previous = ordered_samples[index - 1] if index > 0 else None
        previous_above = (
            bool(previous) and float(previous["el_deg"]) > float(horizon_deg) if previous else False
        )

        if active_pass is None and is_above:
            if previous and not previous_above:
                crossing = _interpolate_crossing_point(previous, sample, horizon_deg=horizon_deg)
                start_time = crossing["time"]
                start_az = float(crossing["az_deg"])
                estimated_start = False
            else:
                start_time = sample["time"]
                start_az = float(sample["az_deg"])
                estimated_start = index == 0

            active_pass = {
                "start_time": start_time,
                "start_azimuth_deg": start_az,
                "peak_time": sample["time"],
                "peak_elevation_deg": float(sample["el_deg"]),
                "peak_azimuth_deg": float(sample["az_deg"]),
                "start_index": index,
                "start_crossing": crossing if previous and not previous_above else None,
                "estimated_start": estimated_start,
            }

        if active_pass:
            if float(sample["el_deg"]) > float(active_pass["peak_elevation_deg"]):
                active_pass["peak_elevation_deg"] = float(sample["el_deg"])
                active_pass["peak_time"] = sample["time"]
                active_pass["peak_azimuth_deg"] = float(sample["az_deg"])

            if previous and previous_above and not is_above:
                crossing = _interpolate_crossing_point(previous, sample, horizon_deg=horizon_deg)
                end_time = crossing["time"]
                end_az = float(crossing["az_deg"])
                start_index = int(active_pass.get("start_index", index))
                end_index = max(start_index, index - 1)
                elevation_curve = _build_pass_elevation_curve(
                    ordered_samples=ordered_samples,
                    start_index=start_index,
                    end_index=end_index,
                    start_crossing=active_pass.get("start_crossing"),
                    end_crossing=crossing,
                    horizon_deg=horizon_deg,
                )
                duration_seconds = max(
                    0.0,
                    (end_time - active_pass["start_time"]).total_seconds(),
                )
                target_key = str(row.get("target_key") or "").strip()
                event_start_iso = active_pass["start_time"].astimezone(timezone.utc).isoformat()
                event_id = (
                    f"{target_key}_projection-open"
                    if active_pass["estimated_start"]
                    else f"{target_key}_{event_start_iso}"
                )
                events.append(
                    {
                        "id": event_id,
                        "target_key": target_key,
                        "target_type": row.get("target_type"),
                        "name": row.get("name"),
                        "command": row.get("command"),
                        "body_id": row.get("body_id"),
                        "color": row.get("color"),
                        "source": row.get("source"),
                        "cache": row.get("cache"),
                        "stale": bool(row.get("stale")),
                        "event_start": event_start_iso,
                        "event_end": end_time.astimezone(timezone.utc).isoformat(),
                        "peak_time": active_pass["peak_time"].astimezone(timezone.utc).isoformat(),
                        "duration_seconds": duration_seconds,
                        "start_azimuth_deg": float(active_pass["start_azimuth_deg"]),
                        "end_azimuth_deg": end_az,
                        "peak_azimuth_deg": float(active_pass["peak_azimuth_deg"]),
                        "peak_elevation_deg": float(active_pass["peak_elevation_deg"]),
                        "start_azimuth": float(active_pass["start_azimuth_deg"]),
                        "end_azimuth": end_az,
                        "peak_azimuth": float(active_pass["peak_azimuth_deg"]),
                        "peak_altitude": float(active_pass["peak_elevation_deg"]),
                        "elevation_curve": elevation_curve,
                        "estimated_start": bool(active_pass["estimated_start"]),
                        "estimated_end": False,
                        "projection_start": (
                            event_start_iso if active_pass["estimated_start"] else None
                        ),
                        "projection_end": None,
                        "horizon_threshold_deg": float(horizon_deg),
                    }
                )
                active_pass = None

    if active_pass:
        final_sample = ordered_samples[-1]
        end_time = final_sample["time"]
        end_az = float(final_sample["az_deg"])
        start_index = int(active_pass.get("start_index", 0))
        end_index = len(ordered_samples) - 1
        elevation_curve = _build_pass_elevation_curve(
            ordered_samples=ordered_samples,
            start_index=start_index,
            end_index=end_index,
            start_crossing=active_pass.get("start_crossing"),
            end_crossing=None,
            horizon_deg=horizon_deg,
        )
        duration_seconds = max(
            0.0,
            (end_time - active_pass["start_time"]).total_seconds(),
        )
        target_key = str(row.get("target_key") or "").strip()
        event_start_iso = active_pass["start_time"].astimezone(timezone.utc).isoformat()
        event_end_iso = end_time.astimezone(timezone.utc).isoformat()
        event_id = (
            f"{target_key}_projection-open"
            if active_pass["estimated_start"]
            else f"{target_key}_{event_start_iso}"
        )
        events.append(
            {
                "id": event_id,
                "target_key": target_key,
                "target_type": row.get("target_type"),
                "name": row.get("name"),
                "command": row.get("command"),
                "body_id": row.get("body_id"),
                "color": row.get("color"),
                "source": row.get("source"),
                "cache": row.get("cache"),
                "stale": bool(row.get("stale")),
                "event_start": event_start_iso,
                "event_end": event_end_iso,
                "peak_time": active_pass["peak_time"].astimezone(timezone.utc).isoformat(),
                "duration_seconds": duration_seconds,
                "start_azimuth_deg": float(active_pass["start_azimuth_deg"]),
                "end_azimuth_deg": end_az,
                "peak_azimuth_deg": float(active_pass["peak_azimuth_deg"]),
                "peak_elevation_deg": float(active_pass["peak_elevation_deg"]),
                "start_azimuth": float(active_pass["start_azimuth_deg"]),
                "end_azimuth": end_az,
                "peak_azimuth": float(active_pass["peak_azimuth_deg"]),
                "peak_altitude": float(active_pass["peak_elevation_deg"]),
                "elevation_curve": elevation_curve,
                "estimated_start": bool(active_pass["estimated_start"]),
                "estimated_end": True,
                "projection_start": (event_start_iso if active_pass["estimated_start"] else None),
                "projection_end": event_end_iso,
                "horizon_threshold_deg": float(horizon_deg),
            }
        )

    return events


def _extract_row_observer_samples(
    row: Dict[str, Any],
    *,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    observer_location: Optional[Dict[str, Any]],
    earth_position_xyz_au: Optional[List[float]],
    earth_orbit_samples: Optional[List[Tuple[datetime, List[float]]]],
    logger: Any,
) -> List[Dict[str, Any]]:
    if row.get("calculation_usable") is False or not observer_location:
        return []

    try:
        observer_lat_deg = float(observer_location["lat"])
        observer_lon_deg = float(observer_location["lon"])
    except (TypeError, ValueError, KeyError):
        return []

    samples: List[Dict[str, Any]] = []
    earth_samples = earth_orbit_samples or []

    positions_obj = row.get("orbit_samples_xyz_au")
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
        # Require Horizons orbit samples for observer pass generation.
        return []

    raw_times_obj = row.get("orbit_sample_times_utc")
    sample_times: List[datetime] = []
    if isinstance(raw_times_obj, list) and len(raw_times_obj) == len(positions):
        parsed_times = [_parse_iso_utc(item) for item in raw_times_obj]
        if all(item is not None for item in parsed_times):
            sample_times = [item for item in parsed_times if item is not None]

    if len(sample_times) != len(positions):
        start = epoch - timedelta(hours=int(past_hours))
        span_seconds = max(1.0, float((int(past_hours) + int(future_hours)) * 3600))
        if len(positions) == 1:
            sample_times = [epoch]
        else:
            sample_times = [
                start + timedelta(seconds=(span_seconds * idx / max(1, len(positions) - 1)))
                for idx in range(len(positions))
            ]

    target_samples = list(zip(sample_times, positions))
    observer_step_minutes = _compute_observer_sample_step_minutes(
        past_hours=past_hours,
        future_hours=future_hours,
        source_step_minutes=step_minutes,
    )
    ordered_target_samples = sorted(target_samples, key=lambda item: item[0])
    ordered_earth_samples = sorted(earth_samples, key=lambda item: item[0])
    if len(ordered_earth_samples) < 2:
        return []

    # Cache-only broadcasts run every five seconds, but their projection data
    # remains fixed until the next Horizons refresh. Anchor pass calculations
    # to the shared vector coverage instead of rebuilding a window around NOW.
    # This makes estimated AOS/LOS boundaries deterministic between refreshes.
    coverage_start = max(ordered_target_samples[0][0], ordered_earth_samples[0][0])
    coverage_end = min(ordered_target_samples[-1][0], ordered_earth_samples[-1][0])
    observer_sample_times = _build_interval_timestamps(
        start=coverage_start,
        end=coverage_end,
        step_minutes=observer_step_minutes,
    )

    for sample_time in observer_sample_times:
        target_position = _interpolate_position_from_samples(target_samples, sample_time)
        if not target_position:
            continue

        earth_position_for_sample = _interpolate_position_from_samples(
            earth_samples,
            sample_time,
        )
        if not earth_position_for_sample:
            continue

        try:
            observer_view = compute_observer_sky_position(
                target_heliocentric_xyz_au=target_position,
                earth_heliocentric_xyz_au=earth_position_for_sample,
                epoch=sample_time,
                observer_lat_deg=observer_lat_deg,
                observer_lon_deg=observer_lon_deg,
            )
            sky_position = observer_view.get("sky_position")
            if not isinstance(sky_position, dict):
                continue
            az_obj = sky_position.get("az_deg")
            el_obj = sky_position.get("el_deg")
            if not isinstance(az_obj, (int, float, str)) or not isinstance(
                el_obj, (int, float, str)
            ):
                continue
            az_deg = float(az_obj)
            el_deg = float(el_obj)
            if not math.isfinite(az_deg) or not math.isfinite(el_deg):
                continue
            samples.append({"time": sample_time, "az_deg": az_deg, "el_deg": el_deg})
        except Exception as exc:
            logger.debug(
                "Observer sample calculation failed for celestial "
                f"'{row.get('target_key') or row.get('command') or row.get('body_id')}': {exc}"
            )
            continue

    return samples


def _build_celestial_passes(
    rows: List[Dict[str, Any]],
    *,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    observer_location: Optional[Dict[str, Any]],
    earth_position_xyz_au: Optional[List[float]],
    earth_orbit_samples: Optional[List[Tuple[datetime, List[float]]]] = None,
    logger: Any,
) -> List[Dict[str, Any]]:
    passes: List[Dict[str, Any]] = []
    for row in rows:
        samples = _extract_row_observer_samples(
            row=row,
            epoch=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            observer_location=observer_location,
            earth_position_xyz_au=earth_position_xyz_au,
            earth_orbit_samples=earth_orbit_samples,
            logger=logger,
        )
        if len(samples) < 2:
            continue
        events = _build_pass_events_from_samples(
            row=row,
            samples=samples,
            horizon_deg=CELESTIAL_PASS_HORIZON_DEG,
        )
        for event in events:
            event["sample_count"] = len(samples)
        passes.extend(events)

    passes.sort(key=lambda item: str(item.get("event_start") or ""))
    return passes
