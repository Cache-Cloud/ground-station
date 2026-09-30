import { describe, expect, it } from 'vitest';
import { mapOutputsToRows, resolveDecodedAssetUrl } from '../decoded-packets-drawer.jsx';

const packet = (timestamp) => ({
    id: `output_${timestamp}`,
    type: 'decoder-output',
    timestamp,
    decoder_type: 'gmsk',
    output: {
        callsigns: {},
    },
});

describe('mapOutputsToRows', () => {
    it('keeps the newest live packets when history exceeds the visible limit', () => {
        // The decoder store is newest-first, matching decoderOutputReceived.
        const newestFirstOutputs = Array.from({ length: 100 }, (_, index) => packet(100 - index));

        const rows = mapOutputsToRows(newestFirstOutputs, 50);

        expect(rows).toHaveLength(50);
        expect(rows.map((row) => row.timestamp / 1000)).toEqual(
            Array.from({ length: 50 }, (_, index) => index + 51),
        );
    });
});

describe('resolveDecodedAssetUrl', () => {
    it('routes scheduled decoder artifacts through their observation bundle', () => {
        const filepath = '/opt/ground-station/backend/data/observations/ISS Pass.gsobs/decoded/aprs packet.json';

        expect(resolveDecodedAssetUrl(filepath, 'aprs packet.json')).toBe(
            '/observations/ISS%20Pass.gsobs/decoded/aprs%20packet.json',
        );
    });

    it('routes manual decoder artifacts through the shared decoded directory', () => {
        const filepath = 'data/decoded/aprs_1200baud_20260731_213604_054488.json';

        expect(resolveDecodedAssetUrl(filepath, 'fallback.json')).toBe(
            '/decoded/aprs_1200baud_20260731_213604_054488.json',
        );
    });

    it('falls back to the emitted filename for older decoder messages', () => {
        expect(resolveDecodedAssetUrl(undefined, 'packet name.json')).toBe(
            '/decoded/packet%20name.json',
        );
    });
});
