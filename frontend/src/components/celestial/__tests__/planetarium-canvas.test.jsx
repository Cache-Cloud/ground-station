import { describe, expect, it } from 'vitest';
import { buildSkyObjects } from '../planetarium-canvas.jsx';

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
