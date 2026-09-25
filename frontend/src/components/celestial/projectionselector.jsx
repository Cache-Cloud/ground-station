/**
 * @license
 * Copyright (c) 2026 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Box, Slider, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';

export const PAST_HOUR_OPTIONS = [
    { value: 1, label: '1h' },
    { value: 6, label: '6h' },
    { value: 12, label: '12h' },
    { value: 24, label: '1d' },
    { value: 72, label: '3d' },
    { value: 168, label: '7d' },
];

export const FUTURE_HOUR_OPTIONS = [
    { value: 6, label: '6h' },
    { value: 12, label: '12h' },
    { value: 24, label: '1d' },
    { value: 72, label: '3d' },
    { value: 168, label: '7d' },
    { value: 336, label: '14d' },
    { value: 720, label: '30d' },
];

const VIEWBOX_WIDTH = 348;
const TRACK_START = 15;
const PAST_TRACK_END = 164;
const NOW_X = VIEWBOX_WIDTH / 2;
const FUTURE_TRACK_START = 184;
const TRACK_END = 333;
const TRACK_Y = 13;
const asPercent = (value) => `${(value / VIEWBOX_WIDTH) * 100}%`;

const findNearestOptionIndex = (options, value) => {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return 0;

    return options.reduce((nearestIndex, option, index) => (
        Math.abs(option.value - numericValue) < Math.abs(options[nearestIndex].value - numericValue)
            ? index
            : nearestIndex
    ), 0);
};

const pastIndexToPosition = (optionIndex) => PAST_HOUR_OPTIONS.length - 1 - optionIndex;
const pastPositionToIndex = (position) => PAST_HOUR_OPTIONS.length - 1 - Number(position);

const sliderSx = {
    position: 'absolute',
    top: 21,
    width: asPercent(PAST_TRACK_END - TRACK_START),
    height: 26,
    p: '0 !important',
    boxSizing: 'border-box',
    color: 'primary.main',
    '& .MuiSlider-rail, & .MuiSlider-track': {
        opacity: 0,
    },
    '& .MuiSlider-thumb': {
        // The selector border shifts the SVG band two pixels above the slider's box.
        top: 11,
        transform: 'translate(-50%, -50%)',
        width: 12,
        height: 12,
        bgcolor: 'background.paper',
        border: '2px solid',
        borderColor: 'primary.main',
        boxShadow: (theme) => `0 1px 3px ${alpha(theme.palette.common.black, 0.28)}`,
        transition: 'box-shadow 120ms ease, transform 120ms ease',
        '&::before': {
            boxShadow: 'none',
        },
        '&:hover, &.Mui-focusVisible': {
            boxShadow: (theme) => `0 0 0 5px ${alpha(theme.palette.primary.main, 0.18)}`,
        },
        '&.Mui-active': {
            transform: 'translate(-50%, -50%) scale(1.14)',
            boxShadow: (theme) => `0 0 0 6px ${alpha(theme.palette.primary.main, 0.22)}`,
        },
    },
    '&.Mui-disabled': {
        color: 'text.disabled',
        '& .MuiSlider-thumb': {
            borderColor: 'text.disabled',
        },
    },
};

const ProjectionSelector = ({
    pastHours,
    futureHours,
    pastLabel,
    futureLabel,
    nowLabel,
    disabled = false,
    onPastHoursChange,
    onFutureHoursChange,
}) => {
    const pastOptionIndex = useMemo(
        () => findNearestOptionIndex(PAST_HOUR_OPTIONS, pastHours),
        [pastHours],
    );
    const futureOptionIndex = useMemo(
        () => findNearestOptionIndex(FUTURE_HOUR_OPTIONS, futureHours),
        [futureHours],
    );
    const [pastPosition, setPastPosition] = useState(pastIndexToPosition(pastOptionIndex));
    const [futurePosition, setFuturePosition] = useState(futureOptionIndex);

    useEffect(() => {
        setPastPosition(pastIndexToPosition(pastOptionIndex));
    }, [pastOptionIndex]);

    useEffect(() => {
        setFuturePosition(futureOptionIndex);
    }, [futureOptionIndex]);

    const selectedPastOption = PAST_HOUR_OPTIONS[pastPositionToIndex(pastPosition)];
    const selectedFutureOption = FUTURE_HOUR_OPTIONS[futurePosition];
    const pastHandleX = TRACK_START
        + (pastPosition / (PAST_HOUR_OPTIONS.length - 1)) * (PAST_TRACK_END - TRACK_START);
    const futureHandleX = FUTURE_TRACK_START
        + (futurePosition / (FUTURE_HOUR_OPTIONS.length - 1)) * (TRACK_END - FUTURE_TRACK_START);
    const labelSx = {
        fontSize: '0.6rem',
        fontWeight: 700,
        letterSpacing: '0.08em',
        lineHeight: 1,
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        color: 'text.secondary',
    };
    const valueSx = {
        fontSize: '0.7rem',
        fontFamily: 'monospace',
        fontWeight: 700,
        lineHeight: 1,
        color: disabled ? 'text.disabled' : 'primary.main',
    };

    return (
        <Box
            role="group"
            aria-label={`${pastLabel} / ${futureLabel}`}
            sx={{
                position: 'relative',
                width: '100%',
                minWidth: 0,
                height: 48,
                flex: '1 1 auto',
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: (theme) => alpha(theme.palette.background.default, 0.42),
                backgroundImage: (theme) => (
                    `radial-gradient(circle at 50% 72%, ${alpha(theme.palette.primary.main, 0.1)}, transparent 26%)`
                ),
                opacity: disabled ? 0.65 : 1,
                transition: 'border-color 120ms ease, opacity 120ms ease',
            }}
        >
            <Box sx={{ position: 'absolute', inset: '5px 11px auto', height: 12 }}>
                <Stack
                    direction="row"
                    spacing={0.55}
                    alignItems="baseline"
                    sx={{ position: 'absolute', left: 0 }}
                >
                    <Typography sx={labelSx}>{pastLabel}</Typography>
                    <Typography sx={valueSx}>−{selectedPastOption.label}</Typography>
                </Stack>
                <Typography
                    sx={{
                        ...labelSx,
                        position: 'absolute',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        color: disabled ? 'text.disabled' : 'text.primary',
                    }}
                >
                    {nowLabel}
                </Typography>
                <Stack
                    direction="row"
                    spacing={0.55}
                    alignItems="baseline"
                    sx={{ position: 'absolute', right: 0 }}
                >
                    <Typography sx={valueSx}>+{selectedFutureOption.label}</Typography>
                    <Typography sx={labelSx}>{futureLabel}</Typography>
                </Stack>
            </Box>

            <Box
                component="svg"
                aria-hidden="true"
                sx={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    bottom: 1,
                    width: '100%',
                    height: 26,
                    color: disabled ? 'text.disabled' : 'primary.main',
                }}
            >
                <line
                    x1={asPercent(TRACK_START)}
                    y1={TRACK_Y}
                    x2={asPercent(TRACK_END)}
                    y2={TRACK_Y}
                    stroke="currentColor"
                    strokeWidth="2"
                    opacity="0.16"
                    vectorEffect="non-scaling-stroke"
                />
                <line
                    x1={asPercent(pastHandleX)}
                    y1={TRACK_Y}
                    x2={asPercent(NOW_X)}
                    y2={TRACK_Y}
                    stroke="currentColor"
                    strokeWidth="2.5"
                    opacity="0.72"
                    vectorEffect="non-scaling-stroke"
                />
                <line
                    x1={asPercent(NOW_X)}
                    y1={TRACK_Y}
                    x2={asPercent(futureHandleX)}
                    y2={TRACK_Y}
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeDasharray="3 3"
                    opacity="0.82"
                    vectorEffect="non-scaling-stroke"
                />
                {PAST_HOUR_OPTIONS.map((option, index) => {
                    const position = pastIndexToPosition(index);
                    const x = TRACK_START
                        + (position / (PAST_HOUR_OPTIONS.length - 1)) * (PAST_TRACK_END - TRACK_START);
                    return <circle key={`past-tick-${option.value}`} cx={asPercent(x)} cy={TRACK_Y} r="1.4" fill="currentColor" opacity="0.42" />;
                })}
                {FUTURE_HOUR_OPTIONS.map((option, index) => {
                    const x = FUTURE_TRACK_START
                        + (index / (FUTURE_HOUR_OPTIONS.length - 1)) * (TRACK_END - FUTURE_TRACK_START);
                    return <circle key={`future-tick-${option.value}`} cx={asPercent(x)} cy={TRACK_Y} r="1.4" fill="currentColor" opacity="0.42" />;
                })}
                <circle cx={asPercent(NOW_X)} cy={TRACK_Y} r="3.5" fill="currentColor" opacity="0.9" />
                <circle cx={asPercent(NOW_X)} cy={TRACK_Y} r="7" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.14" />
            </Box>

            <Box
                aria-hidden="true"
                sx={{
                    position: 'absolute',
                    inset: '19px 0 auto',
                    height: 10,
                    pointerEvents: 'none',
                }}
            >
                {PAST_HOUR_OPTIONS.map((option, index) => {
                    const position = pastIndexToPosition(index);
                    const x = TRACK_START
                        + (position / (PAST_HOUR_OPTIONS.length - 1)) * (PAST_TRACK_END - TRACK_START);
                    const selected = index === pastPositionToIndex(pastPosition);
                    return (
                        <Typography
                            component="span"
                            key={`past-label-${option.value}`}
                            sx={{
                                position: 'absolute',
                                left: asPercent(x),
                                transform: 'translateX(-50%)',
                                color: selected && !disabled ? 'primary.main' : 'text.secondary',
                                fontFamily: 'monospace',
                                fontSize: '0.5rem',
                                fontWeight: selected ? 700 : 500,
                                lineHeight: 1,
                                opacity: selected ? 0.95 : 0.62,
                                whiteSpace: 'nowrap',
                            }}
                        >
                            {option.label}
                        </Typography>
                    );
                })}
                {FUTURE_HOUR_OPTIONS.map((option, index) => {
                    const x = FUTURE_TRACK_START
                        + (index / (FUTURE_HOUR_OPTIONS.length - 1)) * (TRACK_END - FUTURE_TRACK_START);
                    const selected = index === futurePosition;
                    return (
                        <Typography
                            component="span"
                            key={`future-label-${option.value}`}
                            sx={{
                                position: 'absolute',
                                left: asPercent(x),
                                transform: 'translateX(-50%)',
                                color: selected && !disabled ? 'primary.main' : 'text.secondary',
                                fontFamily: 'monospace',
                                fontSize: '0.5rem',
                                fontWeight: selected ? 700 : 500,
                                lineHeight: 1,
                                opacity: selected ? 0.95 : 0.62,
                                whiteSpace: 'nowrap',
                            }}
                        >
                            {option.label}
                        </Typography>
                    );
                })}
            </Box>

            <Slider
                value={pastPosition}
                min={0}
                max={PAST_HOUR_OPTIONS.length - 1}
                step={1}
                track={false}
                disabled={disabled}
                aria-label={`${pastLabel} projection`}
                getAriaValueText={(position) => PAST_HOUR_OPTIONS[pastPositionToIndex(position)].label}
                onChange={(_event, position) => setPastPosition(Number(position))}
                onChangeCommitted={(_event, position) => {
                    onPastHoursChange?.(PAST_HOUR_OPTIONS[pastPositionToIndex(position)].value);
                }}
                sx={{ ...sliderSx, left: asPercent(TRACK_START) }}
            />
            <Slider
                value={futurePosition}
                min={0}
                max={FUTURE_HOUR_OPTIONS.length - 1}
                step={1}
                track={false}
                disabled={disabled}
                aria-label={`${futureLabel} projection`}
                getAriaValueText={(position) => FUTURE_HOUR_OPTIONS[Number(position)].label}
                onChange={(_event, position) => setFuturePosition(Number(position))}
                onChangeCommitted={(_event, position) => {
                    onFutureHoursChange?.(FUTURE_HOUR_OPTIONS[Number(position)].value);
                }}
                sx={{ ...sliderSx, left: asPercent(FUTURE_TRACK_START) }}
            />
        </Box>
    );
};

export default ProjectionSelector;
