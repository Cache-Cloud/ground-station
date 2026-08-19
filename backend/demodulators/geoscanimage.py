"""Raw-IQ JPEG image receiver for the Geoscan/Alferov image downlink.

This receiver is intentionally independent of the project's general FSK
decoder. Alferov images use 9k6 FSK, Geoscan framing (PN9 + CC11xx CRC), and
54-byte JPEG fragments in 74-byte air frames.
"""

import argparse
import base64
import gc
import io
import json
import logging
import os
import queue
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from PIL import Image, ImageFile
from scipy import signal

from constants import FramingType
from demodulators.basedecoderprocess import BaseDecoderProcess

try:  # Keep the pure frame parser testable on hosts without the DSP stack.
    from gnuradio import blocks, gr
    from satellites.components.deframers.geoscan_deframer import geoscan_deframer
    from satellites.components.demodulators.fsk_demodulator import fsk_demodulator

    _DSP_IMPORT_ERROR = None
except ImportError as error:  # pragma: no cover - only used by non-DSP installs
    blocks = gr = geoscan_deframer = fsk_demodulator = None
    _DSP_IMPORT_ERROR = error


logger = logging.getLogger("geoscanimage")

GEOSCAN_AIR_FRAME_SIZE = 74
GEOSCAN_PAYLOAD_SIZE = 72  # CC11xx CRC is removed by geoscan_deframer.
GEOSCAN_IMAGE_MARKER = b"1oko"
GEOSCAN_IMAGE_DATA_SIZE = 54
MAX_JPEG_OFFSET = 20 * 1024 * 1024
PREVIEW_INTERVAL_SECONDS = 2.0
PROGRESS_LOG_INTERVAL_SECONDS = 5.0


class GeoscanImageStatus(Enum):
    LISTENING = "listening"
    DECODING = "decoding"
    CAPTURING = "capturing"
    ERROR = "error"


@dataclass(frozen=True)
class GeoscanImageFragment:
    """One validated JPEG fragment from a CRC-valid Geoscan frame."""

    satellite_id: int
    image_id: int
    offset: int
    data: bytes


def parse_geoscan_image_fragment(
    payload: bytes, satellite_id: Optional[int] = 9
) -> GeoscanImageFragment:
    """Validate and extract an Alferov/Geoscan V2 image fragment.

    The outer Geoscan deframer performs PN9 descrambling and CC11xx CRC
    verification.  These checks protect the image store from valid but
    unrelated Geoscan packets and from malformed offsets.
    """
    if len(payload) != GEOSCAN_PAYLOAD_SIZE:
        raise ValueError(f"Geoscan payload must be {GEOSCAN_PAYLOAD_SIZE} bytes")
    if satellite_id is not None and payload[0] != satellite_id:
        raise ValueError(f"unexpected satellite id {payload[0]:#x}")
    if payload[5:9] != GEOSCAN_IMAGE_MARKER:
        raise ValueError("not a Geoscan JPEG image frame")

    offset = int.from_bytes(payload[9:13], "little")
    if offset > MAX_JPEG_OFFSET or offset + GEOSCAN_IMAGE_DATA_SIZE > MAX_JPEG_OFFSET:
        raise ValueError("JPEG fragment offset exceeds safety limit")

    return GeoscanImageFragment(
        satellite_id=payload[0],
        image_id=int.from_bytes(payload[13:15], "little"),
        offset=offset,
        data=payload[15 : 15 + GEOSCAN_IMAGE_DATA_SIZE],
    )


