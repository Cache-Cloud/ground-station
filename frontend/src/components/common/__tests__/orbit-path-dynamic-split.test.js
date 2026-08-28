import { describe, expect, it } from 'vitest';

import { resolveDynamicOrbitPathSegments } from '../orbit-path-dynamic-split.js';

describe('resolveDynamicOrbitPathSegments', () => {
    it('returns empty paths when neither source supplies points', () => {
        expect(resolveDynamicOrbitPathSegments({ pastPath: null, futurePath: [] })).toEqual({
            past: [],
            future: [],
        });
    });

    it('joins the shared current point and splits at the satellite position', () => {
        const result = resolveDynamicOrbitPathSegments({
            pastPath: [[1, 10], [2, 20]],
            futurePath: [[2, 20], [3, 30]],
            satellitePosition: { lat: 2.1, lon: 20.2 },
        });

        expect(result.past).toEqual([[{ lat: 1, lon: 10 }, { lat: 2, lon: 20 }]]);
        expect(result.future).toEqual([[{ lat: 2, lon: 20 }, { lat: 3, lon: 30 }]]);
    });

    it('accepts segmented object points, filters invalid entries, and protects dateline rendering', () => {
        const result = resolveDynamicOrbitPathSegments({
            pastPath: [[{ lat: '1', lng: '170', label: 'past' }, { lat: 'invalid', lon: 1 }]],
            futurePath: [[{ lat: 2, lon: -170, label: 'future' }]],
            satellitePosition: { lat: 2, lon: -170 },
        });

        expect(result.past).toEqual([[{ lat: 1, lon: 170, lng: '170', label: 'past' }], [{ lat: 2, lon: -170, label: 'future' }]]);
        expect(result.future).toEqual([[{ lat: 2, lon: -170, label: 'future' }]]);
    });

    it('uses the past/future boundary when no valid satellite position is provided', () => {
        const result = resolveDynamicOrbitPathSegments({
            pastPath: [[1, 10]],
            futurePath: [[2, 20]],
            satellitePosition: { lat: 'not-a-number', lon: 20 },
        });

        expect(result).toEqual({
            past: [[{ lat: 1, lon: 10 }]],
            future: [[{ lat: 1, lon: 10 }, { lat: 2, lon: 20 }]],
        });
    });
});
