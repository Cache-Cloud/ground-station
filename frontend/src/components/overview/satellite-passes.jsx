/**
 * @license
 * Copyright (c) 2025 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 */


import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {useSocket} from "../common/socket.jsx";
import { toast } from '../../utils/toast-with-timestamp.jsx';
import {calculateElevationCurvesForPasses} from '../../utils/elevation-curve-calculator.js';
import {
    formatWithZeros,
    getClassNamesBasedOnGridEditing,
    getTimeFromISO,
    humanizeFutureDateInMinutes,
    TitleBar,
    getFrequencyBand,
    getBandColor,
} from "../common/common.jsx";
import {DataGrid, gridClasses} from "@mui/x-data-grid";
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import ArrowUpwardRoundedIcon from '@mui/icons-material/ArrowUpwardRounded';
import ArrowDownwardRoundedIcon from '@mui/icons-material/ArrowDownwardRounded';
import RadioButtonCheckedIcon from '@mui/icons-material/RadioButtonChecked';
import AccessTimeFilledIcon from '@mui/icons-material/AccessTimeFilled';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import BlockIcon from '@mui/icons-material/Block';
import {useDispatch, useSelector} from "react-redux";
import {
    fetchNextPassesForGroup,
    fetchSatelliteGroups,
    fetchSatellitesByGroupId,
    setPasses,
    setSelectedSatelliteId,
    setPassesTablePageSize,
    setPassesTableSortModel,
    updatePassesWithElevationCurves,
    setPassesTableColumnVisibility,
    setOpenPassesTableSettingsDialog,
} from './overview-slice.jsx';
import {Typography, Box, IconButton, Tooltip, Button, useMediaQuery, useTheme} from '@mui/material';
import {useGridApiRef, GridPagination} from '@mui/x-data-grid';
import {alpha, darken, lighten, styled} from '@mui/material/styles';
import {Chip} from "@mui/material";
import {useStore} from 'react-redux';
import {
    gridPageCountSelector,
    gridPageSelector,
    gridRowSelectionCountSelector,
    useGridApiContext,
    useGridSelector,
} from '@mui/x-data-grid';
import ProgressFormatter from "./progressbar-widget.jsx";
import { useTranslation } from 'react-i18next';
import { enUS, elGR } from '@mui/x-data-grid/locales';
import ElevationDisplay from "../common/elevation-display.jsx";
import GpsFixedIcon from '@mui/icons-material/GpsFixed';
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import PassesTableSettingsDialog from './passes-table-settings-dialog.jsx';
import { useUserTimeSettings } from '../../hooks/useUserTimeSettings.jsx';


const getPassBackgroundColor = (color, theme, coefficient) => ({
    backgroundColor: darken(color, coefficient),
    ...theme.applyStyles('light', {
        backgroundColor: lighten(color, coefficient),
    }),
});

const getPassStatus = (row, now = new Date()) => {
    if (row?.status === 'dead') return 'dead';
    const eventStart = new Date(row?.event_start);
    const eventEnd = new Date(row?.event_end);
    if (eventStart <= now && eventEnd >= now) return 'live';
    if (eventEnd < now) return 'passed';
    return 'upcoming';
};

const getPassStatusPriority = (status) => {
    switch (status) {
        case 'live':
            return 0;
        case 'upcoming':
            return 1;
        case 'passed':
            return 2;
        case 'dead':
            return 3;
        default:
            return 4;
    }
};

