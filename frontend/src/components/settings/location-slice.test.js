import { describe, expect, it } from 'vitest';

import reducer, {
    fetchLocationForUserId,
    setAltitude,
    storeLocation,
} from './location-slice.jsx';

describe('location slice', () => {
    it('normalizes persisted locations and derives the station grid locator', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, fetchLocationForUserId.pending('request'));
        state = reducer(state, fetchLocationForUserId.fulfilled({
            id: 'location-1',
            name: '  Athens  ',
            lat: '37.9838',
            lon: '23.7275',
            alt: 220,
            station_type: 'MOBILE',
            horizon_mask: 120,
        }, 'request'));

        expect(state).toMatchObject({
            locationLoading: false,
            locationId: 'location-1',
            altitude: 220,
            qth: 'KM17ux',
            location: { station_type: 'mobile', horizon_mask: 90 },
        });
    });

    it('clears an absent saved location and surfaces save failures', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, fetchLocationForUserId.fulfilled({
            id: 'location-1', lat: '0', lon: '0', alt: 10,
        }, 'request'));
        state = reducer(state, fetchLocationForUserId.fulfilled(null, 'request'));
        state = reducer(state, storeLocation.pending('request'));
        state = reducer(state, storeLocation.rejected(
            null,
            'request',
            undefined,
            'Could not save station',
        ));

        expect(state).toMatchObject({
            location: null,
            locationId: null,
            altitude: 0,
            qth: '',
            locationSaving: false,
            error: 'Could not save station',
        });
    });

    it('retains a manually saved zero altitude', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, setAltitude(257));
        state = reducer(state, storeLocation.fulfilled({
            id: 'location-1', lat: '37.9838', lon: '23.7275', alt: 0,
        }, 'request'));

        expect(state.altitude).toBe(0);
    });
});
