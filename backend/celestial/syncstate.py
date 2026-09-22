# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Runtime and persistent state for celestial ephemeris synchronization."""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.logger import logger
from db import AsyncSessionLocal
from db.models import TrackingState

CELESTIAL_SYNC_STATE_NAME = "celestial-ephemeris-sync:global"


def _initial_state() -> Dict[str, Any]:
    return {
        "status": "idle",
        "progress": 0,
        "success": None,
        "message": "",
        "trigger": None,
        "started_at": None,
        "completed_at": None,
        "last_update": None,
        "count": 0,
        "refreshed": 0,
        "failed": 0,
        "errors": [],
    }


_state_lock = threading.RLock()
_runtime_state: Dict[str, Any] = _initial_state()


def get_celestial_sync_state() -> Dict[str, Any]:
    """Return an isolated snapshot of the current process-wide sync state."""
    with _state_lock:
        return copy.deepcopy(_runtime_state)


def set_celestial_sync_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Replace runtime state with a serializable snapshot."""
    global _runtime_state
    with _state_lock:
        _runtime_state = copy.deepcopy(state)
        return copy.deepcopy(_runtime_state)


def reset_celestial_sync_state() -> Dict[str, Any]:
    """Reset runtime state, primarily for isolated tests."""
    return set_celestial_sync_state(_initial_state())


def should_hydrate_celestial_sync_state(state: Optional[Dict[str, Any]]) -> bool:
    """Return whether runtime state still represents a fresh process start."""
    if not isinstance(state, dict):
        return True
    if state.get("last_update"):
        return False
    return str(state.get("status") or "idle").lower() == "idle"


def start_celestial_sync(trigger: str) -> Dict[str, Any]:
    """Start a new runtime sync state without persisting transient progress."""
    now = datetime.now(timezone.utc).isoformat()
    return set_celestial_sync_state(
        {
            **_initial_state(),
            "status": "inprogress",
            "success": None,
            "message": "Celestial ephemeris synchronization is running.",
            "trigger": str(trigger or "unknown"),
            "started_at": now,
            "last_update": now,
        }
    )


def update_celestial_sync_progress(progress: Dict[str, Any]) -> Dict[str, Any]:
    """Merge one progress event into the process-wide running state."""
    current = get_celestial_sync_state()
    if str(current.get("status") or "").lower() != "inprogress":
        return current

    now = datetime.now(timezone.utc).isoformat()
    current.update(
        {
            "progress": float(progress.get("percent") or 0),
            "count": int(progress.get("total") or 0),
            "processed": int(progress.get("processed") or 0),
            "refreshed": int(progress.get("refreshed") or 0),
            "failed": int(progress.get("failed") or 0),
            "phase": progress.get("phase"),
            "current_target": progress.get("current_target"),
            "last_update": now,
        }
    )
    return set_celestial_sync_state(current)


async def load_celestial_sync_state(session: AsyncSession) -> Optional[Dict[str, Any]]:
    """Load the latest terminal celestial sync snapshot from tracking_state."""
    result = await session.execute(
        select(TrackingState).where(TrackingState.name == CELESTIAL_SYNC_STATE_NAME)
    )
    row = result.scalar_one_or_none()
    if row is None or not isinstance(row.value, dict):
        return None
    return copy.deepcopy(row.value)


async def save_celestial_sync_state(session: AsyncSession, state: Dict[str, Any]) -> bool:
    """Upsert one terminal celestial sync snapshot in tracking_state."""
    if not isinstance(state, dict):
        return False

    try:
        result = await session.execute(
            select(TrackingState).where(TrackingState.name == CELESTIAL_SYNC_STATE_NAME)
        )
        row = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        value = copy.deepcopy(state)
        if row is None:
            session.add(
                TrackingState(
                    name=CELESTIAL_SYNC_STATE_NAME,
                    value=value,
                    added=now,
                    updated=now,
                )
            )
        else:
            row.value = value
            row.updated = now
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        logger.exception("Failed to persist celestial ephemeris sync state")
        return False


async def hydrate_celestial_sync_state() -> Dict[str, Any]:
    """Hydrate fresh runtime state from the last terminal database snapshot."""
    current = get_celestial_sync_state()
    if not should_hydrate_celestial_sync_state(current):
        return current

    async with AsyncSessionLocal() as session:
        persisted = await load_celestial_sync_state(session)
    if persisted:
        return set_celestial_sync_state(persisted)
    return current


async def finish_celestial_sync(result: Dict[str, Any]) -> Dict[str, Any]:
    """Record and persist a completed or failed whole-sync result."""
    current = get_celestial_sync_state()
    now = datetime.now(timezone.utc).isoformat()
    success = bool(result.get("success"))
    failed = int(result.get("failed") or 0)
    state = {
        **current,
        "status": "complete",
        "progress": 100,
        "success": success,
        "message": result.get("error")
        or (
            "Celestial ephemeris synchronization completed."
            if success
            else "Celestial ephemeris synchronization requires attention."
        ),
        "completed_at": now,
        "last_update": now,
        "count": int(result.get("count") or 0),
        "processed": int(result.get("count") or 0),
        "refreshed": int(result.get("refreshed") or 0),
        "failed": failed,
        "errors": copy.deepcopy(result.get("errors") or []),
        "projection": copy.deepcopy(result.get("projection")),
        "current_target": None,
        "phase": "complete" if success else "failed",
    }
    state = set_celestial_sync_state(state)
    async with AsyncSessionLocal() as session:
        await save_celestial_sync_state(session, state)
    return state
