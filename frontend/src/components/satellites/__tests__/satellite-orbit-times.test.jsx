import { describe, expect, it } from 'vitest';

import { normalizeSatelliteFormValues } from '../satellite-edit-dialog.jsx';
import { DEFAULT_CATALOG_COLUMN_VISIBILITY } from '../satellite-table.jsx';
import { formatAlternativeSatelliteNames } from '../../common/satellite-names.js';

describe('satellite orbit timestamps', () => {
    it('normalizes orbit lifecycle timestamps for the edit dialog', () => {
        const values = normalizeSatelliteFormValues({
            norad_id: 25544,
            orbit_epoch: '2026-09-30T01:00:00+00:00',
            orbit_fetched_at: '2026-09-30T01:05:00+00:00',
            orbit_first_seen_at: '2026-09-01T10:00:00+00:00',
            orbit_changed_at: '2026-09-30T01:05:00+00:00',
        });

        expect(values).toMatchObject({
            orbit_epoch: '2026-09-30T01:00:00+00:00',
            orbit_fetched_at: '2026-09-30T01:05:00+00:00',
            orbit_first_seen_at: '2026-09-01T10:00:00+00:00',
            orbit_changed_at: '2026-09-30T01:05:00+00:00',
        });
    });

    it('hides the requested catalog columns by default', () => {
        expect(DEFAULT_CATALOG_COLUMN_VISIBILITY).toEqual({
            alternative_names: false,
            deployed: false,
            orbit_first_seen_at: false,
            orbit_changed_at: false,
        });
    });

    it('merges both persisted alternative-name fields without duplicates', () => {
        expect(formatAlternativeSatelliteNames('ISS', 'ZARYA')).toBe('ISS, ZARYA');
        expect(formatAlternativeSatelliteNames('ISS', 'iss')).toBe('ISS');
    });
});
