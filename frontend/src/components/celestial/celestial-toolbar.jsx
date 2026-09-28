import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, CircularProgress, Divider, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import RefreshIcon from '@mui/icons-material/Refresh';
import FitScreenIcon from '@mui/icons-material/FitScreen';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';
import PanToolIcon from '@mui/icons-material/PanTool';
import ZoomInMapIcon from '@mui/icons-material/ZoomInMap';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { ResetZoomIcon } from '../common/custom-icons.jsx';

const CelestialToolbar = ({
    onRefresh,
    onFitAll,
    onZoomIn,
    onZoomOut,
    onZoomReset,
    onCenterSun,
    onToggleFullscreen,
    loading,
    loadingText = '',
    fullscreen = false,
    fullscreenLabel,
    exitFullscreenLabel,
    mapDraggingEnabled = true,
    mapZoomingEnabled = true,
    onToggleMapDragging,
    onToggleMapZooming,
    showZoomButtons = true,
    viewToggles = [],
    disabled = false,
}) => {
    const { t } = useTranslation('celestial');
    const effectiveFullscreenLabel = fullscreenLabel || t('toolbar.go_fullscreen');
    const effectiveExitFullscreenLabel = exitFullscreenLabel || t('toolbar.exit_fullscreen');
    const scrollViewportRef = useRef(null);
    const [scrollState, setScrollState] = useState({
        hasOverflow: false,
        atStart: true,
        atEnd: true,
    });

    const updateScrollState = useCallback(() => {
        const viewport = scrollViewportRef.current;
        if (!viewport) return;
        const maxScrollLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
        const nextState = {
            hasOverflow: maxScrollLeft > 2,
            atStart: viewport.scrollLeft <= 2,
            atEnd: viewport.scrollLeft >= maxScrollLeft - 2,
        };
        setScrollState((current) => (
            current.hasOverflow === nextState.hasOverflow
            && current.atStart === nextState.atStart
            && current.atEnd === nextState.atEnd
                ? current
                : nextState
        ));
    }, []);

    useEffect(() => {
        const viewport = scrollViewportRef.current;
        if (!viewport) return undefined;

        const animationFrame = window.requestAnimationFrame(updateScrollState);
        viewport.addEventListener('scroll', updateScrollState, { passive: true });
        window.addEventListener('resize', updateScrollState);

        const resizeObserver = typeof ResizeObserver === 'undefined'
            ? null
            : new ResizeObserver(updateScrollState);
        resizeObserver?.observe(viewport);

        return () => {
            window.cancelAnimationFrame(animationFrame);
            viewport.removeEventListener('scroll', updateScrollState);
            window.removeEventListener('resize', updateScrollState);
            resizeObserver?.disconnect();
        };
    }, [showZoomButtons, updateScrollState, viewToggles.length]);

    const scrollToolbar = useCallback((direction) => {
        const viewport = scrollViewportRef.current;
        if (!viewport) return;
        const distance = Math.max(160, Math.round(viewport.clientWidth * 0.75));
        viewport.scrollBy({
            left: direction * distance,
            behavior: 'smooth',
        });
    }, []);

    return (
        <Paper
            elevation={1}
            sx={{
                p: 0,
                display: 'inline-block',
                width: '100%',
                borderBottom: '1px solid',
                borderColor: 'border.main',
                borderRadius: 0,
            }}
        >
            <Box
                sx={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    overflow: 'hidden',
                }}
            >
                {scrollState.hasOverflow ? (
                    <Tooltip title={t('toolbar.scroll_left')}>
                        <span>
                            <IconButton
                                size="small"
                                onClick={() => scrollToolbar(-1)}
                                disabled={scrollState.atStart}
                                aria-label={t('toolbar.scroll_left')}
                                sx={{ borderRadius: 0, flexShrink: 0 }}
                            >
                                <ChevronLeftIcon />
                            </IconButton>
                        </span>
                    </Tooltip>
                ) : null}
                <Box
                    ref={scrollViewportRef}
                    sx={{
                        overflowX: 'auto',
                        minWidth: 0,
                        flex: 1,
                        msOverflowStyle: 'none',
                        scrollbarWidth: 'none',
                        WebkitOverflowScrolling: 'touch',
                        '&::-webkit-scrollbar': { display: 'none' },
                    }}
                >
                    <Stack direction="row" spacing={0} sx={{ minWidth: 'min-content', flexWrap: 'nowrap' }}>
                        <Tooltip title={t('toolbar.fit_all')}>
                            <span>
                                <IconButton
                                    onClick={onFitAll}
                                    disabled={disabled}
                                    color="primary"
                                    sx={{ borderRadius: 0 }}
                                >
                                    <FitScreenIcon />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title={t('layout_options.options.enable_map_dragging.label')}>
                            <span>
                                <IconButton
                                    onClick={onToggleMapDragging}
                                    disabled={disabled || !onToggleMapDragging}
                                    color={mapDraggingEnabled ? 'warning' : 'primary'}
                                    sx={{ borderRadius: 0 }}
                                    aria-pressed={mapDraggingEnabled}
                                >
                                    <PanToolIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title={t('layout_options.options.enable_map_zooming.label')}>
                            <span>
                                <IconButton
                                    onClick={onToggleMapZooming}
                                    disabled={disabled || !onToggleMapZooming}
                                    color={mapZoomingEnabled ? 'warning' : 'primary'}
                                    sx={{ borderRadius: 0 }}
                                    aria-pressed={mapZoomingEnabled}
                                >
                                    <ZoomInMapIcon />
                                </IconButton>
                            </span>
                        </Tooltip>
                        {showZoomButtons ? (
                            <>
                                <Tooltip title={t('toolbar.zoom_in')}>
                                    <span>
                                        <IconButton
                                            onClick={onZoomIn}
                                            disabled={disabled}
                                            color="primary"
                                            sx={{ borderRadius: 0 }}
                                        >
                                            <ZoomInIcon />
                                        </IconButton>
                                    </span>
                                </Tooltip>
                                <Tooltip title={t('toolbar.zoom_out')}>
                                    <span>
                                        <IconButton
                                            onClick={onZoomOut}
                                            disabled={disabled}
                                            color="primary"
                                            sx={{ borderRadius: 0 }}
                                        >
                                            <ZoomOutIcon />
                                        </IconButton>
                                    </span>
                                </Tooltip>
                                <Tooltip title={t('toolbar.reset_zoom')}>
                                    <span>
                                        <IconButton
                                            onClick={onZoomReset}
                                            disabled={disabled}
                                            color="primary"
                                            sx={{ borderRadius: 0 }}
                                        >
                                            <ResetZoomIcon />
                                        </IconButton>
                                    </span>
                                </Tooltip>
                            </>
                        ) : null}
                        <Tooltip title={t('toolbar.center_on_sun')}>
                            <span>
                                <IconButton
                                    onClick={onCenterSun}
                                    disabled={disabled}
                                    color="primary"
                                    sx={{ borderRadius: 0 }}
                                >
                                    <WbSunnyIcon />
                                </IconButton>
                            </span>
                        </Tooltip>
                        {viewToggles.length ? (
                            <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
                        ) : null}
                        {viewToggles.map((toggle) => (
                            <Tooltip key={toggle.key} title={toggle.label}>
                                <span>
                                    <IconButton
                                        onClick={toggle.onClick}
                                        disabled={disabled || !toggle.onClick}
                                        color={toggle.pressed ? 'warning' : 'primary'}
                                        sx={{ borderRadius: 0 }}
                                        aria-label={toggle.label}
                                        aria-pressed={toggle.pressed}
                                    >
                                        {toggle.icon}
                                    </IconButton>
                                </span>
                            </Tooltip>
                        ))}
                        <Tooltip title={t('toolbar.refresh_scene')}>
                            <span>
                                <IconButton
                                    onClick={onRefresh}
                                    disabled={disabled || loading}
                                    color="primary"
                                    sx={{ borderRadius: 0 }}
                                >
                                    <RefreshIcon />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title={fullscreen ? effectiveExitFullscreenLabel : effectiveFullscreenLabel}>
                            <span>
                                <IconButton
                                    onClick={onToggleFullscreen}
                                    disabled={!onToggleFullscreen}
                                    color="primary"
                                    sx={{ borderRadius: 0 }}
                                    aria-label={fullscreen ? effectiveExitFullscreenLabel : effectiveFullscreenLabel}
                                >
                                    {fullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
                                </IconButton>
                            </span>
                        </Tooltip>
                    </Stack>
                </Box>
                {scrollState.hasOverflow ? (
                    <Tooltip title={t('toolbar.scroll_right')}>
                        <span>
                            <IconButton
                                size="small"
                                onClick={() => scrollToolbar(1)}
                                disabled={scrollState.atEnd}
                                aria-label={t('toolbar.scroll_right')}
                                sx={{ borderRadius: 0, flexShrink: 0 }}
                            >
                                <ChevronRightIcon />
                            </IconButton>
                        </span>
                    </Tooltip>
                ) : null}
                <Box sx={{ px: 1.25, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', minWidth: 32, gap: 0.75 }}>
                    {loading && loadingText ? (
                        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1 }}>
                            {loadingText}
                        </Typography>
                    ) : null}
                    {loading ? <CircularProgress size={16} /> : null}
                </Box>
            </Box>
        </Paper>
    );
};

export default React.memo(CelestialToolbar);
