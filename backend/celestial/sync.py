# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Scheduled celestial-vector cache synchronization."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import crud.celestialvectors as crud_vectors
import crud.monitoredcelestial as crud_monitored
import crud.preferences as crud_preferences
from celestial.settings import (
    CELESTIAL_MAP_SETTINGS_NAME,
    SCHEDULED_SYNC_FUTURE_HOURS,
    SCHEDULED_SYNC_PAST_HOURS,
    SCHEDULED_SYNC_STEP_MINUTES,
    VECTOR_EXPIRED_RETENTION_DAYS,
    _parse_projection_options,
    _projection_payload_from_map_settings,
    vector_cache_policy,
)
from celestial.snapshots import _get_vectors_snapshot
from celestial.syncstate import (
    finish_celestial_sync,
    start_celestial_sync,
    update_celestial_sync_progress,
)
from celestial.targets import (
    _build_body_target_payload,
    _build_builtin_body_targets,
    _ensure_scene_targets_registered,
    _target_key_from_parts,
)
from db import AsyncSessionLocal

_scheduled_sync_lock = asyncio.Lock()


def _projection_covers(
    candidate: Tuple[int, int, int],
    required: Tuple[int, int, int],
) -> bool:
    """Return whether one cached trajectory can satisfy another projection."""
    candidate_past, candidate_future, candidate_step = candidate
    required_past, required_future, required_step = required
    return (
        candidate_past >= required_past
        and candidate_future >= required_future
        and candidate_step <= required_step
    )


def _build_earth_cache_projections(
    targets: List[Dict[str, Any]],
) -> List[Tuple[int, int, int]]:
    """Build the smallest active projection set that covers every target."""
    projections = {
        (
            int(target["past_hours"]),
            int(target["future_hours"]),
            int(target["step_minutes"]),
        )
        for target in targets
    }
    required = [
        projection
        for projection in projections
        if not any(
            candidate != projection and _projection_covers(candidate, projection)
            for candidate in projections
        )
    ]
    # Keep ordering deterministic for progress reporting and tests. Dense
    # projections come first, followed by broader windows at the same density.
    return sorted(
        required,
        key=lambda projection: (
            projection[2],
            -(projection[0] + projection[1]),
            -projection[0],
            -projection[1],
        ),
    )


