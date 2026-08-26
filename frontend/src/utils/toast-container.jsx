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

import React from 'react';
import { ToastContainer, Slide } from 'react-toastify';
import { alpha, useTheme } from '@mui/material/styles';
import { useSelector } from 'react-redux';

const SHOULD_PAUSE_ON_FOCUS_LOSS = false;
const SEVERITIES = ['success', 'error', 'warning', 'info'];

export const ToastContainerWithStyles = () => {
    const theme = useTheme();
    const preferences = useSelector((state) => state.preferences.preferences);

    // Get toast position preference
    const toastPositionPreference = preferences.find(pref => pref.name === 'toast_position');
    const position = toastPositionPreference ? toastPositionPreference.value : 'top-right';
    const pauseOnFocusLoss = SHOULD_PAUSE_ON_FOCUS_LOSS;

    const isDark = theme.palette.mode === 'dark';
    // surface/border are ground-station semantic tokens, so fall back to the stock
    // MUI equivalents if this ever renders outside the app's ThemeProvider — a
    // toast stylesheet should degrade, not take the whole app down.
    const surface = theme.palette.surface?.raised ?? theme.palette.background.paper;
    const borderColor = theme.palette.border?.main ?? theme.palette.divider;
    const cardShadow = isDark
        ? '0 6px 16px rgba(0, 0, 0, 0.32)'
        : '0 2px 8px rgba(16, 24, 40, 0.1)';

    // Neutral card surface with a faint severity tint laid over it. The severity
    // reads from the icon and the progress bar rather than from a saturated
    // background, so the toast sits on the same visual plane as dialogs/menus.
    // The tint is deliberately lighter than palette.statusSurface (0.2/0.12),
    // which is tuned for filled status chips and reads too saturated here.
    const severityRules = SEVERITIES.map((severity) => {
        const tint = alpha(theme.palette[severity].main, isDark ? 0.1 : 0.055);
        return `
                .Toastify__toast--${severity} {
                    background-color: ${surface} !important;
                    background-image: linear-gradient(${tint}, ${tint}) !important;
                    color: ${theme.palette.text.primary} !important;
                }

                .Toastify__toast--${severity} .Toastify__toast-icon {
                    color: ${theme.palette[severity].main} !important;
                }
            `;
    }).join('');

    return (
        <>
            <style>{`
                .Toastify__toast-container {
                    /* Card geometry: wider and tighter than the react-toastify default. */
                    --toastify-toast-width: 420px;
                    --toastify-toast-bd-radius: 5px;
                    --toastify-toast-min-height: 0px;
                    --toastify-toast-padding: 10px 32px 12px 12px;
                    --toastify-color-progress-bgo: ${isDark ? 0.28 : 0.18};
                    --toastify-color-progress-success: ${theme.palette.success.main};
                    --toastify-color-progress-error: ${theme.palette.error.main};
                    --toastify-color-progress-warning: ${theme.palette.warning.main};
                    --toastify-color-progress-info: ${theme.palette.info.main};
                    --toastify-icon-color-success: ${theme.palette.success.main};
                    --toastify-icon-color-error: ${theme.palette.error.main};
                    --toastify-icon-color-warning: ${theme.palette.warning.main};
                    --toastify-icon-color-info: ${theme.palette.info.main};

                    z-index: 1299 !important;
                    box-sizing: border-box;
                }

                .Toastify__toast-container--top-left,
                .Toastify__toast-container--top-right {
                    top: 75px !important;
                }

                .Toastify__toast-container--top-center {
                    top: 10px !important;
                    left: 50% !important;
                    transform: translateX(-50%) !important;
                    width: auto !important;
                    min-width: 0 !important;
                    width: max-content !important;
                    max-width: 90vw !important;
                }

                .Toastify__toast-container--top-center .Toastify__toast {
                    width: auto !important;
                    min-width: 0 !important;
                    max-width: 90vw !important;
                }

                .Toastify__toast-container--bottom-center {
                    bottom: 20px !important;
                    left: 50% !important;
                    transform: translateX(-50%) !important;
                    width: auto !important;
                    min-width: 0 !important;
                    width: max-content !important;
                    max-width: 90vw !important;
                }

                .Toastify__toast-container--bottom-center .Toastify__toast {
                    width: auto !important;
                    min-width: 0 !important;
                    max-width: 90vw !important;
                }

                @media (max-width: 600px) {
                    .Toastify__toast-container {
                        padding: 0 12px;
                    }
                }

                .Toastify__toast-container,
                .Toastify__toast,
                .Toastify__toast-body,
                .Toastify__toast-body > div {
                    font-family: 'Roboto', sans-serif !important;
                }

                .Toastify__toast {
                    /* Content is top-aligned so the icon lines up with the first
                       text row instead of floating in the vertical centre. */
                    align-items: flex-start !important;
                    border: 1px solid ${borderColor} !important;
                    box-shadow: ${cardShadow} !important;
                    margin-bottom: 10px !important;
                    overflow: hidden !important;
                }

                ${severityRules}

                .Toastify__toast-icon {
                    width: 20px !important;
                    margin-top: 1px !important;
                    margin-inline-end: 10px !important;
                }

                .Toastify__toast-icon svg {
                    width: 20px;
                    height: 20px;
                    fill: currentColor;
                }

                .Toastify__toast-body {
                    flex: 1 1 auto !important;
                    min-width: 0 !important;
                    align-items: flex-start !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    font-size: 13px !important;
                    line-height: 1.55 !important;
                    white-space: pre-line !important;
                }

                .Toastify__close-button {
                    top: 8px !important;
                    right: 8px !important;
                    color: ${theme.palette.text.secondary} !important;
                    opacity: 0.72 !important;
                }

                .Toastify__close-button:hover,
                .Toastify__close-button:focus-visible {
                    opacity: 1 !important;
                }

                .Toastify__close-button > svg {
                    width: 15px;
                    height: 15px;
                }

                /* Hairline countdown along the bottom edge of the card. */
                .Toastify__progress-bar--wrp {
                    height: 2px !important;
                }

                .Toastify__progress-bar {
                    opacity: 1 !important;
                }

                /* Structured body rows emitted by toast-with-timestamp.jsx. */
                .gs-toast__meta {
                    font-size: 10px;
                    line-height: 1.3;
                    font-family: 'Roboto Mono', ui-monospace, monospace;
                    letter-spacing: 0.01em;
                    color: ${theme.palette.text.secondary};
                    margin-bottom: 4px;
                }

                .gs-toast__message {
                    font-size: 13px;
                    line-height: 1.55;
                    color: ${theme.palette.text.primary};
                }

                .observation-countdown-toast__countdown {
                    font-size: 18px;
                    text-align: right;
                }

                .observation-countdown-toast__line {
                    font-size: 14px;
                    white-space: normal;
                    overflow: visible;
                    text-overflow: clip;
                }

            `}</style>
            <ToastContainer
                position={position}
                autoClose={4000}
                hideProgressBar={false}
                newestOnTop={false}
                closeOnClick={false}
                rtl={false}
                pauseOnFocusLoss={pauseOnFocusLoss}
                draggable={true}
                draggablePercent={30}
                pauseOnHover={true}
                theme={theme.palette.mode}
                transition={Slide}
                toastClassName="custom-toast"
            />
        </>
    );
};
