# Copyright (c) 2025 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Celestial target normalization, catalog metadata, and registration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import crud.celestialvectors as crud_celestial_vectors
from celestial.bodycatalog import list_celestial_bodies
from celestial.settings import DEFAULT_CELESTIAL_TARGETS
from common.targetkey import build_target_key, normalize_target_key
from db import AsyncSessionLocal

BODY_HORIZONS_COMMANDS: Dict[str, str] = {
    # Major planets.
    "mercury": "199",
    "venus": "299",
    "earth": "399",
    "mars": "499",
    "jupiter": "599",
    "saturn": "699",
    "uranus": "799",
    "neptune": "899",
    # IAU-recognized dwarf planets.
    # Use small-body selector for Ceres to avoid major-body ID collision with Mercury.
    "ceres": "1;",
    "pluto": "999",
    "haumea": "136108",
    "makemake": "136472",
    "eris": "136199",
    # Moons currently exposed by the body catalog.
    "moon": "301",
    "io": "501",
    "europa": "502",
    "ganymede": "503",
    "callisto": "504",
    "enceladus": "602",
    "rhea": "605",
    "titan": "606",
    "iapetus": "608",
    "miranda": "705",
    "ariel": "701",
    "umbriel": "702",
    "titania": "703",
    "oberon": "704",
    "triton": "801",
    "nereid": "802",
    "proteus": "808",
    "charon": "901",
}
_BODY_CATALOG_BY_ID: Dict[str, Dict[str, Any]] = {
    str(item.get("body_id") or "").strip().lower(): item
    for item in list_celestial_bodies()
    if str(item.get("body_id") or "").strip()
}


def _target_key_from_parts(
    target_type: str,
    *,
    command: Optional[str] = None,
    body_id: Optional[str] = None,
) -> str:
    return (
        build_target_key(
            target_type=target_type,
            command=command,
            body_id=body_id,
        )
        or ""
    )


def _build_body_target_payload(
    *,
    body_id: str,
    name: Optional[str] = None,
    color: Any = None,
    target_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized_body_id = str(body_id or "").strip().lower()
    if not normalized_body_id:
        return None

    catalog_entry = _BODY_CATALOG_BY_ID.get(normalized_body_id) or {}
    body_class = str(catalog_entry.get("body_type") or "").strip().lower() or None
    parent_body_id = str(catalog_entry.get("parent_body_id") or "").strip().lower() or None
    scene_role = str(catalog_entry.get("scene_role") or "").strip().lower() or None
    horizons_command = str(BODY_HORIZONS_COMMANDS.get(normalized_body_id) or "").strip()
    display_name = str(name or catalog_entry.get("name") or normalized_body_id).strip()
    normalized_target_key = normalize_target_key(target_key)
    if not normalized_target_key or not normalized_target_key.startswith("body:"):
        normalized_target_key = _target_key_from_parts("body", body_id=normalized_body_id)

    return {
        "target_type": "body",
        "target_key": normalized_target_key,
        "body_id": normalized_body_id,
        # Keep "command" populated for existing UI/tooling paths that expect a command-like field.
        "command": horizons_command or normalized_body_id,
        "horizons_command": horizons_command,
        "name": display_name,
        "color": color,
        "body_class": body_class,
        "parent_body_id": parent_body_id,
        "scene_role": scene_role,
        "always_in_scene": scene_role == "system",
    }


def _normalize_targets(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not data:
        return [dict(target) for target in DEFAULT_CELESTIAL_TARGETS]

    requested = data.get("celestial")
    if not requested:
        return [dict(target) for target in DEFAULT_CELESTIAL_TARGETS]

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
                        "horizons_command": command,
                        "name": command,
                    }
                )
            continue

        if isinstance(item, dict):
            color = item.get("color")
            projection_obj = item.get("projection")
            projection = projection_obj if isinstance(projection_obj, dict) else item
            target_projection = {
                "past_hours": projection.get("past_hours", projection.get("pastHours")),
                "future_hours": projection.get("future_hours", projection.get("futureHours")),
                "step_minutes": projection.get("step_minutes", projection.get("stepMinutes")),
            }
            target_projection = {
                key: value for key, value in target_projection.items() if value is not None
            }
            target_type = (
                str(item.get("target_type") or item.get("targetType") or "mission").strip().lower()
            )
            explicit_target_key = normalize_target_key(
                item.get("target_key") or item.get("targetKey")
            )
            if explicit_target_key and not explicit_target_key.startswith(f"{target_type}:"):
                explicit_target_key = None

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
                body_payload = _build_body_target_payload(
                    body_id=body_id,
                    name=str(item.get("name") or body_id).strip(),
                    color=color,
                    target_key=explicit_target_key
                    or _target_key_from_parts("body", body_id=body_id),
                )
                if body_payload:
                    body_payload.update(target_projection)
                    normalized.append(body_payload)
                continue

            command = str(item.get("command") or item.get("id") or item.get("target") or "").strip()
            if not command:
                continue
            name = str(item.get("name") or command).strip()
            normalized.append(
                {
                    "target_type": "mission",
                    "target_key": explicit_target_key
                    or _target_key_from_parts("mission", command=command),
                    "command": command,
                    "horizons_command": command,
                    "name": name,
                    "color": color,
                    **target_projection,
                }
            )

    return normalized


def _build_builtin_body_targets() -> List[Dict[str, Any]]:
    """Build the always-in-scene body target list from the body catalog."""
    rows: List[Dict[str, Any]] = []
    for entry in list_celestial_bodies():
        body_id = str(entry.get("body_id") or "").strip().lower()
        if not body_id or body_id == "sun":
            continue
        # Scene membership is explicit catalog metadata. This keeps selectable
        # catalog bodies from automatically becoming background scene load.
        if str(entry.get("scene_role") or "").strip().lower() != "system":
            continue

        body_payload = _build_body_target_payload(
            body_id=body_id,
            name=str(entry.get("name") or body_id).strip(),
            target_key=_target_key_from_parts("body", body_id=body_id),
        )
        if not body_payload:
            continue
        body_payload["always_in_scene"] = True
        rows.append(body_payload)
    return rows


async def _ensure_scene_targets_registered(
    targets: List[Dict[str, Any]],
    logger: Any,
) -> None:
    """Persist target metadata so snapshots can reference an explicit target row."""
    if not targets:
        return

    upsert_rows: List[Dict[str, Any]] = []
    for target in targets:
        target_key = str(target.get("target_key") or "").strip()
        target_type = str(target.get("target_type") or "").strip().lower()
        if not target_key or target_type not in {"mission", "body"}:
            continue

        upsert_rows.append(
            {
                "id": target_key,
                "target_type": target_type,
                "body_class": target.get("body_class"),
                "display_name": str(target.get("name") or target_key).strip(),
                "horizons_command": str(
                    target.get("horizons_command") or target.get("command") or ""
                ).strip()
                or None,
                "body_id": str(target.get("body_id") or "").strip().lower() or None,
                "parent_body_id": str(target.get("parent_body_id") or "").strip().lower() or None,
                "always_in_scene": bool(target.get("always_in_scene", False)),
                "enabled": True,
            }
        )

    if not upsert_rows:
        return

    async with AsyncSessionLocal() as dbsession:
        result = await crud_celestial_vectors.ensure_celestial_targets(dbsession, upsert_rows)
    if not result.get("success"):
        logger.warning("Failed to register celestial targets: %s", result.get("error"))
