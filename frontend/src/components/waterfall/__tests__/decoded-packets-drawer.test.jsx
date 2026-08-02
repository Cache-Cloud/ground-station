import { describe, expect, it } from 'vitest';
import { mapOutputsToRows } from '../decoded-packets-drawer.jsx';

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