const StyledDataGrid = styled(DataGrid)(({theme}) => ({
    '& .MuiDataGrid-row': {
        borderLeft: '3px solid transparent',
    },
    '& .passes-row-live': {
        backgroundColor: alpha(theme.palette.success.main, 0.2),
        borderLeftColor: alpha(theme.palette.success.main, 0.95),
        ...theme.applyStyles('light', {
            backgroundColor: alpha(theme.palette.success.main, 0.1),
            borderLeftColor: alpha(theme.palette.success.main, 0.65),
        }),
        '&:hover': {
            backgroundColor: alpha(theme.palette.success.main, 0.27),
            ...theme.applyStyles('light', {
                backgroundColor: alpha(theme.palette.success.main, 0.14),
            }),
        },
    },
    '& .passes-row-upcoming-soon': {
        backgroundColor: alpha(theme.palette.warning.main, 0.14),
        borderLeftColor: alpha(theme.palette.warning.main, 0.9),
        ...theme.applyStyles('light', {
            backgroundColor: alpha(theme.palette.warning.main, 0.08),
            borderLeftColor: alpha(theme.palette.warning.main, 0.6),
        }),
    },
    '& .passes-row-passed': {
        '& .MuiDataGrid-cell': {
            color: theme.palette.text.secondary,
        },
        '& .passes-time-absolute': {
            opacity: 0.8,
        },
    },
    '& .passes-row-dead': {
        backgroundColor: alpha(theme.palette.error.main, 0.24),
        borderLeftColor: alpha(theme.palette.error.main, 0.9),
        ...theme.applyStyles('light', {
            backgroundColor: alpha(theme.palette.error.main, 0.1),
            borderLeftColor: alpha(theme.palette.error.main, 0.65),
        }),
    },
    '& .passes-cell-passing': {
        ...getPassBackgroundColor(theme.palette.success.main, theme, 0.7),
        '&:hover': {
            ...getPassBackgroundColor(theme.palette.success.main, theme, 0.6),
        },
        '&.Mui-selected': {
            ...getPassBackgroundColor(theme.palette.success.main, theme, 0.5),
            '&:hover': {
                ...getPassBackgroundColor(theme.palette.success.main, theme, 0.4),
            },
        },
    },
    '& .passes-cell-passed': {
        backgroundColor: alpha(theme.palette.info.main, 0.28),
        borderLeft: `2px solid ${alpha(theme.palette.info.main, 0.85)}`,
        ...theme.applyStyles('light', {
            backgroundColor: alpha(theme.palette.info.main, 0.14),
            borderLeft: `2px solid ${alpha(theme.palette.info.main, 0.55)}`,
        }),
        '&:hover': {
            backgroundColor: alpha(theme.palette.info.main, 0.34),
            ...theme.applyStyles('light', {
                backgroundColor: alpha(theme.palette.info.main, 0.2),
            }),
        },
        '&.Mui-selected': {
            backgroundColor: alpha(theme.palette.info.main, 0.4),
            ...theme.applyStyles('light', {
                backgroundColor: alpha(theme.palette.info.main, 0.24),
            }),
            '&:hover': {
                backgroundColor: alpha(theme.palette.info.main, 0.46),
                ...theme.applyStyles('light', {
                    backgroundColor: alpha(theme.palette.info.main, 0.28),
                }),
            },
        },
        textDecoration: 'line-through',
    },
    '& .passes-cell-dead': {
        ...getPassBackgroundColor(theme.palette.error.main, theme, 0.7),
        '&:hover': {
            ...getPassBackgroundColor(theme.palette.error.main, theme, 0.6),
        },
        '&.Mui-selected': {
            ...getPassBackgroundColor(theme.palette.error.main, theme, 0.5),
            '&:hover': {
                ...getPassBackgroundColor(theme.palette.error.main, theme, 0.4),
            },
        },
        textDecoration: 'line-through',
    },
    '& .passes-cell-warning': {
        color: theme.palette.error.main,
        textDecoration: 'line-through',
    },
    '& .passes-cell-success': {
        color: theme.palette.success.main,
        fontWeight: 'bold',
        textDecoration: 'underline',
    },
    '& .passes-cell-active': {
        ...getPassBackgroundColor(theme.palette.secondary.dark, theme, 0.7),
        fontWeight: 'bold',
        '&:hover': {
            ...getPassBackgroundColor(theme.palette.secondary.main, theme, 0.6),
        },
        '&.Mui-selected': {
            ...getPassBackgroundColor(theme.palette.secondary.main, theme, 0.5),
            '&:hover': {
                ...getPassBackgroundColor(theme.palette.secondary.main, theme, 0.4),
            },
        },
    }
}));

const CustomPagination = () => {
    const apiRef = useGridApiContext();
    const page = useGridSelector(apiRef, gridPageSelector);
    const pageCount = useGridSelector(apiRef, gridPageCountSelector);
    const selectedRowCount = useGridSelector(apiRef, gridRowSelectionCountSelector);
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const isTablet = useMediaQuery(theme.breakpoints.down('md'));
    const isMedium = useMediaQuery(theme.breakpoints.down('lg'));

    const handlePageChange = (newPage) => {
        apiRef.current.setPage(newPage);
    };

    // Calculate which page buttons to show
    const getPageNumbers = () => {
        const maxButtons = isMobile ? 5 : isTablet ? 8 : 12;
        const pages = [];

        if (pageCount <= maxButtons) {
            // Show all pages if they fit
            for (let i = 0; i < pageCount; i++) {
                pages.push(i);
            }
        } else {
            // Show pages around current page
            const halfWindow = Math.floor(maxButtons / 2);
            let start = Math.max(0, page - halfWindow);
            let end = Math.min(pageCount - 1, start + maxButtons - 1);

            // Adjust start if we're near the end
            if (end - start < maxButtons - 1) {
                start = Math.max(0, end - maxButtons + 1);
            }

            for (let i = start; i <= end; i++) {
                pages.push(i);
            }
        }

        return pages;
    };

    const pageNumbers = getPageNumbers();

    return (
        <Box sx={{
            display: 'flex',
            alignItems: 'center',
            width: '100%',
            p: 1,
            gap: 2,
            height: '52px',
            minHeight: '52px',
            maxHeight: '52px',
            position: 'relative',
            overflow: 'hidden',
        }}>
            <Box sx={{ flex: '1 1 0', display: 'flex', justifyContent: 'flex-start', minWidth: 0, alignItems: 'center', height: '100%' }}>
                {selectedRowCount > 0 && (
                    <Typography variant="body2" sx={{ whiteSpace: 'nowrap', lineHeight: 1 }}>
                        {selectedRowCount} pass{selectedRowCount !== 1 ? 'es' : ''} selected
                    </Typography>
                )}
            </Box>
            <Box sx={{
                position: 'absolute',
                left: '50%',
                transform: 'translateX(-50%)',
                display: 'flex',
                gap: 0.5,
                flexWrap: 'nowrap',
                justifyContent: 'center',
                overflow: 'hidden',
                alignItems: 'center',
                height: '100%',
            }}>
                {pageNumbers.map((pageNum) => (
                    <Button
                        key={pageNum}
                        size="small"
                        variant={page === pageNum ? 'contained' : 'outlined'}
                        onClick={() => handlePageChange(pageNum)}
                        sx={{
                            minWidth: isMobile ? '32px' : '40px',
                            px: isMobile ? 0.5 : 1,
                            py: 0.5,
                            height: '32px',
                        }}
                    >
                        {pageNum + 1}
                    </Button>
                ))}
            </Box>
            <Box sx={{ flex: '1 1 0', display: isMedium ? 'none' : 'flex', justifyContent: 'flex-end', minWidth: 0, alignItems: 'center', height: '100%', overflow: 'hidden' }}>
                <Box sx={{ transform: 'scale(0.9)', transformOrigin: 'right center' }}>
                    <GridPagination />
                </Box>
            </Box>
        </Box>
    );
};

