# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Persistence, provider fetches, and cache policy for celestial vectors."""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import crud.celestialvectors as crud_celestial_vectors
from celestial.horizons import HorizonsUnavailableError, fetch_celestial_vectors
from celestial.settings import (
    DEFAULT_CENTER,
    DEFAULT_FRAME,
    MAX_SAMPLES_PER_TARGET,
    VECTOR_DB_TTL_SECONDS,
    VECTOR_EPOCH_BUCKET_MINUTES,
    VECTOR_FETCH_PADDING_HOURS,
    _bucket_epoch,
    vector_cache_policy,
)
from celestial.targets import _target_key_from_parts
from celestial.trajectory import (
    _payload_covers_current_epoch,
    _payload_covers_projection_window,
    _refresh_payload_dynamics_at_epoch,
    _snapshot_projection_is_compatible,
    _trim_payload_to_projection_window,
)
from common.targetkey import normalize_target_key
from db import AsyncSessionLocal

# Share identical provider work across concurrent scene requests. Callers still
# receive independent payload copies because projection trimming mutates them.
_VECTOR_FETCH_TASKS: Dict[Tuple[Any, ...], asyncio.Task] = {}


async def _load_vectors_from_db(
    target_key: str,
    epoch_bucket_utc: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    frame: str = DEFAULT_FRAME,
    center: str = DEFAULT_CENTER,
    valid_only: bool = True,
) -> Optional[Dict[str, Any]]:
    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.fetch_celestial_vector_snapshot(
            dbsession,
            target_id=target_key,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            frame=frame,
            center=center,
            valid_only=valid_only,
            as_of=datetime.now(timezone.utc),
        )
    if not result.get("success"):
        return None
    row = result.get("data")
    return row if isinstance(row, dict) else None


async def _load_latest_vectors_from_db(
    target_key: str,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    frame: str = DEFAULT_FRAME,
    center: str = DEFAULT_CENTER,
    valid_only: bool = True,
) -> Optional[Dict[str, Any]]:
    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.fetch_latest_celestial_vector_snapshot(
            dbsession,
            target_id=target_key,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            frame=frame,
            center=center,
            valid_only=valid_only,
            as_of=datetime.now(timezone.utc),
        )
    if not result.get("success"):
        return None
    row = result.get("data")
    return row if isinstance(row, dict) else None


