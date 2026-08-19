from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from common.imageguard import MAX_THUMBNAIL_SOURCE_PIXELS, is_thumbnail_source_within_pixel_limit
from common.thumbnails import (
    DEFAULT_THUMBNAIL_SIZE,
    THUMBNAIL_DIRECTORY,
    delete_image_thumbnail,
    generate_image_thumbnail,
    get_image_thumbnail_path,
    get_image_thumbnail_url,
)


def _write_png(path: Path, size=(2400, 1200), color=(24, 42, 88)):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.new("RGB", size, color=color) as image:
        image.save(path, format="PNG")


def test_thumbnail_pixel_limit_accepts_expected_satellite_image_size():
    image = SimpleNamespace(width=10240, height=12968)

    assert image.width * image.height == 132792320
    assert is_thumbnail_source_within_pixel_limit(image)


def test_thumbnail_pixel_limit_rejects_oversized_image():
    image = SimpleNamespace(width=MAX_THUMBNAIL_SOURCE_PIXELS + 1, height=1)

    assert not is_thumbnail_source_within_pixel_limit(image)


def test_generate_image_thumbnail_skips_source_above_pixel_limit(tmp_path, monkeypatch):
    source = tmp_path / "oversized.png"
    _write_png(source)
    monkeypatch.setattr(
        "common.thumbnails.is_thumbnail_source_within_pixel_limit",
        lambda image: False,
    )

    assert generate_image_thumbnail(source) is None
    assert not get_image_thumbnail_path(source).exists()


def test_generate_image_thumbnail_creates_small_jpeg(tmp_path):
    source = tmp_path / "recording.png"
    _write_png(source)

    thumb_path = generate_image_thumbnail(source)

    assert thumb_path == tmp_path / THUMBNAIL_DIRECTORY / "recording.jpg"
    assert thumb_path.exists()
    with Image.open(thumb_path) as thumb:
        assert thumb.size == DEFAULT_THUMBNAIL_SIZE
        assert thumb.format == "JPEG"


def test_get_image_thumbnail_url_returns_cache_busted_static_url(tmp_path):
    source = tmp_path / "snapshot.png"
    _write_png(source)

    thumbnail_url = get_image_thumbnail_url(source, "/recordings", lazy_generate=True)

    assert thumbnail_url is not None
    assert thumbnail_url.startswith("/recordings/thumbnails/snapshot.jpg?v=")
    assert get_image_thumbnail_path(source).exists()


def test_delete_image_thumbnail_removes_cached_file(tmp_path):
    source = tmp_path / "snapshot.png"
    _write_png(source)
    thumb_path = generate_image_thumbnail(source)

    deleted_path = delete_image_thumbnail(source)

    assert deleted_path == thumb_path
    assert not thumb_path.exists()
