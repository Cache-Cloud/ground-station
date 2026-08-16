"""Focused unit tests for SSDV packet/image state handling."""

import zlib

import pytest
from reedsolo import RSCodec

from demodulators.ssdvdecoder import SSDVImage, parse_ssdv_packet, recover_ssdv_packet


def _callsign_code(callsign: str) -> int:
    """Encode the upstream SSDV base-40 callsign format for a test packet."""
    code = 0
    for character in reversed(callsign):
        code *= 40
        if character.isdigit():
            code += int(character) + 1
        elif character.isalpha():
            code += ord(character.upper()) - ord("A") + 14
    return code


def _packet(packet_id: int, image_id: int = 7, eoi: bool = False) -> bytes:
    packet = bytearray(256)
    packet[0] = 0x55
    packet[1] = 0x66
    packet[2:6] = _callsign_code("TEST1").to_bytes(4, "big")
    packet[6] = image_id
    packet[7:9] = packet_id.to_bytes(2, "big")
    packet[9] = 20  # 320 px
    packet[10] = 15  # 240 px
    packet[11] = 0x04 if eoi else 0
    return bytes(packet)


def _normal_packet(packet_id: int) -> bytes:
    """Create a CRC/FEC-valid normal SSDV packet for recovery tests."""
    packet = bytearray(_packet(packet_id))
    packet[1] = 0x66
    packet[220:224] = zlib.crc32(packet[1:220]).to_bytes(4, "big")
    codec = RSCodec(nsym=32, nsize=255, fcr=112, prim=0x187, generator=0xAD)
    packet[1:] = codec.encode(bytes(packet[1:224]))
    return bytes(packet)


def test_parses_standard_ssdv_header():
    info = parse_ssdv_packet(_packet(42, eoi=True))

    assert info.callsign == "TEST1"
    assert info.image_id == 7
    assert info.packet_id == 42
    assert (info.width, info.height) == (320, 240)
    assert info.eoi is True
    assert info.packet_type == 0


def test_image_state_orders_packets_and_ignores_retransmits():
    second = _packet(2, eoi=True)
    first = _packet(1)
    image = SSDVImage(info=parse_ssdv_packet(second), started_at=0.0)

    assert image.add_packet(second, parse_ssdv_packet(second)) is True
    assert image.add_packet(first, parse_ssdv_packet(first)) is True
    assert image.add_packet(first, parse_ssdv_packet(first)) is False
    assert image.eoi_received is True
    assert image.missing_packets == 1
    assert image.encoded_packets() == first + second


def test_recovers_a_correctable_normal_ssdv_packet_error():
    packet = _normal_packet(42)
    corrupted = bytearray(packet)
    corrupted[35] ^= 0x20

    assert recover_ssdv_packet(bytes(corrupted)) == packet


def test_rejects_candidate_with_invalid_crc_and_fec():
    packet = bytearray(_normal_packet(42))
    for index in range(30, 48):
        packet[index] ^= 0x01

    assert recover_ssdv_packet(bytes(packet)) is None


@pytest.mark.parametrize("packet", [b"", bytes(255), bytes([0x55, 0x65]) + bytes(254)])
def test_rejects_non_ssdv_packet_candidates(packet):
    with pytest.raises(ValueError):
        parse_ssdv_packet(packet)
