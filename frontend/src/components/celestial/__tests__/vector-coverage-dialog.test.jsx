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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import '../../../i18n/config.js';
import { CelestialTargetsPage } from '../admin-pages.jsx';
import celestialReducer from '../celestial-slice.jsx';
import monitoredReducer from '../monitored-slice.jsx';
import VectorCoverageDialog from '../vector-coverage-dialog.jsx';

const socket = vi.hoisted(() => ({ emit: vi.fn() }));
const historyResponse = (sampleCount = 49) => ({
    success: true,
    data: {
        target_key: 'mission:-61',
        now_utc: '2026-09-23T03:30:00+00:00',
        snapshot_count: 1,
        expired_snapshot_count: 0,
        snapshots: [{
            id: 'snapshot-1',
            epoch_bucket_utc: '2026-09-23T03:00:00+00:00',
            fetched_at: '2026-09-23T03:00:00+00:00',
            expires_at: '2026-09-23T05:00:00+00:00',
            sample_start_utc: '2026-09-22T03:00:00+00:00',
            sample_end_utc: '2026-09-24T03:00:00+00:00',
            requested_start_utc: '2026-09-22T03:00:00+00:00',
            requested_end_utc: '2026-09-24T03:00:00+00:00',
            sample_count: sampleCount,
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
                acknowledge(historyResponse());
                return;
            }
            if (request.cmd === 'delete-celestial-vector-snapshot'
                || request.cmd === 'clear-celestial-vector-snapshots') {
                acknowledge({ success: true, data: { deleted_count: 1 } });
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
        expect(screen.queryByText(/Observer AZ\/EL also requires/i)).not.toBeInTheDocument();
        await waitFor(() => expect(socket.emit).toHaveBeenCalledWith(
            'api.call',
            {
                cmd: 'get-celestial-vector-snapshot-history',
                data: { target_key: 'mission:-61', limit: 24 },
            },
            expect.any(Function),
        ));
    });

    it('keeps the existing timeline visible while refreshed history is loading', async () => {
        let historyRequestCount = 0;
        let finishHistoryRefresh;
        socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd !== 'get-celestial-vector-snapshot-history') return;
            historyRequestCount += 1;
            if (historyRequestCount === 1) {
                acknowledge(historyResponse());
                return;
            }
            finishHistoryRefresh = () => acknowledge(historyResponse(50));
        });

        render(<VectorCoverageDialog
            open
            target={{
                id: 'monitored-juno',
                targetKey: 'mission:-61',
                targetType: 'mission',
                displayName: 'Juno',
                command: '-61',
            }}
            socket={socket}
            timezone="UTC"
            locale="en-US"
            onClose={vi.fn()}
            onRefresh={vi.fn().mockResolvedValue(undefined)}
        />);

        expect(await screen.findAllByText('49 samples')).toHaveLength(2);
        fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

        await waitFor(() => expect(historyRequestCount).toBe(2));
        expect(screen.getAllByText('49 samples')).toHaveLength(2);
        expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();

        act(() => finishHistoryRefresh());
        expect(await screen.findAllByText('50 samples')).toHaveLength(2);
    });

    it('confirms and deletes an individual target-scoped snapshot', async () => {
        render(<VectorCoverageDialog
            open
            target={{
                id: 'monitored-juno',
                targetKey: 'mission:-61',
                targetType: 'mission',
                displayName: 'Juno',
                command: '-61',
            }}
            socket={socket}
            timezone="UTC"
            locale="en-US"
            onClose={vi.fn()}
            onRefresh={vi.fn()}
        />);

        fireEvent.click(await screen.findByRole('button', { name: 'Delete snapshot' }));
        expect(await screen.findByText('Delete snapshot?')).toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button', { name: 'Delete snapshot' }).at(-1));

        await waitFor(() => expect(socket.emit).toHaveBeenCalledWith(
            'api.call',
            {
                cmd: 'delete-celestial-vector-snapshot',
                data: {
                    target_key: 'mission:-61',
                    snapshot_id: 'snapshot-1',
                },
            },
            expect.any(Function),
        ));
        await waitFor(() => expect(
            socket.emit.mock.calls.filter(([, request]) => (
                request.cmd === 'get-celestial-vector-snapshot-history'
            )),
        ).toHaveLength(2));
    });

    it('confirms clearing every snapshot for only the selected target', async () => {
        render(<VectorCoverageDialog
            open
            target={{
                id: 'monitored-juno',
                targetKey: 'mission:-61',
                targetType: 'mission',
                displayName: 'Juno',
                command: '-61',
            }}
            socket={socket}
            timezone="UTC"
            locale="en-US"
            onClose={vi.fn()}
            onRefresh={vi.fn()}
        />);

        fireEvent.click(await screen.findByRole('button', { name: 'Clear all snapshots' }));
        expect(await screen.findByText('Clear all snapshots?')).toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button', { name: 'Clear all snapshots' }).at(-1));

        await waitFor(() => expect(socket.emit).toHaveBeenCalledWith(
            'api.call',
            {
                cmd: 'clear-celestial-vector-snapshots',
                data: {
                    target_key: 'mission:-61',
                    expired_only: false,
                },
            },
            expect.any(Function),
        ));
    });
});
