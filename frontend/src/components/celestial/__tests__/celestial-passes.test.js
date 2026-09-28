import { describe, expect, it } from 'vitest';

import {
    calculateProjectionProgress,
    calculateProjectionRemainingSeconds,
    getCelestialPassStatus,
    resolvePassBoundaryNowMs,
} from '../celestial-passes.jsx';

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

describe('calculateProjectionProgress', () => {
    it('advances on the five-second celestial update cadence', () => {
        const row = { eventStartMs: 0, eventEndMs: 100_000 };

        expect(calculateProjectionProgress(row, 12_000)).toBe(10);
        expect(calculateProjectionProgress(row, 14_999)).toBe(10);
        expect(calculateProjectionProgress(row, 15_000)).toBe(15);
    });

    it('clamps progress at the projection boundaries', () => {
        const row = { eventStartMs: 10_000, eventEndMs: 20_000 };

        expect(calculateProjectionProgress(row, 0)).toBe(0);
        expect(calculateProjectionProgress(row, 25_000)).toBe(100);
    });
});

describe('calculateProjectionRemainingSeconds', () => {
    it('counts down to the fixed projection boundary', () => {
        const row = { eventEndMs: 100_000 };

        expect(calculateProjectionRemainingSeconds(row, 40_000)).toBe(60);
        expect(calculateProjectionRemainingSeconds(row, 45_000)).toBe(55);
    });

    it('stops at zero after the projection boundary', () => {
        expect(calculateProjectionRemainingSeconds({ eventEndMs: 100_000 }, 105_000)).toBe(0);
    });
});

describe('resolvePassBoundaryNowMs', () => {
    it('uses the backend scene timestamp for pass-boundary labels', () => {
        expect(resolvePassBoundaryNowMs('2026-01-01T12:00:05Z', 123)).toBe(
            Date.parse('2026-01-01T12:00:05Z'),
        );
    });

    it('falls back to the browser clock when the scene timestamp is unavailable', () => {
        expect(resolvePassBoundaryNowMs('', 456)).toBe(456);
    });
});
