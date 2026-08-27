/**
 * @license
 * Copyright (c) 2026 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, useTheme } from '@mui/material';
import { alpha } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';

/**
 * Draws the centered portion of the live SDR spectrum that an IQ recording
 * retains after decimation. It is intentionally visual-only: the containing
 * waterfall canvas group supplies pan and zoom through its shared transform.
 */
const RecordingBandOverlay = ({
    inputSampleRate,
    decimationFactor,
    isRecording = false,
    containerWidth,
    transformTick = 0,
    interactionActive = false,
    allowInteractionMeasure = false,
    interactionMeasureTick = 0,
    height,
    topPadding = 0,
}) => {
    const theme = useTheme();
    const { t } = useTranslation('waterfall');
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const [actualWidth, setActualWidth] = useState(2048);
    const lastMeasuredWidthRef = useRef(0);
    const factor = Number(decimationFactor) || 1;
    const isVisible = Number(inputSampleRate) > 0 && factor > 1;
    const statusColor = isRecording ? theme.palette.error.main : theme.palette.info.main;
    const statusText = isRecording
        ? t('recording.statusRecording', 'Recording')
        : t('recording.statusReady', 'Ready');

    const formatSampleRate = (rate) => {
        if (rate >= 1000000) {
            return `${(rate / 1000000).toFixed(rate % 1000000 === 0 ? 0 : 1)} MS/s`;
        }
        return `${Math.round(rate / 1000)} kS/s`;
    };

    const outputRate = formatSampleRate(Number(inputSampleRate) / factor);

    const updateActualWidth = useCallback(() => {
        const rect = containerRef.current?.getBoundingClientRect();
        const width = Math.round(rect?.width || 0);
        if (width > 0 && width !== lastMeasuredWidthRef.current) {
            lastMeasuredWidthRef.current = width;
            setActualWidth(width);
        }
    }, []);

    useEffect(() => {
        if (!interactionActive) {
            updateActualWidth();
        }
    }, [containerWidth, transformTick, interactionActive, updateActualWidth]);

    useEffect(() => {
        if (interactionActive && allowInteractionMeasure) {
            updateActualWidth();
        }
    }, [interactionActive, allowInteractionMeasure, interactionMeasureTick, updateActualWidth]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const targetHeight = Math.max(1, height);
        if (canvas.width !== actualWidth) canvas.width = actualWidth;
        if (canvas.height !== targetHeight) canvas.height = targetHeight;
    }, [actualWidth, height]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!isVisible) return;

        const drawTop = Math.max(0, topPadding);
        const drawHeight = Math.max(0, canvas.height - drawTop);
        const recordedWidth = canvas.width / factor;
        const leftEdge = (canvas.width - recordedWidth) / 2;
        const rightEdge = leftEdge + recordedWidth;
        // Keep the selected bandwidth legible across the full spectrum. The
        // tint deliberately fades toward the trace, so a zoomed-in retained
        // region remains readable instead of becoming a uniform grey wash.
        const fillGradient = ctx.createLinearGradient(0, drawTop, 0, canvas.height);
        fillGradient.addColorStop(0, 'rgba(48, 196, 255, 0.14)');
        fillGradient.addColorStop(0.22, 'rgba(48, 196, 255, 0.065)');
        fillGradient.addColorStop(1, 'rgba(48, 196, 255, 0.012)');
        ctx.fillStyle = fillGradient;
        ctx.fillRect(leftEdge, drawTop, recordedWidth, drawHeight);

        ctx.fillStyle = alpha(theme.palette.info.main, 0.82);
        ctx.fillRect(Math.round(leftEdge) - 1, drawTop, 2, drawHeight);
        ctx.fillRect(Math.round(rightEdge) - 1, drawTop, 2, drawHeight);

        // Draw the status in this canvas, as bookmark and band-plan labels are.
        // The backing store tracks the transformed width, preventing CSS zoom
        // from stretching the pill or its text.
        const pillHeight = 18;
        const pillY = drawTop + 2;
        const statusLabel = statusText.toUpperCase();
        ctx.save();
        ctx.textBaseline = 'middle';
        ctx.font = '700 10px Arial, sans-serif';
        const statusWidth = ctx.measureText(statusLabel).width;
        ctx.font = '10px Arial, sans-serif';
        const rateWidth = ctx.measureText(outputRate).width;
        const pillWidth = 31 + statusWidth + rateWidth;
        const pillX = (canvas.width - pillWidth) / 2;

        ctx.beginPath();
        ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 4);
        ctx.fillStyle = alpha(theme.palette.background.paper, 0.9);
        ctx.fill();
        ctx.strokeStyle = alpha(statusColor, 0.7);
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(pillX + 9, pillY + pillHeight / 2, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = statusColor;
        ctx.fill();

        const statusX = pillX + 17;
        ctx.font = '700 10px Arial, sans-serif';
        ctx.fillStyle = theme.palette.text.primary;
        ctx.fillText(statusLabel, statusX, pillY + pillHeight / 2 + 0.25);

        const dividerX = statusX + statusWidth + 6;
        ctx.strokeStyle = alpha(theme.palette.text.primary, 0.22);
        ctx.beginPath();
        ctx.moveTo(dividerX, pillY + 3);
        ctx.lineTo(dividerX, pillY + pillHeight - 3);
        ctx.stroke();

        ctx.font = '10px Arial, sans-serif';
        ctx.fillStyle = theme.palette.text.secondary;
        ctx.fillText(outputRate, dividerX + 6, pillY + pillHeight / 2 + 0.25);
        ctx.restore();

    }, [
        actualWidth,
        factor,
        height,
        isVisible,
        outputRate,
        statusColor,
        statusText,
        theme.palette.background.paper,
        theme.palette.info.main,
        theme.palette.text.primary,
        theme.palette.text.secondary,
        topPadding,
    ]);

    if (!isVisible) return null;

    return (
        <Box
            ref={containerRef}
            aria-label={t('recording.statusAriaLabel', {
                status: statusText,
                rate: outputRate,
                defaultValue: `IQ recording ${statusText.toLowerCase()}, ${outputRate}`,
            })}
            role="img"
            sx={{
                position: 'absolute',
                inset: 0,
                height: `${height}px`,
                pointerEvents: 'none',
                zIndex: 5,
            }}
        >
            <canvas
                className="recording-band-overlay"
                ref={canvasRef}
                width={actualWidth}
                height={height}
                style={{ display: 'block', width: '100%', height: '100%' }}
            />
        </Box>
    );
};

export default React.memo(RecordingBandOverlay);
