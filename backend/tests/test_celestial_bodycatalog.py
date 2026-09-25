import pytest

from celestial.bodycatalog import get_celestial_body, list_celestial_bodies
from celestial.scene import BODY_HORIZONS_COMMANDS
from handlers.entities.celestial import (
    get_celestial_body_catalog,
    get_spacecraft_index_entries,
    search_spacecraft_index_entries,
)


class _DummyLogger:
    def error(self, *_args, **_kwargs):
        return None


def test_body_catalog_includes_sun():
    bodies = list_celestial_bodies()
    body_ids = {str(item.get("body_id") or "").strip().lower() for item in bodies}
    assert "sun" in body_ids
    for dwarf in ("ceres", "pluto", "haumea", "makemake", "eris"):
        assert dwarf in body_ids

    sun = get_celestial_body("sun")
    assert sun is not None
    assert sun.get("name") == "Sun"
    assert sun.get("body_type") == "star"

    pluto = get_celestial_body("pluto")
    assert pluto is not None
    assert pluto.get("body_type") == "dwarf"


def test_earth_remains_a_system_body_but_is_not_monitorable():
    earth = get_celestial_body("earth")

    assert earth is not None
    assert earth.get("scene_role") == "system"
    assert earth.get("monitorable") is False


def test_body_catalog_includes_uranus_neptune_and_pluto_moons():
    expected = {
        "miranda": ("uranus", "705"),
        "ariel": ("uranus", "701"),
        "umbriel": ("uranus", "702"),
        "titania": ("uranus", "703"),
        "oberon": ("uranus", "704"),
        "triton": ("neptune", "801"),
        "nereid": ("neptune", "802"),
        "proteus": ("neptune", "808"),
        "charon": ("pluto", "901"),
    }

    for body_id, (parent_body_id, horizons_command) in expected.items():
        entry = get_celestial_body(body_id)
        assert entry is not None
        assert entry.get("body_type") == "moon"
        assert entry.get("parent_body_id") == parent_body_id
        assert BODY_HORIZONS_COMMANDS.get(body_id) == horizons_command


@pytest.mark.asyncio
async def test_full_spacecraft_catalog_exposes_unique_target_keys():
    result = await get_spacecraft_index_entries(
        None,
        {"limit": 1000},
        _DummyLogger(),
        "test-client",
    )

    assert result["success"] is True
    rows = result["data"]
    target_keys = [row["target_key"] for row in rows]
    assert len(rows) > 1
    assert len(target_keys) == len(set(target_keys))
    assert all(key.startswith("mission:") for key in target_keys)
    assert all(row["target_type"] == "mission" for row in rows)


@pytest.mark.asyncio
async def test_spacecraft_search_exposes_canonical_target_keys():
    result = await search_spacecraft_index_entries(
        None,
        {"query": "voyager", "limit": 100},
        _DummyLogger(),
        "test-client",
    )

    assert result["success"] is True
    rows = result["data"]
    assert rows
    assert all(row["target_type"] == "mission" for row in rows)
    assert all(row["target_key"].startswith("mission:") for row in rows)


@pytest.mark.asyncio
async def test_body_catalog_api_exposes_unique_target_keys():
    result = await get_celestial_body_catalog(None, None, _DummyLogger(), "test-client")

    assert result["success"] is True
    rows = result["data"]
    target_keys = [row["target_key"] for row in rows]
    assert rows
    assert len(target_keys) == len(set(target_keys))
    assert all(row["target_type"] == "body" for row in rows)
    assert all(key.startswith("body:") for key in target_keys)
