# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Observer location and local-sky calculations for celestial objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import crud.locations as crud_locations
from celestial.observermath import compute_observer_sky_position
from celestial.settings import _parse_epoch, _parse_projection_options
from celestial.snapshots import _get_vectors_snapshot, _load_covering_vectors_for_target_from_db
from celestial.targets import BODY_HORIZONS_COMMANDS, _target_key_from_parts
from celestial.trajectory import (
    _extract_orbit_samples,
    _interpolate_position_from_samples,
    _payload_covers_projection_window,
)
from db import AsyncSessionLocal


async def _load_earth_observer_vectors(
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
) -> Tuple[Optional[List[float]], List[Tuple[datetime, List[float]]]]:
    """
    Load Earth vectors using the same Horizons snapshot pipeline as targets.

    Using Earth vectors from the same source avoids observer-angle drift caused by
    mixing Horizons target vectors with low-precision Earth ephemerides.
    """
    earth_snapshot = await _get_vectors_snapshot(
        target_key=_target_key_from_parts("body", body_id="earth"),
        command=str(BODY_HORIZONS_COMMANDS.get("earth") or "399"),
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
    earth_cache = str(earth_snapshot.get("cache") or "")
    if not allow_network_fetch and (
        earth_cache.endswith("partial")
        or earth_cache in {"cache-only-miss", "db-compatible-current-only"}
    ):
        # A target-slot request can keep writing a narrow Earth snapshot around
        # NOW, or request a denser step than the scheduled Earth snapshot. Prefer
        # scheduled broad coverage so current AZ/EL and pass calculations remain
        # available between projection-specific refreshes.
        covering_earth = await _load_covering_vectors_for_target_from_db(
            target_key=_target_key_from_parts("body", body_id="earth"),
            past_hours=past_hours,
            future_hours=future_hours,
            maximum_step_minutes=max(60, int(step_minutes)),
        )
        covering_payload = (
            covering_earth.get("payload") if isinstance(covering_earth, dict) else None
        )
        if isinstance(covering_payload, dict) and _payload_covers_projection_window(
            covering_payload,
            epoch=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
        ):
            earth_snapshot = {
                "payload": dict(covering_payload),
                "cache": "db-earth-covering-hit",
                "stale": False,
                "error": None,
                "current_position_usable": True,
                "calculation_usable": True,
            }
    payload = earth_snapshot.get("payload")
    if isinstance(payload, dict):
        # Current pointing only needs samples around this epoch. A stale snapshot
        # can remain valid here even when it no longer spans the full pass window.
        if (
            earth_snapshot.get(
                "current_position_usable", earth_snapshot.get("calculation_usable", True)
            )
            is False
        ):
            return None, []
        earth_samples = _extract_orbit_samples(
            payload,
            epoch_fallback=epoch,
            past_hours=past_hours,
            future_hours=future_hours,
        )
        # Vector snapshots are reused for hours, but observer coordinates must
        # use Earth's position at this response's epoch, just like target rows.
        interpolated = _interpolate_position_from_samples(earth_samples, epoch)
        if interpolated:
            return interpolated, earth_samples
        position_obj = payload.get("position_xyz_au")
        if isinstance(position_obj, list) and len(position_obj) >= 3:
            try:
                return (
                    [float(position_obj[0]), float(position_obj[1]), float(position_obj[2])],
                    earth_samples,
                )
            except (TypeError, ValueError):
                pass
        logger.warning(
            "Earth Horizons payload is missing usable observer vectors (cache=%s)",
            earth_snapshot.get("cache"),
        )
    else:
        upstream_unavailable = bool(earth_snapshot.get("error_code"))
        log = (
            getattr(logger, "debug", logger.warning)
            if not allow_network_fetch or upstream_unavailable
            else logger.warning
        )
        log(
            "Earth Horizons vectors unavailable for observer calculations (cache=%s error=%s)",
            earth_snapshot.get("cache"),
            earth_snapshot.get("error"),
        )

    # Never fall back to low-precision Earth vectors for observer pass calculations.
    return None, []


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
    # Paths and passes require the complete projection window, while current
    # AZ/EL only requires a target vector that is valid at this scene epoch.
    current_position_usable = row.get(
        "current_position_usable", row.get("calculation_usable", True)
    )
    if current_position_usable is False or not observer_location or not earth_position_xyz_au:
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


def _build_observer_sun(
    *,
    epoch: datetime,
    observer_location: Optional[Dict[str, Any]],
    earth_position_xyz_au: Optional[List[float]],
    logger: Any,
) -> Dict[str, Any]:
    """Build the Sun's local-sky row without treating it as a trackable target."""
    sun = {
        "id": "sun",
        "target_key": "observer:sun",
        "target_type": "observer",
        "body_id": "sun",
        "name": "Sun",
        "body_type": "star",
        # The Sun is the origin of the heliocentric frame used by observer math.
        "position_xyz_au": [0.0, 0.0, 0.0],
        "source": "observer-math",
        "color": "#fbbf24",
    }
    _attach_observer_view_local(
        sun,
        epoch,
        observer_location,
        earth_position_xyz_au,
        logger,
    )
    return sun


async def build_observer_sky_bodies(
    data: Optional[Dict[str, Any]],
    logger: Any,
    *,
    allow_network_fetch: bool = True,
) -> List[Dict[str, Any]]:
    """Return visual-only observer bodies for live tracker emissions and scene responses."""
    epoch = _parse_epoch(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    observer_location = await _load_observer_location()
    earth_position_xyz_au, _earth_orbit_samples = await _load_earth_observer_vectors(
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
        step_minutes=step_minutes,
        observer_location=observer_location,
        force_refresh=False,
        allow_network_fetch=allow_network_fetch,
        logger=logger,
    )
    return [
        _build_observer_sun(
            epoch=epoch,
            observer_location=observer_location,
            earth_position_xyz_au=earth_position_xyz_au,
            logger=logger,
        )
    ]