const TimeFormatter = React.memo(function TimeFormatter({params, value, nowMs}) {
    const { timezone, locale } = useUserTimeSettings();
    const relativeTime = useMemo(() => humanizeFutureDateInMinutes(value), [value, nowMs]);

    if (params.row.is_geostationary || params.row.is_geosynchronous) {
        return "∞";
    }

    return (
        <Box sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <Typography component="span" variant="caption" sx={{ fontWeight: 700, color: 'text.primary' }}>
                {relativeTime}
            </Typography>
            <Typography component="span" className="passes-time-absolute" variant="caption" sx={{ color: 'text.secondary', ml: 0.5 }}>
                · {getTimeFromISO(value, timezone, locale)}
            </Typography>
        </Box>
    );
});


const DurationFormatter = React.memo(function DurationFormatter({params, event_start, event_end, nowMs}) {
    const { t } = useTranslation('overview');
    const now = new Date(nowMs);
    const startDate = new Date(event_start);
    const endDate = new Date(event_end);

    if (params.row.is_geostationary || params.row.is_geosynchronous) {
        return "∞";
    }

    if (startDate > now) {
        // Pass is in the future
        const diffInSeconds = Math.floor((endDate - startDate) / 1000);
        const minutes = Math.floor(diffInSeconds / 60);
        const seconds = diffInSeconds % 60;
        return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;

    } else if (endDate < now) {
        // Pass ended
        const diffInSeconds = Math.floor((endDate - startDate) / 1000);
        const minutes = Math.floor(diffInSeconds / 60);
        const seconds = diffInSeconds % 60;
        return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;

    } else if (startDate < now && now < endDate) {
        // Passing now
        const diffInSeconds = Math.floor((endDate - now) / 1000);
        const minutes = Math.floor(diffInSeconds / 60);
        const seconds = diffInSeconds % 60;
        return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;

    } else {
        return t('passes_table.no_value');
    }
});

const PassStatusCell = React.memo(function PassStatusCell({status}) {
    const statusConfig = {
        live: {
            label: 'Live',
            color: 'success',
            icon: <RadioButtonCheckedIcon sx={{ fontSize: '0.85rem' }} />,
        },
        upcoming: {
            label: 'Upcoming',
            color: 'warning',
            icon: <AccessTimeFilledIcon sx={{ fontSize: '0.85rem' }} />,
        },
        passed: {
            label: 'Passed',
            color: 'info',
            icon: <DoneAllIcon sx={{ fontSize: '0.85rem' }} />,
        },
        dead: {
            label: 'Dead',
            color: 'error',
            icon: <BlockIcon sx={{ fontSize: '0.85rem' }} />,
        },
    };
    const config = statusConfig[status] || statusConfig.upcoming;
    return (
        <Chip
            icon={config.icon}
            size="small"
            label={config.label}
            color={config.color}
            variant={status === 'upcoming' ? 'outlined' : 'filled'}
            sx={{ fontWeight: 700, minWidth: 85 }}
        />
    );
});

const PassBandsCell = React.memo(function PassBandsCell({transmitters, noDataText}) {
    if (!transmitters) {
        return noDataText;
    }

    const bandDetails = transmitters.reduce((acc, transmitter) => {
        const upBand = transmitter['uplink_low'] != null
            ? getFrequencyBand(transmitter['uplink_low'])
            : null;
        const downBand = transmitter['downlink_low'] != null
            ? getFrequencyBand(transmitter['downlink_low'])
            : null;

        const uniqueBands = new Set([upBand, downBand].filter(Boolean));
        uniqueBands.forEach((band) => {
            if (!acc[band]) {
                acc[band] = { count: 0, uplink: false, downlink: false };
            }
            acc[band].count += 1;
        });

        if (upBand) {
            if (!acc[upBand]) acc[upBand] = { count: 0, uplink: false, downlink: false };
            acc[upBand].uplink = true;
        }

        if (downBand) {
            if (!acc[downBand]) acc[downBand] = { count: 0, uplink: false, downlink: false };
            acc[downBand].downlink = true;
        }

        return acc;
    }, {});

    const bands = Object.keys(bandDetails);

    return (
        <div style={{display: 'flex', gap: 2, flexWrap: 'wrap', justifyContent: 'center'}}>
            {bands.map((band, index) => (
                <React.Fragment key={index}>
                    {bandDetails[band].count} ✕ <Chip
                    label={
                        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.35 }}>
                            <Box component="span">{band}</Box>
                            {bandDetails[band].uplink && <ArrowUpwardRoundedIcon sx={{ fontSize: '0.85rem' }} />}
                            {bandDetails[band].downlink && <ArrowDownwardRoundedIcon sx={{ fontSize: '0.85rem' }} />}
                        </Box>
                    }
                    size="small"
                    sx={{
                        mt: '8px',
                        height: '18px',
                        fontSize: '0.65rem',
                        fontWeight: 'bold',
                        backgroundColor: getBandColor(band),
                        color: 'common.white',
                        '& .MuiChip-label': {
                            px: 0.75
                        },
                        '&:hover': {
                            filter: 'brightness(90%)',
                        }
                    }}
                />
                </React.Fragment>
            ))}
        </div>
    );
});

