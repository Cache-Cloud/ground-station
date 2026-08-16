from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List


def get_backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_recordings_root() -> Path:
    return (get_backend_root() / "data" / "recordings").resolve()


def get_observations_root() -> Path:
    """Return the root containing automated-observation artifact bundles."""
    return (get_backend_root() / "data" / "observations").resolve()


def get_snapshots_root() -> Path:
    return (get_backend_root() / "data" / "snapshots").resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def get_sigmf_allowed_roots(recordings_root: Path | None = None) -> List[Path]:
    roots: List[Path] = [
        (recordings_root or get_recordings_root()).resolve(),
        get_observations_root(),
    ]
    extra_roots = os.environ.get("GS_SIGMF_ALLOWED_DIRS", "")
    for raw_root in extra_roots.split(os.pathsep):
        cleaned = raw_root.strip()
        if cleaned:
            roots.append(Path(cleaned).resolve())

    # Keep order stable while deduplicating.
    unique_roots: List[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            unique_roots.append(root)
            seen.add(root)
    return unique_roots


def ensure_path_in_allowed_roots(path: Path, allowed_roots: Iterable[Path]) -> Path:
    resolved_path = path.resolve()
    normalized_roots = [Path(root).resolve() for root in allowed_roots]
    if any(_is_within(resolved_path, root) for root in normalized_roots):
        return resolved_path
    raise ValueError(
        "Path is outside allowed directories. "
        "Set GS_SIGMF_ALLOWED_DIRS to permit additional trusted locations."
    )


def resolve_sigmf_meta_path(
    recording_path: str,
    recordings_root: Path | None = None,
    allowed_roots: Iterable[Path] | None = None,
) -> Path:
    if not recording_path or not str(recording_path).strip():
        raise ValueError("No recording_path provided")

    base_recordings_root = (recordings_root or get_recordings_root()).resolve()
    candidate = Path(str(recording_path).strip())
    if not candidate.is_absolute():
        candidate = base_recordings_root / candidate

    candidate_text = str(candidate)
    if candidate_text.endswith(".sigmf-meta"):
        meta_path = candidate
    elif candidate_text.endswith(".sigmf-data"):
        meta_path = candidate.with_suffix(".sigmf-meta")
    else:
        meta_path = Path(f"{candidate_text}.sigmf-meta")

    roots = (
        list(allowed_roots)
        if allowed_roots is not None
        else get_sigmf_allowed_roots(base_recordings_root)
    )
    return ensure_path_in_allowed_roots(meta_path, roots)


def resolve_sigmf_data_path(meta_path: Path, allowed_roots: Iterable[Path] | None = None) -> Path:
    data_path = meta_path.with_suffix(".sigmf-data")
    roots = list(allowed_roots) if allowed_roots is not None else get_sigmf_allowed_roots()
    return ensure_path_in_allowed_roots(data_path, roots)
