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
                columns.filter((column) => column.field === 'row_actions').map((column) => (
                    ReactModule.createElement(
                        ReactModule.Fragment,
                        { key: column.field },
                        column.renderCell({ row, value: row[column.field] }),
                    )
                )),
            )),
        ),
    };
});

describe('Celestial target edit dialog', () => {
    beforeEach(() => {
        socket.emit.mockReset();
        socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-monitored-celestial') {
                acknowledge({
                    success: true,
                    data: [{
                        id: 'mars',
                        target_key: 'body:mars',
                        target_type: 'body',
                        display_name: 'Mars',
                        body_id: 'mars',
                        enabled: true,
                        projection_past_hours: 6,
                        projection_future_hours: 72,
                        projection_step_minutes: 30,
                    }],
                });
                return;
            }
            if (request.cmd === 'update-monitored-celestial') {
                acknowledge({ success: true, data: request.data });
            }
        });
    });

    it('shows and saves the target projection settings', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
            },
        });
        render(<Provider store={store}><CelestialTargetsPage /></Provider>);

        fireEvent.click((await screen.findByTestId('EditIcon')).closest('button'));

        expect(await screen.findByText('Edit monitored celestial')).toBeInTheDocument();
        expect(await screen.findByText('Time projection')).toBeInTheDocument();
        expect(screen.getByRole('combobox', { name: 'Past duration' })).toHaveTextContent('6h');
        expect(screen.getByRole('combobox', { name: 'Future duration' })).toHaveTextContent('72h');
        expect(screen.getByRole('combobox', { name: 'Sample interval' })).toHaveTextContent('30m');

        fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Past duration' }));
        fireEvent.click(await screen.findByRole('option', { name: '12h' }));
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));

        await waitFor(() => expect(socket.emit).toHaveBeenCalledWith(
            'api.call',
            expect.objectContaining({
                cmd: 'update-monitored-celestial',
                data: expect.objectContaining({
                    id: 'mars',
                    projection_past_hours: 12,
                    projection_future_hours: 72,
                    projection_step_minutes: 30,
                }),
            }),
            expect.any(Function),
        ));
    });
});