@dataclass
class GeoscanImageAssembly:
    """Sparse JPEG reassembly state for one image/file number."""

    satellite_id: int
    image_id: int
    started_at: float
    fragments: Dict[int, bytes] = field(default_factory=dict)
    last_render_at: float = 0.0
    revision: int = 0

    def add(self, fragment: GeoscanImageFragment) -> bool:
        """Store a fragment, returning False when it is a retransmission."""
        if fragment.offset in self.fragments:
            return False
        self.fragments[fragment.offset] = fragment.data
        return True

    @property
    def received_bytes(self) -> int:
        return sum(len(data) for data in self.fragments.values())

    @property
    def jpeg_size(self) -> int:
        return max((offset + len(data) for offset, data in self.fragments.items()), default=0)

    @property
    def coverage_percent(self) -> float:
        return (100.0 * self.received_bytes / self.jpeg_size) if self.jpeg_size else 0.0

    def jpeg_bytes(self) -> bytes:
        """Materialize the sparse fragments without accepting an unbounded offset."""
        size = self.jpeg_size
        if size > MAX_JPEG_OFFSET:
            raise ValueError("JPEG assembly exceeds safety limit")
        jpeg = bytearray(size)
        for offset, data in self.fragments.items():
            jpeg[offset : offset + len(data)] = data
        return bytes(jpeg)


if gr is not None:

    class GeoscanMessageHandler(gr.basic_block):
        """Bridge Geoscan PDUs into the isolated image reassembler."""

        def __init__(self, callback):
            gr.basic_block.__init__(
                self, name="geoscan_image_message_handler", in_sig=None, out_sig=None
            )
            self.callback = callback
            self.message_port_register_in(gr.pmt.intern("in"))
            self.set_msg_handler(gr.pmt.intern("in"), self.handle_msg)

        def handle_msg(self, message):
            try:
                value = (
                    gr.pmt.to_python(gr.pmt.cdr(message))
                    if gr.pmt.is_pair(message)
                    else gr.pmt.to_python(message)
                )
                if isinstance(value, np.ndarray):
                    value = bytes(value)
                if isinstance(value, bytes):
                    self.callback(value)
            except Exception as error:
                logger.debug("Unable to read Geoscan PDU: %s", error)


