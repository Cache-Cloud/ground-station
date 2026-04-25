# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Scene builder for celestial page (offline planets + Horizons celestial)."""

from __future__ import annotations

import asyncio
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import crud.celestialvectors as crud_celestial_vectors
import crud.locations as crud_locations
from celestial.asteroidzones import get_static_asteroid_zones
from celestial.horizons import fetch_celestial_vectors
from celestial.observermath import compute_observer_sky_position
from celestial.solarsystem import compute_solar_system_snapshot
from db import AsyncSessionLocal

CACHE_TTL_SECONDS = 120
VECTOR_DB_TTL_SECONDS = 30 * 60
VECTOR_EPOCH_BUCKET_MINUTES = 10
COMPUTED_EPOCH_BUCKET_SECONDS = 60
MAX_SAMPLES_PER_TARGET = 1500
DEFAULT_CELESTIAL_TARGETS: List[Dict[str, str]] = []
NO_EPHEMERIS_ERROR_FRAGMENT = "No ephemeris data returned by Horizons"


@dataclass
class CacheEntry:
    payload: Dict[str, Any]
    fetched_at_monotonic: float


_computed_cache: Dict[str, CacheEntry] = {}
_computed_cache_lock = threading.Lock()


def _target_key_from_parts(
    target_type: str,
    *,
    command: Optional[str] = None,
    body_id: Optional[str] = None,
) -> str:
    normalized_type = str(target_type or "mission").strip().lower()
    if normalized_type == "body":
        normalized_body = str(body_id or "").strip().lower()
        return f"body:{normalized_body}" if normalized_body else ""
    normalized_command = str(command or "").strip()
    return f"mission:{normalized_command}" if normalized_command else ""


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


