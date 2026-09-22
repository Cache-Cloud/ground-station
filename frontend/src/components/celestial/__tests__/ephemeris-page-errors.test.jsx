/**
 * @license
 * Copyright (c) 2025 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CelestialEphemerisPage } from '../admin-pages.jsx';
import celestialReducer from '../celestial-slice.jsx';

const { socket } = vi.hoisted(() => ({
    socket: {
        emit: vi.fn(),
        on: vi.fn(),
        off: vi.fn(),
    },
}));

vi.mock('../../common/socket.jsx', () => ({
    useSocket: () => ({ socket }),
}));

const statusResponse = {
    success: true,
    data: {
        provider: {
            name: 'NASA JPL Horizons',
            status: {
                availability: 'unavailable',
                circuit: 'open',
                reason: 'connection_failure',
                retry_at_utc: '2026-09-22T08:45:00+00:00',
                last_failure_at_utc: '2026-09-22T08:44:00+00:00',
            },
        },
        cache: { total_snapshots: 0, fresh_snapshots: 0 },
        sync: { enabled: true, interval_minutes: 60, past_hours: 1 },
    },
};

describe('CelestialEphemerisPage synchronization failures', () => {
    beforeEach(() => {
        socket.emit.mockReset();
        socket.on.mockReset();
        socket.off.mockReset();
        socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-celestial-ephemeris-status') {
                acknowledge(statusResponse);
                return;
            }
            acknowledge({
                success: false,
                data: {
                    count: 2,
                    refreshed: 0,
                    failed: 2,
                    provider_status: statusResponse.data.provider.status,
                    errors: [
                        {
                            target_key: 'body:mars',
                            target_name: 'Mars',
                            error_code: 'connection_failure',
                            error: 'NASA JPL Horizons could not be reached',
                        },
                    ],
                },
            });
        });
    });

    it('shows the cause, retry information, counts, and failed targets', async () => {
        const store = configureStore({ reducer: { celestial: celestialReducer } });
        render(
            <Provider store={store}>
                <CelestialEphemerisPage />
            </Provider>,
        );

        const synchronizeButton = await screen.findByRole('button', { name: /synchronize now/i });
        await waitFor(() => expect(synchronizeButton).toBeEnabled());
        fireEvent.click(synchronizeButton);

        expect(await screen.findByText('Could not reach NASA JPL Horizons')).toBeInTheDocument();
        expect(screen.getByText(/0 of 2 targets refreshed; 2 failed/)).toBeInTheDocument();
        expect(screen.getAllByText(/could not establish a network connection/).length).toBeGreaterThan(0);
        expect(screen.getByText('Failed targets (1)')).toBeInTheDocument();
        expect(screen.getByText('Mars')).toBeInTheDocument();
        expect(screen.getByText('Action required')).toBeInTheDocument();
        expect(store.getState().celestial.ephemerisSync).toMatchObject({
            status: 'failed',
            failed: 2,
            providerStatus: { availability: 'unavailable' },
        });
    });

    it('shows a persisted successful terminal sync as completed', async () => {
        socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-celestial-ephemeris-status') {
                acknowledge({
                    ...statusResponse,
                    data: {
                        ...statusResponse.data,
                        sync: {
                            ...statusResponse.data.sync,
                            state: {
                                status: 'complete',
                                success: true,
                                progress: 100,
                                last_update: '2026-09-22T08:01:00+00:00',
                            },
                        },
                    },
                });
                return;
            }
            acknowledge({ success: true, data: {} });
        });

        const store = configureStore({ reducer: { celestial: celestialReducer } });
        render(
            <Provider store={store}>
                <CelestialEphemerisPage />
            </Provider>,
        );

        expect(await screen.findByText('Completed')).toBeInTheDocument();
    });
});
