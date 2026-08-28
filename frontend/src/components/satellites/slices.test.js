import { describe, expect, it } from 'vitest';

import satelliteReducer, {
    fetchSatellite,
    fetchSatelliteCatalogStats,
    submitOrEditSatellite,
} from './satellite-slice.jsx';
import groupsReducer, {
    AddOrEditSatelliteGroup,
    deleteSatelliteGroups,
    setDeleteConfirmDialogOpen,
} from './groups-slice.jsx';
import sourcesReducer, {
    deleteOrbitalSources,
    fetchOrbitalSources,
    setFormValues,
} from './sources-slice.jsx';

describe('satellite state slices', () => {
    it('loads a satellite with its transmitters and replaces saved satellite rows', () => {
        let state = satelliteReducer(undefined, { type: '@@INIT' });
        state = satelliteReducer(state, fetchSatellite.pending('request'));
        state = satelliteReducer(state, fetchSatellite.fulfilled({
            details: { id: 'sat-1', name: 'NOAA 19' },
            transmitters: [{ id: 'tx-1', frequency: 137100000 }],
        }, 'request'));
        state = satelliteReducer(state, submitOrEditSatellite.fulfilled([
            { id: 'sat-1', name: 'NOAA 19' },
        ], 'request'));
        state = satelliteReducer(state, fetchSatelliteCatalogStats.rejected(null, 'request'));

        expect(state).toMatchObject({
            status: 'succeeded',
            loading: false,
            catalogStats: null,
            satellites: [{ id: 'sat-1', name: 'NOAA 19' }],
            clickedSatellite: {
                name: 'NOAA 19',
                transmitters: [{ id: 'tx-1', frequency: 137100000 }],
            },
        });
    });

    it('normalizes source data returned from the orbital-source API and closes deletion confirmation', () => {
        let state = sourcesReducer(undefined, { type: '@@INIT' });
        state = sourcesReducer(state, setFormValues({ name: 'Weather TLEs', priority: '25' }));
        state = sourcesReducer(state, fetchOrbitalSources.fulfilled([{
            id: 'source-1',
            format: 'TLE',
            query_mode: 'URL',
            norad_ids: ['25338', 'invalid', 0],
            provider: 'CELESTRAK',
            enabled: 0,
            priority: '25',
            central_body: 'EARTH',
        }], 'request'));

        expect(state.tleSources).toEqual([expect.objectContaining({
            id: 'source-1',
            format: 'tle',
            query_mode: 'url',
            norad_ids: [25338],
            provider: 'celestrak',
            enabled: false,
            priority: 25,
            central_body: 'earth',
        })]);

        state = sourcesReducer(state, deleteOrbitalSources.fulfilled({ data: [] }, 'request'));

        expect(state).toMatchObject({
            loading: false,
            status: 'succeeded',
            formValues: { name: 'Weather TLEs', priority: '25' },
            tleSources: [],
            openDeleteConfirm: false,
        });
    });

    it('tracks group operation state for deletion and upsert outcomes', () => {
        let state = groupsReducer(undefined, { type: '@@INIT' });
        state = groupsReducer(state, setDeleteConfirmDialogOpen(true));
        state = groupsReducer(state, deleteSatelliteGroups.pending('request'));
        state = groupsReducer(state, deleteSatelliteGroups.fulfilled([{ id: 'group-2' }], 'request'));
        state = groupsReducer(state, AddOrEditSatelliteGroup.rejected(
            null,
            'request',
            undefined,
            'Group name already exists',
        ));

        expect(state).toMatchObject({
            loading: false,
            error: 'Group name already exists',
            groups: [{ id: 'group-2' }],
            deleteConfirmDialogOpen: true,
        });
    });
});
