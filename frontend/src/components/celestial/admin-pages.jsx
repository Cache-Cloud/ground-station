/**
 * @license
 * Copyright (c) 2025 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Alert,
    AlertTitle,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    IconButton,
    InputAdornment,
    InputLabel,
    LinearProgress,
    MenuItem,
    Paper,
    Select,
    Stack,
    Switch,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import { DataGrid, gridClasses } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/Edit';
import RefreshIcon from '@mui/icons-material/Refresh';
import SearchIcon from '@mui/icons-material/Search';
import StorageIcon from '@mui/icons-material/Storage';
import SyncIcon from '@mui/icons-material/Sync';
import PublicIcon from '@mui/icons-material/Public';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router';
import { useSocket } from '../common/socket.jsx';
import { humanizeDate } from '../common/common.jsx';
import {
    createMonitoredCelestial,
    deleteMonitoredCelestial,
    fetchMonitoredCelestial,
    toggleMonitoredCelestialEnabled,
    updateMonitoredCelestial,
} from './monitored-slice.jsx';
import {
    refreshMonitoredCelestialNow,
    setCelestialEphemerisProviderStatus,
    setCelestialEphemerisSyncCompleted,
    setCelestialEphemerisSyncFailed,
    setCelestialEphemerisSyncProgress,
    setCelestialEphemerisSyncStarted,
} from './celestial-slice.jsx';
import { buildEphemerisSyncFailure, describeHorizonsFailure } from './ephemeris-errors.js';
import { toRowSelectionModel, toSelectedIds } from '../../utils/datagrid-selection.js';

const PAGE_PAPER_SX = { padding: 2, marginTop: 0, borderRadius: 0 };
const DATA_GRID_SX = {
    border: 0,
    marginTop: 0,
    minHeight: 420,
    '& .MuiDataGrid-cell': {
        display: 'flex',
        alignItems: 'center',
        py: 1,
    },
    [`& .${gridClasses.cell}:focus, & .${gridClasses.cell}:focus-within`]: {
        outline: 'none',
    },
    [`& .${gridClasses.columnHeader}:focus, & .${gridClasses.columnHeader}:focus-within`]: {
        outline: 'none',
    },
    '& .MuiDataGrid-columnHeaders': {
        backgroundColor: (theme) => alpha(
            theme.palette.primary.main,
            theme.palette.mode === 'dark' ? 0.18 : 0.10,
        ),
        borderBottom: (theme) => `2px solid ${alpha(theme.palette.primary.main, 0.45)}`,
    },
    '& .MuiDataGrid-columnHeader': {
        backgroundColor: 'transparent',
    },
    '& .MuiDataGrid-columnHeaderTitle': {
        fontSize: '0.8125rem',
        fontWeight: 700,
        letterSpacing: '0.02em',
    },
    '& .MuiDataGrid-overlay': {
        fontSize: '0.875rem',
        fontStyle: 'italic',
        color: 'text.secondary',
    },
};

const apiCall = (socket, cmd, data = null) => new Promise((resolve, reject) => {
    if (!socket) {
        reject(new Error('No active backend connection.'));
        return;
    }
    socket.emit('api.call', { cmd, data }, (response) => {
        if (response?.success) {
            resolve(response.data);
            return;
        }
        const error = new Error(response?.error || `Command ${cmd} failed.`);
        error.response = response;
        reject(error);
    });
});

const formatDateTime = (value) => {
    if (!value) return 'Never';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
};

function PageHeading({ title, subtitle, actions }) {
    return (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="space-between" sx={{ mb: 2 }}>
            <Box>
                <Typography variant="h6">{title}</Typography>
                <Typography variant="body2" color="text.secondary">{subtitle}</Typography>
            </Box>
            {actions ? <Stack direction="row" spacing={1} alignItems="center">{actions}</Stack> : null}
        </Stack>
    );
}

function MetricCard({ icon, label, value, detail, tone = 'info' }) {
    return (
        <Paper
            elevation={3}
            sx={(theme) => ({
                flex: '1 1 210px',
                minWidth: 0,
                overflow: 'hidden',
                borderRadius: 1,
                border: `1px solid ${theme.palette[tone].main}4D`,
                backgroundColor: `${theme.palette[tone].main}1A`,
            })}
        >
            <Box sx={(theme) => ({ px: 1.5, py: 1, backgroundColor: `${theme.palette[tone].main}33` })}>
                <Typography variant="caption" sx={{ color: `${tone}.main`, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    {label}
                </Typography>
            </Box>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ p: 1.5 }}>
                <Box sx={{ color: `${tone}.main`, display: 'flex' }}>{icon}</Box>
                <Box sx={{ minWidth: 0 }}>
                    <Typography variant="h6" sx={{ lineHeight: 1.25 }}>{value}</Typography>
                    {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
                </Box>
            </Stack>
        </Paper>
    );
}

export function CelestialEphemerisPage() {
    const dispatch = useDispatch();
    const { socket } = useSocket();
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [message, setMessage] = useState(null);
    const [syncProgress, setSyncProgress] = useState({
        processed: 0,
        total: 0,
        percent: 0,
        refreshed: 0,
        failed: 0,
        phase: 'idle',
        current_target: null,
    });

    const loadStatus = useCallback(async ({ preserveMessage = false } = {}) => {
        if (!socket) {
            setLoading(false);
            setMessage({ severity: 'error', text: 'No active backend connection.' });
            return;
        }
        setLoading(true);
        try {
            const nextStatus = await apiCall(socket, 'get-celestial-ephemeris-status');
            setStatus(nextStatus);
            dispatch(setCelestialEphemerisProviderStatus(nextStatus?.provider?.status || null));
            if (!preserveMessage) setMessage(null);
        } catch (error) {
            setMessage({ severity: 'error', text: error.message });
        } finally {
            setLoading(false);
        }
    }, [dispatch, socket]);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    useEffect(() => {
        if (!socket) return undefined;

        const handleProgress = (progress) => {
            setSyncProgress((current) => ({ ...current, ...(progress || {}) }));
            dispatch(setCelestialEphemerisSyncProgress(progress));
        };
        socket.on('celestial-cache-refresh-progress', handleProgress);
        return () => socket.off('celestial-cache-refresh-progress', handleProgress);
    }, [dispatch, socket]);

    const handleRefreshCache = async () => {
        dispatch(setCelestialEphemerisSyncStarted());
        setRefreshing(true);
        setMessage(null);
        setSyncProgress({
            processed: 0,
            total: 0,
            percent: 0,
            refreshed: 0,
            failed: 0,
            phase: 'starting',
            current_target: null,
        });
        try {
            const result = await apiCall(socket, 'refresh-celestial-cache-now');
            dispatch(setCelestialEphemerisSyncCompleted(result));
            setSyncProgress((current) => ({
                ...current,
                processed: result?.count ?? current.processed,
                total: result?.count ?? current.total,
                percent: 100,
                refreshed: result?.refreshed ?? current.refreshed,
                failed: result?.failed ?? current.failed,
                phase: 'complete',
            }));
        } catch (error) {
            const result = error.response?.data;
            const failure = buildEphemerisSyncFailure(result, error.message);
            dispatch(setCelestialEphemerisSyncFailed({ result, error: error.message }));
            setSyncProgress((current) => ({ ...current, phase: 'failed' }));
            setMessage({ severity: 'error', failure });
        } finally {
            setRefreshing(false);
            await loadStatus({ preserveMessage: true });
        }
    };

    const provider = status?.provider || {};
    const providerStatus = provider.status || {};
    const cache = status?.cache || {};
    const sync = status?.sync || {};
    const availability = providerStatus.availability || 'unknown';
    const providerPresentation = availability === 'available'
        ? { label: 'Online', color: 'success', detail: 'The last live request succeeded.' }
        : availability === 'unavailable'
            ? { label: 'Unavailable', color: 'error', detail: 'Live requests are paused during backoff.' }
            : { label: 'Not checked', color: 'default', detail: 'No live request has been made since the backend started.' };
    const circuitLabel = providerStatus.circuit === 'open'
        ? 'Requests paused'
        : providerStatus.circuit === 'half_open'
            ? 'Checking connection'
            : null;
    const totalSnapshots = Number(cache.total_snapshots || 0);
    const freshSnapshots = Number(cache.fresh_snapshots || 0);
    const freshnessPercent = totalSnapshots > 0
        ? Math.round((freshSnapshots / totalSnapshots) * 100)
        : 0;
    const lastSuccessfulFetch = providerStatus.last_success_at_utc || cache.newest_fetch_at;
    const syncPercent = Math.max(0, Math.min(100, Number(syncProgress.percent || 0)));
    const syncHasTotal = Number(syncProgress.total || 0) > 0;
    const currentTargetName = syncProgress.current_target?.name || syncProgress.current_target?.key;
    const activeFailureStatus = message?.failure || {};
    const failureReason = activeFailureStatus.reason || providerStatus.reason;
    const failureCause = failureReason
        ? describeHorizonsFailure(failureReason)
        : activeFailureStatus.cause;
    const failureRetryAt = activeFailureStatus.retryAtUtc || providerStatus.retry_at_utc;
    const lastFailureAt = activeFailureStatus.lastFailureAtUtc || providerStatus.last_failure_at_utc;
    const outputMessage = refreshing
        ? currentTargetName
            ? `${syncProgress.phase === 'processed' ? 'Processed' : 'Processing'} ${currentTargetName} (${syncProgress.processed}/${syncProgress.total})`
            : 'Preparing celestial ephemeris synchronization…'
        : message?.text || (message?.failure
            ? 'Synchronization stopped with errors. See details below.'
            : availability === 'available'
            ? 'Ephemeris cache is ready.'
            : availability === 'unavailable'
                ? 'Using cached ephemeris data while Horizons is unavailable.'
                : 'Ready to synchronize ephemeris data.');

    return (
        <Paper elevation={3} sx={PAGE_PAPER_SX}>
            <Paper
                variant="outlined"
                sx={{ mt: 0, borderRadius: 2, borderColor: 'divider', overflow: 'hidden' }}
            >
                <Box
                    sx={{
                        px: { xs: 2, md: 2.5 },
                        py: 1.75,
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        backgroundColor: (theme) => theme.palette.mode === 'dark'
                            ? alpha(theme.palette.primary.main, 0.07)
                            : alpha(theme.palette.primary.main, 0.04),
                    }}
                >
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1.5 }}>
                        <Stack direction="row" spacing={1.5} alignItems="center">
                            <Box
                                sx={{
                                    width: 36,
                                    height: 36,
                                    borderRadius: 1.5,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    color: 'primary.main',
                                    backgroundColor: (theme) => theme.palette.mode === 'dark'
                                        ? alpha(theme.palette.primary.main, 0.22)
                                        : alpha(theme.palette.primary.main, 0.12),
                                }}
                            >
                                <PublicIcon sx={{ fontSize: 20 }} />
                            </Box>
                            <Box>
                                <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                                    Synchronize Celestial Ephemeris
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>
                                    Refresh celestial vectors from {provider.name || 'NASA JPL Horizons'}.
                                </Typography>
                            </Box>
                        </Stack>
                        <Stack direction="row" spacing={1}>
                            <Button size="small" variant="outlined" startIcon={<RefreshIcon />} onClick={loadStatus} disabled={loading || refreshing}>
                                Refresh status
                            </Button>
                            <Button size="small" variant="contained" startIcon={refreshing ? <CircularProgress size={16} color="inherit" /> : <SyncIcon />} onClick={handleRefreshCache} disabled={!socket || loading || refreshing}>
                                Synchronize now
                            </Button>
                        </Stack>
                    </Box>

                    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1.5, mt: 1 }}>
                        <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>Status</Typography>
                        <Chip size="small" color={providerPresentation.color} label={providerPresentation.label} />
                        {circuitLabel ? <Chip size="small" variant="outlined" color={availability === 'unavailable' ? 'error' : 'default'} label={circuitLabel} /> : null}
                        <Typography variant="caption" color="text.secondary">
                            {providerPresentation.detail}
                        </Typography>
                        <Box sx={{ ml: 'auto', minWidth: 0 }}>
                            <Tooltip title={`Last successful fetch: ${formatDateTime(lastSuccessfulFetch)}`}>
                                <Typography variant="caption" color="text.disabled" sx={{ display: 'block', fontFamily: 'monospace', textAlign: 'right' }}>
                                    Last successful fetch: {humanizeDate(lastSuccessfulFetch)}
                                </Typography>
                            </Tooltip>
                            <Typography variant="caption" color="text.disabled" sx={{ display: 'block', fontFamily: 'monospace', textAlign: 'right' }}>
                                Periodic sync: {sync.enabled ? `every ${sync.interval_minutes ?? 60} minutes` : 'disabled'}
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                <Box sx={{ px: { xs: 2, md: 2.5 }, pt: 1.75, pb: 2 }}>
                    {loading && !status ? <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box> : (
                        <>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
                                <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
                                    {refreshing ? 'Synchronization progress' : 'Cache freshness'}
                                </Typography>
                                <Typography variant="caption" color="text.disabled" sx={{ fontFamily: 'monospace' }}>
                                    {refreshing
                                        ? syncHasTotal
                                            ? `${syncProgress.processed}/${syncProgress.total} · ${Math.round(syncPercent)}%`
                                            : 'Preparing…'
                                        : `${freshnessPercent}%`}
                                </Typography>
                            </Box>
                            <LinearProgress
                                variant={refreshing && !syncHasTotal ? 'indeterminate' : 'determinate'}
                                value={refreshing ? syncPercent : freshnessPercent}
                                sx={{ height: 3, borderRadius: 999, mb: 0.75 }}
                            />
                            <Stack direction="row" spacing={0.75} alignItems="baseline" sx={{ mb: 1.5 }}>
                                <Typography variant="caption" color="text.disabled" sx={{ fontWeight: 600, flexShrink: 0 }}>Output:</Typography>
                                <Typography variant="caption" color="text.secondary" title={outputMessage} sx={{ fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {outputMessage}
                                </Typography>
                            </Stack>

                            {message ? (
                                <Alert severity={message.severity} sx={{ mb: 1.5 }}>
                                    {message.failure ? (
                                        <>
                                            <AlertTitle>{message.failure.title}</AlertTitle>
                                            <Typography variant="body2">{message.failure.summary}</Typography>
                                            {failureCause ? (
                                                <Typography variant="body2" sx={{ mt: 0.75 }}>
                                                    <Box component="span" sx={{ fontWeight: 700 }}>Cause:</Box>{' '}
                                                    {failureCause}
                                                </Typography>
                                            ) : null}
                                            {failureRetryAt ? (
                                                <Typography variant="body2">
                                                    <Box component="span" sx={{ fontWeight: 700 }}>Next connection attempt:</Box>{' '}
                                                    {formatDateTime(failureRetryAt)}
                                                </Typography>
                                            ) : null}
                                            {lastFailureAt ? (
                                                <Typography variant="body2">
                                                    <Box component="span" sx={{ fontWeight: 700 }}>Last failed attempt:</Box>{' '}
                                                    {formatDateTime(lastFailureAt)}
                                                </Typography>
                                            ) : null}
                                            {message.failure.errors.length > 0 ? (
                                                <Box component="details" sx={{ mt: 1 }}>
                                                    <Box component="summary" sx={{ cursor: 'pointer', fontWeight: 600 }}>
                                                        Failed targets ({message.failure.errors.length})
                                                    </Box>
                                                    <Box component="ul" sx={{ maxHeight: 180, overflowY: 'auto', mt: 0.75, mb: 0, pl: 2.5 }}>
                                                        {message.failure.errors.map((entry, index) => (
                                                            <Box component="li" key={`${entry.targetKey}-${index}`} sx={{ mb: 0.5 }}>
                                                                <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
                                                                    {entry.targetName}
                                                                </Typography>
                                                                <Typography component="span" variant="body2">
                                                                    {` — ${entry.message}`}
                                                                </Typography>
                                                            </Box>
                                                        ))}
                                                    </Box>
                                                </Box>
                                            ) : null}
                                        </>
                                    ) : message.text}
                                </Alert>
                            ) : null}
                            {availability === 'unavailable' && !message?.failure ? (
                                <Box sx={(theme) => ({ backgroundColor: `${theme.palette.error.main}1A`, border: `1px solid ${theme.palette.error.main}4D`, borderRadius: 1, p: 1.25, mb: 1.5 })}>
                                    <Stack direction="row" spacing={1} alignItems="center">
                                        <CloudOffIcon color="error" fontSize="small" />
                                        <Box>
                                            <Typography variant="body2" color="error.main" fontWeight={600}>NASA JPL Horizons is unavailable</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {describeHorizonsFailure(failureReason)} Cached data remains available. Next automatic probe: {formatDateTime(providerStatus.retry_at_utc)}.
                                            </Typography>
                                        </Box>
                                    </Stack>
                                </Box>
                            ) : null}

                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 2 }}>
                                <MetricCard icon={<StorageIcon />} label="Stored snapshots" value={cache.total_snapshots ?? 0} detail={`${cache.distinct_targets ?? 0} targets`} tone="info" />
                                <MetricCard icon={<CheckCircleOutlineIcon />} label="Fresh snapshots" value={cache.fresh_snapshots ?? 0} detail={`Newest: ${formatDateTime(cache.newest_fetch_at)}`} tone="success" />
                                <MetricCard icon={<CloudOffIcon />} label="Expired snapshots" value={cache.expired_snapshots ?? 0} detail={`${cache.error_snapshots ?? 0} with errors`} tone="warning" />
                            </Stack>

                            <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
                                <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600, mb: 1 }}>Periodic synchronization</Typography>
                                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
                                    <Box><Typography variant="caption" color="text.secondary">Status</Typography><Box><Chip size="small" color={sync.enabled ? 'success' : 'default'} label={sync.enabled ? 'Enabled' : 'Disabled'} /></Box></Box>
                                    <Box><Typography variant="caption" color="text.secondary">Interval</Typography><Typography variant="body2">Every {sync.interval_minutes ?? 60} minutes</Typography></Box>
                                    <Box><Typography variant="caption" color="text.secondary">Past projection</Typography><Typography variant="body2">{sync.past_hours ?? 1} hours</Typography></Box>
                                    <Box><Typography variant="caption" color="text.secondary">Next cache expiry</Typography><Typography variant="body2">{formatDateTime(cache.next_expiry_at)}</Typography></Box>
                                    <Box><Typography variant="caption" color="text.secondary">Last failure</Typography><Typography variant="body2">{formatDateTime(providerStatus.last_failure_at_utc)}</Typography></Box>
                                </Stack>
                            </Box>
                        </>
                    )}
                </Box>
            </Paper>
        </Paper>
    );
}

export function CelestialCatalogPage() {
    const dispatch = useDispatch();
    const { socket } = useSocket();
    const monitored = useSelector((state) => state.celestialMonitored?.monitored || []);
    const [bodies, setBodies] = useState([]);
    const [missions, setMissions] = useState([]);
    const [kind, setKind] = useState('all');
    const [statusFilter, setStatusFilter] = useState('all');
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(true);
    const [busyKey, setBusyKey] = useState('');
    const [message, setMessage] = useState(null);
    const [pendingUnmonitor, setPendingUnmonitor] = useState(null);
    const [unmonitorError, setUnmonitorError] = useState('');

    const loadCatalog = useCallback(async () => {
        if (!socket) return;
        setLoading(true);
        try {
            const [bodyRows, missionRows] = await Promise.all([
                apiCall(socket, 'get-celestial-body-catalog'),
                apiCall(socket, 'get-spacecraft-index', { limit: 1000 }),
                dispatch(fetchMonitoredCelestial({ socket })).unwrap(),
            ]);
            setBodies((bodyRows || []).filter((body) => body?.monitorable !== false));
            setMissions(missionRows || []);
            setMessage(null);
        } catch (error) {
            setMessage({ severity: 'error', text: error.message });
        } finally {
            setLoading(false);
        }
    }, [dispatch, socket]);

    useEffect(() => {
        loadCatalog();
    }, [loadCatalog]);

    const monitoredByKey = useMemo(() => new Map(monitored.map((entry) => [
        entry.targetType === 'body' ? `body:${entry.bodyId}` : `mission:${String(entry.command).toLowerCase()}`,
        entry,
    ])), [monitored]);

    const rows = useMemo(() => {
        const bodyRows = bodies.map((body) => ({
            key: `body:${body.body_id}`,
            kind: 'body',
            name: body.name,
            identifier: body.body_id,
            type: body.body_type,
            parent: body.parent_body_id || 'Sun',
            status: 'available',
            raw: body,
        }));
        const missionRows = missions.map((mission) => ({
            key: `mission:${String(mission.command).toLowerCase()}`,
            kind: 'mission',
            name: mission.display_name,
            identifier: mission.command,
            type: 'spacecraft',
            parent: mission.agency || 'Unknown agency',
            status: mission.mission_status || 'unknown',
            raw: mission,
        }));
        const needle = search.trim().toLowerCase();
        return [...bodyRows, ...missionRows].filter((row) => {
            if (kind !== 'all' && row.kind !== kind) return false;
            if (statusFilter !== 'all' && row.kind === 'mission' && row.status !== statusFilter) return false;
            if (!needle) return true;
            const aliases = row.raw.aliases || [];
            return [row.name, row.identifier, row.type, row.parent, ...aliases]
                .some((value) => String(value || '').toLowerCase().includes(needle));
        });
    }, [bodies, kind, missions, search, statusFilter]);

    const handleMonitor = async (row) => {
        setBusyKey(row.key);
        setMessage(null);
        try {
            const created = await dispatch(createMonitoredCelestial({
                socket,
                entry: {
                    targetType: row.kind,
                    displayName: row.name,
                    command: row.kind === 'mission' ? row.identifier : '',
                    bodyId: row.kind === 'body' ? row.identifier : '',
                    enabled: true,
                    sourceMode: row.kind === 'mission' ? 'catalog' : 'static-body',
                },
            })).unwrap();
            const refreshResult = await dispatch(refreshMonitoredCelestialNow({ socket, ids: [created.id] }));
            await dispatch(fetchMonitoredCelestial({ socket }));
            if (refreshMonitoredCelestialNow.rejected.match(refreshResult)) {
                setMessage({
                    severity: 'warning',
                    text: `${row.name} is monitored, but its first data refresh failed: ${refreshResult.payload || refreshResult.error?.message || 'Unknown error'}`,
                });
            } else {
                setMessage({ severity: 'success', text: `${row.name} is now monitored and its data was refreshed.` });
            }
        } catch (error) {
            setMessage({ severity: 'error', text: String(error?.message || error) });
        } finally {
            setBusyKey('');
        }
    };

    const handleConfirmUnmonitor = async () => {
        const row = pendingUnmonitor;
        const existing = row ? monitoredByKey.get(row.key) : null;
        if (!row || !existing) return;

        setBusyKey(row.key);
        setUnmonitorError('');
        try {
            await dispatch(deleteMonitoredCelestial({ socket, ids: [existing.id] })).unwrap();
            setMessage({ severity: 'success', text: `${row.name} is no longer monitored.` });
            setPendingUnmonitor(null);
        } catch (error) {
            setUnmonitorError(String(error?.message || error));
        } finally {
            setBusyKey('');
        }
    };

    const statuses = useMemo(() => [...new Set(missions.map((row) => row.mission_status).filter(Boolean))].sort(), [missions]);
    const columns = [
        {
            field: 'name',
            headerName: 'Name',
            minWidth: 180,
            flex: 1,
            renderCell: (params) => <Typography variant="body2" fontWeight={500}>{params.value}</Typography>,
        },
        {
            field: 'type',
            headerName: 'Type',
            width: 120,
            renderCell: (params) => <Chip size="small" variant="outlined" label={params.value} />,
        },
        { field: 'parent', headerName: 'Agency / Parent', minWidth: 150, flex: 0.8 },
        {
            field: 'status',
            headerName: 'Status',
            width: 120,
            renderCell: (params) => (
                <Chip
                    size="small"
                    color={params.value === 'active' || params.value === 'available' ? 'success' : 'default'}
                    label={params.value}
                />
            ),
        },
        {
            field: 'identifier',
            headerName: 'Horizons command / ID',
            minWidth: 190,
            flex: 1,
            renderCell: (params) => <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{params.value}</Typography>,
        },
        {
            field: 'row_actions',
            headerName: '',
            width: 132,
            sortable: false,
            filterable: false,
            disableColumnMenu: true,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => {
                const isMonitored = monitoredByKey.has(params.row.key);
                return (
                    <Button
                        size="small"
                        variant={isMonitored ? 'outlined' : 'contained'}
                        color={isMonitored ? 'error' : 'primary'}
                        startIcon={isMonitored ? <DeleteOutlineIcon /> : <AddIcon />}
                        disabled={!socket || busyKey === params.row.key}
                        onClick={(event) => {
                            event.stopPropagation();
                            if (isMonitored) {
                                setUnmonitorError('');
                                setPendingUnmonitor(params.row);
                            } else {
                                handleMonitor(params.row);
                            }
                        }}
                    >
                        {busyKey === params.row.key ? 'Working…' : isMonitored ? 'Unmonitor' : 'Monitor'}
                    </Button>
                );
            },
        },
    ];

    return (
        <Paper elevation={3} sx={PAGE_PAPER_SX}>
            <PageHeading title="Celestial Catalog" subtitle="Browse solar-system bodies and the built-in spacecraft catalog, then choose what to monitor." actions={<Button startIcon={<RefreshIcon />} onClick={loadCatalog} disabled={loading}>Reload</Button>} />
            {message ? <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message.text}</Alert> : null}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
                <FormControl size="small" sx={{ minWidth: 160 }}>
                    <InputLabel>Catalog</InputLabel>
                    <Select label="Catalog" value={kind} onChange={(event) => setKind(event.target.value)}>
                        <MenuItem value="all">All entries</MenuItem>
                        <MenuItem value="body">Solar bodies</MenuItem>
                        <MenuItem value="mission">Spacecraft</MenuItem>
                    </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 160 }} disabled={kind === 'body'}>
                    <InputLabel>Status</InputLabel>
                    <Select label="Status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                        <MenuItem value="all">All statuses</MenuItem>
                        {statuses.map((status) => <MenuItem key={status} value={status}>{status}</MenuItem>)}
                    </Select>
                </FormControl>
                <TextField
                    size="small"
                    label="Search catalog"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    sx={{ flex: 1, minWidth: 220 }}
                    InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }}
                />
            </Stack>
            <DataGrid
                loading={loading}
                rows={rows}
                columns={columns}
                getRowId={(row) => row.key}
                pageSizeOptions={[5, 10, 25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
                disableRowSelectionOnClick
                localeText={{ noRowsLabel: 'No catalog entries match the filters.' }}
                sx={DATA_GRID_SX}
            />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{rows.length} entries shown · {monitored.length} monitored</Typography>

            <Dialog
                open={Boolean(pendingUnmonitor)}
                onClose={() => !busyKey && setPendingUnmonitor(null)}
                maxWidth="sm"
                fullWidth
                PaperProps={{ sx: { bgcolor: 'background.paper', borderRadius: 2 } }}
            >
                <DialogTitle
                    sx={{
                        bgcolor: 'error.main',
                        color: 'error.contrastText',
                        fontSize: '1.125rem',
                        fontWeight: 600,
                        py: 2,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1.5,
                    }}
                >
                    <Box
                        component="span"
                        sx={{
                            width: 24,
                            height: 24,
                            borderRadius: '50%',
                            bgcolor: 'error.contrastText',
                            color: 'error.main',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 'bold',
                            fontSize: '1rem',
                        }}
                    >
                        !
                    </Box>
                    Confirm unmonitor
                </DialogTitle>
                <DialogContent sx={{ px: 3, pt: 3, pb: 3 }}>
                    <Typography variant="body1" sx={{ mt: 2, mb: 1 }}>
                        Stop monitoring <strong>{pendingUnmonitor?.name || 'this target'}</strong>?
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        It will stop appearing in the Solar System view. You can monitor it again from this catalog later.
                    </Typography>
                    {unmonitorError ? <Alert severity="error" sx={{ mt: 2 }}>{unmonitorError}</Alert> : null}
                </DialogContent>
                <DialogActions
                    sx={{
                        bgcolor: (theme) => theme.palette.mode === 'dark' ? 'grey.900' : 'grey.100',
                        borderTop: '1px solid',
                        borderColor: 'divider',
                        px: 3,
                        py: 2,
                        gap: 1,
                    }}
                >
                    <Button variant="outlined" onClick={() => setPendingUnmonitor(null)} disabled={Boolean(busyKey)}>
                        Cancel
                    </Button>
                    <Button
                        variant="contained"
                        color="error"
                        startIcon={<DeleteOutlineIcon />}
                        disabled={!pendingUnmonitor || Boolean(busyKey)}
                        onClick={handleConfirmUnmonitor}
                    >
                        Unmonitor
                    </Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
}

export function CelestialTargetsPage() {
    const dispatch = useDispatch();
    const navigate = useNavigate();
    const { socket } = useSocket();
    const { monitored = [], loading = false, saveLoading = false } = useSelector((state) => state.celestialMonitored || {});
    const [selected, setSelected] = useState([]);
    const [search, setSearch] = useState('');
    const [editTarget, setEditTarget] = useState(null);
    const [pendingDeleteIds, setPendingDeleteIds] = useState([]);
    const [editError, setEditError] = useState('');
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState(null);
    const [rowRefreshStates, setRowRefreshStates] = useState({});

    const loadTargets = useCallback(() => {
        if (socket) dispatch(fetchMonitoredCelestial({ socket }));
    }, [dispatch, socket]);

    useEffect(() => {
        loadTargets();
    }, [loadTargets]);

    const rows = useMemo(() => {
        const needle = search.trim().toLowerCase();
        return monitored.filter((row) => !needle || [row.displayName, row.command, row.bodyId, row.targetType]
            .some((value) => String(value || '').toLowerCase().includes(needle)));
    }, [monitored, search]);

    useEffect(() => {
        const valid = new Set(monitored.map((row) => row.id));
        setSelected((current) => current.filter((id) => valid.has(id)));
    }, [monitored]);

    const setRowsRefreshState = (ids, status, error = '') => {
        setRowRefreshStates((current) => {
            const next = { ...current };
            ids.forEach((id) => {
                next[id] = { status, error };
            });
            return next;
        });
    };

    const runBulk = async (action, requestedIds = selected) => {
        setBusy(true);
        setMessage(null);
        if (action === 'refresh') {
            setRowsRefreshState(requestedIds, 'refreshing');
        }
        try {
            if (action === 'refresh') {
                await dispatch(refreshMonitoredCelestialNow({ socket, ids: requestedIds })).unwrap();
            } else if (action === 'delete') {
                await dispatch(deleteMonitoredCelestial({ socket, ids: requestedIds })).unwrap();
                setSelected([]);
            } else {
                await Promise.all(requestedIds.map((id) => dispatch(toggleMonitoredCelestialEnabled({ socket, id, enabled: action === 'enable' })).unwrap()));
            }
            const refreshedRows = await dispatch(fetchMonitoredCelestial({ socket })).unwrap();
            if (action === 'refresh') {
                const refreshedById = new Map(refreshedRows.map((row) => [row.id, row]));
                setRowRefreshStates((current) => {
                    const next = { ...current };
                    requestedIds.forEach((id) => {
                        const row = refreshedById.get(id);
                        next[id] = row?.lastError
                            ? { status: 'error', error: row.lastError }
                            : { status: 'success', error: '' };
                    });
                    return next;
                });
            } else if (action !== 'delete') {
                setMessage({ severity: 'success', text: `Selected targets ${action}d.` });
            }
        } catch (error) {
            const errorText = String(error?.message || error);
            if (action === 'refresh') {
                setRowsRefreshState(requestedIds, 'error', errorText);
            } else {
                setMessage({ severity: 'error', text: errorText });
            }
        } finally {
            setBusy(false);
        }
    };

    const handleSaveEdit = async () => {
        const name = String(editTarget?.displayName || '').trim();
        const identifier = editTarget?.targetType === 'body'
            ? String(editTarget.bodyId || '').trim()
            : String(editTarget?.command || '').trim();
        if (!name || !identifier) {
            setEditError('Name and target identifier are required.');
            return;
        }
        try {
            await dispatch(updateMonitoredCelestial({ socket, entry: editTarget })).unwrap();
            setEditTarget(null);
            setEditError('');
            setMessage({ severity: 'success', text: 'Target updated.' });
        } catch (error) {
            setEditError(String(error?.message || error));
        }
    };

    const rowSelectionModel = useMemo(() => toRowSelectionModel(selected), [selected]);
    const columns = [
        {
            field: 'displayName',
            headerName: 'Target',
            minWidth: 220,
            flex: 1.2,
            renderCell: (params) => (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                    {params.row.color ? <Box sx={{ width: 10, height: 10, flexShrink: 0, borderRadius: '50%', bgcolor: params.row.color }} /> : null}
                    <Box sx={{ minWidth: 0 }}>
                        <Typography variant="body2" fontWeight={500} noWrap>{params.value}</Typography>
                        <Typography
                            variant="caption"
                            color={(params.row.targetType === 'body' ? params.row.bodyId : params.row.command) ? 'text.secondary' : 'text.disabled'}
                            noWrap
                            sx={{
                                display: 'block',
                                fontFamily: 'monospace',
                                fontStyle: (params.row.targetType === 'body' ? params.row.bodyId : params.row.command) ? 'normal' : 'italic',
                            }}
                        >
                            {(params.row.targetType === 'body' ? params.row.bodyId : params.row.command) || 'N/A'}
                        </Typography>
                    </Box>
                </Stack>
            ),
        },
        {
            field: 'targetType',
            headerName: 'Type',
            width: 110,
            renderCell: (params) => <Chip size="small" variant="outlined" label={params.value} />,
        },
        {
            field: 'enabled',
            headerName: 'Enabled',
            width: 95,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Switch
                    size="small"
                    checked={params.value}
                    disabled={!socket || busy}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => dispatch(toggleMonitoredCelestialEnabled({
                        socket,
                        id: params.row.id,
                        enabled: !params.value,
                    }))}
                />
            ),
        },
        {
            field: 'lastRefreshAt',
            headerName: 'Last refresh',
            minWidth: 180,
            flex: 0.8,
            renderCell: (params) => formatDateTime(params.value),
        },
        {
            field: 'lastError',
            headerName: 'Status',
            width: 135,
            renderCell: (params) => {
                const refreshState = rowRefreshStates[params.row.id];
                if (refreshState?.status === 'refreshing') {
                    return <Chip size="small" color="info" icon={<CircularProgress size={14} color="inherit" />} label="Refreshing" />;
                }
                if (refreshState?.status === 'success') {
                    return <Chip size="small" color="success" label="Refreshed" />;
                }
                if (refreshState?.status === 'error') {
                    return <Tooltip title={refreshState.error || 'Refresh failed'}><Chip size="small" color="error" label="Refresh failed" /></Tooltip>;
                }
                return params.value ? (
                    <Tooltip title={params.value}><Chip size="small" color="error" label="Error" /></Tooltip>
                ) : (
                    <Chip
                        size="small"
                        color={params.row.lastRefreshAt ? 'success' : 'warning'}
                        label={params.row.lastRefreshAt ? 'Ready' : 'Not fetched'}
                    />
                );
            },
        },
        {
            field: 'row_actions',
            headerName: '',
            width: 132,
            sortable: false,
            filterable: false,
            disableColumnMenu: true,
            align: 'center',
            headerAlign: 'center',
            renderCell: (params) => (
                <Stack direction="row" spacing={0.25}>
                    <Tooltip title="Refresh"><span><IconButton size="small" disabled={!socket || busy} onClick={(event) => { event.stopPropagation(); runBulk('refresh', [params.row.id]); }}>{rowRefreshStates[params.row.id]?.status === 'refreshing' ? <CircularProgress size={18} /> : <RefreshIcon fontSize="small" />}</IconButton></span></Tooltip>
                    <Tooltip title="Edit"><span><IconButton size="small" disabled={!socket || busy} onClick={(event) => { event.stopPropagation(); setEditTarget({ ...params.row }); }}><EditIcon fontSize="small" /></IconButton></span></Tooltip>
                    <Tooltip title="Delete"><span><IconButton size="small" color="error" disabled={!socket || busy} onClick={(event) => { event.stopPropagation(); setPendingDeleteIds([params.row.id]); }}><DeleteOutlineIcon fontSize="small" /></IconButton></span></Tooltip>
                </Stack>
            ),
        },
    ];

    return (
        <Paper elevation={3} sx={PAGE_PAPER_SX}>
            <PageHeading
                title="Monitored Celestial Targets"
                subtitle="Enable, refresh, edit, and remove the bodies and spacecraft used by the Solar System view."
                actions={(
                    <>
                        <Button startIcon={<RefreshIcon />} onClick={loadTargets} disabled={loading || busy}>Reload</Button>
                        <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/admin/celestial/catalog')}>Add from catalog</Button>
                    </>
                )}
            />
            {message ? <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message.text}</Alert> : null}
            <TextField size="small" label="Search targets" value={search} onChange={(event) => setSearch(event.target.value)} sx={{ mb: 2, minWidth: { xs: '100%', sm: 320 } }} InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }} />
            <DataGrid
                loading={loading}
                rows={rows}
                columns={columns}
                pageSizeOptions={[5, 10, 25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
                rowHeight={64}
                checkboxSelection
                rowSelectionModel={rowSelectionModel}
                onRowSelectionModelChange={(model) => setSelected(toSelectedIds(model))}
                localeText={{ noRowsLabel: 'No monitored targets found.' }}
                sx={DATA_GRID_SX}
            />
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 2 }}>
                <Button variant="contained" startIcon={<RefreshIcon />} disabled={!socket || busy || selected.length === 0} onClick={() => runBulk('refresh')}>Refresh selected</Button>
                <Button variant="outlined" disabled={!socket || busy || selected.length === 0} onClick={() => runBulk('enable')}>Enable</Button>
                <Button variant="outlined" disabled={!socket || busy || selected.length === 0} onClick={() => runBulk('disable')}>Disable</Button>
                <Button variant="contained" color="error" startIcon={<DeleteOutlineIcon />} disabled={!socket || busy || selected.length === 0} onClick={() => setPendingDeleteIds(selected)}>Delete</Button>
                <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center', ml: { sm: 'auto' } }}>{selected.length} selected</Typography>
            </Stack>

            <Dialog open={Boolean(editTarget)} onClose={() => setEditTarget(null)} maxWidth="sm" fullWidth>
                <DialogTitle>Edit celestial target</DialogTitle>
                <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
                    <TextField label="Display name" size="small" value={editTarget?.displayName || ''} onChange={(event) => setEditTarget((current) => ({ ...current, displayName: event.target.value }))} />
                    <TextField label={editTarget?.targetType === 'body' ? 'Body ID' : 'Horizons command'} size="small" value={editTarget?.targetType === 'body' ? editTarget?.bodyId || '' : editTarget?.command || ''} onChange={(event) => setEditTarget((current) => ({ ...current, [current.targetType === 'body' ? 'bodyId' : 'command']: event.target.value }))} />
                    <Stack direction="row" spacing={1} alignItems="center">
                        <TextField label="Color" size="small" value={editTarget?.color || ''} onChange={(event) => setEditTarget((current) => ({ ...current, color: event.target.value }))} sx={{ flex: 1 }} />
                        <input type="color" aria-label="Pick target color" value={/^#[0-9a-f]{6}$/i.test(editTarget?.color || '') ? editTarget.color : '#06D6A0'} onChange={(event) => setEditTarget((current) => ({ ...current, color: event.target.value.toUpperCase() }))} style={{ width: 44, height: 36 }} />
                    </Stack>
                    {editError ? <Alert severity="error">{editError}</Alert> : null}
                </Stack></DialogContent>
                <DialogActions><Button onClick={() => setEditTarget(null)}>Cancel</Button><Button variant="contained" onClick={handleSaveEdit} disabled={saveLoading}>Save</Button></DialogActions>
            </Dialog>

            <Dialog
                open={pendingDeleteIds.length > 0}
                onClose={() => !busy && setPendingDeleteIds([])}
                maxWidth="sm"
                fullWidth
                PaperProps={{ sx: { bgcolor: 'background.paper', borderRadius: 2 } }}
            >
                <DialogTitle
                    sx={{
                        bgcolor: 'error.main',
                        color: 'error.contrastText',
                        fontSize: '1.125rem',
                        fontWeight: 600,
                        py: 2,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1.5,
                    }}
                >
                    <Box
                        component="span"
                        sx={{
                            width: 24,
                            height: 24,
                            borderRadius: '50%',
                            bgcolor: 'error.contrastText',
                            color: 'error.main',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 'bold',
                            fontSize: '1rem',
                        }}
                    >
                        !
                    </Box>
                    Confirm target deletion
                </DialogTitle>
                <DialogContent sx={{ px: 3, pt: 3, pb: 3 }}>
                    <Typography variant="body1" sx={{ mt: 2, mb: 1 }}>
                        {pendingDeleteIds.length === 1
                            ? 'This target will be removed from the monitored list.'
                            : `${pendingDeleteIds.length} targets will be removed from the monitored list.`}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        Deleted targets stop appearing in the Solar System view. You can monitor them again from the Celestial Catalog.
                    </Typography>
                </DialogContent>
                <DialogActions
                    sx={{
                        bgcolor: (theme) => theme.palette.mode === 'dark' ? 'grey.900' : 'grey.100',
                        borderTop: '1px solid',
                        borderColor: 'divider',
                        px: 3,
                        py: 2,
                        gap: 1,
                    }}
                >
                    <Button variant="outlined" onClick={() => setPendingDeleteIds([])} disabled={busy}>Cancel</Button>
                    <Button
                        variant="contained"
                        color="error"
                        startIcon={<DeleteOutlineIcon />}
                        disabled={busy}
                        onClick={async () => {
                            const ids = pendingDeleteIds;
                            setPendingDeleteIds([]);
                            await runBulk('delete', ids);
                        }}
                    >
                        Delete
                    </Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
}
