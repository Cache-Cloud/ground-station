# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Solar-system body snapshots used by celestial scenes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from celestial.snapshots import _get_vectors_snapshot
from celestial.solarsystem import compute_solar_system_snapshot
from celestial.targets import _build_builtin_body_targets, _ensure_scene_targets_registered


def _build_body_snapshot_by_id(planets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    snapshot = {
        str(body.get("id") or "").strip().lower(): dict(body) for body in planets if body.get("id")
    }
    # Sun is the heliocentric frame origin; expose it as a selectable body target
    # without duplicating it in the regular planets array.
    snapshot.setdefault(
        "sun",
        {
            "id": "sun",
            "name": "Sun",
            "body_type": "star",
            "position_xyz_au": [0.0, 0.0, 0.0],
            "velocity_xyz_au_per_day": [0.0, 0.0, 0.0],
            "orbit_samples_xyz_au": [],
            "phase": None,
        },
    )
    return snapshot


async def _build_horizons_solar_system_bodies(
    *,
    epoch: datetime,
    past_hours: int,
    future_hours: int,
    step_minutes: int,
    observer_location: Optional[Dict[str, Any]],
    force_refresh: bool,
    allow_network_fetch: bool,
    logger: Any,
    retry_horizons: bool = False,
    per_body_callback: Optional[Callable[[Dict[str, Any], int, int], Awaitable[None]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Build the solar-system body list from Horizons snapshots.

    This list is independent from monitored targets and is always included in scene payloads.
    """
    builtin_targets = _build_builtin_body_targets()
    await _ensure_scene_targets_registered(builtin_targets, logger)

    planets: List[Dict[str, Any]] = []
    stale_count = 0
    missing_count = 0
    offline_count = 0
    _offline_meta, offline_rows = compute_solar_system_snapshot(epoch)
    offline_by_id = {str(row.get("id") or "").strip().lower(): row for row in offline_rows}

    async def append_body(row: Dict[str, Any]) -> None:
        planets.append(row)
        if per_body_callback is not None:
            await per_body_callback(dict(row), len(planets), len(builtin_targets))

    for target in builtin_targets:
        body_id = str(target.get("body_id") or "").strip().lower()
        target_key = str(target.get("target_key") or "").strip()
        command = str(target.get("horizons_command") or "").strip()
        if not body_id or not target_key or not command:
            continue

        snapshot = await _get_vectors_snapshot(
            target_key=target_key,
            command=command,
            epoch=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
            step_minutes=step_minutes,
            observer_location=observer_location,
            force_refresh=force_refresh,
            logger=logger,
            allow_network_fetch=allow_network_fetch,
            retry_horizons=retry_horizons,
        )
        payload = snapshot.get("payload")
        if not isinstance(payload, dict):
            offline_payload = offline_by_id.get(body_id)
            if isinstance(offline_payload, dict):
                offline_count += 1
                stale_count += 1
                await append_body(
                    {
                        **offline_payload,
                        "target_key": target_key,
                        "id": body_id,
                        "name": str(target.get("name") or offline_payload.get("name") or body_id),
                        "body_type": target.get("body_class")
                        or offline_payload.get("body_type")
                        or "body",
                        "parent_id": target.get("parent_body_id")
                        or offline_payload.get("parent_id"),
                        "scene_role": target.get("scene_role"),
                        "source": "offline-analytic-kepler",
                        "cache": "offline-fallback",
                        "stale": True,
                        "approximate": True,
                        "calculation_usable": False,
                        "error": snapshot.get("error") or "Horizons data unavailable",
                        "error_code": snapshot.get("error_code"),
                    }
                )
                continue
            missing_count += 1
            # Keep a body metadata row when Horizons is unavailable. Do not
            # synthesize origin vectors here: [0,0,0] is the heliocentric Sun
            # and would create misleading overlap in the solar-system canvas.
            await append_body(
                {
                    "target_key": target_key,
                    "id": body_id,
                    "name": str(target.get("name") or body_id),
                    "body_type": target.get("body_class") or "body",
                    "parent_id": target.get("parent_body_id"),
                    "scene_role": target.get("scene_role"),
                    "position_xyz_au": None,
                    "velocity_xyz_au_per_day": None,
                    "orbit_samples_xyz_au": [],
                    "source": "horizons",
                    "cache": snapshot.get("cache"),
                    "stale": True,
                    "calculation_usable": False,
                    "error": snapshot.get("error") or "No data returned",
                    "error_code": snapshot.get("error_code"),
                    "phase": None,
                }
            )
            continue

        row_payload = {
            "target_key": target_key,
            "id": body_id,
            "name": str(target.get("name") or body_id),
            "body_type": target.get("body_class") or "body",
            "parent_id": target.get("parent_body_id"),
            "scene_role": target.get("scene_role"),
            "position_xyz_au": payload.get("position_xyz_au"),
            "velocity_xyz_au_per_day": payload.get("velocity_xyz_au_per_day"),
            "orbit_samples_xyz_au": payload.get("orbit_samples_xyz_au") or [],
            "orbit_sample_times_utc": payload.get("orbit_sample_times_utc") or [],
            "source": payload.get("source") or "horizons",
            "cache": snapshot.get("cache"),
            "stale": bool(snapshot.get("stale")),
            "calculation_usable": snapshot.get("calculation_usable", True),
            "current_position_usable": snapshot.get("current_position_usable", True),
            "phase": None,
        }
        if snapshot.get("error"):
            row_payload["error"] = snapshot.get("error")
        if snapshot.get("error_code"):
            row_payload["error_code"] = snapshot.get("error_code")
        if row_payload["stale"]:
            stale_count += 1
        await append_body(row_payload)

    solar_meta = {
        "source": "horizons",
        "reference": "JPL Horizons vectors",
        "epoch_utc": epoch.astimezone(timezone.utc).isoformat(),
        "body_type_counts": {
            "planet": sum(1 for row in planets if str(row.get("body_type")) == "planet"),
            "dwarf": sum(1 for row in planets if str(row.get("body_type")) == "dwarf"),
            "moon": sum(1 for row in planets if str(row.get("body_type")) == "moon"),
        },
        "cache": {
            "stale_count": stale_count,
            "missing_count": missing_count,
            "offline_count": offline_count,
            "cached_count": sum(
                1
                for row in planets
                if str(row.get("cache") or "") in {"db-stale-hit", "db-stale-fallback"}
            ),
        },
    }

    return solar_meta, planets
