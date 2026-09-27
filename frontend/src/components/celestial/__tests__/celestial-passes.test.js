import { describe, expect, it } from 'vitest';

import { getCelestialPassStatus } from '../celestial-passes.jsx';

describe('getCelestialPassStatus', () => {
    it('reports an elapsed projection boundary as expired instead of a completed pass', () => {
        const now = Date.parse('2026-01-01T12:00:00Z');

        expect(getCelestialPassStatus({
            eventStartMs: now - 60_000,
            eventEndMs: now - 1,
            estimatedEnd: true,
        }, now)).toBe('projection-expired');
    });

    it('reports a real elapsed LOS as passed', () => {
        const now = Date.parse('2026-01-01T12:00:00Z');

        expect(getCelestialPassStatus({
            eventStartMs: now - 120_000,
            eventEndMs: now - 60_000,
            estimatedEnd: false,
        }, now)).toBe('passed');
    });
});