async def _refresh_celestial_vector_snapshots_cache(
    logger: Any,
    *,
    progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Refresh Horizons vectors for monitored missions and always-in-scene bodies."""
    if _scheduled_sync_lock.locked():
        return {
            "success": False,
            "skipped": True,
            "error": "Scheduled celestial vectors sync already running",
        }

    async with _scheduled_sync_lock:
        payload = {
            "past_hours": SCHEDULED_SYNC_PAST_HOURS,
            "future_hours": SCHEDULED_SYNC_FUTURE_HOURS,
            "step_minutes": SCHEDULED_SYNC_STEP_MINUTES,
        }
        past_hours, future_hours, step_minutes = _parse_projection_options(payload)
        epoch = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as dbsession:
            monitored_result = await crud_monitored.fetch_monitored_celestial(
                dbsession,
                enabled_only=True,
            )
            map_settings_result = await crud_preferences.get_map_settings(
                dbsession,
                name=CELESTIAL_MAP_SETTINGS_NAME,
            )

        settings_row = map_settings_result.get("data") if map_settings_result.get("success") else {}
        settings_value = settings_row.get("value") if isinstance(settings_row, dict) else {}
        if isinstance(settings_value, dict):
            payload = _projection_payload_from_map_settings(settings_value)
            past_hours, future_hours, step_minutes = _parse_projection_options(payload)

        if not monitored_result.get("success"):
            return {
                "success": False,
                "error": monitored_result.get("error")
                or "Failed loading monitored celestial targets",
            }

        rows_obj = monitored_result.get("data")
        rows: List[Dict[str, Any]] = rows_obj if isinstance(rows_obj, list) else []
        monitored_targets: List[Dict[str, Any]] = []
        for row in rows:
            target_type = str(row.get("target_type") or "mission").strip().lower()
            target_projection = _parse_projection_options(
                {
                    "past_hours": row.get("projection_past_hours"),
                    "future_hours": row.get("projection_future_hours"),
                    "step_minutes": row.get("projection_step_minutes"),
                }
            )
            if target_type == "body":
                body_id = str(row.get("body_id") or "").strip().lower()
                body_target = _build_body_target_payload(
                    body_id=body_id,
                    name=str(row.get("display_name") or body_id).strip(),
                    target_key=_target_key_from_parts("body", body_id=body_id),
                )
                if body_target:
                    body_target.update(
                        {
                            "past_hours": target_projection[0],
                            "future_hours": target_projection[1],
                            "step_minutes": target_projection[2],
                        }
                    )
                    monitored_targets.append(body_target)
                continue
            command = str(row.get("command") or "").strip()
            if not command:
                continue
            monitored_targets.append(
                {
                    "target_type": "mission",
                    "target_key": _target_key_from_parts("mission", command=command),
                    "name": str(row.get("display_name") or command).strip() or command,
                    "command": command,
                    "horizons_command": command,
                    "always_in_scene": False,
                    "past_hours": target_projection[0],
                    "future_hours": target_projection[1],
                    "step_minutes": target_projection[2],
                }
            )

        builtin_targets = _build_builtin_body_targets()
        all_targets_by_projection: Dict[Tuple[str, int, int, int], Dict[str, Any]] = {}
        for target in builtin_targets + monitored_targets:
            target_key = str(target.get("target_key") or "").strip()
            if not target_key:
                continue
            target_past_hours, target_future_hours, target_step_minutes = (
                _parse_projection_options(target)
                if any(
                    target.get(name) is not None
                    for name in ("past_hours", "future_hours", "step_minutes")
                )
                else (past_hours, future_hours, step_minutes)
            )
            target["past_hours"] = target_past_hours
            target["future_hours"] = target_future_hours
            target["step_minutes"] = target_step_minutes
            projection_key = (
                target_key,
                target_past_hours,
                target_future_hours,
                target_step_minutes,
            )
            all_targets_by_projection[projection_key] = target

        normalized_targets = list(all_targets_by_projection.values())
        earth_cache_projections = _build_earth_cache_projections(normalized_targets)
        earth_target_key = _target_key_from_parts("body", body_id="earth")

        # Observer AZ/EL and pass calculations need an Earth trajectory matching
        # every active target window. Keep only non-dominated coverage profiles:
        # one broad, equally dense profile can serve all narrower projections.
        all_targets_by_projection = {
            key: target
            for key, target in all_targets_by_projection.items()
            if key[0] != earth_target_key
        }
        for earth_past, earth_future, earth_step in earth_cache_projections:
            earth_target = _build_body_target_payload(
                body_id="earth",
                name="Earth",
                target_key=earth_target_key,
            )
            if earth_target is None:
                continue
            earth_target.update(
                {
                    "always_in_scene": True,
                    "past_hours": earth_past,
                    "future_hours": earth_future,
                    "step_minutes": earth_step,
                }
            )
            all_targets_by_projection[(earth_target_key, earth_past, earth_future, earth_step)] = (
                earth_target
            )

        all_targets = list(all_targets_by_projection.values())
        if not all_targets:
            return {
                "success": True,
                "count": 0,
                "refreshed": 0,
                "provider_fetched": 0,
                "cache_reused": 0,
                "stale_fallback": 0,
                "failed": 0,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
            }

        # Registration is target metadata, so projection variants should not
        # produce duplicate upserts for the same canonical Earth target.
        registration_targets = {
            str(target.get("target_key") or "").strip(): target for target in all_targets
        }
        await _ensure_scene_targets_registered(list(registration_targets.values()), logger)

        refreshed = 0
        provider_fetched = 0
        cache_reused = 0
        stale_fallback = 0
        failed = 0
        errors: List[Dict[str, str]] = []

        async def report_progress(
            *,
            processed: int,
            target: Optional[Dict[str, Any]],
            phase: str,
            outcome: Optional[str] = None,
            error: Optional[str] = None,
        ) -> None:
            if progress_callback is None:
                return

            total = len(all_targets)
            target_key = str(target.get("target_key") or "") if target else None
            target_name = str(target.get("name") or target_key or "") if target else None
            payload = {
                "processed": processed,
                "total": total,
                "percent": (float(processed) / float(total) * 100.0) if total else 100.0,
                "refreshed": refreshed,
                "provider_fetched": provider_fetched,
                "cache_reused": cache_reused,
                "stale_fallback": stale_fallback,
                "failed": failed,
                "phase": phase,
                "outcome": outcome,
                "error": error,
                "current_target": (
                    {
                        "key": target_key,
                        "name": target_name,
                    }
                    if target
                    else None
                ),
            }
            try:
                await progress_callback(payload)
            except Exception as exc:
                # Progress delivery must never interrupt the cache refresh itself.
                logger.warning(f"Failed to report celestial cache refresh progress: {exc}")

        # Keep the scheduler job deterministic and easy to observe in logs.
        await report_progress(processed=0, target=None, phase="starting")
        for index, target in enumerate(all_targets):
            target_key = str(target.get("target_key") or "").strip()
            command = str(target.get("horizons_command") or target.get("command") or "").strip()
            await report_progress(processed=index, target=target, phase="processing")
            if not target_key or not command:
                failed += 1
                error = "Missing Horizons command"
                errors.append(
                    {
                        "target_key": target_key or "unknown",
                        "target_name": str(target.get("name") or target_key or "Unknown"),
                        "error_code": "invalid_target",
                        "error": error,
                    }
                )
                await report_progress(
                    processed=index + 1,
                    target=target,
                    phase="processed",
                    outcome="failed",
                    error=error,
                )
                continue
            snapshot = await _get_vectors_snapshot(
                target_key=target_key,
                command=command,
                epoch=epoch,
                past_hours=int(target["past_hours"]),
                future_hours=int(target["future_hours"]),
                step_minutes=int(target["step_minutes"]),
                observer_location=None,
                force_refresh=False,
                logger=logger,
                allow_network_fetch=True,
                refresh_reserve_hours=vector_cache_policy(target_key)["refresh_reserve_hours"],
            )
            if isinstance(snapshot.get("payload"), dict):
                cache_result = str(snapshot.get("cache") or "")
                if snapshot.get("provider_fetched") or not cache_result:
                    provider_fetched += 1
                    refreshed += 1
                    outcome = "provider_fetched"
                elif cache_result == "db-stale-fallback":
                    stale_fallback += 1
                    outcome = "stale_fallback"
                else:
                    cache_reused += 1
                    outcome = "cache_reused"
                await report_progress(
                    processed=index + 1,
                    target=target,
                    phase="processed",
                    outcome=outcome,
                )
                continue
            failed += 1
            error = str(snapshot.get("error") or "Unknown error")
            errors.append(
                {
                    "target_key": target_key,
                    "target_name": str(target.get("name") or target_key),
                    "error_code": str(snapshot.get("error_code") or "target_error"),
                    "error": error,
                }
            )
            await report_progress(
                processed=index + 1,
                target=target,
                phase="processed",
                outcome="failed",
                error=error,
            )

        try:
            async with AsyncSessionLocal() as dbsession:
                prune_result = await crud_vectors.prune_expired_celestial_vector_snapshots(
                    dbsession,
                    expired_before=epoch - timedelta(days=VECTOR_EXPIRED_RETENTION_DAYS),
                )
        except Exception as exc:
            # Retention is housekeeping and must not change a successful sync
            # into a provider failure.
            prune_result = {"success": False, "error": str(exc)}
        pruned_snapshots = int((prune_result.get("data") or {}).get("deleted_count") or 0)
        if not prune_result.get("success"):
            logger.warning(
                f"Failed to prune expired celestial snapshots: {prune_result.get('error')}"
            )

        return {
            "success": failed == 0,
            "count": len(all_targets),
            "refreshed": refreshed,
            "provider_fetched": provider_fetched,
            "cache_reused": cache_reused,
            "stale_fallback": stale_fallback,
            "pruned_snapshots": pruned_snapshots,
            "failed": failed,
            "mission_count": sum(
                1 for target in monitored_targets if target.get("target_type") == "mission"
            ),
            "monitored_count": len(monitored_targets),
            "always_in_scene_count": len(builtin_targets),
            "earth_projection_count": len(earth_cache_projections),
            "errors": errors,
            "projection": {
                "past_hours": past_hours,
                "future_hours": future_hours,
                "step_minutes": step_minutes,
            },
            "cache_policy": {
                "body": vector_cache_policy("body:example"),
                "mission": vector_cache_policy("mission:example"),
                "expired_retention_days": VECTOR_EXPIRED_RETENTION_DAYS,
            },
        }


async def refresh_celestial_vector_snapshots_cache(
    logger: Any,
    *,
    progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    trigger: str = "manual",
) -> Dict[str, Any]:
    """Run a whole cache sync while maintaining its shared persistent state."""
    # A second caller must not replace the active run's state with a skipped result.
    if _scheduled_sync_lock.locked():
        return {
            "success": False,
            "skipped": True,
            "error": "Scheduled celestial vectors sync already running",
        }

    start_celestial_sync(trigger)

    async def track_progress(progress: Dict[str, Any]) -> None:
        update_celestial_sync_progress(progress)
        if progress_callback is not None:
            await progress_callback(progress)

    try:
        result = await _refresh_celestial_vector_snapshots_cache(
            logger,
            progress_callback=track_progress,
        )
    except Exception as exc:
        await finish_celestial_sync(
            {
                "success": False,
                "error": str(exc),
                "errors": [{"error": str(exc)}],
            }
        )
        raise

    if not result.get("skipped"):
        await finish_celestial_sync(result)
    return result
