/**
 * @license
 * Copyright (c) 2026 Efstratios Goudelis
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
import '../../../i18n/config.js';
import { CelestialTargetsPage } from '../admin-pages.jsx';
import celestialReducer from '../celestial-slice.jsx';
import monitoredReducer from '../monitored-slice.jsx';

const socket = vi.hoisted(() => ({ emit: vi.fn() }));

vi.mock('../../common/socket.jsx', () => ({
    useSocket: () => ({ socket }),
}));

vi.mock('@mui/x-data-grid', async () => {
    const ReactModule = await import('react');
    return {
        gridClasses: { cell: 'MuiDataGrid-cell', columnHeader: 'MuiDataGrid-columnHeader' },
        DataGrid: ({ rows = [], columns = [] }) => ReactModule.createElement(
            'div',
            null,
            rows.map((row) => ReactModule.createElement(
                'div',
                { key: row.id },
                columns.filter((column) => column.field === 'row_actions').map((column) => ReactModule.createElement(
                    ReactModule.Fragment,
                    { key: column.field },
                    column.renderCell({ row, value: row[column.field] }),
                )),
            )),
        ),
    };
});

describe('Celestial target vector coverage dialog', () => {
    beforeEach(() => {
        socket.emit.mockReset();
        socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-monitored-celestial') {
                acknowledge({
                    success: true,
                    data: [{
                        id: 'monitored-juno',
                        target_key: 'mission:-61',
                        target_type: 'mission',
                        display_name: 'Juno',
                        command: '-61',
                        enabled: true,
                    }],
                });
                return;
            }
            if (request.cmd === 'get-celestial-vector-snapshot-history') {
                acknowledge({
                    success: true,
                    data: {
                        target_key: 'mission:-61',
                        now_utc: '2026-09-23T03:30:00+00:00',
                        snapshots: [{
                            id: 'snapshot-1',
                            epoch_bucket_utc: '2026-09-23T03:00:00+00:00',
                            fetched_at: '2026-09-23T03:00:00+00:00',
                            expires_at: '2026-09-23T05:00:00+00:00',
                            sample_start_utc: '2026-09-22T03:00:00+00:00',
                            sample_end_utc: '2026-09-24T03:00:00+00:00',
                            requested_start_utc: '2026-09-22T03:00:00+00:00',
                            requested_end_utc: '2026-09-24T03:00:00+00:00',
                            sample_count: 49,
                            past_hours: 24,
                            future_hours: 24,
                            step_minutes: 60,
                            cache_fresh: true,
                            covers_now: true,
                            covers_projection_window: true,
                            vector_available: true,
                            source: 'horizons',
                            error: null,
                        }],
                    },
                });
            }
        });
    });

    it('opens from a target row and renders vector validity on a custom timeline', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
            },
        });
        render(<Provider store={store}><CelestialTargetsPage /></Provider>);

        fireEvent.click(await screen.findByRole('button', { name: 'Vector details' }));

        expect(await screen.findByText('Vector data · Juno')).toBeInTheDocument();
        expect(screen.getByText('mission:-61')).toBeInTheDocument();
        expect(screen.getByText('Vector data available')).toBeInTheDocument();
        expect(screen.getAllByText('49 samples')).toHaveLength(2);
        expect(screen.getByRole('img', { name: /timeline of vector sample coverage/i })).toBeInTheDocument();
        await waitFor(() => expect(socket.emit).toHaveBeenCalledWith(
            'api.call',
            {
                cmd: 'get-celestial-vector-snapshot-history',
                data: { target_key: 'mission:-61', limit: 24 },
            },
            expect.any(Function),
        ));
    });
});
