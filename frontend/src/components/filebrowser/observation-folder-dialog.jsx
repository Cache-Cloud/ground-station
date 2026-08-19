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
    Tooltip,
    Typography,
} from '@mui/material';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import DescriptionIcon from '@mui/icons-material/Description';
import DownloadIcon from '@mui/icons-material/Download';
import ImageIcon from '@mui/icons-material/Image';
import RadioIcon from '@mui/icons-material/Radio';
import SatelliteAltIcon from '@mui/icons-material/SatelliteAlt';

const IMAGE_FILE_TYPES = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'];

function formatBytes(bytes) {
    if (!bytes) return '0 Bytes';
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1);
    return `${Math.round((bytes / 1024 ** index) * 100) / 100} ${sizes[index]}`;
}

function formatFrequency(frequencyHz) {
    if (!Number.isFinite(frequencyHz)) return null;
    if (frequencyHz >= 1e9) return `${(frequencyHz / 1e9).toFixed(3)} GHz`;
    if (frequencyHz >= 1e6) return `${(frequencyHz / 1e6).toFixed(3)} MHz`;
    if (frequencyHz >= 1e3) return `${(frequencyHz / 1e3).toFixed(1)} kHz`;
    return `${frequencyHz} Hz`;
}

function formatSampleRate(sampleRateHz) {
    if (!Number.isFinite(sampleRateHz)) return null;
    return sampleRateHz >= 1e6
        ? `${Math.round((sampleRateHz / 1e6) * 100) / 100} Msps`
        : `${Math.round(sampleRateHz / 1e3)} ksps`;
}

/** Summary line for a grouped recording card: size, frequency and sample rate. */
function recordingSummary(recording) {
    return [
        formatBytes(recording.data_size),
        formatFrequency(recording.metadata?.center_frequency),
        formatSampleRate(recording.metadata?.sample_rate),
    ]
        .filter(Boolean)
        .join(' · ');
}

function artifactIcon(artifact) {
    if (IMAGE_FILE_TYPES.includes(artifact.file_type)) {
        return <ImageIcon color="success" />;
    }
    if (artifact.kind === 'audio') return <AudioFileIcon color="info" />;
    if (artifact.kind === 'recording') return <RadioIcon color="error" />;
    return <DescriptionIcon color="action" />;
}

function artifactLabel(artifact) {
    if (IMAGE_FILE_TYPES.includes(artifact.file_type)) return 'Image';
    if (artifact.file_type === '.sigmf-data') return 'IQ recording';
    if (artifact.kind === 'audio') return 'Audio recording';
    if (artifact.kind === 'transcription') return 'Transcript';
    if (artifact.kind === 'decoded') return 'Decoded data';
    return 'Supporting file';
}

export default function ObservationFolderDialog({ open, onClose, folder, onOpenArtifact }) {
    if (!folder) return null;

    const artifacts = folder.artifacts || [];
    const recordings = folder.recordings || [];
    // An IQ capture owns several files (SigMF pair, waterfall, thumbnail). The
    // backend tags them with the owning recording so each capture appears once,
    // as a single card, instead of once per file.
    const images = (folder.images || []).filter((image) => !image.recording_name);
    const nonImageArtifacts = artifacts.filter(
        (artifact) => !artifact.recording_name && !IMAGE_FILE_TYPES.includes(artifact.file_type)
    );
    const hasSupportingFiles = nonImageArtifacts.length > 0;
    const openArtifact = (artifact) => {
        if (onOpenArtifact) {
            onOpenArtifact(artifact);
            return;
        }
        // Grouped recordings carry download URLs instead of a single file URL.
        const fallbackUrl = artifact.url || artifact.download_urls?.data;
        if (fallbackUrl) window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
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
                        {folder.observation_in_progress && (
                            <Chip label="In progress" size="small" color="warning" />
                        )}
                        {recordings.length > 0 && (
                            <Chip
                                label={`${recordings.length} ${recordings.length === 1 ? 'recording' : 'recordings'}`}
                                size="small"
                                color="error"
                                variant="outlined"
                            />
                        )}
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
                <Box sx={{ mt: 1, mb: 2 }}>
                    <Typography variant="subtitle1" fontWeight={700}>Observation artifacts</Typography>
                    <Typography variant="body2" color="text.secondary">Select an item to open it in its dedicated viewer.</Typography>
                </Box>
                {recordings.length > 0 && (
                    <>
                        <Typography variant="subtitle2" sx={{ mb: 1.25 }}>IQ recordings</Typography>
                        <Grid container spacing={1.5} sx={{ mb: 3 }}>
                            {recordings.map((recording) => {
                                const previewUrl = recording.snapshot?.thumbnail_url || recording.snapshot?.url;
                                return (
                                    <Grid item xs={12} sm={6} md={4} key={recording.name}>
                                        <Paper
                                            elevation={0}
                                            onClick={() => openArtifact(recording)}
                                            data-testid="observation-recording-card"
                                            sx={{ cursor: 'pointer', border: 1, borderColor: 'divider', borderRadius: 2, overflow: 'hidden', transition: 'all 160ms ease', '&:hover': { borderColor: 'primary.main', transform: 'translateY(-2px)', boxShadow: 3 } }}
                                        >
                                            <Box sx={{ position: 'relative', height: 164, bgcolor: 'grey.900', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                {previewUrl ? (
                                                    <Box component="img" src={previewUrl} alt={recording.name} loading="lazy" sx={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }} />
                                                ) : (
                                                    <RadioIcon sx={{ fontSize: 48, color: 'grey.600' }} />
                                                )}
                                                <Chip
                                                    label={recording.recording_in_progress ? 'Recording' : 'IQ recording'}
                                                    size="small"
                                                    color={recording.recording_in_progress ? 'warning' : 'error'}
                                                    sx={{ position: 'absolute', top: 8, left: 8 }}
                                                />
                                            </Box>
                                            <Box sx={{ p: 1.25 }}>
                                                <Tooltip title={recording.name}>
                                                    <Typography variant="body2" noWrap fontWeight={600}>{recording.name}</Typography>
                                                </Tooltip>
                                                <Typography variant="caption" color="text.secondary" noWrap component="div">
                                                    {recordingSummary(recording)}
                                                </Typography>
                                                <Typography variant="caption" color="text.secondary" noWrap component="div">
                                                    Open recording details
                                                </Typography>
                                            </Box>
                                        </Paper>
                                    </Grid>
                                );
                            })}
                        </Grid>
                        <Divider sx={{ mb: 2 }} />
                    </>
                )}
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
                {hasSupportingFiles && (
                    <Typography variant="subtitle2" sx={{ mb: 1.25 }}>Supporting files</Typography>
                )}
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
