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
import ArrowDownwardRoundedIcon from '@mui/icons-material/ArrowDownwardRounded';
import ArrowUpwardRoundedIcon from '@mui/icons-material/ArrowUpwardRounded';
import {Box, Chip, Tooltip, Typography} from '@mui/material';
import {getFrequencyBand} from './common.jsx';

const txLinkPalette = ['#0B7285', '#2B8A3E', '#1C7ED6', '#5F3DC4', '#087F5B', '#364FC7'];

const getPaletteColor = (signature) => {
    let hash = 0;
    for (let i = 0; i < signature.length; i += 1) {
        hash = ((hash << 5) - hash) + signature.charCodeAt(i);
        hash |= 0;
    }
    return txLinkPalette[Math.abs(hash) % txLinkPalette.length];
};

const getConfigurationTooltip = (link, t, translationPrefix) => {
    const key = `${translationPrefix}.transmitter_link_tooltips`;
    if (link.upBand && link.downBand) {
        if (link.upBand === link.downBand) {
            return t(`${key}.same_band`, {
                count: link.count,
                band: link.upBand,
                defaultValue: '{{count}} transmitter(s) with {{band}} uplink and downlink',
            });
        }
        return t(`${key}.split_band`, {
            count: link.count,
            uplinkBand: link.upBand,
            downlinkBand: link.downBand,
            defaultValue: '{{count}} transmitter(s) with {{uplinkBand}} uplink and {{downlinkBand}} downlink',
        });
    }
    if (link.upBand) {
        return t(`${key}.uplink_only`, {
            count: link.count,
            uplinkBand: link.upBand,
            defaultValue: '{{count}} transmitter(s) with {{uplinkBand}} uplink only',
        });
    }
    if (link.downBand) {
        return t(`${key}.downlink_only`, {
            count: link.count,
            downlinkBand: link.downBand,
            defaultValue: '{{count}} transmitter(s) with {{downlinkBand}} downlink only',
        });
    }
    return t(`${key}.unknown`, {
        count: link.count,
        defaultValue: '{{count}} transmitter(s) with no listed uplink or downlink band',
    });
};

const PassTransmitterLinksCell = React.memo(function PassTransmitterLinksCell({
    transmitters,
    noDataText,
    t,
    translationPrefix,
}) {
    if (!Array.isArray(transmitters) || transmitters.length === 0) {
        return noDataText;
    }

    const transmitterLinks = Object.entries(
        transmitters.reduce((acc, transmitter) => {
            const upBand = transmitter.uplink_low != null ? getFrequencyBand(transmitter.uplink_low) : null;
            const downBand = transmitter.downlink_low != null ? getFrequencyBand(transmitter.downlink_low) : null;

            let signature = noDataText;
            if (upBand && downBand) {
                signature = upBand === downBand ? `${upBand}↕` : `${upBand}↑/${downBand}↓`;
            } else if (upBand) {
                signature = `${upBand}↑`;
            } else if (downBand) {
                signature = `${downBand}↓`;
            }

            if (!acc[signature]) {
                acc[signature] = {
                    count: 0,
                    isSplitBand: Boolean(upBand && downBand && upBand !== downBand),
                    descriptions: new Set(),
                    upBand,
                    downBand,
                };
            }

            acc[signature].count += 1;
            if (transmitter?.description) {
                acc[signature].descriptions.add(transmitter.description.trim());
            }
            return acc;
        }, {})
    )
        .map(([signature, details]) => ({
            signature,
            count: details.count,
            isSplitBand: details.isSplitBand,
            descriptions: Array.from(details.descriptions).join(', '),
            upBand: details.upBand,
            downBand: details.downBand,
        }))
        .sort((a, b) => {
            if (a.isSplitBand !== b.isSplitBand) {
                return a.isSplitBand ? -1 : 1;
            }
            return a.signature.localeCompare(b.signature);
        });

    return (
        <Box sx={{display: 'flex', width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center'}}>
            <Box
                sx={{
                    display: 'flex',
                    width: '100%',
                    minWidth: 0,
                    gap: 0.5,
                    flexWrap: 'nowrap',
                    justifyContent: 'flex-start',
                    overflow: 'hidden',
                    WebkitMaskImage: 'linear-gradient(to right, black 0%, black 88%, transparent 100%)',
                    maskImage: 'linear-gradient(to right, black 0%, black 88%, transparent 100%)',
                }}
            >
                {transmitterLinks.map((link) => {
                    const paletteColor = getPaletteColor(link.signature);
                    const chip = (
                        <Chip
                            label={
                                <Box sx={{display: 'inline-flex', alignItems: 'center', gap: 0.35}}>
                                    {link.count > 1 && <Box component="span">{link.count} ×</Box>}
                                    {link.upBand && <><Box component="span">{link.upBand}</Box><ArrowUpwardRoundedIcon sx={{fontSize: '0.85rem'}} /></>}
                                    {link.upBand && link.downBand && link.upBand !== link.downBand && <Box component="span">/</Box>}
                                    {link.downBand && <><Box component="span">{link.downBand}</Box><ArrowDownwardRoundedIcon sx={{fontSize: '0.85rem'}} /></>}
                                    {!link.upBand && !link.downBand && <Box component="span">{link.signature}</Box>}
                                </Box>
                            }
                            size="small"
                            variant="filled"
                            sx={{
                                height: '18px', maxWidth: '100%', flexShrink: 0, fontSize: '0.65rem', fontWeight: 700,
                                backgroundColor: link.isSplitBand ? '#E67700' : `${paletteColor}CC`, color: 'common.white',
                                border: '1px solid', borderColor: link.isSplitBand ? '#D9480F' : `${paletteColor}B3`,
                                '& .MuiChip-label': {px: 0.75},
                            }}
                        />
                    );

                    return (
                        <Tooltip
                            key={`tx-link-tooltip-${link.signature}`}
                            title={
                                <Box>
                                    <Typography variant="caption" component="div">
                                        {getConfigurationTooltip(link, t, translationPrefix)}
                                    </Typography>
                                    {link.descriptions && (
                                        <Typography variant="caption" component="div">
                                            {t(`${translationPrefix}.transmitter_link_tooltips.details`, {
                                                descriptions: link.descriptions,
                                                defaultValue: 'Details: {{descriptions}}',
                                            })}
                                        </Typography>
                                    )}
                                </Box>
                            }
                        >
                            <span>{chip}</span>
                        </Tooltip>
                    );
                })}
            </Box>
        </Box>
    );
});

export default PassTransmitterLinksCell;
