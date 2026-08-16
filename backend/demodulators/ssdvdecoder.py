"""SSDV image decoder built on the project's raw-IQ BPSK receiver.

SSDV is a packetised JPEG format.  It is not analogue SSTV: the BPSK
flowgraph extracts fixed-size packets and this module groups those packets by
their on-air callsign and image ID before asking the reference ``ssdv`` codec
to reconstruct a JPEG preview.
"""

import base64
import json
import logging
import os
import queue
import shutil
import subprocess
import time
import zlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from reedsolo import ReedSolomonError, RSCodec

from constants import FramingType

_BPSK_IMPORT_ERROR: Optional[ImportError] = None

if TYPE_CHECKING:
    from demodulators.bpskdecoder import BPSKDecoder
else:
    try:
        from demodulators.bpskdecoder import BPSKDecoder
    except ImportError as error:  # pragma: no cover - exercised on non-DSP test hosts
        # Keeping packet parsing importable lets protocol tests run on hosts
        # that intentionally do not install GNU Radio. Actual decoder startup
        # reports the original dependency problem below.
        _BPSK_IMPORT_ERROR = error

        class BPSKDecoder:  # type: ignore[no-redef]
            """Runtime-only fallback when GNU Radio is intentionally absent."""

            pass


logger = logging.getLogger("ssdvdecoder")

SSDV_PACKET_SIZE = 256
SSDV_SYNC_BYTE = 0x55
SSDV_PACKET_TYPES = {0x66, 0x67}
SSDV_RENDER_INTERVAL_SECONDS = 2.0

# SSDV's normal 256-byte packet is a shortened RS(255, 223) code over
# GF(2^8), using the non-default field/generator values from libssdv's rs8.c.
# Keeping this validation in-process prevents an 0x55 noise match from creating
# an image stream or repeatedly spawning the JPEG renderer.
_SSDV_RS_CODEC = RSCodec(nsym=32, nsize=255, fcr=112, prim=0x187, generator=0xAD)


class SSDVStatus(Enum):
    """Additional image-lifecycle status used by the SSDV UI."""

    CAPTURING = "capturing"


def decode_callsign(code: int) -> str:
    """Decode SSDV's compact base-40 callsign representation."""
    if code > 0xF423FFFF:
        return ""

    characters = []
    while code:
        symbol = code % 40
        if symbol == 0 or 11 <= symbol < 14:
            characters.append("-")
        elif symbol < 11:
            characters.append(chr(ord("0") + symbol - 1))
        else:
            characters.append(chr(ord("A") + symbol - 14))
        code //= 40
    return "".join(characters)


@dataclass(frozen=True)
class SSDVPacketInfo:
    """Header fields used to group a validated-size SSDV packet."""

    callsign: str
    callsign_code: int
    image_id: int
    packet_id: int
    width: int
    height: int
    eoi: bool
    packet_type: int

    @property
    def image_key(self) -> Tuple[int, int]:
        """Return the stable stream key (callsign code, image ID)."""
        return self.callsign_code, self.image_id


def parse_ssdv_packet(packet: bytes) -> SSDVPacketInfo:
    """Parse the fixed SSDV header without accepting arbitrary RF data.

    ``recover_ssdv_packet`` performs CRC/Reed-Solomon validation before this
    parser is called by the receiver. These inexpensive header checks also
    keep this protocol helper useful independently in tests and tools.
    """
    if len(packet) != SSDV_PACKET_SIZE:
        raise ValueError(f"SSDV packet must be {SSDV_PACKET_SIZE} bytes")
    if packet[0] != SSDV_SYNC_BYTE or packet[1] not in SSDV_PACKET_TYPES:
        raise ValueError("SSDV packet marker is invalid")

    width = packet[9] << 4
    height = packet[10] << 4
    if not width or not height:
        raise ValueError("SSDV image dimensions are invalid")

    callsign_code = int.from_bytes(packet[2:6], "big")
    return SSDVPacketInfo(
        callsign=decode_callsign(callsign_code),
        callsign_code=callsign_code,
        image_id=packet[6],
        packet_id=int.from_bytes(packet[7:9], "big"),
        width=width,
        height=height,
        eoi=bool((packet[11] >> 2) & 1),
        packet_type=packet[1] - 0x66,
    )


def _packet_crc_is_valid(packet: bytes) -> bool:
    """Check the uncorrected SSDV CRC for normal and no-FEC packet forms."""
    if packet[1] == 0x66:
        # Normal packets: bytes 1..219 are CRC-covered, followed by four CRC
        # bytes and 32 Reed-Solomon parity bytes.
        crc_end = 220
    elif packet[1] == 0x67:
        # No-FEC packets have a longer payload and end directly after the CRC.
        crc_end = 252
    else:
        return False

    expected_crc = int.from_bytes(packet[crc_end : crc_end + 4], "big")
    return zlib.crc32(packet[1:crc_end]) == expected_crc


