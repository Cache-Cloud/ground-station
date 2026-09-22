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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CelestialCatalogPage } from '../admin-pages.jsx';
import celestialReducer from '../celestial-slice.jsx';
import monitoredReducer from '../monitored-slice.jsx';

const socketState = vi.hoisted(() => ({
    createAcknowledge: null,
    created: false,
    socket: { emit: vi.fn() },
}));

vi.mock('../../common/socket.jsx', () => ({
    useSocket: () => ({ socket: socketState.socket }),
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
                { key: row.key },
                columns
                    .filter((column) => column.field === 'row_actions')
                    .map((column) => ReactModule.createElement(
                        ReactModule.Fragment,
                        { key: column.field },
                        column.renderCell({ row, value: row[column.field] }),
                    )),
            )),
        ),
    };
});

describe('CelestialCatalogPage monitor actions', () => {
    beforeEach(() => {
        socketState.createAcknowledge = null;
        socketState.created = false;
        socketState.socket.emit.mockReset();
        socketState.socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-celestial-body-catalog') {
                acknowledge({
                    success: true,
                    data: [{ body_id: 'sun', name: 'Sun', body_type: 'star', monitorable: true }],
                });
                return;
            }
            if (request.cmd === 'get-spacecraft-index') {
                acknowledge({ success: true, data: [] });
                return;
            }
            if (request.cmd === 'get-monitored-celestial') {
                acknowledge({
                    success: true,
                    data: socketState.created
                        ? [{
                            id: 'sun-id',
                            target_type: 'body',
                            display_name: 'Sun',
                            body_id: 'sun',
                            enabled: true,
                        }]
                        : [],
                });
                return;
            }
            if (request.cmd === 'create-monitored-celestial') {
                socketState.createAcknowledge = acknowledge;
                return;
            }
            if (request.cmd === 'refresh-monitored-celestial-now') {
                acknowledge({ success: true, data: { celestial: [] } });
            }
        });
    });

    it('starts only one create and first-refresh chain after rapid repeated clicks', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
            },
        });
        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        const monitorButton = await screen.findByRole('button', { name: /^monitor$/i });
        fireEvent.click(monitorButton);
        fireEvent.click(monitorButton);

        const createRequests = socketState.socket.emit.mock.calls.filter(
            ([, request]) => request.cmd === 'create-monitored-celestial',
        );
        expect(createRequests).toHaveLength(1);

        socketState.created = true;
        await act(async () => {
            socketState.createAcknowledge({
                success: true,
                data: {
                    id: 'sun-id',
                    target_type: 'body',
                    display_name: 'Sun',
                    body_id: 'sun',
                    enabled: true,
                },
            });
        });

        await waitFor(() => {
            const refreshRequests = socketState.socket.emit.mock.calls.filter(
                ([, request]) => request.cmd === 'refresh-monitored-celestial-now',
            );
            expect(refreshRequests).toHaveLength(1);
        });
        expect(await screen.findByText('Sun is now monitored and its data was refreshed.')).toBeInTheDocument();
    });
});
