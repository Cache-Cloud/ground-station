# Copyright (c) 2026 Efstratios Goudelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Canonical identity helpers for non-satellite tracking targets."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

TARGET_TYPES = {"mission", "body"}
_SEPARATOR_PATTERN = re.compile(r"[\s_]+", flags=re.UNICODE)


def normalize_target_identifier(value: Any) -> str:
    """Normalize a target identifier into its persisted key suffix."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return _SEPARATOR_PATTERN.sub("_", text).strip("_")


def build_target_key(
    *,
    target_type: Any,
    command: Any = None,
    body_id: Any = None,
) -> str | None:
    """Build a canonical mission/body key from its authoritative metadata."""
    normalized_type = str(target_type or "").strip().lower()
    if normalized_type == "mission":
        identifier = normalize_target_identifier(command)
    elif normalized_type == "body":
        identifier = normalize_target_identifier(body_id)
    else:
        return None
    return f"{normalized_type}:{identifier}" if identifier else None


def normalize_target_key(value: Any) -> str | None:
    """Validate and canonicalize a complete mission/body target key."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if ":" not in text:
        return None
    prefix, suffix = text.split(":", 1)
    normalized_type = prefix.strip().lower()
    if normalized_type not in TARGET_TYPES:
        return None
    identifier = normalize_target_identifier(suffix)
    return f"{normalized_type}:{identifier}" if identifier else None
