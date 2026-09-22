# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Build and publish celestial ephemeris synchronization status."""

from __future__ import annotations

from typing import Any, Dict

import crud.celestialvectors as crud_vectors
from celestial.horizons import get_horizons_status
from celestial.syncstate import get_celestial_sync_state, hydrate_celestial_sync_state
from common.arguments import arguments
from db import AsyncSessionLocal

CELESTIAL_EPHEMERIS_STATUS_EVENT = "celestial-ephemeris-status-update"


async def build_celestial_ephemeris_status(logger: Any) -> Dict[str, Any]:
    """Return the status response shared by API calls and push events."""
    try:
        sync_state = await hydrate_celestial_sync_state()
    except Exception:
        logger.exception("Failed to hydrate celestial ephemeris sync state")
        sync_state = get_celestial_sync_state()

    async with AsyncSessionLocal() as dbsession:
        cache_result = await crud_vectors.fetch_celestial_vector_snapshot_stats(dbsession)

    if not cache_result.get("success"):
        return {
            "success": False,
            "error": cache_result.get("error") or "Failed to load celestial cache status",
        }

    return {
        "success": True,
        "data": {
            "provider": {
                "name": "NASA JPL Horizons",
                "status": get_horizons_status(),
            },
            "cache": cache_result.get("data") or {},
            "sync": {
                "enabled": bool(getattr(arguments, "celestial_periodic_sync_enabled", True)),
                "interval_minutes": int(
                    getattr(arguments, "celestial_periodic_sync_interval_minutes", 60)
                ),
                "past_hours": int(getattr(arguments, "celestial_sync_past_hours", 1)),
                "state": sync_state,
            },
        },
        "error": None,
    }


async def emit_celestial_ephemeris_status(sio: Any, logger: Any) -> Dict[str, Any]:
    """Broadcast the latest ephemeris status without disrupting sync completion."""
    try:
        response = await build_celestial_ephemeris_status(logger)
    except Exception as exc:
        logger.exception("Failed to build celestial ephemeris status")
        response = {
            "success": False,
            "error": str(exc) or "Failed to build celestial ephemeris status",
        }
    try:
        await sio.emit(CELESTIAL_EPHEMERIS_STATUS_EVENT, response)
    except Exception:
        logger.exception("Failed to broadcast celestial ephemeris status")
    return response
