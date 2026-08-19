"""Safety limits for opening full-resolution images to create UI previews."""

from PIL import Image

# SatDump products regularly exceed Pillow's conservative 89 MP warning limit.
# Keep the UI's thumbnail path bounded nevertheless: RGB decoding needs roughly
# three bytes per source pixel before temporary image buffers are considered.
MAX_THUMBNAIL_SOURCE_PIXELS = 140_000_000


def is_thumbnail_source_within_pixel_limit(image: Image.Image) -> bool:
    """Return whether an opened image is safe for the thumbnail worker to decode."""
    return int(image.width) * int(image.height) <= MAX_THUMBNAIL_SOURCE_PIXELS
