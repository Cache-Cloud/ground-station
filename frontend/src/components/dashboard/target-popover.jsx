
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

import * as React from "react";
import {
    Box,
    Button,
    IconButton,
    Popover,
    Stack,
    Typography,
    Chip,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useState, useRef, useEffect, useMemo } from "react";
import { shallowEqual, useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import Tooltip from "@mui/material/Tooltip";
import { useTranslation } from 'react-i18next';
import SatelliteAltIcon from '@mui/icons-material/SatelliteAlt';
import InfoIcon from '@mui/icons-material/Info';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import { formatLegibleDateTime } from "../common/common.jsx";
import { useUserTimeSettings } from '../../hooks/useUserTimeSettings.jsx';
import { formatDate as formatDateHelper } from '../../utils/date-time.js';

const EMPTY_OPEN_TARGET_DATA = Object.freeze({
    satelliteData: {
        details: {},
        position: {},
        transmitters: [],
    },
    trackingState: {},
    rotatorData: {},
    satellitePasses: [],
    groundStationLocation: null,
});

const SatelliteInfoPopover = () => {
    const dispatch = useDispatch();
    const theme = useTheme();
    const buttonRef = useRef(null);
    const [anchorEl, setAnchorEl] = useState(null);
    const navigate = useNavigate();
    const { t } = useTranslation('dashboard');
    const { timezone, locale } = useUserTimeSettings();

    const open = Boolean(anchorEl);
    const trackerId = useSelector((state) => state.targetSatTrack?.trackerId || "");
    const trackerInstances = useSelector((state) => state.trackerInstances?.instances || []);
    const trackerViews = useSelector((state) => state.targetSatTrack?.trackerViews || {});

    // Keep closed-state subscriptions intentionally lightweight.
    const selectedTrackerView = (trackerId && trackerViews?.[trackerId]) || null;
    const targetSummary = useSelector((state) => {
        const target = state.targetSatTrack || {};
        const details = selectedTrackerView?.satelliteData?.details || target.satelliteData?.details || {};
        const position = selectedTrackerView?.satelliteData?.position || target.satelliteData?.position || {};
        const trackingState = selectedTrackerView?.trackingState || target.trackingState || {};
        const rotatorData = selectedTrackerView?.rotatorData || target.rotatorData || {};

        return {
            noradId: details.norad_id ?? null,
            name: details.name ?? '',
            elevation: Number.isFinite(position.el) ? Math.round(position.el * 10) / 10 : position.el,
            trackingNoradId: trackingState?.norad_id ?? null,
            minElevation: rotatorData?.minel ?? 0,
        };
    }, shallowEqual);

    const openTargetData = useSelector((state) => {
        if (!open) {
            return EMPTY_OPEN_TARGET_DATA;
        }
        if (selectedTrackerView) {
            return {
                satelliteData: selectedTrackerView?.satelliteData || EMPTY_OPEN_TARGET_DATA.satelliteData,
                trackingState: selectedTrackerView?.trackingState || EMPTY_OPEN_TARGET_DATA.trackingState,
                rotatorData: selectedTrackerView?.rotatorData || EMPTY_OPEN_TARGET_DATA.rotatorData,
                satellitePasses: state.targetSatTrack?.satellitePasses || EMPTY_OPEN_TARGET_DATA.satellitePasses,
                groundStationLocation: state.location?.location || EMPTY_OPEN_TARGET_DATA.groundStationLocation,
            };
        }
        return {
            satelliteData: state.targetSatTrack?.satelliteData || EMPTY_OPEN_TARGET_DATA.satelliteData,
            trackingState: state.targetSatTrack?.trackingState || EMPTY_OPEN_TARGET_DATA.trackingState,
            rotatorData: state.targetSatTrack?.rotatorData || EMPTY_OPEN_TARGET_DATA.rotatorData,
            satellitePasses: state.targetSatTrack?.satellitePasses || EMPTY_OPEN_TARGET_DATA.satellitePasses,
            groundStationLocation: state.location?.location || EMPTY_OPEN_TARGET_DATA.groundStationLocation,
        };
    }, shallowEqual);

    const satelliteData = useMemo(() => (
        open
            ? openTargetData.satelliteData
            : {
                details: {
                    norad_id: targetSummary.noradId,
                    name: targetSummary.name,
                },
                position: {
                    el: targetSummary.elevation,
                },
                transmitters: [],
            }
    ), [open, openTargetData.satelliteData, targetSummary.noradId, targetSummary.name, targetSummary.elevation]);

    const trackingState = useMemo(() => (
        open ? openTargetData.trackingState : { norad_id: targetSummary.trackingNoradId }
    ), [open, openTargetData.trackingState, targetSummary.trackingNoradId]);

    const rotatorData = useMemo(() => (
        open ? openTargetData.rotatorData : { minel: targetSummary.minElevation }
    ), [open, openTargetData.rotatorData, targetSummary.minElevation]);
    const satellitePasses = open ? openTargetData.satellitePasses : EMPTY_OPEN_TARGET_DATA.satellitePasses;
    const fleetRows = useMemo(() => {
        return trackerInstances.map((instance, index) => {
            const instanceTrackerId = instance?.tracker_id || '';
            const targetNumber = Number(instance?.target_number || (index + 1));
            const view = trackerViews?.[instanceTrackerId] || {};
            const details = view?.satelliteData?.details || {};
            const position = view?.satelliteData?.position || {};
            const tracking = view?.trackingState || {};
            const rotator = view?.rotatorData || {};
            const noradId = details?.norad_id ?? tracking?.norad_id ?? null;
            const satName = details?.name || 'No satellite';
            const satNorad = noradId ?? 'none';
            const elevation = position?.el;
            const isActive = instanceTrackerId === trackerId;
            const minElevation = rotator?.minel ?? 0;
            const isTracking = noradId != null && tracking?.norad_id === noradId;
            return {
                trackerId: instanceTrackerId,
                targetNumber,
                satName,
                satNorad,
                elevation,
                isActive,
                minElevation,
                isTracking,
            };
        });
    }, [trackerInstances, trackerViews, trackerId]);

    const handleClick = (event) => {
        setAnchorEl(event.currentTarget);
    };

    const handleClose = () => {
        setAnchorEl(null);
    };

    const handleNavigateToSatelliteInfo = () => {
        if (satelliteData.details.norad_id) {
            navigate(`/satellite/${satelliteData.details.norad_id}`);
            handleClose(); // Close the popover after navigation
        }
    };

    // Format date helper - use common function
    const formatDate = (dateString) => {
        if (!dateString) return 'N/A';
        return formatDateHelper(dateString, { timezone, locale });
    };

    const getTooltipText = () => {
        const satName = satelliteData.details.name || 'No satellite selected';
        if (!satelliteData.details.norad_id) {
            return `Satellite Info: ${satName}`;
        }

        const elevation = satelliteData.position.el;
        const visibilityText = elevation > 0 ? 'Visible' : 'Below horizon';

        return `Satellite Info: ${satName} (${visibilityText}, El: ${elevation?.toFixed(1)}°)`;
    };

    const isTrackingActive = trackingState.norad_id === satelliteData.details.norad_id;

    // Get icon color based on satellite visibility
    const getSatelliteIconColor = () => {
        if (!satelliteData.details.norad_id) {
            return 'text.secondary'; // Grey when no satellite selected
        }

        const elevation = satelliteData.position.el;
        const minElevation = rotatorData.minel ?? 0;

        if (elevation < 0) {
            return 'error.main'; // Red when satellite is below horizon
        } else if (elevation < minElevation) {
            return 'status.polling'; // Orange when satellite is below minimum elevation limit
        } else if (isTrackingActive) {
            return 'success.main'; // Bright green when actively tracking and above minimum elevation
        } else {
            return 'info.main'; // Light blue when satellite is well above minimum elevation
        }
    };

    // Get satellite status information
    const getSatelliteStatus = (theme) => {
        if (!satelliteData.details.norad_id) {
            return {
                status: 'No Satellite',
                color: 'text.secondary',
                backgroundColor: 'action.hover',
                icon: <InfoIcon />,
                description: 'No satellite selected'
            };
        }

        const elevation = satelliteData.position.el;
        const minElevation = rotatorData.minel ?? 0;

        if (elevation < 0) {
            return {
                status: 'Below Horizon',
                color: 'error.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.error.main}25` // 15% opacity on dark
                    : 'error.light',
                icon: <VisibilityOffIcon />,
                description: 'Satellite is not visible from current location'
            };
        } else if (elevation < minElevation) {
            return {
                status: 'Low Elevation',
                color: 'warning.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.warning.main}25` // 15% opacity on dark
                    : 'warning.light',
                icon: <TrendingDownIcon />,
                description: `Satellite is below minimum elevation limit (${minElevation}°)`
            };
        } else if (isTrackingActive) {
            return {
                status: 'Actively Tracking',
                color: 'success.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.success.main}25` // 15% opacity on dark
                    : 'success.light',
                icon: <SatelliteAltIcon />,
                description: 'Currently tracking this satellite'
            };
        } else {
            return {
                status: 'Visible',
                color: 'info.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.info.main}25` // 15% opacity on dark
                    : 'info.light',
                icon: <VisibilityIcon />,
                description: 'Satellite is well positioned above horizon'
            };
        }
    };

    // Get elevation color based on value
    const getElevationColor = (elevation) => {
        const minElevation = rotatorData.minel ?? 0;

        if (elevation < 0) return 'error.main'; // Red - below horizon
        if (elevation < minElevation) return 'warning.main'; // Orange - below minimum elevation limit
        if (elevation < 45) return 'info.main'; // Light blue - above minimum but not optimal
        return 'success.main'; // Green - optimal elevation
    };

    const getFleetStatus = (row) => {
        if (row.satNorad === 'none') {
            return {
                status: 'No Satellite',
                color: 'text.secondary',
                backgroundColor: 'action.hover',
            };
        }

        const elevation = Number(row.elevation);
        if (!Number.isFinite(elevation)) {
            return {
                status: 'Unknown',
                color: 'text.secondary',
                backgroundColor: 'action.hover',
            };
        }

        if (elevation < 0) {
            return {
                status: 'Below Horizon',
                color: 'error.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.error.main}25`
                    : 'error.light',
            };
        }

        if (elevation < row.minElevation) {
            return {
                status: 'Low Elevation',
                color: 'warning.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.warning.main}25`
                    : 'warning.light',
            };
        }

        if (row.isTracking) {
            return {
                status: 'Actively Tracking',
                color: 'success.main',
                backgroundColor: theme.palette.mode === 'dark'
                    ? `${theme.palette.success.main}25`
                    : 'success.light',
            };
        }

        return {
            status: 'Visible',
            color: 'info.main',
            backgroundColor: theme.palette.mode === 'dark'
                ? `${theme.palette.info.main}25`
                : 'info.light',
        };
    };

    // Component for displaying numerical values with monospace font
    const NumericValue = ({ children, color }) => (
        <span style={{
            fontFamily: 'Monaco, Consolas, "Courier New", monospace',
            color: color || 'inherit',
            fontWeight: 'bold'
        }}>
            {children}
        </span>
    );

    const statusInfo = getSatelliteStatus(theme);

    // Memoize the next pass calculation to prevent unnecessary recalculations
    const nextPass = useMemo(() => {
        if (!open) return null;
        if (!satellitePasses || satellitePasses.length === 0 || !satelliteData.details.norad_id) return null;

        const now = new Date();

        // Find the earliest upcoming pass without creating a large intermediate array
        let earliestPass = null;
        let earliestTime = null;

        for (const pass of satellitePasses) {
            if (pass.norad_id === satelliteData.details.norad_id) {
                const startTime = new Date(pass.event_start);
                if (startTime > now) {
                    if (!earliestPass || startTime < earliestTime) {
                        earliestPass = pass;
                        earliestTime = startTime;
                    }
                }
            }
        }

        return earliestPass;
    }, [satellitePasses, satelliteData.details.norad_id]);

    // Countdown Component - extracted outside to use memoized nextPass
    const NextPassCountdown = React.memo(({ pass }) => {
        // We intentionally read from outer scope to react to store updates over time
        // without relying only on props that don't change as time advances.
        const selectedNoradId = satelliteData.details?.norad_id;

        // Utility: find earliest future pass for the selected satellite
        const findNextFuturePass = React.useCallback(() => {
            if (!selectedNoradId) return null;
            const now = new Date();
            let earliest = null;
            let earliestTime = null;
            for (const p of satellitePasses || []) {
                if (p.norad_id === selectedNoradId && p?.event_start) {
                    const st = new Date(p.event_start);
                    if (!isNaN(st) && st > now) {
                        if (!earliest || st < earliestTime) {
                            earliest = p;
                            earliestTime = st;
                        }
                    }
                }
            }
            return earliest;
        }, [selectedNoradId, satellitePasses]);

        // Local pass state that can advance to the next pass when current has started
        const [currentPass, setCurrentPass] = useState(pass || findNextFuturePass());
        const passId = currentPass?.id;
        const passStartTime = currentPass?.event_start;

        // Calculate initial countdown value to avoid empty state
        const calculateCountdown = (startTimeStr) => {
            if (!selectedNoradId) return 'No satellite selected';
            if (!startTimeStr) return 'No upcoming passes';

            const now = new Date();
            const startTime = new Date(startTimeStr);
            if (isNaN(startTime)) return 'Invalid pass start time';

            const diff = startTime - now;

            if (diff <= 0) {
                // Try to advance to the next future pass
                const nxt = findNextFuturePass();
                if (nxt && nxt.id !== currentPass?.id) {
                    setCurrentPass(nxt);
                    // Recalculate based on the new pass
                    return calculateCountdown(nxt.event_start);
                }
                // No future pass found — report a helpful message
                return 'No upcoming passes (schedule not updated)';
            }

            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);

            if (days > 0) {
                return `${days}d ${hours}h ${minutes}m`;
            } else if (hours > 0) {
                return `${hours}h ${minutes}m ${seconds}s`;
            } else if (minutes > 0) {
                return `${minutes}m ${seconds}s`;
            } else {
                return `${seconds}s`;
            }
        };

        const [countdown, setCountdown] = useState(() => calculateCountdown(passStartTime));

        // Keep local pass in sync if parent prop changes (e.g., selected satellite changes)
        useEffect(() => {
            setCurrentPass(pass || findNextFuturePass());
        }, [pass, findNextFuturePass]);

        // Recompute countdown every second; also attempt to advance to the next pass if needed
        useEffect(() => {
            const updateCountdown = () => {
                setCountdown(calculateCountdown(currentPass?.event_start));
            };

            updateCountdown();
            const interval = setInterval(updateCountdown, 1000);
            return () => clearInterval(interval);
        }, [passId, currentPass?.event_start, selectedNoradId, findNextFuturePass]);

        if (!selectedNoradId) {
            return (
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    No satellite selected
                </Typography>
            );
        }

        if (!currentPass) {
            return (
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    No upcoming passes
                </Typography>
            );
        }

        return (
            <Box sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 1
            }}>
                <Typography variant="body2" color="text.secondary">
                    Next pass in
                </Typography>
                <Typography
                    variant="h4"
                    sx={{
                        fontFamily: 'Monaco, Consolas, "Courier New", monospace',
                        fontWeight: 'bold',
                        color: 'info.light'
                    }}
                >
                    {countdown}
                </Typography>
                <Typography variant="caption" color="text.disabled">
                    {formatLegibleDateTime(currentPass.event_start, timezone, locale)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                    Peak elevation: {currentPass.peak_altitude?.toFixed(1)}°
                </Typography>
            </Box>
        );
    });

    return (
        <>
            <Box sx={{ position: 'relative', display: 'inline-block' }}>
                <Tooltip title={getTooltipText()}>
                    <IconButton
                        ref={buttonRef}
                        onClick={handleClick}
                        size="small"
                        sx={{
                            width: 40,
                            color: getSatelliteIconColor(),
                            '&:hover': {
                                backgroundColor: 'overlay.light'
                            },
                            '& svg': {
                                height: '75%',
                            }
                        }}
                    >
                        <SatelliteAltIcon />
                    </IconButton>
                </Tooltip>

                {/* Elevation Overlay */}
                {satelliteData.details.norad_id && (
                    <Box
                        sx={{
                            position: 'absolute',
                            bottom: 5,
                            right: 6,
                            backgroundColor: 'overlay.dark',
                            border: `1px solid ${getElevationColor(satelliteData.position.el)}`,
                            borderRadius: '3px',
                            paddingLeft: 0.6,
                            paddingTop: 0.2,
                            minWidth: 22,
                            width: 30,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            pointerEvents: 'none',
                            zIndex: 1
                        }}
                    >
                        <Typography
                            variant="caption"
                            sx={{
                                color: getElevationColor(satelliteData.position.el),
                                fontSize: '0.65rem',
                                fontWeight: 'bold',
                                fontFamily: 'Monaco, Consolas, "Courier New", monospace',
                                lineHeight: 1
                            }}
                        >
                            {satelliteData.position.el >= 0 ? '+' : ''}{satelliteData.position.el?.toFixed(0)}°
                        </Typography>
                    </Box>
                )}

            </Box>

            <Popover
                sx={{
                    '& .MuiPaper-root': {
                        borderRadius: 0,
                    }
                }}
                open={open}
                anchorEl={anchorEl}
                onClose={handleClose}
                anchorOrigin={{
                    vertical: 'bottom',
                    horizontal: 'right',
                }}
                transformOrigin={{
                    vertical: 'top',
                    horizontal: 'right',
                }}
            >
                {open && (
                <Box sx={{
                    borderRadius: 0,
                    border: '1px solid',
                    borderColor: 'border.main',
                    p: 1,
                    minWidth: 320,
                    maxWidth: 350,
                    backgroundColor: 'background.paper',
                    color: 'text.primary',
                }}>
                    {fleetRows.length > 0 && (
                        <Stack spacing={0.8}>
                            {fleetRows.map((row) => {
                                const rowStatus = getFleetStatus(row);
                                const hasElevation = Number.isFinite(Number(row.elevation));

                                return (
                                    <Box
                                        key={row.trackerId}
                                        sx={{
                                            p: 1,
                                            borderRadius: 1,
                                            border: `1px solid ${rowStatus.color}`,
                                            backgroundColor: rowStatus.backgroundColor,
                                        }}
                                    >
                                        <Stack direction="row" spacing={0.6} alignItems="center" sx={{ mb: 0.6 }}>
                                            <Chip
                                                size="small"
                                                label={`Target ${row.targetNumber}`}
                                                color="default"
                                                variant="outlined"
                                            />
                                            <Chip
                                                size="small"
                                                label={`NORAD ${row.satNorad}`}
                                                variant="outlined"
                                            />
                                        </Stack>

                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                                                <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 0.2 }}>
                                                    {row.satName}
                                                </Typography>
                                                <Typography
                                                    variant="caption"
                                                    sx={{ color: rowStatus.color, fontWeight: 'bold' }}
                                                >
                                                    {rowStatus.status}
                                                </Typography>
                                            </Box>
                                            {hasElevation && (
                                                <Box sx={{ textAlign: 'right' }}>
                                                    <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.75rem' }}>
                                                        Elevation
                                                    </Typography>
                                                    <Typography variant="h6" sx={{
                                                        color: getElevationColor(Number(row.elevation)),
                                                        fontWeight: 'bold',
                                                        fontFamily: 'Monaco, Consolas, \"Courier New\", monospace'
                                                    }}>
                                                        {Number(row.elevation).toFixed(1)}°
                                                    </Typography>
                                                </Box>
                                            )}
                                        </Box>
                                    </Box>
                                );
                            })}
                        </Stack>
                    )}
                </Box>
                )}
            </Popover>
        </>
    );
};

export default React.memo(SatelliteInfoPopover);
