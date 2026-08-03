import React from 'react';
import {
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Grid,
    IconButton,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Paper,
    Stack,
    Tooltip,
    Typography,
} from '@mui/material';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import DescriptionIcon from '@mui/icons-material/Description';
import DownloadIcon from '@mui/icons-material/Download';
import ImageIcon from '@mui/icons-material/Image';
import RadioIcon from '@mui/icons-material/Radio';
import SatelliteAltIcon from '@mui/icons-material/SatelliteAlt';

function formatBytes(bytes) {
    if (!bytes) return '0 Bytes';
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1);
    return `${Math.round((bytes / 1024 ** index) * 100) / 100} ${sizes[index]}`;
}

function artifactIcon(artifact) {
    if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'].includes(artifact.file_type)) {
        return <ImageIcon color="success" />;
    }
    if (artifact.kind === 'audio') return <AudioFileIcon color="info" />;
    if (artifact.kind === 'recording') return <RadioIcon color="error" />;
    return <DescriptionIcon color="action" />;
}

function artifactLabel(artifact) {
    if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'].includes(artifact.file_type)) return 'Image';
    if (artifact.file_type === '.sigmf-data') return 'IQ recording';
    if (artifact.kind === 'audio') return 'Audio recording';
    if (artifact.kind === 'transcription') return 'Transcript';
    if (artifact.kind === 'decoded') return 'Decoded data';
    return 'Supporting file';
}

export default function ObservationFolderDialog({ open, onClose, folder, onOpenArtifact }) {
    if (!folder) return null;

    const artifacts = folder.artifacts || [];
    const images = folder.images || [];
    const nonImageArtifacts = artifacts.filter(
        (artifact) => !['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'].includes(artifact.file_type)
    );
    const openArtifact = (artifact) => {
        if (onOpenArtifact) {
            onOpenArtifact(artifact);
            return;
        }
        window.open(artifact.url, '_blank', 'noopener,noreferrer');
    };

    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="lg"
            fullWidth
            PaperProps={{
                sx: {
                    bgcolor: 'background.paper',
                    border: (theme) => `1px solid ${theme.palette.divider}`,
                    borderRadius: 2,
                    height: '90vh',
                    maxHeight: '90vh',
                }
            }}
        >
            <DialogTitle sx={{
                bgcolor: (theme) => (theme.palette.mode === 'dark' ? 'grey.900' : 'grey.100'),
                borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
                py: 2.5,
                px: 3,
            }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
                    <Box sx={{ minWidth: 0 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <SatelliteAltIcon color="primary" />
                            <Typography variant="h6">{folder.satellite_name || 'Automated Observation'}</Typography>
                        </Box>
                        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            {folder.foldername}
                        </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexShrink: 0 }}>
                        <Chip label={`${folder.artifact_count || 0} files`} size="small" color="info" />
                        <Chip label={formatBytes(folder.size)} size="small" variant="outlined" />
                    </Box>
                </Box>
            </DialogTitle>
            <DialogContent sx={{
                bgcolor: (theme) => (theme.palette.mode === 'dark' ? 'rgba(0, 0, 0, 0.36)' : 'grey.100'),
                overflow: 'auto',
                flex: 1,
                px: 3,
                pt: '32px !important',
                pb: 3,
            }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ sm: 'center' }} sx={{ mt: 1, mb: 2 }}>
                    <Box>
                        <Typography variant="subtitle1" fontWeight={700}>Observation artifacts</Typography>
                        <Typography variant="body2" color="text.secondary">Select an item to open it in its dedicated viewer.</Typography>
                    </Box>
                    <Button
                        variant="outlined"
                        color="inherit"
                        startIcon={<DownloadIcon />}
                        onClick={() => window.open(folder.download_url, '_blank', 'noopener,noreferrer')}
                    >
                        Download ZIP
                    </Button>
                </Stack>
                {images.length > 0 && (
                    <>
                        <Typography variant="subtitle2" sx={{ mb: 1.25 }}>Image products</Typography>
                        <Grid container spacing={1.5} sx={{ mb: 3 }}>
                            {images.map((image) => (
                                <Grid item xs={12} sm={6} md={4} key={image.path}>
                                    <Paper
                                        elevation={0}
                                        onClick={() => openArtifact(image)}
                                        sx={{ cursor: 'pointer', border: 1, borderColor: 'divider', borderRadius: 2, overflow: 'hidden', transition: 'all 160ms ease', '&:hover': { borderColor: 'primary.main', transform: 'translateY(-2px)', boxShadow: 3 } }}
                                    >
                                        <Box component="img" src={image.url} alt={image.name} loading="lazy" sx={{ display: 'block', width: '100%', height: 164, objectFit: 'contain', bgcolor: 'grey.900' }} />
                                        <Box sx={{ p: 1.25 }}>
                                            <Typography variant="body2" noWrap fontWeight={600}>{image.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">{formatBytes(image.size)} · Open image viewer</Typography>
                                        </Box>
                                    </Paper>
                                </Grid>
                            ))}
                        </Grid>
                        <Divider sx={{ mb: 2 }} />
                    </>
                )}
                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>Supporting files</Typography>
                <List disablePadding sx={{ display: 'grid', gap: 1 }}>
                    {nonImageArtifacts.map((artifact) => (
                        <Paper
                            key={artifact.path}
                            variant="outlined"
                            sx={{ borderRadius: 2, overflow: 'hidden', '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' } }}
                        >
                            <ListItemButton onClick={() => openArtifact(artifact)} sx={{ py: 1.1 }}>
                                <ListItemIcon sx={{ minWidth: 44 }}>{artifactIcon(artifact)}</ListItemIcon>
                                <ListItemText
                                    primary={artifact.name}
                                    secondary={`${artifactLabel(artifact)} · ${formatBytes(artifact.size)} · ${artifact.path}`}
                                    primaryTypographyProps={{ noWrap: true, fontWeight: 600 }}
                                    secondaryTypographyProps={{ noWrap: true }}
                                />
                                <Tooltip title="Open in dedicated viewer">
                                    <IconButton edge="end" onClick={(event) => { event.stopPropagation(); openArtifact(artifact); }}><DownloadIcon /></IconButton>
                                </Tooltip>
                            </ListItemButton>
                        </Paper>
                    ))}
                    {artifacts.length === 0 && <Typography color="text.secondary">No files were produced by this observation.</Typography>}
                    {artifacts.length > 0 && nonImageArtifacts.length === 0 && <Typography color="text.secondary">This observation only produced image products.</Typography>}
                </List>
            </DialogContent>
            <DialogActions disableSpacing sx={{
                bgcolor: (theme) => (theme.palette.mode === 'dark' ? 'grey.900' : 'grey.100'),
                borderTop: (theme) => `1px solid ${theme.palette.divider}`,
                px: 3,
                py: 2.5,
                gap: 1,
            }}>
                <Button onClick={onClose} variant="outlined">Close</Button>
            </DialogActions>
        </Dialog>
    );
}
