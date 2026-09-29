import React from 'react';
import { Box, Divider, ListItemIcon, Menu, MenuItem, Typography } from '@mui/material';

const formatItemLabel = (item) => {
    const label = String(item?.label || '');
    if (!item?.opensDialog) return label;
    return `${label.replace(/(?:\.\.\.|…)\s*$/, '')}...`;
};

export default function CelestialContextMenu({
    open,
    onClose,
    onSuppressNativeContextMenu,
    anchorPosition,
    title,
    targetType,
    targetIdentifier,
    items = [],
}) {
    const normalizedType = String(targetType || '').trim().toLowerCase();
    const typeLabel = normalizedType === 'mission' ? 'MISSION' : 'BODY';
    const identifierLabel = normalizedType === 'mission' ? 'CMD' : 'ID';

    return (
        <Menu
            open={Boolean(open)}
            onClose={onClose}
            onContextMenu={onSuppressNativeContextMenu}
            anchorReference="anchorPosition"
            transitionDuration={0}
            PaperProps={{
                onContextMenu: onSuppressNativeContextMenu,
                sx: {
                    minWidth: 210,
                },
            }}
            MenuListProps={{
                dense: true,
                onContextMenu: onSuppressNativeContextMenu,
                sx: {
                    py: 0,
                    px: 0,
                },
            }}
            anchorPosition={anchorPosition}
        >
            <MenuItem
                dense
                disabled
                disableRipple
                sx={{
                    m: 0,
                    p: 0,
                    minHeight: 0,
                    opacity: 1,
                    borderRadius: 0,
                    backgroundColor: 'action.hover',
                    '&.Mui-disabled': { opacity: 1 },
                }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 1,
                        width: '100%',
                        minWidth: 0,
                        height: 32,
                        px: 1,
                    }}
                >
                    <Typography
                        variant="body2"
                        sx={{
                            fontSize: '0.82rem',
                            fontWeight: 800,
                            lineHeight: 1.2,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                        }}
                    >
                        {title || '-'}
                    </Typography>
                    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
                        <Box
                            component="span"
                            sx={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                px: 0.7,
                                py: 0.1,
                                borderRadius: 999,
                                border: '1px solid',
                                borderColor: 'divider',
                                color: 'text.secondary',
                                fontSize: '0.66rem',
                                lineHeight: 1.2,
                                whiteSpace: 'nowrap',
                                flexShrink: 0,
                            }}
                        >
                            {typeLabel}
                        </Box>
                        <Box
                            component="span"
                            sx={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                px: 0.7,
                                py: 0.1,
                                borderRadius: 999,
                                border: '1px solid',
                                borderColor: 'divider',
                                color: 'text.secondary',
                                fontSize: '0.66rem',
                                lineHeight: 1.2,
                                whiteSpace: 'nowrap',
                                flexShrink: 0,
                            }}
                        >
                            {`${identifierLabel} ${targetIdentifier || '-'}`}
                        </Box>
                    </Box>
                </Box>
            </MenuItem>
            {items.map((item, index) => {
                if (item?.type === 'divider') {
                    return <Divider key={item.key || `divider-${index}`} sx={{ my: 0 }} />;
                }
                return (
                    <MenuItem
                        key={item?.key || `item-${index}`}
                        sx={{ px: 1, py: 0.4, minHeight: 29, fontSize: '0.82rem', borderRadius: 0 }}
                        disabled={Boolean(item?.disabled)}
                        onClick={item?.onClick}
                    >
                        <ListItemIcon
                            sx={(theme) => ({
                                minWidth: 20,
                                color: theme.palette.mode === 'dark'
                                    ? theme.palette.grey[500]
                                    : theme.palette.grey[800],
                                '& .MuiSvgIcon-root': { fontSize: '0.92rem' },
                            })}
                        >
                            {item?.icon}
                        </ListItemIcon>
                        {formatItemLabel(item)}
                    </MenuItem>
                );
            })}
        </Menu>
    );
}