async def _load_latest_vectors_for_target_from_db(
    target_key: str,
    valid_only: bool = True,
    past_hours: Optional[int] = None,
    future_hours: Optional[int] = None,
    maximum_step_minutes: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Load the freshest snapshot regardless of the requested projection window."""
    if (
        valid_only
        and past_hours is not None
        and future_hours is not None
        and maximum_step_minutes is not None
    ):
        # Select a covering row in SQL. The newest row may be an older narrow
        # derived snapshot and must not hide a reusable provider envelope.
        return await _load_covering_vectors_for_target_from_db(
            target_key=target_key,
            past_hours=past_hours,
            future_hours=future_hours,
            maximum_step_minutes=maximum_step_minutes,
        )
    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.fetch_latest_celestial_vector_snapshot_for_target(
            dbsession,
            target_id=target_key,
            valid_only=valid_only,
            as_of=datetime.now(timezone.utc),
        )
    if not result.get("success"):
        return None
    row = result.get("data")
    return row if isinstance(row, dict) else None


async def _load_covering_vectors_for_target_from_db(
    target_key: str,
    past_hours: int,
    future_hours: int,
    maximum_step_minutes: int,
) -> Optional[Dict[str, Any]]:
    """Load a broad fresh snapshot suitable for a complete observer window."""
    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.fetch_covering_celestial_vector_snapshot_for_target(
            dbsession,
            target_id=target_key,
            past_hours=past_hours,
            future_hours=future_hours,
            maximum_step_minutes=maximum_step_minutes,
            valid_only=True,
            as_of=datetime.now(timezone.utc),
        )
    if not result.get("success"):
        return None
    row = result.get("data")
    return row if isinstance(row, dict) else None


async def _store_vectors_in_db(
    target_key: str,
    epoch_bucket_utc: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    payload: Dict[str, Any],
    source: str,
    frame: str = DEFAULT_FRAME,
    center: str = DEFAULT_CENTER,
    error: Optional[str] = None,
    ttl_seconds: int = VECTOR_DB_TTL_SECONDS,
) -> None:
    position_xyz_au = payload.get("position_xyz_au")
    velocity_xyz_au_per_day = payload.get("velocity_xyz_au_per_day")
    orbit_samples_xyz_au = payload.get("orbit_samples_xyz_au")
    orbit_sample_times_utc = payload.get("orbit_sample_times_utc")
    async with AsyncSessionLocal() as dbsession:
        await crud_celestial_vectors.upsert_celestial_vector_snapshot(
            dbsession,
            data={
                "target_id": target_key,
                "epoch_bucket_utc": epoch_bucket_utc,
                "past_hours": past_hours,
                "future_hours": future_hours,
                "step_minutes": step_minutes,
                "frame": frame,
                "center": center,
                "position_xyz_au": position_xyz_au,
                "velocity_xyz_au_per_day": velocity_xyz_au_per_day,
                "orbit_samples_xyz_au": orbit_samples_xyz_au,
                "orbit_sample_times_utc": orbit_sample_times_utc,
                "horizons_signature": payload.get("horizons_signature"),
                "source": source,
                "error": error,
                "fetched_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc)
                + timedelta(seconds=max(60, int(ttl_seconds))),
            },
        )


async def _fetch_vectors_singleflight(
    *,
    command: str,
    target_key: str,
    epoch: datetime,
    epoch_bucket_utc: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    retry_horizons: bool,
) -> Dict[str, Any]:
    """Share an identical in-flight Horizons request across scene callers."""
    key = (
        target_key,
        epoch_bucket_utc.isoformat(),
        int(past_hours),
        int(future_hours),
        int(step_minutes),
        bool(retry_horizons),
    )
    running_loop = asyncio.get_running_loop()
    task = _VECTOR_FETCH_TASKS.get(key)
    if task is not None and task.get_loop() is not running_loop:
        # Test runners and application reloads may replace the event loop.
        # Never retain a task owned by a closed or unrelated loop.
        _VECTOR_FETCH_TASKS.pop(key, None)
        task = None

    if task is None:
        task = asyncio.create_task(
            asyncio.to_thread(
                fetch_celestial_vectors,
                command,
                epoch,
                past_hours,
                future_hours,
                step_minutes,
                force_probe=retry_horizons,
            )
        )
        _VECTOR_FETCH_TASKS[key] = task

        def _discard_finished_task(finished_task: asyncio.Task) -> None:
            if _VECTOR_FETCH_TASKS.get(key) is finished_task:
                _VECTOR_FETCH_TASKS.pop(key, None)

        task.add_done_callback(_discard_finished_task)

    # A caller cancellation must not cancel provider work awaited by another
    # browser. Each caller gets a deep copy because trajectory trimming mutates it.
    return copy.deepcopy(await asyncio.shield(task))


async def _get_vectors_snapshot(
    command: str,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    observer_location: Optional[Dict[str, Any]],
    force_refresh: bool,
    logger: Any,
    allow_network_fetch: bool = True,
    target_key: str = "",
    retry_horizons: bool = False,
    refresh_reserve_hours: int = 0,
) -> Dict[str, Any]:
    normalized_target_key = normalize_target_key(target_key) or ""
    if not normalized_target_key:
        normalized_target_key = _target_key_from_parts("mission", command=command)
    if not normalized_target_key:
        return {
            "payload": None,
            "cache": "miss",
            "stale": True,
            "error": "Target key is required",
        }

    cache_policy = vector_cache_policy(normalized_target_key)
    maximum_span_hours = max(
        1,
        int((MAX_SAMPLES_PER_TARGET - 1) * int(step_minutes) / 60),
    )
    effective_refresh_reserve_hours = min(
        max(0, int(refresh_reserve_hours)),
        max(0, maximum_span_hours - int(past_hours) - int(future_hours)),
    )

    epoch_bucket_utc = _bucket_epoch(epoch, VECTOR_EPOCH_BUCKET_MINUTES * 60)
    if not force_refresh:
        cached = await _load_vectors_from_db(
            target_key=normalized_target_key,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            frame=DEFAULT_FRAME,
            center=DEFAULT_CENTER,
            valid_only=True,
        )
        if cached and isinstance(cached.get("payload"), dict):
            payload = dict(cached["payload"])
            projection_covered = _payload_covers_projection_window(
                payload,
                epoch=epoch,
                past_hours=past_hours,
                future_hours=future_hours + effective_refresh_reserve_hours,
            )
            current_position_usable = _payload_covers_current_epoch(payload, epoch=epoch)
            if projection_covered or (not allow_network_fetch and current_position_usable):
                _refresh_payload_dynamics_at_epoch(
                    payload=payload,
                    epoch=epoch,
                    past_hours=past_hours,
                    future_hours=future_hours,
                )
                if projection_covered:
                    _trim_payload_to_projection_window(
                        payload=payload,
                        epoch=epoch,
                        past_hours=past_hours,
                        future_hours=future_hours,
                    )
                return {
                    "payload": payload,
                    "cache": "db-hit" if projection_covered else "db-hit-partial",
                    "stale": False,
                    "error": None,
                    "current_position_usable": current_position_usable,
                    # Cache-only broadcasts keep the remaining portion of this
                    # target's own projection. Pass curves then end at its real
                    # cached boundary instead of inheriting another target's span.
                    "calculation_usable": True,
                }
        # The scene loop runs more frequently than Horizons fetches. If the
        # exact epoch bucket is missing, use the newest cached snapshot for the
        # same projection and recompute the current vector from its samples.
        latest_cached = await _load_latest_vectors_from_db(
            target_key=normalized_target_key,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            frame=DEFAULT_FRAME,
            center=DEFAULT_CENTER,
            valid_only=True,
        )
        if latest_cached and isinstance(latest_cached.get("payload"), dict):
            payload = dict(latest_cached["payload"])
            projection_covered = _payload_covers_projection_window(
                payload,
                epoch=epoch,
                past_hours=past_hours,
                future_hours=future_hours + effective_refresh_reserve_hours,
            )
            current_position_usable = _payload_covers_current_epoch(payload, epoch=epoch)
            if projection_covered or (not allow_network_fetch and current_position_usable):
                _refresh_payload_dynamics_at_epoch(
                    payload=payload,
                    epoch=epoch,
                    past_hours=past_hours,
                    future_hours=future_hours,
                )
                if projection_covered:
                    _trim_payload_to_projection_window(
                        payload=payload,
                        epoch=epoch,
                        past_hours=past_hours,
                        future_hours=future_hours,
                    )
                return {
                    "payload": payload,
                    "cache": ("db-latest-hit" if projection_covered else "db-latest-hit-partial"),
                    "stale": False,
                    "error": None,
                    "current_position_usable": current_position_usable,
                    "calculation_usable": True,
                }
        # A differently keyed snapshot is reusable for a trajectory only when
        # its window is at least as wide and its samples are at least as dense.
        # A shorter snapshot may still provide the live marker, but it must not
        # freeze at an endpoint while another body's trajectory continues.
        compatible_cached = await _load_latest_vectors_for_target_from_db(
            target_key=normalized_target_key,
            valid_only=True,
            past_hours=past_hours,
            future_hours=future_hours + effective_refresh_reserve_hours,
            maximum_step_minutes=step_minutes,
        )
        if compatible_cached and isinstance(compatible_cached.get("payload"), dict):
            payload = dict(compatible_cached["payload"])
            projection_is_compatible = _snapshot_projection_is_compatible(
                compatible_cached,
                past_hours=past_hours,
                future_hours=future_hours + effective_refresh_reserve_hours,
                step_minutes=step_minutes,
            ) and _payload_covers_projection_window(
                payload,
                epoch=epoch,
                past_hours=past_hours,
                future_hours=future_hours + effective_refresh_reserve_hours,
            )
            current_position_usable = _payload_covers_current_epoch(payload, epoch=epoch)
            if projection_is_compatible or (not allow_network_fetch and current_position_usable):
                _refresh_payload_dynamics_at_epoch(
                    payload=payload,
                    epoch=epoch,
                    past_hours=past_hours,
                    future_hours=future_hours,
                )
                if projection_is_compatible:
                    _trim_payload_to_projection_window(
                        payload=payload,
                        epoch=epoch,
                        past_hours=past_hours,
                        future_hours=future_hours,
                    )
                return {
                    "payload": payload,
                    "cache": (
                        "db-compatible-hit"
                        if projection_is_compatible
                        else "db-compatible-current-only"
                    ),
                    "stale": False,
                    "error": None,
                    "current_position_usable": current_position_usable,
                    "calculation_usable": projection_is_compatible,
                }

    if not allow_network_fetch:
        stale_cached = await _load_latest_vectors_from_db(
            target_key=normalized_target_key,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            frame=DEFAULT_FRAME,
            center=DEFAULT_CENTER,
            valid_only=False,
        )
        if stale_cached and isinstance(stale_cached.get("payload"), dict):
            payload = dict(stale_cached["payload"])
            _refresh_payload_dynamics_at_epoch(
                payload=payload,
                epoch=epoch,
                past_hours=past_hours,
                future_hours=future_hours,
            )
            return {
                "payload": payload,
                "cache": "db-stale-hit",
                "stale": True,
                "error": None,
                "current_position_usable": _payload_covers_current_epoch(
                    payload,
                    epoch=epoch,
                ),
                "calculation_usable": _payload_covers_projection_window(
                    payload,
                    epoch=epoch,
                    past_hours=past_hours,
                    future_hours=future_hours,
                ),
            }
        return {
            "payload": None,
            "cache": "cache-only-miss",
            "stale": True,
            "error": f"No cached vectors available for target '{normalized_target_key}'",
        }

    padded_past_hours = int(past_hours) + VECTOR_FETCH_PADDING_HOURS
    available_headroom_hours = max(
        0,
        maximum_span_hours - padded_past_hours - int(future_hours),
    )
    future_headroom_hours = min(
        int(cache_policy["future_headroom_hours"]),
        available_headroom_hours,
    )
    padded_future_hours = int(future_hours) + future_headroom_hours
    try:
        fetched = await _fetch_vectors_singleflight(
            command=command,
            target_key=normalized_target_key,
            epoch=epoch,
            epoch_bucket_utc=epoch_bucket_utc,
            past_hours=padded_past_hours,
            future_hours=padded_future_hours,
            step_minutes=step_minutes,
            retry_horizons=retry_horizons,
        )
    except Exception as exc:
        error_code = exc.reason if isinstance(exc, HorizonsUnavailableError) else "target_error"
        log = (
            getattr(logger, "debug", logger.warning)
            if isinstance(exc, HorizonsUnavailableError)
            else logger.warning
        )
        log(f"Horizons fetch failed for celestial '{command}': {exc}")

        # An expired Horizons snapshot is still preferable to dropping a target.
        # Its stale marker prevents the UI from presenting it as current data.
        stale_cached = await _load_latest_vectors_for_target_from_db(
            target_key=normalized_target_key,
            valid_only=False,
        )
        if stale_cached and isinstance(stale_cached.get("payload"), dict):
            payload = dict(stale_cached["payload"])
            _refresh_payload_dynamics_at_epoch(
                payload=payload,
                epoch=epoch,
                past_hours=past_hours,
                future_hours=future_hours,
            )
            return {
                "payload": payload,
                "cache": "db-stale-fallback",
                "stale": True,
                "error": str(exc),
                "error_code": error_code,
                "current_position_usable": _payload_covers_current_epoch(
                    payload,
                    epoch=epoch,
                ),
                "calculation_usable": _payload_covers_projection_window(
                    payload,
                    epoch=epoch,
                    past_hours=past_hours,
                    future_hours=future_hours,
                ),
            }
        return {
            "payload": None,
            "cache": "miss",
            "stale": True,
            "error": str(exc),
            "error_code": error_code,
        }

    await _store_vectors_in_db(
        target_key=normalized_target_key,
        epoch_bucket_utc=epoch_bucket_utc,
        # Persist the actual provider envelope. Later requests can reuse it for
        # narrower per-object projections without creating derived DB rows.
        past_hours=padded_past_hours,
        future_hours=padded_future_hours,
        step_minutes=step_minutes,
        payload=fetched,
        source="horizons",
        frame=DEFAULT_FRAME,
        center=DEFAULT_CENTER,
        error=None,
        ttl_seconds=int(cache_policy["ttl_seconds"]),
    )
    response_payload = copy.deepcopy(fetched)
    _trim_payload_to_projection_window(
        payload=response_payload,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    _refresh_payload_dynamics_at_epoch(
        payload=response_payload,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    return {
        "payload": response_payload,
        "cache": "db-miss",
        "stale": False,
        "error": None,
        "provider_fetched": True,
    }
