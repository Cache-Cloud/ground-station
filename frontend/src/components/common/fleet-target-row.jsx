import * as React from 'react';
import { Box, Chip, IconButton, Stack, Tooltip, Typography } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';

const FleetTargetRow = React.memo(function FleetTargetRow({
    targetNumber,
    satName = 'No satellite',
    satNorad = 'none',
    elevation = null,
    isActive = false,
    onFocus,
    onOpenConsole,
    extraMeta = null,
    statusChip = null,
    actions = null,
}) {
    const hasElevation = elevation !== null && elevation !== undefined && Number.isFinite(Number(elevation));

    return (
        <Box
            sx={{
                p: 0.8,
                border: '1px solid',
                borderColor: isActive ? 'primary.main' : 'divider',
                borderRadius: 1,
                backgroundColor: isActive ? 'action.hover' : 'transparent',
            }}
        >
            <Stack direction="row" spacing={0.6} alignItems="center" useFlexGap flexWrap="wrap">
                <Chip
                    size="small"
                    clickable
                    color={isActive ? 'primary' : 'default'}
                    variant={isActive ? 'filled' : 'outlined'}
                    label={`Target ${targetNumber}`}
                    onClick={onFocus}
                    sx={{ '& .MuiChip-label': { fontWeight: 'bold', fontSize: '12px' } }}
                />
                <Typography
                    variant="caption"
                    color="text.secondary"
                    noWrap
                    sx={{ maxWidth: 120, fontWeight: 'bold', fontSize: '12px', lineHeight: 1.25 }}
                >
                    {satName}
                </Typography>
                <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontWeight: 'bold', fontSize: '12px', lineHeight: 1.25 }}
                >
                    {`(${satNorad})`}
                </Typography>
                {hasElevation && (
                    <Chip
                        size="small"
                        label={`El ${Number(elevation).toFixed(1)}°`}
                        color={Number(elevation) > 0 ? 'success' : 'default'}
                        variant={Number(elevation) > 0 ? 'filled' : 'outlined'}
                        sx={{ '& .MuiChip-label': { fontSize: '11px' } }}
                    />
                )}
            </Stack>
            {extraMeta && (
                <Box sx={{ mt: 0.6 }}>
                    {extraMeta}
                </Box>
            )}
            {(statusChip || actions || onOpenConsole) && (
                <Stack direction="row" spacing={0.6} alignItems="center" sx={{ mt: 0.6 }}>
                    {statusChip}
                    <Box sx={{ flexGrow: 1 }} />
                    <Tooltip title="Open Tracking Console">
                        <IconButton size="small" onClick={onOpenConsole}>
                            <OpenInNewIcon fontSize="small" />
                        </IconButton>
                    </Tooltip>
                    {actions}
                </Stack>
            )}
        </Box>
    );
});

export default FleetTargetRow;