def recover_ssdv_packet(packet: bytes) -> Optional[bytes]:
    """Validate an SSDV packet and repair correctable normal-packet errors.

    The BPSK deframer only sees SSDV's short 0x55 sync byte. A full protocol
    check is therefore required before allocating image state. Normal packets
    can repair up to 16 erroneous bytes; no-FEC packets must pass their CRC as
    received. ``None`` means the candidate is not an SSDV packet.
    """
    if len(packet) != SSDV_PACKET_SIZE or packet[0] != SSDV_SYNC_BYTE:
        return None

    # A direct CRC check is cheap and covers the usual error-free case.
    if _packet_crc_is_valid(packet):
        return packet

    # The no-FEC form has no way to repair a damaged packet. The normal form
    # stores its 255-byte shortened RS codeword after the 0x55 sync marker.
    if packet[1] != 0x66:
        return None

    try:
        _, corrected_codeword, _ = _SSDV_RS_CODEC.decode(packet[1:])
    except ReedSolomonError:
        return None

    corrected = bytes([SSDV_SYNC_BYTE]) + bytes(corrected_codeword)
    if corrected[1] != 0x66 or not _packet_crc_is_valid(corrected):
        return None
    return corrected


@dataclass
class SSDVImage:
    """Packet store for one image transmission."""

    info: SSDVPacketInfo
    started_at: float
    packets: Dict[int, bytes] = field(default_factory=dict)
    eoi_received: bool = False
    last_render_at: float = 0.0
    render_revision: int = 0

    def add_packet(self, packet: bytes, info: SSDVPacketInfo) -> bool:
        """Store a new packet, returning False for a retransmitted packet."""
        if info.packet_id in self.packets:
            return False
        self.packets[info.packet_id] = packet
        self.eoi_received = self.eoi_received or info.eoi
        return True

    @property
    def missing_packets(self) -> int:
        """Return gaps up to the last received packet, when known."""
        if not self.packets:
            return 0
        return max(self.packets) + 1 - len(self.packets)

    def encoded_packets(self) -> bytes:
        """Return ordered packets for the reference SSDV decoder."""
        return b"".join(self.packets[packet_id] for packet_id in sorted(self.packets))


