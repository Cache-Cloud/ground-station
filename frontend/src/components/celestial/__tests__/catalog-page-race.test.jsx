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
import '../../../i18n/config.js';
import { CelestialCatalogPage } from '../admin-pages.jsx';
import celestialReducer from '../celestial-slice.jsx';
import monitoredReducer from '../monitored-slice.jsx';
import satellitesReducer from '../../satellites/satellite-slice.jsx';

const socketState = vi.hoisted(() => ({
    createAcknowledge: null,
    created: false,
    bodyCatalogFailure: '',
    missions: [],
    monitoredRows: null,
    refreshResponse: { success: true, data: { celestial: [] } },
    socket: { emit: vi.fn() },
}));

vi.mock('../../common/socket.jsx', () => ({
    useSocket: () => ({ socket: socketState.socket }),
}));

vi.mock('@mui/x-data-grid', async () => {
    const ReactModule = await import('react');
    const MockDataGrid = ({ rows = [], columns = [], getRowId, checkboxSelection, onRowSelectionModelChange }) => {
        const [selectedIds, setSelectedIds] = ReactModule.useState([]);

        const updateSelection = (rowId, checked) => {
            setSelectedIds((current) => {
                const next = checked
                    ? [...new Set([...current, rowId])]
                    : current.filter((id) => id !== rowId);
                onRowSelectionModelChange?.(next);
                return next;
            });
        };

        return ReactModule.createElement(
            'div',
            {
                'data-testid': 'catalog-grid',
                'data-row-ids': rows.map((row) => getRowId?.(row) ?? row.key).join('|'),
            },
            rows.map((row) => {
                const rowId = getRowId?.(row) ?? row.key;
                return ReactModule.createElement(
                    'div',
                    { key: rowId },
                    checkboxSelection && ReactModule.createElement('input', {
                        type: 'checkbox',
                        checked: selectedIds.includes(rowId),
                        'aria-label': `Select ${row.name || row.key}`,
                        onChange: (event) => updateSelection(rowId, event.target.checked),
                    }),
                    columns
                        .filter((column) => column.field === 'monitoring')
                        .map((column) => ReactModule.createElement(
                            ReactModule.Fragment,
                            { key: column.field },
                            column.renderCell({ row, value: row[column.field] }),
                        )),
                );
            }),
        );
    };

    return {
        gridClasses: { cell: 'MuiDataGrid-cell', columnHeader: 'MuiDataGrid-columnHeader' },
        DataGrid: MockDataGrid,
    };
});

