import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {configureStore} from '@reduxjs/toolkit';
import {Provider} from 'react-redux';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';

import {setupTheme} from '../../../theme.js';
import {useSocket} from '../../common/socket.jsx';
import RotatorControl from '../../dashboard/rotator-control.jsx';
import rotatorReducer from '../../hardware/rotator-slice.jsx';
import targetReducer from '../target-slice.jsx';

vi.mock('../../common/socket.jsx', () => ({useSocket: vi.fn()}));
vi.mock('react-i18next', async importOriginal => ({
    ...await importOriginal(), useTranslation: () => ({t: key => key}),
}));

describe('rotator satellite tracking lead', () => {
    it('persists an island adjustment to the selected rotator definition', async () => {
        const targetInitial = targetReducer(undefined, {type: '@@init'});
        const trackingState = {
            rotator_id: 'mount',
            rotator_state: 'tracking',
            target_type: 'satellite',
            norad_id: 25544,
        };
        const view = {
            trackingState,
            confirmedTrackingState: trackingState,
            selectedRotator: 'mount',
            satelliteId: 25544,
            satelliteData: {position: {az: 120, el: 35}},
            rotatorData: {connected: true, tracking: true, az: 118, el: 34},
            hardwareObservedAt: Date.now(),
            hardwareReceivedAt: Date.now(),
        };
        const rotator = {
            id: 'mount',
            name: 'Az/El Mount',
            host: 'localhost',
            port: 4533,
            tracking_lead_seconds: 2,
        };
        const store = configureStore({
            reducer: {
                targetSatTrack: targetReducer,
                rotators: rotatorReducer,
                trackerInstances: () => ({
                    instances: [{tracker_id: 'target-1', rotator_id: 'mount', tracking_state: trackingState}],
                }),
                celestial: () => ({}),
            },
            preloadedState: {
                targetSatTrack: {
                    ...targetInitial,
                    trackerId: 'target-1',
                    trackerViews: {'target-1': view},
                },
                rotators: {
                    ...rotatorReducer(undefined, {type: '@@init'}),
                    rotators: [rotator],
                },
            },
            middleware: getDefault => getDefault({serializableCheck: false}),
        });
        const requests = [];
        const socket = {
            connected: true,
            on: vi.fn(),
            off: vi.fn(),
            timeout: () => ({emit: vi.fn()}),
            emit: (_event, request, ack) => {
                requests.push(request);
                ack({
                    success: true,
                    data: [{...rotator, tracking_lead_seconds: request.data.tracking_lead_seconds}],
                });
            },
        };
        useSocket.mockReturnValue({socket});

        render(
            <Provider store={store}>
                <ThemeProvider theme={setupTheme()}>
                    <RotatorControl />
                </ThemeProvider>
            </Provider>
        );

        const slider = screen.getByRole('slider', {name: 'rotator_control.tracking_lead'});
        fireEvent.change(slider, {
            target: {value: '4.5'},
        });
        fireEvent.mouseUp(slider);

        await waitFor(() => expect(requests).toHaveLength(1));
        expect(requests[0]).toEqual({
            cmd: 'edit-rotator',
            data: {id: 'mount', tracking_lead_seconds: 4.5},
        });
        await waitFor(() => {
            expect(store.getState().rotators.rotators[0].tracking_lead_seconds).toBe(4.5);
        });
    });
});
