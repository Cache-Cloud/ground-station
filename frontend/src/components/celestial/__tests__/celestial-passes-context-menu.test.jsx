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
import { fireEvent, render, screen } from '@testing-library/react';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { ThemeProvider } from '@mui/material/styles';
import { describe, expect, it, vi } from 'vitest';
import '../../../i18n/config.js';
import { setupTheme } from '../../../theme.js';
import CelestialPasses from '../celestial-passes.jsx';

const socket = vi.hoisted(() => ({ emit: vi.fn() }));

vi.mock('../../common/socket.jsx', () => ({
    useSocket: () => ({ socket }),
}));

vi.mock('../../target/use-target-rotator-selection-dialog.jsx', () => ({
    useTargetRotatorSelectionDialog: () => ({
        requestRotatorForTarget: vi.fn(),
        dialog: null,
    }),
}));

vi.mock('@mui/x-data-grid', async () => {
    const ReactModule = await import('react');
    return {
        DataGrid: ReactModule.forwardRef(({ rows = [], slotProps = {} }, ref) => ReactModule.createElement(
            'div',
            { ref },
            rows.map((row) => ReactModule.createElement(
                'div',
                {
                    key: row.id,
                    'data-id': row.id,
                    'data-testid': `pass-row-${row.id}`,
                    onContextMenu: slotProps?.row?.onContextMenu,
                },
                row.name,
            )),
        )),
        GridPagination: () => null,
        gridClasses: { cell: 'MuiDataGrid-cell', columnHeader: 'MuiDataGrid-columnHeader' },
        gridPageCountSelector: () => 1,
        gridPageSelector: () => 0,
        gridRowSelectionCountSelector: () => 0,
        useGridApiContext: () => ({ current: { setPage: vi.fn() } }),
        useGridSelector: () => 0,
    };
});

const fixedReducer = (initialState) => (state = initialState) => state;

describe('Celestial passes context menu', () => {
    it('opens projection editing for the matching monitored celestial', async () => {
        const store = configureStore({
            reducer: {
                celestial: fixedReducer({
                    passesTableColumnVisibility: {},
                    passesTablePageSize: 10,
                    passesTableSortModel: [],
                }),
                celestialMonitored: fixedReducer({ monitored: [] }),
                trackerInstances: fixedReducer({ instances: [] }),
                targetSatTrack: fixedReducer({ trackingState: {}, trackerViews: {} }),
                preferences: fixedReducer({
                    preferences: [
                        { name: 'timezone', value: 'UTC' },
                        { name: 'locale', value: 'en-US' },
                    ],
                }),
            },
        });
        const monitored = {
            id: 'monitored-mars',
            targetKey: 'body:mars',
            targetType: 'body',
            displayName: 'Mars',
            bodyId: 'mars',
            enabled: true,
            projectionPastHours: 6,
            projectionFutureHours: 72,
            projectionStepMinutes: 30,
        };

        render(
            <Provider store={store}>
                <ThemeProvider theme={setupTheme()}>
                    <CelestialPasses
                        passes={[{
                            id: 'mars-pass',
                            target_key: 'body:mars',
                            target_type: 'body',
                            body_id: 'mars',
                            name: 'Mars',
                            event_start: '2026-09-28T10:00:00Z',
                            event_end: '2026-09-28T11:00:00Z',
                            peak_time: '2026-09-28T10:30:00Z',
                        }]}
                        monitoredRows={[monitored]}
                    />
                </ThemeProvider>
            </Provider>,
        );

        fireEvent.contextMenu(screen.getByTestId('pass-row-mars-pass'), {
            clientX: 100,
            clientY: 120,
        });
        fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit projection' }));

        expect(await screen.findByRole('dialog', { name: 'Edit projection' })).toBeInTheDocument();
        expect(screen.getByRole('combobox', { name: 'Past duration' })).toHaveTextContent('6h');
        expect(screen.getByRole('combobox', { name: 'Future duration' })).toHaveTextContent('72h');
        expect(screen.getByRole('combobox', { name: 'Sample interval' })).toHaveTextContent('30m');
    });
});