describe('CelestialCatalogPage monitor actions', () => {
    beforeEach(() => {
        socketState.createAcknowledge = null;
        socketState.created = false;
        socketState.bodyCatalogFailure = '';
        socketState.missions = [];
        socketState.monitoredRows = null;
        socketState.refreshResponse = { success: true, data: { celestial: [] } };
        socketState.socket.emit.mockReset();
        socketState.socket.emit.mockImplementation((_event, request, acknowledge) => {
            if (request.cmd === 'get-celestial-body-catalog') {
                if (socketState.bodyCatalogFailure) {
                    acknowledge({ success: false, error: socketState.bodyCatalogFailure });
                    return;
                }
                acknowledge({
                    success: true,
                    data: [{
                        target_key: 'body:sun',
                        body_id: 'sun',
                        name: 'Sun',
                        body_type: 'star',
                        monitorable: true,
                    }],
                });
                return;
            }
            if (request.cmd === 'get-spacecraft-index') {
                acknowledge({ success: true, data: socketState.missions });
                return;
            }
            if (request.cmd === 'get-monitored-celestial') {
                acknowledge({
                    success: true,
                    data: socketState.monitoredRows ?? (socketState.created
                        ? [{
                            id: 'sun-id',
                            target_key: 'body:sun',
                            target_type: 'body',
                            display_name: 'Sun',
                            body_id: 'sun',
                            enabled: true,
                        }]
                        : []),
                });
                return;
            }
            if (request.cmd === 'create-monitored-celestial') {
                socketState.createAcknowledge = acknowledge;
                return;
            }
            if (request.cmd === 'refresh-monitored-celestial-now') {
                acknowledge(socketState.refreshResponse);
                return;
            }
            if (request.cmd === 'toggle-monitored-celestial-enabled') {
                socketState.monitoredRows = (socketState.monitoredRows || []).map((row) => (
                    row.id === request.data.id ? { ...row, enabled: request.data.enabled } : row
                ));
                acknowledge({ success: true, data: null });
                return;
            }
            if (request.cmd === 'get-transmitters') {
                acknowledge({ success: true, data: [] });
            }
        });
    });

    it('opens transmitter management for the selected celestial target key', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        const editTransmittersButton = await screen.findByRole('button', { name: /^edit transmitters$/i });
        expect(editTransmittersButton).toBeDisabled();
        fireEvent.click(screen.getByRole('checkbox', { name: 'Select Sun' }));
        expect(editTransmittersButton).toBeEnabled();
        fireEvent.click(editTransmittersButton);

        expect(await screen.findByRole('dialog')).toHaveTextContent('Edit Transmitters: Sun');
        await waitFor(() => {
            expect(socketState.socket.emit).toHaveBeenCalledWith(
                'api.call',
                { cmd: 'get-transmitters', data: { target_key: 'body:sun' } },
                expect.any(Function),
            );
        });
    });

    it('uses stable unique grid IDs when catalog target identity is missing', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.missions = [
            { id: 'voyager1', display_name: 'Voyager 1', command: 'Voyager 1' },
            { id: 'dawn', display_name: 'Dawn', command: 'Dawn' },
        ];

        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        const grid = await screen.findByTestId('catalog-grid');
        await waitFor(() => {
            const rowIds = String(grid.getAttribute('data-row-ids') || '').split('|');
            expect(rowIds).toEqual([
                'body:sun',
                'catalog:mission:voyager1',
                'catalog:mission:dawn',
            ]);
            expect(new Set(rowIds).size).toBe(rowIds.length);
        });
        expect(screen.getByRole('button', { name: /^monitor$/i })).toBeDisabled();
        expect(screen.getByRole('button', { name: /^unmonitor$/i })).toBeDisabled();
        expect(screen.getAllByText('Not monitored')).toHaveLength(3);
        expect(screen.queryByText(/^working$/i)).not.toBeInTheDocument();
    });

    it('keeps a custom monitored target manageable when it is absent from the catalogs', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.monitoredRows = [{
            id: 'custom-probe',
            target_key: 'mission:custom_probe',
            target_type: 'mission',
            display_name: 'Custom Probe',
            command: 'CUSTOM PROBE',
            enabled: false,
        }];

        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        const checkbox = await screen.findByRole('checkbox', { name: 'Select Custom Probe' });
        expect(screen.getByTestId('catalog-grid')).toHaveAttribute(
            'data-row-ids',
            expect.stringContaining('mission:custom_probe'),
        );
        expect(screen.getByText('Disabled')).toBeInTheDocument();
        fireEvent.click(checkbox);
        expect(screen.getByRole('button', { name: /^unmonitor$/i })).toBeEnabled();
    });

    it('does not show a success alert after enabling a monitored target', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.monitoredRows = [{
            id: 'custom-probe',
            target_key: 'mission:custom_probe',
            target_type: 'mission',
            display_name: 'Custom Probe',
            command: 'CUSTOM PROBE',
            enabled: false,
        }];

        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        fireEvent.click(await screen.findByRole('checkbox', { name: 'Select Custom Probe' }));
        fireEvent.click(screen.getByRole('button', { name: 'Enable' }));
        await waitFor(() => expect(socketState.socket.emit).toHaveBeenCalledWith(
            'api.call',
            expect.objectContaining({
                cmd: 'toggle-monitored-celestial-enabled',
                data: { id: 'custom-probe', enabled: true },
            }),
            expect.any(Function),
        ));
        expect(document.querySelector('.MuiAlert-colorSuccess')).not.toBeInTheDocument();
    });

    it('still renders monitored targets when a catalog source fails', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.bodyCatalogFailure = 'Body catalog unavailable';
        socketState.monitoredRows = [{
            id: 'custom-probe',
            target_key: 'mission:custom_probe',
            target_type: 'mission',
            display_name: 'Custom Probe',
            command: 'CUSTOM PROBE',
            enabled: true,
        }];

        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        expect(await screen.findByText('Body catalog unavailable')).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: 'Select Custom Probe' })).toBeInTheDocument();
    });

    it('enables both actions for a mixed monitored selection', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.created = true;
        socketState.missions = [{
            id: 'voyager1',
            target_key: 'mission:voyager_1',
            display_name: 'Voyager 1',
            command: 'Voyager 1',
        }];

        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        await screen.findByText('Enabled');
        fireEvent.click(screen.getByRole('checkbox', { name: 'Select Sun' }));
        fireEvent.click(screen.getByRole('checkbox', { name: 'Select Voyager 1' }));

        expect(screen.getByRole('button', { name: /^edit transmitters$/i })).toBeDisabled();
        expect(screen.getByRole('button', { name: /^monitor$/i })).toBeEnabled();
        expect(screen.getByRole('button', { name: /^unmonitor$/i })).toBeEnabled();
    });

    it('starts only one create and first-refresh chain after rapid repeated clicks', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        fireEvent.click(await screen.findByRole('checkbox', { name: 'Select Sun' }));
        const monitorButton = screen.getByRole('button', { name: /^monitor$/i });
        expect(monitorButton).toBeEnabled();
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
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /^unmonitor$/i })).toBeEnabled();
            expect(screen.getByText('Enabled')).toBeInTheDocument();
        });
        expect(screen.queryByText('Sun is now monitored and its data was refreshed.')).not.toBeInTheDocument();
    });

    it('shows a first-refresh failure in an error dialog', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        socketState.refreshResponse = { success: false, error: 'Horizons is unavailable' };
        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        fireEvent.click(await screen.findByRole('checkbox', { name: 'Select Sun' }));
        fireEvent.click(screen.getByRole('button', { name: /^monitor$/i }));
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

        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent(
            'Sun is monitored, but its first data refresh failed: Horizons is unavailable',
        );
    });

    it('shows a monitor failure in an error dialog', async () => {
        const store = configureStore({
            reducer: {
                celestial: celestialReducer,
                celestialMonitored: monitoredReducer,
                satellites: satellitesReducer,
            },
        });
        render(
            <Provider store={store}>
                <CelestialCatalogPage />
            </Provider>,
        );

        fireEvent.click(await screen.findByRole('checkbox', { name: 'Select Sun' }));
        fireEvent.click(screen.getByRole('button', { name: /^monitor$/i }));
        await act(async () => {
            socketState.createAcknowledge({ success: false, error: 'Database write failed' });
        });

        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('Could not monitor Sun: Database write failed');
    });
});
