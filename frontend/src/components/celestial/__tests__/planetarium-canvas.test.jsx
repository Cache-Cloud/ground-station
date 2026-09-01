import { describe, expect, it } from 'vitest';
import { buildSkyObjects, getPassCurveDash } from '../planetarium-canvas.jsx';

describe('buildSkyObjects', () => {
    it('renders the observer Sun only while it is above the horizon', () => {
        const scene = {
            observer_bodies: [
                {
                    target_key: 'observer:sun',
                    name: 'Sun',
                    sky_position: { az_deg: 140, el_deg: 31.5 },
                    visibility: { visible: true },
                },
            ],
        };

        expect(buildSkyObjects(scene)).toEqual(expect.arrayContaining([
            expect.objectContaining({ key: 'observer:sun', kind: 'observer', name: 'Sun' }),
        ]));
    });

    it('does not render the observer Sun below the horizon', () => {
        const scene = {
            observer_bodies: [
                {
                    target_key: 'observer:sun',
                    name: 'Sun',
                    sky_position: { az_deg: 320, el_deg: -0.1 },
                    visibility: { visible: false },
                },
            ],
        };

        expect(buildSkyObjects(scene)).toHaveLength(0);
    });
});

describe('getPassCurveDash', () => {
    const nowMs = Date.parse('2026-09-01T12:00:00Z');

    it('renders future passes as dotted, including selected targets', () => {
        expect(getPassCurveDash({ startMs: nowMs + 60_000 }, nowMs, true)).toEqual([1, 4]);
        expect(getPassCurveDash({ startMs: nowMs + 60_000 }, nowMs, false)).toEqual([1, 4]);
    });

    it('keeps an active selected pass solid', () => {
        expect(getPassCurveDash({ startMs: nowMs - 60_000 }, nowMs, true)).toEqual([]);
    });
});