def _normalize_targets(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not data:
        return DEFAULT_CELESTIAL_TARGETS.copy()

    requested = data.get("celestial")
    if not requested:
        return DEFAULT_CELESTIAL_TARGETS.copy()

    normalized: List[Dict[str, Any]] = []

    for item in requested:
        if isinstance(item, str):
            command = item.strip()
            if command:
                normalized.append(
                    {
                        "target_type": "mission",
                        "target_key": _target_key_from_parts("mission", command=command),
                        "command": command,
                        "name": command,
                    }
                )
            continue

        if isinstance(item, dict):
            color = item.get("color")
            target_type = (
                str(item.get("target_type") or item.get("targetType") or "mission").strip().lower()
            )

            if target_type == "body":
                body_id = (
                    str(
                        item.get("body_id")
                        or item.get("bodyId")
                        or item.get("id")
                        or item.get("target")
                        or ""
                    )
                    .strip()
                    .lower()
                )
                if not body_id:
                    continue
                name = str(item.get("name") or body_id).strip()
                normalized.append(
                    {
                        "target_type": "body",
                        "target_key": _target_key_from_parts("body", body_id=body_id),
                        "body_id": body_id,
                        "name": name,
                        "color": color,
                    }
                )
                continue

            command = str(item.get("command") or item.get("id") or item.get("target") or "").strip()
            if not command:
                continue
            name = str(item.get("name") or command).strip()
            normalized.append(
                {
                    "target_type": "mission",
                    "target_key": _target_key_from_parts("mission", command=command),
                    "command": command,
                    "name": name,
                    "color": color,
                }
            )

    return normalized


def _parse_projection_options(data: Optional[Dict[str, Any]]) -> Tuple[int, int, int]:
    if not data:
        return 24, 24, 60

    def parse_int(name: str, default: int, low: int, high: int) -> int:
        try:
            value = int(data.get(name, default))
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    past_hours = parse_int("past_hours", 24, 1, 24 * 365)
    future_hours = parse_int("future_hours", 24, 1, 24 * 365)
    step_minutes = parse_int("step_minutes", 60, 5, 24 * 60)
    adaptive_step_minutes = _compute_adaptive_step_minutes(
        past_hours=past_hours,
        future_hours=future_hours,
        requested_step_minutes=step_minutes,
        max_samples=MAX_SAMPLES_PER_TARGET,
    )
    return past_hours, future_hours, adaptive_step_minutes


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

    # Increase minimum resolution progressively as window span grows.
    if span_hours <= 72:
        min_step_for_span = 30
    elif span_hours <= 14 * 24:
        min_step_for_span = 60
    elif span_hours <= 60 * 24:
        min_step_for_span = 180
    elif span_hours <= 180 * 24:
        min_step_for_span = 360
    else:
        min_step_for_span = 720

    effective_step = max(int(requested_step_minutes), min_step_for_span)

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


def _is_no_ephemeris_error(error: Exception) -> bool:
    return NO_EPHEMERIS_ERROR_FRAGMENT in str(error)


def _iter_projection_fallbacks(
    past_hours: int,
    future_hours: int,
    step_minutes: int,
) -> List[Tuple[int, int, int]]:
    fallbacks: List[Tuple[int, int, int]] = []
    seen: set[Tuple[int, int, int]] = set()

    # Some Horizons targets fail for very wide windows; progressively reduce span.
    for cap_hours in (24 * 14, 24 * 7, 72, 24):
        reduced_past = min(int(past_hours), cap_hours)
        reduced_future = min(int(future_hours), cap_hours)
        if reduced_past == int(past_hours) and reduced_future == int(future_hours):
            continue

        reduced_step = _compute_adaptive_step_minutes(
            past_hours=reduced_past,
            future_hours=reduced_future,
            requested_step_minutes=int(step_minutes),
            max_samples=MAX_SAMPLES_PER_TARGET,
        )
        candidate = (reduced_past, reduced_future, reduced_step)
        if candidate in seen:
            continue
        seen.add(candidate)
        fallbacks.append(candidate)

    return fallbacks


def _bucket_epoch(epoch: datetime, bucket_seconds: int) -> datetime:
    utc_epoch = epoch.astimezone(timezone.utc)
    timestamp = int(utc_epoch.timestamp())
    bucketed = timestamp - (timestamp % max(1, int(bucket_seconds)))
    return datetime.fromtimestamp(bucketed, tz=timezone.utc)


def _extract_earth_position_xyz_au(planets: List[Dict[str, Any]]) -> Optional[List[float]]:
    for body in planets:
        if str(body.get("id") or "").lower() == "earth":
            position = body.get("position_xyz_au")
            if isinstance(position, list) and len(position) >= 3:
                try:
                    return [float(position[0]), float(position[1]), float(position[2])]
                except (TypeError, ValueError):
                    return None
    return None


async def _load_observer_location() -> Optional[Dict[str, Any]]:
    """Load the first configured ground-station location for observer sky coordinates."""
    async with AsyncSessionLocal() as dbsession:
        result = await crud_locations.fetch_all_locations(dbsession)

    rows_obj = result.get("data") if isinstance(result, dict) else None
    rows = rows_obj if isinstance(rows_obj, list) else []
    if not rows:
        return None

    first = rows[0]
    try:
        lat = float(first.get("lat"))
        lon = float(first.get("lon"))
        alt_m = float(first.get("alt") or 0.0)
    except (TypeError, ValueError):
        return None

    return {
        "id": first.get("id"),
        "name": first.get("name"),
        "lat": lat,
        "lon": lon,
        "alt_m": alt_m,
    }


def _attach_observer_view_local(
    row: Dict[str, Any],
    epoch: datetime,
    observer_location: Optional[Dict[str, Any]],
    earth_position_xyz_au: Optional[List[float]],
    logger: Any,
) -> None:
    """Attach observer-centric sky position and visibility metadata using local math."""
    if not observer_location or not earth_position_xyz_au:
        row["sky_position"] = None
        row["visibility"] = {
            "above_horizon": None,
            "visible": None,
            "horizon_threshold_deg": 0.0,
        }
        return

    target_position = row.get("position_xyz_au")
    if not isinstance(target_position, list) or len(target_position) < 3:
        row["sky_position"] = None
        row["visibility"] = {
            "above_horizon": None,
            "visible": None,
            "horizon_threshold_deg": 0.0,
            "error": "Missing target position vector",
        }
        return

    try:
        observer_view = compute_observer_sky_position(
            target_heliocentric_xyz_au=[
                float(target_position[0]),
                float(target_position[1]),
                float(target_position[2]),
            ],
            earth_heliocentric_xyz_au=earth_position_xyz_au,
            epoch=epoch,
            observer_lat_deg=float(observer_location["lat"]),
            observer_lon_deg=float(observer_location["lon"]),
        )
        row["sky_position"] = observer_view.get("sky_position")
        row["visibility"] = observer_view.get("visibility")
    except Exception as exc:
        logger.warning(f"Local observer math failed for celestial '{row.get('command')}': {exc}")
        row["sky_position"] = None
        row["visibility"] = {
            "above_horizon": None,
            "visible": None,
            "horizon_threshold_deg": 0.0,
            "error": str(exc),
        }


async def _load_vectors_from_db(
    command: str,
    epoch_bucket_utc: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    valid_only: bool = True,
) -> Optional[Dict[str, Any]]:
    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.fetch_celestial_vectors_cache_entry(
            dbsession,
            command=command,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            valid_only=valid_only,
            as_of=datetime.now(timezone.utc),
        )
    if not result.get("success"):
        return None
    row = result.get("data")
    return row if isinstance(row, dict) else None


async def _store_vectors_in_db(
    command: str,
    epoch_bucket_utc: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    payload: Dict[str, Any],
    source: str,
    error: Optional[str] = None,
) -> None:
    async with AsyncSessionLocal() as dbsession:
        await crud_celestial_vectors.upsert_celestial_vectors_cache_entry(
            dbsession,
            data={
                "command": command,
                "epoch_bucket_utc": epoch_bucket_utc,
                "past_hours": past_hours,
                "future_hours": future_hours,
                "step_minutes": step_minutes,
                "payload": payload,
                "source": source,
                "error": error,
                "fetched_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=VECTOR_DB_TTL_SECONDS),
            },
        )


async def _get_vectors_snapshot(
    command: str,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    force_refresh: bool,
    logger: Any,
) -> Dict[str, Any]:
    epoch_bucket_utc = _bucket_epoch(epoch, VECTOR_EPOCH_BUCKET_MINUTES * 60)

    if not force_refresh:
        cached = await _load_vectors_from_db(
            command=command,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            valid_only=True,
        )
        if cached and isinstance(cached.get("payload"), dict):
            return {
                "payload": dict(cached["payload"]),
                "cache": "db-hit",
                "stale": False,
                "error": None,
            }

    try:
        fetched = await asyncio.to_thread(
            fetch_celestial_vectors,
            command,
            epoch,
            past_hours,
            future_hours,
            step_minutes,
        )
        await _store_vectors_in_db(
            command=command,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            payload=fetched,
            source="horizons",
            error=None,
        )
        return {"payload": fetched, "cache": "db-miss", "stale": False, "error": None}
    except Exception as exc:
        fetch_error: Exception = exc

        if _is_no_ephemeris_error(exc) and (past_hours + future_hours) > 72:
            for reduced_past, reduced_future, reduced_step in _iter_projection_fallbacks(
                past_hours=past_hours,
                future_hours=future_hours,
                step_minutes=step_minutes,
            ):
                try:
                    fetched = await asyncio.to_thread(
                        fetch_celestial_vectors,
                        command,
                        epoch,
                        reduced_past,
                        reduced_future,
                        reduced_step,
                    )
                    fetched["fallback_projection"] = {
                        "requested": {
                            "past_hours": past_hours,
                            "future_hours": future_hours,
                            "step_minutes": step_minutes,
                        },
                        "used": {
                            "past_hours": reduced_past,
                            "future_hours": reduced_future,
                            "step_minutes": reduced_step,
                        },
                    }
                    await _store_vectors_in_db(
                        command=command,
                        epoch_bucket_utc=epoch_bucket_utc,
                        past_hours=past_hours,
                        future_hours=future_hours,
                        step_minutes=step_minutes,
                        payload=fetched,
                        source="horizons",
                        error=None,
                    )
                    logger.info(
                        "Horizons fallback projection succeeded for celestial "
                        f"'{command}' (requested p={past_hours}h f={future_hours}h s={step_minutes}m, "
                        f"used p={reduced_past}h f={reduced_future}h s={reduced_step}m)"
                    )
                    return {"payload": fetched, "cache": "db-miss", "stale": False, "error": None}
                except Exception as retry_exc:
                    fetch_error = retry_exc

        logger.warning(f"Horizons fetch failed for celestial '{command}': {fetch_error}")
        fallback = await _load_vectors_from_db(
            command=command,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            valid_only=False,
        )
        if fallback and isinstance(fallback.get("payload"), dict):
            return {
                "payload": dict(fallback["payload"]),
                "cache": "db-stale",
                "stale": True,
                "error": str(fetch_error),
            }
        return {"payload": None, "cache": "miss", "stale": True, "error": str(fetch_error)}


async def _fetch_celestial_with_cache(
    targets: List[Dict[str, Any]],
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    observer_location: Optional[Dict[str, Any]],
    earth_position_xyz_au: Optional[List[float]],
    body_snapshot_by_id: Dict[str, Dict[str, Any]],
    force_refresh: bool,
    logger,
    per_row_callback: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    now_monotonic = time.monotonic()
    total_targets = len(targets)

    for index, target in enumerate(targets):
        target_type = str(target.get("target_type") or "mission").strip().lower()
        target_key = str(target.get("target_key") or "").strip()
        name = target["name"]
        color = target.get("color")

        if target_type == "body":
            body_id = str(target.get("body_id") or "").strip().lower()
            body_row = body_snapshot_by_id.get(body_id)
            if body_row:
                body_payload = dict(body_row)
                body_payload["target_type"] = "body"
                body_payload["target_key"] = target_key or _target_key_from_parts(
                    "body", body_id=body_id
                )
                body_payload["body_id"] = body_id
                body_payload["command"] = body_id
                body_payload["name"] = name or body_payload.get("name") or body_id
                body_payload["color"] = color
                body_payload["source"] = "offline-solar-system"
                body_payload["stale"] = False
                body_payload["cache"] = "offline"
                _attach_observer_view_local(
                    row=body_payload,
                    epoch=epoch,
                    observer_location=observer_location,
                    earth_position_xyz_au=earth_position_xyz_au,
                    logger=logger,
                )
                rows.append(body_payload)
                if per_row_callback:
                    await per_row_callback(dict(body_payload), index + 1, total_targets)
                continue

            body_error = {
                "target_type": "body",
                "target_key": target_key or _target_key_from_parts("body", body_id=body_id),
                "body_id": body_id,
                "command": body_id,
                "name": name,
                "color": color,
                "source": "offline-solar-system",
                "stale": True,
                "cache": "offline-miss",
                "error": f"Body '{body_id}' not present in offline snapshot",
                "sky_position": None,
                "visibility": {
                    "above_horizon": None,
                    "visible": None,
                    "horizon_threshold_deg": 0.0,
                },
            }
            rows.append(body_error)
            if per_row_callback:
                await per_row_callback(dict(body_error), index + 1, total_targets)
            continue

        command = str(target.get("command") or "").strip()
        if not command:
            continue
        observer_cache_key = "no-observer"
        if observer_location:
            observer_cache_key = (
                f"{observer_location.get('id')}"
                f"|{observer_location.get('lat')}"
                f"|{observer_location.get('lon')}"
                f"|{observer_location.get('alt_m')}"
            )
        epoch_cache_key = _bucket_epoch(epoch, COMPUTED_EPOCH_BUCKET_SECONDS).isoformat()
        cache_key = (
            f"mission:{command}|{epoch_cache_key}|p{past_hours}|f{future_hours}|s{step_minutes}"
            f"|obs:{observer_cache_key}"
        )

        use_cached = False
        cached_entry: Optional[CacheEntry] = None

        with _computed_cache_lock:
            cached_entry = _computed_cache.get(cache_key)
            if (
                cached_entry
                and not force_refresh
                and now_monotonic - cached_entry.fetched_at_monotonic <= CACHE_TTL_SECONDS
            ):
                use_cached = True

        if use_cached and cached_entry:
            cached_payload = dict(cached_entry.payload)
            cached_payload["target_type"] = "mission"
            cached_payload["target_key"] = target_key or _target_key_from_parts(
                "mission", command=command
            )
            cached_payload["name"] = name
            cached_payload["color"] = color
            cached_payload["stale"] = False
            cached_payload["cache"] = "computed-hit"
            rows.append(cached_payload)
            if per_row_callback:
                await per_row_callback(dict(cached_payload), index + 1, total_targets)
            continue

        snapshot = await _get_vectors_snapshot(
            command=command,
            epoch=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            force_refresh=force_refresh,
            logger=logger,
        )

        payload = snapshot.get("payload")
        if isinstance(payload, dict):
            row_payload = dict(payload)
            row_payload["target_type"] = "mission"
            row_payload["target_key"] = target_key or _target_key_from_parts(
                "mission", command=command
            )
            row_payload["name"] = name
            row_payload["color"] = color
            row_payload["stale"] = bool(snapshot.get("stale"))
            row_payload["cache"] = snapshot.get("cache")
            if snapshot.get("error"):
                row_payload["error"] = snapshot.get("error")
            _attach_observer_view_local(
                row=row_payload,
                epoch=epoch,
                observer_location=observer_location,
                earth_position_xyz_au=earth_position_xyz_au,
                logger=logger,
            )
            with _computed_cache_lock:
                _computed_cache[cache_key] = CacheEntry(
                    payload=dict(row_payload),
                    fetched_at_monotonic=time.monotonic(),
                )
            rows.append(row_payload)
            if per_row_callback:
                await per_row_callback(dict(row_payload), index + 1, total_targets)
            continue

        error_row = {
            "target_type": "mission",
            "target_key": target_key or _target_key_from_parts("mission", command=command),
            "name": name,
            "command": command,
            "color": color,
            "source": "horizons",
            "stale": True,
            "cache": snapshot.get("cache"),
            "error": snapshot.get("error") or "No data returned",
            "sky_position": None,
            "visibility": {
                "above_horizon": None,
                "visible": None,
                "horizon_threshold_deg": 0.0,
            },
        }
        rows.append(error_row)
        if per_row_callback:
            await per_row_callback(dict(error_row), index + 1, total_targets)

    return rows


async def build_celestial_scene(
    data: Optional[Dict[str, Any]],
    logger,
    force_refresh: bool = False,
    per_row_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a scene payload for UI rendering and backend sharing."""
    epoch = _parse_epoch(data)
    targets = _normalize_targets(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    observer_location = await _load_observer_location()

    solar_meta, planets = compute_solar_system_snapshot(epoch)
    earth_position_xyz_au = _extract_earth_position_xyz_au(planets)
    body_snapshot_by_id = {
        str(body.get("id") or "").strip().lower(): dict(body) for body in planets if body.get("id")
    }
    asteroid_zones, asteroid_resonance_gaps, asteroid_meta = get_static_asteroid_zones()
    celestial = await _fetch_celestial_with_cache(
        targets,
        epoch,
        past_hours,
        future_hours,
        step_minutes,
        observer_location,
        earth_position_xyz_au,
        body_snapshot_by_id,
        force_refresh,
        logger,
        per_row_callback,
    )

    return {
        "success": True,
        "data": {
            "timestamp_utc": epoch.isoformat(),
            "frame": "heliocentric-ecliptic",
            "center": "sun",
            "units": {
                "position": "au",
                "velocity": "au/day",
            },
            "planets": planets,
            "celestial": celestial,
            "asteroid_zones": asteroid_zones,
            "asteroid_resonance_gaps": asteroid_resonance_gaps,
            "meta": {
                "solar_system": solar_meta,
                "celestial_source": "horizons",
                "asteroid_zones": asteroid_meta,
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "vector_db_ttl_seconds": VECTOR_DB_TTL_SECONDS,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
                "observer_location": observer_location,
                "visibility_definition": "visible == elevation_deg > 0",
            },
        },
    }


async def build_solar_system_scene(
    data: Optional[Dict[str, Any]],
    logger,
) -> Dict[str, Any]:
    """Build only the offline solar system portion for fast initial render."""
    epoch = _parse_epoch(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    solar_meta, planets = compute_solar_system_snapshot(epoch)
    asteroid_zones, asteroid_resonance_gaps, asteroid_meta = get_static_asteroid_zones()

    return {
        "success": True,
        "data": {
            "timestamp_utc": epoch.isoformat(),
            "frame": "heliocentric-ecliptic",
            "center": "sun",
            "units": {
                "position": "au",
                "velocity": "au/day",
            },
            "planets": planets,
            "asteroid_zones": asteroid_zones,
            "asteroid_resonance_gaps": asteroid_resonance_gaps,
            "meta": {
                "solar_system": solar_meta,
                "asteroid_zones": asteroid_meta,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
            },
        },
    }


async def build_celestial_tracks(
    data: Optional[Dict[str, Any]],
    logger,
    force_refresh: bool = False,
    per_row_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build only Horizons-backed tracked celestial objects."""
    epoch = _parse_epoch(data)
    targets = _normalize_targets(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    observer_location = await _load_observer_location()
    _, planets = compute_solar_system_snapshot(epoch)
    earth_position_xyz_au = _extract_earth_position_xyz_au(planets)
    body_snapshot_by_id = {
        str(body.get("id") or "").strip().lower(): dict(body) for body in planets if body.get("id")
    }
    celestial = await _fetch_celestial_with_cache(
        targets,
        epoch,
        past_hours,
        future_hours,
        step_minutes,
        observer_location,
        earth_position_xyz_au,
        body_snapshot_by_id,
        force_refresh,
        logger,
        per_row_callback,
    )

    return {
        "success": True,
        "data": {
            "timestamp_utc": epoch.isoformat(),
            "frame": "heliocentric-ecliptic",
            "center": "sun",
            "units": {
                "position": "au",
                "velocity": "au/day",
            },
            "celestial": celestial,
            "meta": {
                "celestial_source": "horizons",
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "vector_db_ttl_seconds": VECTOR_DB_TTL_SECONDS,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
                "observer_location": observer_location,
                "visibility_definition": "visible == elevation_deg > 0",
            },
        },
    }