class SSDVDecoder(BPSKDecoder):
    """Receive standard 256-byte SSDV packets over the BPSK raw-IQ path.

    The PHY is deliberately BPSK for the first release, matching OBJECT AY's
    active 9600-baud downlink.  Future FSK/AFSK transport profiles can reuse
    the packet/image handling in this class without changing its artifact API.
    """

    def __init__(self, *args, **kwargs):
        if _BPSK_IMPORT_ERROR is not None:
            raise RuntimeError(
                "SSDV decoding requires GNU Radio BPSK support"
            ) from _BPSK_IMPORT_ERROR
        super().__init__(*args, **kwargs)
        self.images: Dict[Tuple[int, int], SSDVImage] = {}
        self.codec_path: Optional[str] = os.environ.get("GS_SSDV_BIN") or shutil.which("ssdv")
        self.framing = FramingType.SSDV
        self.packet_size = SSDV_PACKET_SIZE

    def _get_decoder_type_for_init(self) -> str:
        return "SSDV"

    def _get_decoder_type(self) -> str:
        return "ssdv"

    def _get_decoder_specific_metadata(self):
        return {
            "modulation_subtype": "BPSK",
            "packet_size": SSDV_PACKET_SIZE,
            "codec": "libssdv",
        }

    def _get_filename_params(self) -> str:
        return f"{self.baudrate}baud"

    def _get_parameters_string(self) -> str:
        return f"BPSK, {self.baudrate}baud, 256-byte SSDV"

    def _get_payload_protocol(self) -> str:
        return "ssdv"

    def _packet_basename(self, image: SSDVImage) -> str:
        callsign = image.info.callsign or f"station_{image.info.callsign_code:08x}"
        safe_callsign = "".join(character for character in callsign if character.isalnum())
        started = time.strftime("%Y%m%d_%H%M%S", time.localtime(image.started_at))
        return f"ssdv_{safe_callsign or 'unknown'}_{image.info.image_id:03d}_{started}"

    def _write_raw_packets(self, image: SSDVImage) -> Path:
        path = Path(self.output_dir) / f"{self._packet_basename(image)}.ssdv"
        temporary = path.with_suffix(".ssdv.tmp")
        temporary.write_bytes(image.encoded_packets())
        temporary.replace(path)
        return path

    def _render_jpeg(self, raw_path: Path, jpeg_path: Path) -> bool:
        """Run the reference decoder and atomically publish a usable JPEG."""
        if not self.codec_path:
            logger.error("SSDV codec is unavailable; expected /usr/local/bin/ssdv in Docker")
            return False

        temporary = jpeg_path.with_suffix(".jpg.tmp")
        try:
            result = subprocess.run(
                [self.codec_path, "-d", str(raw_path), str(temporary)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                logger.warning("SSDV codec rejected image packets: %s", result.stderr.strip())
                return False
            if not temporary.exists() or temporary.stat().st_size < 4:
                return False
            if not temporary.read_bytes().startswith(b"\xff\xd8"):
                logger.debug("SSDV codec has not produced a JPEG preview yet")
                return False
            temporary.replace(jpeg_path)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("SSDV codec timed out while rendering %s", raw_path.name)
            return False
        except OSError as error:
            logger.error("Unable to run SSDV codec: %s", error)
            return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _emit_image(self, image: SSDVImage) -> None:
        raw_path = self._write_raw_packets(image)
        jpeg_path = Path(self.output_dir) / f"{self._packet_basename(image)}.jpg"
        if not self._render_jpeg(raw_path, jpeg_path):
            return

        image.render_revision += 1
        decode_timestamp = time.time()
        jpeg_bytes = jpeg_path.read_bytes()
        metadata = {
            "image": {
                "filename": jpeg_path.name,
                "filepath": str(jpeg_path),
                "raw_packets": raw_path.name,
                "format": "image/jpeg",
                "width": image.info.width,
                "height": image.info.height,
                "filesize": len(jpeg_bytes),
                "timestamp": decode_timestamp,
                "timestamp_iso": time.strftime(
                    "%Y-%m-%dT%H:%M:%S%z", time.localtime(decode_timestamp)
                ),
            },
            "decoder": {
                "type": "ssdv",
                "session_id": self.session_id,
                "baudrate": self.baudrate,
                "modulation": "BPSK",
            },
            "ssdv": {
                "callsign": image.info.callsign,
                "image_id": image.info.image_id,
                "packets_received": len(image.packets),
                "missing_packets": image.missing_packets,
                "eoi_received": image.eoi_received,
                "revision": image.render_revision,
            },
            "signal": self._get_signal_metadata(self._get_vfo_state()),
            "vfo": self._get_vfo_metadata(self._get_vfo_state()),
            "satellite": self._get_satellite_metadata(),
            "transmitter": self._get_transmitter_metadata(),
        }
        metadata_path = jpeg_path.with_suffix(".json")
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        message = {
            "type": "decoder-output",
            "decoder_type": "ssdv",
            "session_id": self.session_id,
            "vfo": self.vfo,
            "timestamp": decode_timestamp,
            "output": {
                "format": "image/jpeg",
                "filename": jpeg_path.name,
                "filepath": str(jpeg_path),
                "metadata_filename": metadata_path.name,
                "metadata_filepath": str(metadata_path),
                "image_data": base64.b64encode(jpeg_bytes).decode("ascii"),
                "width": image.info.width,
                "height": image.info.height,
                "filesize": len(jpeg_bytes),
                "mode": f"SSDV image {image.info.image_id}",
                "parameters": self._get_parameters_string(),
                "ssdv": metadata["ssdv"],
                "decoder_config": self._get_decoder_config_metadata(),
                "signal": self._get_signal_metadata(self._get_vfo_state()),
            },
        }
        try:
            self.data_queue.put(message, block=False)
            with self.stats_lock:
                self.stats["data_messages_out"] += 1
                self.stats["images_decoded"] = self.stats.get("images_decoded", 0) + 1
        except queue.Full:
            logger.warning("Data queue full, dropping SSDV image update")

    def _on_packet_decoded(self, payload: bytes, callsigns=None) -> None:
        """Store each framed SSDV packet and publish periodic image previews."""
        packet = recover_ssdv_packet(payload)
        if packet is None:
            logger.debug("Discarded SSDV candidate that failed CRC/FEC validation")
            return

        try:
            info = parse_ssdv_packet(packet)
        except ValueError as error:
            logger.debug("Discarded invalid SSDV candidate: %s", error)
            return

        image = self.images.get(info.image_key)
        if image is None:
            image = SSDVImage(info=info, started_at=time.time())
            self.images[info.image_key] = image
            self._send_status_update(
                SSDVStatus.CAPTURING,
                {"image_id": info.image_id, "callsign": info.callsign},
            )

        if not image.add_packet(packet, info):
            return

        self.packet_count += 1
        with self.stats_lock:
            self.stats["packets_decoded"] = self.packet_count

        now = time.time()
        if image.eoi_received or now - image.last_render_at >= SSDV_RENDER_INTERVAL_SECONDS:
            image.last_render_at = now
            self._emit_image(image)


__all__ = [
    "SSDVDecoder",
    "SSDVImage",
    "SSDVPacketInfo",
    "decode_callsign",
    "parse_ssdv_packet",
]
