#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared deframer factories for decoder flowgraphs.

This module centralizes framing -> GNU Radio deframer construction so new
framing protocols can be added in one place.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from gnuradio import digital, gr
from satellites.components.deframers.ax25_deframer import ax25_deframer
from satellites.components.deframers.ax100_deframer import ax100_deframer
from satellites.components.deframers.ccsds_concatenated_deframer import ccsds_concatenated_deframer
from satellites.components.deframers.ccsds_rs_deframer import ccsds_rs_deframer
from satellites.components.deframers.geoscan_deframer import geoscan_deframer
from satellites.components.deframers.usp_deframer import usp_deframer
from satellites.hier.sync_to_pdu_packed import sync_to_pdu_packed

from constants import FramingType


class SSDVDeframer(gr.hier_block2):
    """Turn BPSK soft symbols into fixed SSDV packet PDUs."""

    def __init__(self):
        super().__init__(
            "SSDV Deframer",
            gr.io_signature(1, 1, gr.sizeof_float),
            gr.io_signature(0, 0, 0),
        )
        self.message_port_register_hier_out("out")
        self.slicer = digital.binary_slicer_fb()
        self.packet_sync = sync_to_pdu_packed(
            packlen=255,
            sync="01010101",  # SSDV's leading 0x55 marker, MSB first.
            # An eight-bit marker is intentionally exact: SSDV performs its
            # own FEC validation after packet extraction, and accepting a
            # fuzzy marker here creates too many false 256-byte candidates.
            threshold=0,
        )
        self.connect(self, self.slicer, self.packet_sync)
        self.msg_connect((self.packet_sync, "out"), (self, "out"))


def create_fsk_deframer(
    framing: str,
    options: Any,
    framing_params: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, str]:
    """Create FSK-family deframer block and human-readable frame info."""
    params = framing_params or {}

    if framing == FramingType.GEOSCAN:
        frame_size = int(params.get("frame_size", 66))
        syncword_thresh = int(params.get("syncword_threshold", 4))
        deframer = geoscan_deframer(
            frame_size=frame_size,
            syncword_threshold=syncword_thresh,
            options=options,
        )
        frame_info = f"GEOSCAN(sz={frame_size},sw_th={syncword_thresh},PN9,CC11xx)"
        return deframer, frame_info

    if framing == FramingType.USP:
        syncword_thresh = 20
        deframer = usp_deframer(syncword_threshold=syncword_thresh, options=options)
        frame_info = f"USP(sw_th={syncword_thresh},Vit+RS)"
        return deframer, frame_info

    if framing == FramingType.DOKA:
        deframer = ccsds_concatenated_deframer(options=options)
        return deframer, "DOKA(CCSDS)"

    if framing == FramingType.AX100_RS:
        deframer = ax100_deframer(mode="RS", options=options)
        return deframer, "AX100(RS)"

    if framing == FramingType.AX100_ASM:
        deframer = ax100_deframer(mode="ASM", scrambler="CCSDS", options=options)
        return deframer, "AX100(ASM+Golay)"

    deframer = ax25_deframer(g3ruh_scrambler=True, options=options)
    return deframer, "AX25(G3RUH)"


def create_bpsk_deframer(framing: str, options: Any) -> Tuple[Any, str]:
    """Create BPSK deframer block and human-readable frame info."""
    if framing == FramingType.SSDV:
        # SSDV packets are 256-byte blocks.  The sync block is consumed by
        # sync_to_pdu_packed, so the message handler restores the leading
        # 0x55 before handing the complete packet to the image decoder.
        deframer = SSDVDeframer()
        return deframer, "SSDV(sz=256,sw_th=0)"

    if framing == FramingType.DOKA:
        deframer = ccsds_rs_deframer(
            frame_size=223,
            precoding=None,
            rs_en=True,
            rs_basis="dual",
            rs_interleaving=1,
            scrambler="CCSDS",
            syncword_threshold=None,
            options=options,
        )
        return deframer, "CCSDS_RS(sz=223,dual)"

    deframer = ax25_deframer(g3ruh_scrambler=True, options=options)
    return deframer, "AX25(G3RUH)"
