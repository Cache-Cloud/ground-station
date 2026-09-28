# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Public composition facade for celestial scenes and tracks."""

from __future__ import annotations

from typing import Any, Dict, Optional

# Keep the established celestial.scene import surface while implementation
# details live in modules with one clear responsibility.
from celestial.asteroidzones import get_static_asteroid_zones
from celestial.bodies import _build_body_snapshot_by_id as _build_body_snapshot_by_id
from celestial.bodies import (
    _build_horizons_solar_system_bodies as _build_horizons_solar_system_bodies,
)
from celestial.horizons import get_horizons_status
from celestial.observer import _build_observer_sun as _build_observer_sun
from celestial.observer import _load_observer_location as _load_observer_location
from celestial.observer import build_observer_sky_bodies as build_observer_sky_bodies  # noqa: F401
from celestial.passes import _build_celestial_passes as _build_celestial_passes
from celestial.settings import CACHE_TTL_SECONDS as CACHE_TTL_SECONDS
from celestial.settings import CELESTIAL_PASS_HORIZON_DEG as CELESTIAL_PASS_HORIZON_DEG
from celestial.settings import DEFAULT_CENTER as DEFAULT_CENTER
from celestial.settings import DEFAULT_FRAME as DEFAULT_FRAME
from celestial.settings import VECTOR_DB_TTL_SECONDS as VECTOR_DB_TTL_SECONDS
from celestial.settings import _parse_epoch as _parse_epoch
from celestial.settings import _parse_projection_options as _parse_projection_options
from celestial.sync import (  # noqa: F401
    refresh_celestial_vector_snapshots_cache as refresh_celestial_vector_snapshots_cache,
)
from celestial.targets import _ensure_scene_targets_registered as _ensure_scene_targets_registered
from celestial.targets import _normalize_targets as _normalize_targets
from celestial.tracks import _fetch_celestial_with_cache as _fetch_celestial_with_cache
from celestial.tracks import build_celestial_tracks as build_celestial_tracks  # noqa: F401
from celestial.trajectory import _extract_earth_orbit_samples as _extract_earth_orbit_samples
from celestial.trajectory import _extract_earth_position_xyz_au as _extract_earth_position_xyz_au


async def build_celestial_scene(
    data: Optional[Dict[str, Any]],
    logger,
    force_refresh: bool = False,
    allow_network_fetch: bool = True,
    per_row_callback: Optional[Any] = None,
    use_computed_cache: bool = True,
) -> Dict[str, Any]:
    """Build a scene payload for UI rendering and backend sharing."""
    epoch = _parse_epoch(data)
    targets = _normalize_targets(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    retry_horizons = bool(data.get("retry_horizons")) if isinstance(data, dict) else False
    observer_location = await _load_observer_location()
    await _ensure_scene_targets_registered(targets, logger)
    solar_meta, planets = await _build_horizons_solar_system_bodies(
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
        step_minutes=step_minutes,
        observer_location=observer_location,
        force_refresh=force_refresh,
        allow_network_fetch=allow_network_fetch,
        logger=logger,
        retry_horizons=retry_horizons,
    )
    earth_position_xyz_au = _extract_earth_position_xyz_au(planets)
    earth_orbit_samples = _extract_earth_orbit_samples(
        planets,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
    )
    body_snapshot_by_id = _build_body_snapshot_by_id(planets)
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
        allow_network_fetch,
        logger,
        per_row_callback,
        use_computed_cache,
        retry_horizons,
    )
    celestial_passes = _build_celestial_passes(
        rows=celestial,
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
        step_minutes=step_minutes,
        observer_location=observer_location,
        earth_position_xyz_au=earth_position_xyz_au,
        earth_orbit_samples=earth_orbit_samples,
        logger=logger,
    )
    observer_bodies = [
        _build_observer_sun(
            epoch=epoch,
            observer_location=observer_location,
            earth_position_xyz_au=earth_position_xyz_au,
            logger=logger,
        )
    ]

    return {
        "success": True,
        "data": {
            "timestamp_utc": epoch.isoformat(),
            "frame": DEFAULT_FRAME,
            "center": DEFAULT_CENTER,
            "units": {
                "position": "au",
                "velocity": "au/day",
            },
            "planets": planets,
            "celestial": celestial,
            "observer_bodies": observer_bodies,
            "celestial_passes": celestial_passes,
            "asteroid_zones": asteroid_zones,
            "asteroid_resonance_gaps": asteroid_resonance_gaps,
            "meta": {
                "solar_system": solar_meta,
                "horizons": {
                    **get_horizons_status(),
                    **solar_meta.get("cache", {}),
                },
                "celestial_source": "horizons",
                "asteroid_zones": asteroid_meta,
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "vector_db_ttl_seconds": VECTOR_DB_TTL_SECONDS,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
                "passes": {
                    "horizon_threshold_deg": CELESTIAL_PASS_HORIZON_DEG,
                    "count": len(celestial_passes),
                },
                "observer_location": observer_location,
                "visibility_definition": "visible == elevation_deg > 0",
            },
        },
    }


async def build_solar_system_scene(
    data: Optional[Dict[str, Any]],
    logger,
    allow_network_fetch: bool = True,
    per_body_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build the solar-system portion for UI rendering."""
    epoch = _parse_epoch(data)
    past_hours, future_hours, step_minutes = _parse_projection_options(data)
    retry_horizons = bool(data.get("retry_horizons")) if isinstance(data, dict) else False
    solar_meta, planets = await _build_horizons_solar_system_bodies(
        epoch=epoch,
        past_hours=past_hours,
        future_hours=future_hours,
        step_minutes=step_minutes,
        observer_location=None,
        force_refresh=False,
        allow_network_fetch=allow_network_fetch,
        logger=logger,
        retry_horizons=retry_horizons,
        per_body_callback=per_body_callback,
    )
    asteroid_zones, asteroid_resonance_gaps, asteroid_meta = get_static_asteroid_zones()

    return {
        "success": True,
        "data": {
            "timestamp_utc": epoch.isoformat(),
            "frame": DEFAULT_FRAME,
            "center": DEFAULT_CENTER,
            "units": {
                "position": "au",
                "velocity": "au/day",
            },
            "planets": planets,
            "asteroid_zones": asteroid_zones,
            "asteroid_resonance_gaps": asteroid_resonance_gaps,
            "meta": {
                "solar_system": solar_meta,
                "horizons": {
                    **get_horizons_status(),
                    **solar_meta.get("cache", {}),
                },
                "asteroid_zones": asteroid_meta,
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "vector_db_ttl_seconds": VECTOR_DB_TTL_SECONDS,
                "projection": {
                    "past_hours": past_hours,
                    "future_hours": future_hours,
                    "step_minutes": step_minutes,
                },
            },
        },
    }