class GeoscanImageDecoder(BaseDecoderProcess):
    """Independent raw-IQ Geoscan image decoder with per-batch DSP graphs."""

    def __init__(self, *args, batch_interval: float = 5.0, **kwargs):
        if _DSP_IMPORT_ERROR is not None:
            raise RuntimeError(
                "Geoscan image decoding requires GNU Radio and gr-satellites"
            ) from _DSP_IMPORT_ERROR
        super().__init__(*args, **kwargs)
        self.baudrate = self._positive_int(getattr(self.config, "baudrate", 9600), 9600)
        self.deviation = self._positive_int(getattr(self.config, "deviation", 5000), 5000)
        params = getattr(self.config, "framing_params", None) or {}
        self.frame_size = self._bounded_int(
            params.get("frame_size"), GEOSCAN_AIR_FRAME_SIZE, 16, 512
        )
        self.syncword_threshold = self._bounded_int(params.get("syncword_threshold"), 4, 0, 32)
        configured_id = params.get("satellite_id", 9)
        self.satellite_id = (
            None if configured_id is None else self._bounded_int(configured_id, 9, 0, 255)
        )
        self.batch_interval = max(float(batch_interval), 0.5)
        self.sample_rate: Optional[float] = None
        self.sdr_sample_rate: Optional[float] = None
        self.sdr_center_freq: Optional[float] = None
        self.decimation = 1
        self.sample_buffer = np.empty(0, dtype=np.complex64)
        self.batch_vfo = None
        self.images: Dict[tuple[int, int], GeoscanImageAssembly] = {}
        self._accepted_since_log = 0
        self._last_progress_log_at = 0.0
        self.power_measurements: list[float] = []
        self.max_power_history = 100
        self.current_power_dbfs = None
        self.logger = logger
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def _positive_int(value, default: int) -> int:
        try:
            value = int(value)
            return value if value > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(int(value), maximum))
        except (TypeError, ValueError):
            return default

    def _get_decoder_type_for_init(self) -> str:
        return "GeoscanImage"

    def _get_decoder_type(self) -> str:
        return "geoscanimage"

    def _vfo_state(self):
        return self.batch_vfo or {}

    def _send_status(self, status: GeoscanImageStatus, extra: Optional[dict] = None) -> None:
        info = {
            "baudrate": self.baudrate,
            "deviation_hz": self.deviation,
            "frame_size": self.frame_size,
            "syncword_threshold": self.syncword_threshold,
            "satellite_id": self.satellite_id,
            "framing": FramingType.GEOSCAN,
            "images": len(self.images),
            "fragments": self.packet_count,
        }
        if extra:
            info.update(extra)
        self._put(
            {
                "type": "decoder-status",
                "status": status.value,
                "decoder_type": self._get_decoder_type(),
                "decoder_id": self.decoder_id,
                "session_id": self.session_id,
                "vfo": self.vfo,
                "timestamp": time.time(),
                "info": info,
            }
        )

    def _put(self, message: dict) -> None:
        try:
            self.data_queue.put(message, block=False)
            with self.stats_lock:
                self.stats["data_messages_out"] = self.stats.get("data_messages_out", 0) + 1
        except queue.Full:
            self.logger.warning("Data queue full, dropping Geoscan image update")

    def _configure_rate(self, sdr_rate: float) -> None:
        self.sdr_sample_rate = sdr_rate
        self.decimation = max(1, int(sdr_rate / (self.baudrate * 8)))
        self.sample_rate = sdr_rate / self.decimation
        self.logger.info(
            "Geoscan image receiver: %dbd, %.0fS/s (%dsps), dev=%dHz, frame=%dB, sync=%d",
            self.baudrate,
            self.sample_rate,
            round(self.sample_rate / self.baudrate),
            self.deviation,
            self.frame_size,
            self.syncword_threshold,
        )

    def _translate_and_decimate(self, samples: np.ndarray, offset: float) -> np.ndarray:
        if offset:
            sdr_sample_rate = self.sdr_sample_rate
            if sdr_sample_rate is None:
                raise RuntimeError("received IQ before the SDR sample rate was configured")
            time_axis = np.arange(len(samples), dtype=np.float64) / sdr_sample_rate
            samples = samples * np.exp(-2j * np.pi * offset * time_axis)
        power = self._measure_signal_power(samples)
        self._update_power_measurement(power)
        if self.decimation > 1:
            samples = signal.resample_poly(samples, up=1, down=self.decimation)
        return np.asarray(samples, dtype=np.complex64)

    def _process_batch(self) -> None:
        if not len(self.sample_buffer):
            return
        samples, self.sample_buffer = self.sample_buffer, np.empty(0, dtype=np.complex64)
        source = demod = deframer = handler = tb = None
        try:
            tb = gr.top_block("Geoscan Image Batch")
            source = blocks.vector_source_c(samples.tolist(), repeat=False)
            options = argparse.Namespace(
                clk_bw=0.06,
                clk_limit=0.004,
                deviation=self.deviation,
                use_agc=True,
                disable_dc_block=False,
                syncword_threshold=self.syncword_threshold,
            )
            demod = fsk_demodulator(
                baudrate=self.baudrate,
                samp_rate=self.sample_rate,
                iq=True,
                deviation=self.deviation,
                subaudio=False,
                dc_block=True,
                dump_path=None,
                options=options,
            )
            deframer = geoscan_deframer(
                frame_size=self.frame_size,
                syncword_threshold=self.syncword_threshold,
                options=options,
            )
            handler = GeoscanMessageHandler(self._on_geoscan_frame)
            tb.connect(source, demod, deframer)
            tb.msg_connect((deframer, "out"), (handler, "in"))
            tb.start()
            tb.wait()
        except Exception as error:
            self.logger.exception("Geoscan image flowgraph batch failed: %s", error)
            with self.stats_lock:
                self.stats["errors"] += 1
        finally:
            if tb is not None:
                try:
                    tb.stop()
                    tb.wait()
                    tb.disconnect_all()
                except Exception:
                    pass
            del source, demod, deframer, handler, tb
            gc.collect()

    def _assembly_basename(self, assembly: GeoscanImageAssembly) -> str:
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(assembly.started_at))
        return f"geoscan_{assembly.satellite_id:02x}_{assembly.image_id:05d}_{stamp}"

    def _emit_preview(self, assembly: GeoscanImageAssembly) -> None:
        raw = assembly.jpeg_bytes()
        start = raw.find(b"\xff\xd8")
        if start < 0:
            return
        raw = raw[start:]
        basename = self._assembly_basename(assembly)
        raw_path = Path(self.output_dir) / f"{basename}.jpg.part"
        raw_path.write_bytes(raw)

        # Fragment loss leaves zero-filled JPEG gaps.  Pillow can still render
        # useful partial previews, but bad random dimensions must be rejected.
        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    image.thumbnail((1600, 1600))
                    width, height = image.size
                    preview_path = Path(self.output_dir) / f"{basename}.jpg"
                    image.convert("RGB").save(preview_path, "JPEG", quality=90)
        except (OSError, ValueError, Image.DecompressionBombWarning):
            return

        assembly.revision += 1
        jpeg = preview_path.read_bytes()
        timestamp = time.time()
        coverage = round(assembly.coverage_percent, 1)
        metadata = {
            "image": {
                "filename": preview_path.name,
                "filepath": str(preview_path),
                "format": "image/jpeg",
                "width": width,
                "height": height,
                "filesize": len(jpeg),
                "timestamp": timestamp,
            },
            "decoder": {
                "type": self._get_decoder_type(),
                "session_id": self.session_id,
                "baudrate": self.baudrate,
                "modulation": "FSK",
            },
            "geoscan": {
                "satellite_id": assembly.satellite_id,
                "image_id": assembly.image_id,
                "fragments": len(assembly.fragments),
                "received_bytes": assembly.received_bytes,
                "jpeg_size": assembly.jpeg_size,
                "coverage_percent": coverage,
                "raw_fragments": raw_path.name,
                "revision": assembly.revision,
            },
        }
        metadata_path = preview_path.with_suffix(".json")
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        self._put(
            {
                "type": "decoder-output",
                "decoder_type": self._get_decoder_type(),
                "session_id": self.session_id,
                "vfo": self.vfo,
                "timestamp": timestamp,
                "output": {
                    "format": "image/jpeg",
                    "filename": preview_path.name,
                    "filepath": str(preview_path),
                    "metadata_filename": metadata_path.name,
                    "metadata_filepath": str(metadata_path),
                    "image_data": base64.b64encode(jpeg).decode("ascii"),
                    "width": width,
                    "height": height,
                    "filesize": len(jpeg),
                    "mode": f"Geoscan image {assembly.image_id}",
                    "parameters": f"FSK {self.baudrate} baud, {self.deviation} Hz deviation",
                    "geoscan": metadata["geoscan"],
                },
            }
        )

    def _on_geoscan_frame(self, payload: bytes) -> None:
        try:
            fragment = parse_geoscan_image_fragment(payload, self.satellite_id)
        except ValueError:
            return
        key = fragment.satellite_id, fragment.image_id
        assembly = self.images.get(key)
        if assembly is None:
            assembly = GeoscanImageAssembly(fragment.satellite_id, fragment.image_id, time.time())
            self.images[key] = assembly
            self._send_status(GeoscanImageStatus.CAPTURING, {"image_id": fragment.image_id})
        if not assembly.add(fragment):
            return
        self.packet_count += 1
        self._accepted_since_log += 1
        with self.stats_lock:
            self.stats["packets_decoded"] = self.packet_count
        now = time.time()
        # A good pass contains hundreds of fragments.  Report confirmed
        # reception and reassembly progress without turning it into log spam.
        if now - self._last_progress_log_at >= PROGRESS_LOG_INTERVAL_SECONDS:
            self.logger.info(
                "Geoscan image fragments accepted: +%d image=%d fragments=%d coverage=%.1f%%",
                self._accepted_since_log,
                fragment.image_id,
                len(assembly.fragments),
                assembly.coverage_percent,
            )
            self._accepted_since_log = 0
            self._last_progress_log_at = now
        if now - assembly.last_render_at >= PREVIEW_INTERVAL_SECONDS:
            assembly.last_render_at = now
            self._emit_preview(assembly)

    def _send_stats(self) -> None:
        with self.stats_lock:
            stats = self.stats.copy()
        stats.update(
            {
                "fragments_decoded": self.packet_count,
                "images": len(self.images),
                "baudrate": self.baudrate,
                "deviation": self.deviation,
            }
        )
        stats.update(self._get_power_statistics())
        self._put(
            {
                "type": "decoder-stats",
                "decoder_type": self._get_decoder_type(),
                "session_id": self.session_id,
                "vfo": self.vfo,
                "timestamp": time.time(),
                "stats": stats,
                "perf_stats": stats,
            }
        )

    def run(self) -> None:
        self.stats = {
            "iq_chunks_in": 0,
            "samples_in": 0,
            "packets_decoded": 0,
            "data_messages_out": 0,
            "errors": 0,
            "queue_timeouts": 0,
        }
        self._send_status(GeoscanImageStatus.LISTENING)
        last_stats = time.time()
        try:
            while self.running.value == 1:
                try:
                    message = self.iq_queue.get(timeout=0.2)
                except queue.Empty:
                    with self.stats_lock:
                        self.stats["queue_timeouts"] += 1
                    message = None
                if message:
                    samples = message.get("samples")
                    rate = message.get("sample_rate")
                    center = message.get("logical_center_freq_hz", message.get("center_freq"))
                    state = message.get("vfo_states", {}).get(self.vfo)
                    if (
                        samples is not None
                        and len(samples)
                        and rate
                        and center
                        and state
                        and state.get("active")
                    ):
                        if self.sample_rate is None:
                            self._configure_rate(rate)
                            self.sdr_center_freq = center
                        offset = float(state.get("center_freq", center)) - float(center)
                        converted = self._translate_and_decimate(
                            np.asarray(samples, dtype=np.complex64), offset
                        )
                        self.sample_buffer = np.concatenate((self.sample_buffer, converted))
                        self.batch_vfo = state
                        with self.stats_lock:
                            self.stats["iq_chunks_in"] += 1
                            self.stats["samples_in"] += len(samples)
                        sample_rate = self.sample_rate
                        if sample_rate is None:
                            continue
                        if len(self.sample_buffer) >= int(sample_rate * self.batch_interval):
                            self._process_batch()
                            self._monitor_shared_memory()
                if time.time() - last_stats >= 1.0:
                    self._send_stats()
                    last_stats = time.time()
        except Exception as error:
            self.logger.exception("Geoscan image decoder stopped after error: %s", error)
            self._send_status(GeoscanImageStatus.ERROR, {"error": str(error)})
        finally:
            self._process_batch()
            # A recording can feed its final batch much faster than wall time.
            # Publish its best assembled preview even when the periodic timer
            # did not get another chance to run.
            for assembly in self.images.values():
                self._emit_preview(assembly)
            self._put(
                {
                    "type": "decoder-status",
                    "status": "closed",
                    "decoder_type": self._get_decoder_type(),
                    "decoder_id": self.decoder_id,
                    "session_id": self.session_id,
                    "vfo": self.vfo,
                    "timestamp": time.time(),
                    "restart_requested": self.should_restart(),
                }
            )


__all__ = [
    "GeoscanImageAssembly",
    "GeoscanImageDecoder",
    "GeoscanImageFragment",
    "parse_geoscan_image_fragment",
]
