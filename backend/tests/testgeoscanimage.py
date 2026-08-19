import pytest

from demodulators.geoscanimage import (
    GEOSCAN_PAYLOAD_SIZE,
    MAX_JPEG_OFFSET,
    GeoscanImageAssembly,
    parse_geoscan_image_fragment,
)
from pipeline.config.decoderconfigservice import DecoderConfigService


def image_payload(offset=0, image_id=6, satellite_id=9):
    """Build a CRC-stripped 74-byte-air-frame image payload for parser tests."""
    payload = bytearray(GEOSCAN_PAYLOAD_SIZE)
    payload[0] = satellite_id
    payload[5:9] = b"1oko"
    payload[9:13] = offset.to_bytes(4, "little")
    payload[13:15] = image_id.to_bytes(2, "little")
    payload[15:69] = bytes([0xFF, 0xD8]) + bytes(range(52))
    return bytes(payload)


def test_parses_alferov_v2_image_fragment():
    fragment = parse_geoscan_image_fragment(image_payload(offset=108, image_id=7))

    assert fragment.satellite_id == 9
    assert fragment.image_id == 7
    assert fragment.offset == 108
    assert fragment.data.startswith(b"\xff\xd8")
    assert len(fragment.data) == 54


@pytest.mark.parametrize(
    "payload",
    [
        b"",  # short frame
        image_payload(satellite_id=8),
        bytes(GEOSCAN_PAYLOAD_SIZE),  # no image marker
        image_payload(offset=MAX_JPEG_OFFSET),
    ],
)
def test_rejects_non_image_or_unsafe_geoscan_frames(payload):
    with pytest.raises(ValueError):
        parse_geoscan_image_fragment(payload)


def test_sparse_reassembly_deduplicates_offsets_and_preserves_gaps():
    first = parse_geoscan_image_fragment(image_payload(offset=0))
    second = parse_geoscan_image_fragment(image_payload(offset=108))
    assembly = GeoscanImageAssembly(9, 6, started_at=0.0)

    assert assembly.add(second) is True
    assert assembly.add(first) is True
    assert assembly.add(first) is False

    jpeg = assembly.jpeg_bytes()
    assert len(jpeg) == 162
    assert jpeg[:2] == b"\xff\xd8"
    assert jpeg[54:108] == b"\0" * 54
    assert jpeg[108:110] == b"\xff\xd8"
    assert assembly.received_bytes == 108
    assert assembly.coverage_percent == pytest.approx(100 * 108 / 162)


def test_geoscan_image_config_ignores_transmitter_profile_and_keeps_manual_values():
    config = DecoderConfigService().get_config(
        "geoscanimage",
        satellite={"norad_id": 64881},
        transmitter={"baud": 1200, "mode": "GFSK", "deviation": 600},
        overrides={
            "baudrate": 9600,
            "deviation": 5000,
            "framing": "ax25",
            "framing_params": {"frame_size": 74, "syncword_threshold": 4, "satellite_id": 9},
        },
    )

    assert config.baudrate == 9600
    assert config.deviation == 5000
    assert config.framing == "geoscan"
    assert config.framing_params == {"frame_size": 74, "syncword_threshold": 4, "satellite_id": 9}
