import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/test-utils.jsx';
import ObservationFolderDialog from '../observation-folder-dialog.jsx';

const BUNDLE = 'ALFEROV_20260816_121242.gsobs';
const BASE = 'capture_iq_1';

const recording = {
    type: 'recording',
    name: BASE,
    observation_bundle: BUNDLE,
    data_file: `${BASE}.sigmf-data`,
    meta_file: `${BASE}.sigmf-meta`,
    data_size: 1536,
    meta_size: 64,
    metadata: { center_frequency: 437_025_000, sample_rate: 2_400_000 },
    snapshot: {
        filename: `${BASE}.png`,
        url: `/observations/${BUNDLE}/recordings/${BASE}.png`,
        thumbnail_url: `/observations/${BUNDLE}/recordings/${BASE}_waterfall_thumb.png?v=1`,
    },
    download_urls: {
        data: `/observations/${BUNDLE}/recordings/${BASE}.sigmf-data`,
        meta: `/observations/${BUNDLE}/recordings/${BASE}.sigmf-meta`,
    },
};

// Every file the capture owns is tagged by the backend with its owner.
const groupedArtifacts = [
    { name: `${BASE}.sigmf-data`, path: `recordings/${BASE}.sigmf-data`, url: recording.download_urls.data, size: 1536, kind: 'recording', file_type: '.sigmf-data', recording_name: BASE },
    { name: `${BASE}.sigmf-meta`, path: `recordings/${BASE}.sigmf-meta`, url: recording.download_urls.meta, size: 64, kind: 'recording', file_type: '.sigmf-meta', recording_name: BASE },
    { name: `${BASE}.png`, path: `recordings/${BASE}.png`, url: recording.snapshot.url, size: 4096, kind: 'recording', file_type: '.png', recording_name: BASE },
    { name: `${BASE}_waterfall_thumb.png`, path: `recordings/${BASE}_waterfall_thumb.png`, url: recording.snapshot.thumbnail_url, size: 512, kind: 'recording', file_type: '.png', recording_name: BASE },
];

const telemetryArtifact = {
    name: 'telemetry.bin',
    path: 'decoded/telemetry.bin',
    url: `/observations/${BUNDLE}/decoded/telemetry.bin`,
    size: 128,
    kind: 'decoded',
    file_type: '.bin',
    recording_name: null,
};

const decodedImage = {
    name: 'preview.png',
    path: 'decoded/preview.png',
    url: `/observations/${BUNDLE}/decoded/preview.png`,
    size: 2048,
    kind: 'decoded',
    file_type: '.png',
    recording_name: null,
};

const folder = {
    type: 'decoded_folder',
    folder_kind: 'observation',
    foldername: BUNDLE,
    satellite_name: '239ALFEROV RS61S',
    size: 6336,
    artifact_count: groupedArtifacts.length + 2,
    recording_count: 1,
    download_url: `/api/observations/${BUNDLE}/download`,
    recordings: [recording],
    artifacts: [...groupedArtifacts, telemetryArtifact, decodedImage],
    images: [
        { ...groupedArtifacts[2] },
        { ...groupedArtifacts[3] },
        decodedImage,
    ],
};

describe('ObservationFolderDialog', () => {
    it('collapses each IQ capture into a single card', () => {
        renderWithProviders(
            <ObservationFolderDialog open onClose={vi.fn()} folder={folder} onOpenArtifact={vi.fn()} />
        );

        expect(screen.getAllByTestId('observation-recording-card')).toHaveLength(1);
        expect(screen.getByText(BASE)).toBeInTheDocument();
        expect(screen.getByText('1.5 KB · 437.025 MHz · 2.4 Msps')).toBeInTheDocument();

        // The capture's own files must not appear again as images or list rows.
        expect(screen.queryByText(`${BASE}.sigmf-data`)).not.toBeInTheDocument();
        expect(screen.queryByText(`${BASE}.sigmf-meta`)).not.toBeInTheDocument();
        expect(screen.queryByText(`${BASE}.png`)).not.toBeInTheDocument();
        expect(screen.queryByText(`${BASE}_waterfall_thumb.png`)).not.toBeInTheDocument();

        // Unrelated artifacts keep their own entries.
        expect(screen.getByText('preview.png')).toBeInTheDocument();
        expect(screen.getByText('telemetry.bin')).toBeInTheDocument();
    });

    it('uses the waterfall thumbnail as the recording card preview', () => {
        renderWithProviders(
            <ObservationFolderDialog open onClose={vi.fn()} folder={folder} onOpenArtifact={vi.fn()} />
        );

        expect(screen.getByAltText(BASE)).toHaveAttribute('src', recording.snapshot.thumbnail_url);
    });

    it('hands the recording payload to the artifact opener when clicked', async () => {
        const onOpenArtifact = vi.fn();
        renderWithProviders(
            <ObservationFolderDialog open onClose={vi.fn()} folder={folder} onOpenArtifact={onOpenArtifact} />
        );

        await userEvent.click(screen.getByTestId('observation-recording-card'));

        expect(onOpenArtifact).toHaveBeenCalledTimes(1);
        expect(onOpenArtifact).toHaveBeenCalledWith(recording);
    });

    it('falls back to per-file entries when the payload has no grouped recordings', () => {
        const legacyFolder = {
            ...folder,
            recordings: undefined,
            recording_count: undefined,
            artifacts: [...groupedArtifacts, telemetryArtifact].map(
                ({ recording_name, ...artifact }) => artifact
            ),
            images: [{ ...groupedArtifacts[2], recording_name: undefined }],
        };

        renderWithProviders(
            <ObservationFolderDialog open onClose={vi.fn()} folder={legacyFolder} onOpenArtifact={vi.fn()} />
        );

        expect(screen.queryAllByTestId('observation-recording-card')).toHaveLength(0);
        expect(screen.getByText(`${BASE}.sigmf-data`)).toBeInTheDocument();
    });
});