const PassProgressCell = React.memo(function PassProgressCell({row, nowMs}) {
    return <ProgressFormatter row={row} nowMs={nowMs} />;
}, (prevProps, nextProps) => (
    prevProps.nowMs === nextProps.nowMs &&
    prevProps.row?.id === nextProps.row?.id &&
    prevProps.row?.event_start === nextProps.row?.event_start &&
    prevProps.row?.event_end === nextProps.row?.event_end &&
    prevProps.row?.peak_time === nextProps.row?.peak_time &&
    prevProps.row?.is_geostationary === nextProps.row?.is_geostationary &&
    prevProps.row?.is_geosynchronous === nextProps.row?.is_geosynchronous
));

const MemoizedStyledDataGrid = React.memo(function MemoizedStyledDataGrid({
    passes,
    passesLoading,
    quickFilterPreset,
    onRowClick,
    onRowDoubleClick,
    passesAreCached = false,
    orbitProjectionDuration = 240,
    pageSize = 10,
    onPageSizeChange,
    sortModel,
    onSortModelChange,
    columnVisibility,
    onColumnVisibilityChange
}) {
    const apiRef = useGridApiRef();
    const store = useStore();
    const { t, i18n } = useTranslation('overview');
    const theme = useTheme();
    const isCompactView = useMediaQuery(theme.breakpoints.down('md'));
    const currentLanguage = i18n.language;
    const dataGridLocale = currentLanguage === 'el' ? elGR : enUS;
    const [page, setPage] = useState(0);
    const [nowMs, setNowMs] = useState(() => Date.now());
    const [relativeNowMs, setRelativeNowMs] = useState(() => Date.now());
    const nowMsRef = useRef(nowMs);
    nowMsRef.current = nowMs;
    const relativeNowMsRef = useRef(relativeNowMs);
    relativeNowMsRef.current = relativeNowMs;

    // Convert minutes to hours for display
    const projectionHours = Math.round(orbitProjectionDuration / 60);

    // This method allows us to reference values in redux without a re-render, crucial in the next passes table
    const targetSatTrackRef = useRef(() => {
        const state = store.getState();
        return state.targetSatTrack;
    });

    const selectedSatellitePositionsRef = useRef(() => {
        const state = store.getState();
        return state.overviewSatTrack.selectedSatellitePositions;
    });

    useEffect(() => {
        const intervalId = setInterval(() => {
            setNowMs(Date.now());
        }, 1000);
        return () => clearInterval(intervalId);
    }, []);

    useEffect(() => {
        const intervalId = setInterval(() => {
            setRelativeNowMs(Date.now());
        }, 5000);
        return () => clearInterval(intervalId);
    }, []);

    const localeText = useMemo(() => ({
        ...dataGridLocale.components.MuiDataGrid.defaultProps.localeText,
        noRowsLabel: t('passes_table.no_passes', { hours: projectionHours })
    }), [dataGridLocale.components.MuiDataGrid.defaultProps.localeText, projectionHours, t]);

    const filteredPasses = useMemo(() => {
        const now = new Date(nowMs);
        if (quickFilterPreset === 'live') {
            return passes.filter((pass) => getPassStatus(pass, now) === 'live');
        }
        if (quickFilterPreset === 'next30') {
            return passes.filter((pass) => {
                const status = getPassStatus(pass, now);
                if (status === 'live') return true;
                if (status !== 'upcoming') return false;
                const start = new Date(pass.event_start);
                return (start - now) <= 30 * 60 * 1000;
            });
        }
        return passes;
    }, [passes, quickFilterPreset, nowMs]);

    const columns = useMemo(() => [
        {
            field: 'status',
            minWidth: 110,
            headerName: 'Status',
            flex: 1,
            align: 'center',
            headerAlign: 'center',
            valueGetter: (_value, row) => getPassStatus(row, new Date(nowMsRef.current)),
            sortComparator: (v1, v2) => getPassStatusPriority(v1) - getPassStatusPriority(v2),
            renderCell: (params) => <PassStatusCell status={params.value} />
        },
        {
            field: 'name',
            minWidth: 120,
            headerName: t('passes_table.name'),
            flex: 2,
            renderCell: (params) => {
                const targetSatTrack = targetSatTrackRef.current();
                const isTracked = targetSatTrack.satelliteData['details']['name'] === params.value;

                return <>
                    {isTracked && (
                        <GpsFixedIcon sx={{ mr: 0.5, fontSize: '1.3rem', color: 'info.main', verticalAlign: 'middle' }} />
                    )}
                    {params.value}
                </>;
            }
        },
        {
            field: 'alternative_name',
            minWidth: 120,
            headerName: t('passes_table.alternative_name'),
            flex: 2,
            valueGetter: (value, row) => {
                return row.alternative_name || '-';
            }
        },
        {
            field: 'name_other',
            minWidth: 120,
            headerName: t('passes_table.name_other'),
            flex: 2,
            valueGetter: (value, row) => {
                return row.name_other || '-';
            }
        },
        {
            field: 'peak_altitude',
            minWidth: 80,
            headerName: t('passes_table.peak_elevation'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return `${parseFloat(value).toFixed(2)}°`;
            },
            cellClassName: (params) => {
                if (params.value < 10.0) {
                    return "passes-cell-warning";
                } else if (params.value > 45.0) {
                    return "passes-cell-success";
                } else {
                    return '';
                }
            }
        },
        {
            field: 'elevation',
            minWidth: 90,
            headerName: t('passes_table.current_elevation'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            sortable: false,
            renderCell: (params) => {
                const now = new Date(nowMsRef.current);
                const isActive = new Date(params.row.event_start) < now && new Date(params.row.event_end) > now;

                if (!isActive) {
                    return <span>-</span>;
                }

                const selectedSatellitePositions = selectedSatellitePositionsRef.current();
                const noradId = params.row.id.split("_")[1];
                const position = selectedSatellitePositions?.[noradId];

                return (
                    <ElevationDisplay
                        elevation={position?.el}
                        trend={position?.trend}
                        timeToMaxEl={position?.timeToMaxEl}
                        elRate={position?.elRate}
                    />
                );
            }
        },
        {
            field: 'progress',
            minWidth: 100,
            headerName: t('passes_table.progress'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            renderCell: (params) => <PassProgressCell row={params.row} nowMs={nowMsRef.current} />
        },
        {
            field: 'duration',
            minWidth: 100,
            headerName: t('passes_table.duration'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            sortable: false,
            renderCell: (params) => (
                <div>
                    <DurationFormatter params={params} event_start={params.row.event_start}
                                       event_end={params.row.event_end} nowMs={nowMsRef.current}/>
                </div>
            )
        },
        {
            field: 'transmitters',
            minWidth: 120,
            align: 'center',
            headerAlign: 'center',
            headerName: t('passes_table.bands'),
            flex: 2,
            renderCell: (params) => <PassBandsCell transmitters={params.value} noDataText={t('passes_table.no_data')} />

        },
        {
            field: 'event_start',
            minWidth: 170,
            headerName: t('passes_table.start'),
            flex: 2,
            renderCell: (params) => {
                const status = getPassStatus(params.row, new Date(nowMsRef.current));
                const timeTickMs = status === 'live' ? nowMsRef.current : relativeNowMsRef.current;
                return <TimeFormatter params={params} value={params.value} nowMs={timeTickMs}/>;
            }
        },
        {
            field: 'event_end',
            minWidth: 170,
            headerName: t('passes_table.end'),
            flex: 2,
            renderCell: (params) => {
                const status = getPassStatus(params.row, new Date(nowMsRef.current));
                const timeTickMs = status === 'live' ? nowMsRef.current : relativeNowMsRef.current;
                return <TimeFormatter params={params} value={params.value} nowMs={timeTickMs}/>;
            }
        },
        {
            field: 'distance_at_start',
            minWidth: 100,
            headerName: t('passes_table.distance_aos'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return `${parseFloat(value).toFixed(2)} km`
            }
        },
        {
            field: 'distance_at_end',
            minWidth: 100,
            headerName: t('passes_table.distance_los'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return `${parseFloat(value).toFixed(2)} km`
            }
        },
        {
            field: 'distance_at_peak',
            minWidth: 100,
            headerName: t('passes_table.distance_peak'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return `${parseFloat(value).toFixed(2)} km`
            }
        },
        {
            field: 'is_geostationary',
            minWidth: 70,
            headerName: t('passes_table.geo_stat'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return value ? 'Yes' : 'No';
            },
            hide: true,
        },
        {
            field: 'is_geosynchronous',
            minWidth: 70,
            headerName: t('passes_table.geo_sync'),
            align: 'center',
            headerAlign: 'center',
            flex: 1,
            valueFormatter: (value) => {
                return value ? 'Yes' : 'No';
            },
            hide: true,
        },
    ], [t, targetSatTrackRef, selectedSatellitePositionsRef]);

    const effectiveColumnVisibility = useMemo(() => {
        const base = {
            status: true,
            ...columnVisibility,
        };
        if (!isCompactView) {
            return base;
        }
        return {
            ...base,
            alternative_name: false,
            name_other: false,
            elevation: false,
            duration: false,
            transmitters: false,
            event_end: false,
            distance_at_start: false,
            distance_at_end: false,
            distance_at_peak: false,
            is_geostationary: false,
            is_geosynchronous: false,
        };
    }, [columnVisibility, isCompactView]);

    const getPassesRowStyles = useCallback((param) => {
        if (param.row) {
            const now = new Date(nowMsRef.current);
            const eventStart = new Date(param.row.event_start);
            const status = getPassStatus(param.row, now);
            if (status === 'dead') return 'passes-row-dead pointer-cursor';
            if (status === 'passed') return 'passes-row-passed pointer-cursor';
            if (status === 'live') return 'passes-row-live pointer-cursor';
            if ((eventStart - now) <= 30 * 60 * 1000) {
                return 'passes-row-upcoming-soon pointer-cursor';
            }
            return "pointer-cursor";
        }
        return "pointer-cursor";
    }, []);

    const getRowId = useCallback((params) => params.id, []);

    const handlePaginationModelChange = useCallback((model) => {
        setPage(model.page);
        if (onPageSizeChange && model.pageSize !== pageSize) {
            onPageSizeChange(model.pageSize);
        }
    }, [onPageSizeChange, pageSize]);

    return (
        <StyledDataGrid
            apiRef={apiRef}
            pageSizeOptions={[5, 10, 15, 20]}
            fullWidth={true}
            loading={passesLoading}
            getRowClassName={getPassesRowStyles}
            onRowClick={onRowClick}
            onRowDoubleClick={onRowDoubleClick}
            getRowId={getRowId}
            localeText={localeText}
            sx={{
                border: 0,
                marginTop: 0,
                [`& .${gridClasses.cell}:focus, & .${gridClasses.cell}:focus-within`]: {
                    outline: 'none',
                },
                [`& .${gridClasses.columnHeader}:focus, & .${gridClasses.columnHeader}:focus-within`]:
                    {
                        outline: 'none',
                    },
                '& .MuiDataGrid-overlay': {
                    fontSize: '0.875rem',
                    fontStyle: 'italic',
                    color: 'text.secondary',
                },
                '& .MuiDataGrid-selectedRowCount': {
                    visibility: 'hidden',
                    position: 'absolute',
                },
            }}
            density={"compact"}
            rows={filteredPasses}
            paginationModel={{
                pageSize: pageSize,
                page: page,
            }}
            onPaginationModelChange={handlePaginationModelChange}
            sortModel={sortModel}
            onSortModelChange={onSortModelChange}
            columnVisibilityModel={effectiveColumnVisibility}
            onColumnVisibilityModelChange={onColumnVisibilityChange}
            columns={columns}
            pinnedColumns={isCompactView ? { left: ['name'], right: [] } : { left: ['name', 'status'], right: ['progress'] }}
            slots={{
                pagination: CustomPagination,
            }}
        />
    );
}, (prevProps, nextProps) => {
    // Custom comparison function - return true if props haven't changed in ways that matter
    return (
        prevProps.passes === nextProps.passes &&
        prevProps.quickFilterPreset === nextProps.quickFilterPreset &&
        prevProps.passesLoading === nextProps.passesLoading &&
        prevProps.orbitProjectionDuration === nextProps.orbitProjectionDuration &&
        prevProps.pageSize === nextProps.pageSize &&
        prevProps.sortModel === nextProps.sortModel &&
        prevProps.columnVisibility === nextProps.columnVisibility
    );
});


const NextPassesGroupIsland = React.memo(function NextPassesGroupIsland() {
    const {socket} = useSocket();
    const dispatch = useDispatch();
    const { t } = useTranslation('overview');
    const containerRef = useRef(null);
    const hasFetchedRef = useRef(false);
    const lastFetchParamsRef = useRef(null);
    const [containerHeight, setContainerHeight] = useState(0);
    const {
        selectedSatGroupId,
        passes,
        passesAreCached,
        passesLoading,
        passesRangeStart,
        passesRangeEnd,
        passesCachedGroupId,
        nextPassesHours,
        orbitProjectionDuration,
        gridEditable,
        passesTablePageSize,
        passesTableSortModel,
        passesTableColumnVisibility,
        openPassesTableSettingsDialog,
        selectedSatellites
    } = useSelector(state => state.overviewSatTrack);
    const { location } = useSelector(state => state.location);

    const minHeight = 200;
    const maxHeight = 400;
    const [columnUpdateKey, setColumnUpdateKey] = useState(0);
    const hasLoadedFromStorageRef = useRef(false);
    const isLoadingRef = useRef(false);
    const [quickFilterPreset, setQuickFilterPreset] = useState('all');

    // Load column visibility from localStorage on mount
    useEffect(() => {
        // Prevent double loading (React StrictMode or component remounting)
        if (isLoadingRef.current || hasLoadedFromStorageRef.current) {
            return;
        }

        isLoadingRef.current = true;

        const loadColumnVisibility = () => {
            try {
                const stored = localStorage.getItem('passes-table-column-visibility');
                if (stored) {
                    const parsedVisibility = JSON.parse(stored);
                    dispatch(setPassesTableColumnVisibility(parsedVisibility));
                }
            } catch (e) {
                console.error('Failed to load passes table column visibility:', e);
            } finally {
                hasLoadedFromStorageRef.current = true;
                isLoadingRef.current = false;
            }
        };
        loadColumnVisibility();
    }, []); // Empty deps - only run once on mount

    // Persist column visibility to localStorage whenever it changes (but not on initial load)
    useEffect(() => {
        if (passesTableColumnVisibility && hasLoadedFromStorageRef.current) {
            try {
                localStorage.setItem('passes-table-column-visibility', JSON.stringify(passesTableColumnVisibility));
            } catch (e) {
                console.error('Failed to save passes table column visibility:', e);
            }
        }
    }, [passesTableColumnVisibility]);

    const handleRefreshPasses = () => {
        if (selectedSatGroupId) {
            dispatch(fetchNextPassesForGroup({
                socket,
                selectedSatGroupId,
                hours: nextPassesHours,
                forceRecalculate: true
            }));
        }
    };

    useEffect(() => {
        if (selectedSatGroupId) {
            const currentParams = `${selectedSatGroupId}-${nextPassesHours}`;

            // Only fetch if parameters have changed
            if (lastFetchParamsRef.current !== currentParams) {
                lastFetchParamsRef.current = currentParams;
                hasFetchedRef.current = false; // Reset for new parameters

                // Immediately fetch when group changes - don't rely on cache from different group
                hasFetchedRef.current = true;
                dispatch(fetchNextPassesForGroup({socket, selectedSatGroupId, hours: nextPassesHours}));
                return; // Exit early to prevent cache check logic
            }

            // Check if we have valid cached data covering the requested time window
            const hasValidTimeWindow = () => {
                if (!passes || passes.length === 0) return false;
                if (!passesRangeStart || !passesRangeEnd) return false;

                // Check if cached data is for the currently selected group
                if (passesCachedGroupId !== selectedSatGroupId) return false;

                // Calculate expected time window
                const now = new Date();

                // Parse cached time window
                const cachedStart = new Date(passesRangeStart);
                const cachedEnd = new Date(passesRangeEnd);

                // Check if cached window still covers most of the requested window
                // Allow some tolerance since time passes between visits
                // If cached data covers at least 90% of the requested window, consider it valid
                const tolerance = 0.9; // 90% coverage required
                const requestedWindowDuration = nextPassesHours * 60 * 60 * 1000; // in milliseconds
                const minAcceptableEnd = new Date(now.getTime() + (requestedWindowDuration * tolerance));

                // Check if cached window covers the requested window (with tolerance)
                const cachedStartValid = cachedStart <= now;
                const cachedEndValid = cachedEnd >= minAcceptableEnd;

                return cachedStartValid && cachedEndValid;
            };

            if (!hasFetchedRef.current && !hasValidTimeWindow()) {
                hasFetchedRef.current = true;
                dispatch(fetchNextPassesForGroup({socket, selectedSatGroupId, hours: nextPassesHours}));
            } else if (hasValidTimeWindow()) {
                // Mark as fetched to prevent refetch - we have valid data in Redux
                hasFetchedRef.current = true;
            }
        }

        // Don't reset hasFetchedRef in cleanup - that's what causes the double call in StrictMode
        // return () => {
        //     hasFetchedRef.current = false;
        // };
    }, [selectedSatGroupId, dispatch, socket, nextPassesHours, passes, passesRangeStart, passesRangeEnd, passesCachedGroupId]);

    // Track which passes we've calculated curves for by creating a hash
    const calculatedPassesHashRef = useRef(null);
    const calculatingRef = useRef(false);

    // Fetch satellites if we have a selected group but no satellites loaded yet
    // This handles the case where page loads with a group already selected (from localStorage)
    useEffect(() => {
        if (selectedSatGroupId && (!selectedSatellites || selectedSatellites.length === 0) && !passesLoading) {
            dispatch(fetchSatellitesByGroupId({ socket, satGroupId: selectedSatGroupId }));
        }
    }, [selectedSatGroupId, selectedSatellites, dispatch, socket, passesLoading]);

    // Calculate elevation curves when passes are received
    useEffect(() => {
        // If we're currently calculating, skip
        if (calculatingRef.current) {
            return;
        }

        // Check if location is valid (not null)
        const isLocationValid = location && location.lat != null && location.lon != null;

        if (passes && passes.length > 0 && isLocationValid && selectedSatellites && selectedSatellites.length > 0) {
            // Create hash of pass IDs to detect if these are actually NEW passes
            const currentPassesHash = passes?.map(p => `${p.norad_id}-${p.event_start}`).sort().join('|') || '';

            // If we already attempted calculation for this hash, skip
            // (even if some passes still have empty curves - those are likely defensive BSTAR rejections)
            if (calculatedPassesHashRef.current === currentPassesHash && currentPassesHash !== '') {
                return;
            }

            // If hash changed (new passes), calculate
            if (calculatedPassesHashRef.current !== currentPassesHash) {
                calculatingRef.current = true;
                calculatedPassesHashRef.current = currentPassesHash;

                // Create satellite lookup from selectedSatellites
                const satelliteLookup = {};
                selectedSatellites.forEach(sat => {
                    satelliteLookup[sat.norad_id] = {
                        norad_id: sat.norad_id,
                        tle1: sat.tle1,
                        tle2: sat.tle2
                    };
                });

                // Verify all passes have corresponding satellites in the lookup
                const allPassesHaveSatellites = passes.every(pass => satelliteLookup[pass.norad_id]);

                if (!allPassesHaveSatellites) {
                    // Passes belong to a different satellite group, skip calculation
                    calculatingRef.current = false;
                    calculatedPassesHashRef.current = null;
                    return;
                }

                // Calculate elevation curves in the background
                setTimeout(() => {
                    const passesWithCurves = calculateElevationCurvesForPasses(
                        passes,
                        { lat: location.lat, lon: location.lon },
                        satelliteLookup
                    );
                    dispatch(updatePassesWithElevationCurves(passesWithCurves));
                    calculatingRef.current = false;
                }, 0);
            }
        }
    }, [passes, location, dispatch, selectedSatellites]);

    useEffect(() => {
        // Update the passes every two hours plus 5 mins to wait until the cache is invalidated
        const interval = setInterval(() => {
            if (selectedSatGroupId) {
                dispatch(fetchNextPassesForGroup({socket, selectedSatGroupId, hours: nextPassesHours}));
            }
        }, 7200000 + (60000 * 5));

        return () => {
            clearInterval(interval);
        }
    }, [selectedSatGroupId, socket, nextPassesHours, dispatch]);

    useEffect(() => {
        const target = containerRef.current;
        const observer = new ResizeObserver((entries) => {
            setContainerHeight(entries[0].contentRect.height);
        });
        if (target) {
            observer.observe(target);
        }
        return () => {
            observer.disconnect();
        };
    }, [containerRef]);

    const handleOnRowClick = (params) => {
        const noradId = params.row.id.split("_")[1];
        dispatch(setSelectedSatelliteId(parseInt(noradId)));
    };

    const handleOnRowDoubleClick = (params) => {
        handleOnRowClick(params);
    };

    const handlePageSizeChange = (newPageSize) => {
        dispatch(setPassesTablePageSize(newPageSize));
    };

    const handleSortModelChange = (newSortModel) => {
        dispatch(setPassesTableSortModel(newSortModel));
    };

    const handleColumnVisibilityChange = (newModel) => {
        dispatch(setPassesTableColumnVisibility(newModel));
    };

    const handleOpenSettings = () => {
        dispatch(setOpenPassesTableSettingsDialog(true));
    };

    const handleCloseSettings = () => {
        dispatch(setOpenPassesTableSettingsDialog(false));
    };

    const applyDefaultSort = useCallback(() => {
        dispatch(setPassesTableSortModel([
            { field: 'status', sort: 'asc' },
            { field: 'event_start', sort: 'asc' },
        ]));
    }, [dispatch]);

    const handleQuickPreset = useCallback((preset) => {
        setQuickFilterPreset(preset);
        if (preset === 'highEl') {
            dispatch(setPassesTableSortModel([
                { field: 'peak_altitude', sort: 'desc' },
                { field: 'event_start', sort: 'asc' },
            ]));
            return;
        }
        applyDefaultSort();
    }, [dispatch, applyDefaultSort]);

    useEffect(() => {
        const handleKeyboardShortcuts = (event) => {
            if (!event.altKey) return;
            if (event.key === '1') {
                handleQuickPreset('all');
            } else if (event.key === '2') {
                handleQuickPreset('live');
            } else if (event.key === '3') {
                handleQuickPreset('next30');
            } else if (event.key === '4') {
                handleQuickPreset('highEl');
            } else {
                return;
            }
            event.preventDefault();
        };

        window.addEventListener('keydown', handleKeyboardShortcuts);
        return () => window.removeEventListener('keydown', handleKeyboardShortcuts);
    }, [handleQuickPreset]);

    return (
        <>
            <TitleBar
                className={getClassNamesBasedOnGridEditing(gridEditable, ["window-title-bar"])}
                sx={{
                    bgcolor: 'background.titleBar',
                    borderBottom: '1px solid',
                    borderColor: 'border.main',
                    backdropFilter: 'blur(10px)',
                    height: 30,
                    minHeight: 30,
                    py: 0,
                    display: 'flex',
                    alignItems: 'center',
                }}
            >
                <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', height: '100%'}}>
                    <Box sx={{display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, flex: 1}}>
                        <Typography variant="subtitle2" sx={{
                            fontWeight: 'bold',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            minWidth: 0
                        }}>
                            {t('passes_table.title', { hours: nextPassesHours })}
                        </Typography>
                        <Typography variant="caption" sx={{
                            fontStyle: 'italic',
                            color: 'text.secondary',
                            opacity: 0.7,
                            whiteSpace: 'nowrap',
                            flexShrink: 0
                        }}>
                            ({passes.length} {passes.length === 1 ? 'pass' : 'passes'}{passesAreCached ? `, ${t('passes_table.cached')}` : ''})
                        </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                        <Button size="small" variant={quickFilterPreset === 'all' ? 'contained' : 'outlined'} onClick={() => handleQuickPreset('all')} sx={{ minHeight: 24, height: 24, py: 0, px: 1, lineHeight: 1.1, fontSize: '0.72rem' }}>
                            All
                        </Button>
                        <Button size="small" variant={quickFilterPreset === 'live' ? 'contained' : 'outlined'} onClick={() => handleQuickPreset('live')} sx={{ minHeight: 24, height: 24, py: 0, px: 1, lineHeight: 1.1, fontSize: '0.72rem' }}>
                            Live
                        </Button>
                        <Button size="small" variant={quickFilterPreset === 'next30' ? 'contained' : 'outlined'} onClick={() => handleQuickPreset('next30')} sx={{ minHeight: 24, height: 24, py: 0, px: 1, lineHeight: 1.1, fontSize: '0.72rem' }}>
                            Next 30m
                        </Button>
                        <Button size="small" variant={quickFilterPreset === 'highEl' ? 'contained' : 'outlined'} onClick={() => handleQuickPreset('highEl')} sx={{ minHeight: 24, height: 24, py: 0, px: 1, lineHeight: 1.1, fontSize: '0.72rem' }}>
                            High El
                        </Button>
                        <Tooltip title={t('passes_table_settings.title')}>
                            <span>
                                <IconButton
                                    size="small"
                                    onClick={handleOpenSettings}
                                    sx={{ padding: '2px' }}
                                >
                                    <SettingsIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title="Refresh passes (force recalculate)">
                            <span>
                                <IconButton
                                    size="small"
                                    onClick={handleRefreshPasses}
                                    disabled={passesLoading || !selectedSatGroupId}
                                    sx={{ padding: '2px' }}
                                >
                                    <RefreshIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                    </Box>
                </Box>
            </TitleBar>
            <div style={{position: 'relative', display: 'block', height: '100%'}} ref={containerRef}>
                <div style={{
                    padding: '0rem 0rem 0rem 0rem',
                    display: 'flex',
                    flexDirection: 'column',
                    height: containerHeight - 25,
                    minHeight,
                }}>
                    <MemoizedStyledDataGrid
                        passes={passes}
                        passesLoading={passesLoading}
                        quickFilterPreset={quickFilterPreset}
                        onRowClick={handleOnRowClick}
                        onRowDoubleClick={handleOnRowDoubleClick}
                        orbitProjectionDuration={orbitProjectionDuration}
                        pageSize={passesTablePageSize}
                        onPageSizeChange={handlePageSizeChange}
                        sortModel={passesTableSortModel}
                        onSortModelChange={handleSortModelChange}
                        columnVisibility={passesTableColumnVisibility}
                        onColumnVisibilityChange={handleColumnVisibilityChange}
                    />
                </div>
            </div>
            <PassesTableSettingsDialog
                open={openPassesTableSettingsDialog}
                onClose={handleCloseSettings}
            />
        </>
    );
});

export default NextPassesGroupIsland;
