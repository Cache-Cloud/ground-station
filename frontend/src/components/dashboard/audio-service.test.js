import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    flushAudioBuffers,
    registerFlushCallback,
    unregisterFlushCallback,
} from './audio-service.js';
import {
    AUDIO_AUTO_FLUSH_CHECK_INTERVAL_MS,
    AUDIO_AUTO_FLUSH_MAX_BUFFER_SECONDS,
    AUDIO_WORKER_CATCHUP_RETAIN_CHUNKS,
    AUDIO_WORKER_MAX_QUEUE_FOR_CATCHUP,
    AUDIO_WORKER_MAX_QUEUE_SIZE,
} from './audio-buffer-config.js';

afterEach(() => unregisterFlushCallback());

describe('audio service', () => {
    it('forwards all-buffer and per-VFO flush requests to the registered callback', () => {
        const flush = vi.fn();
        registerFlushCallback(flush);

        flushAudioBuffers();
        flushAudioBuffers(2);

        expect(flush).toHaveBeenNthCalledWith(1, null);
        expect(flush).toHaveBeenNthCalledWith(2, 2);
    });

    it('does nothing after its callback is unregistered', () => {
        const flush = vi.fn();
        registerFlushCallback(flush);
        unregisterFlushCallback();

        flushAudioBuffers(1);

        expect(flush).not.toHaveBeenCalled();
    });
});

describe('audio buffer limits', () => {
    it('keeps catch-up limits internally consistent', () => {
        expect(AUDIO_WORKER_MAX_QUEUE_SIZE).toBe(3);
        expect(AUDIO_WORKER_MAX_QUEUE_FOR_CATCHUP).toBeGreaterThan(AUDIO_WORKER_MAX_QUEUE_SIZE);
        expect(AUDIO_WORKER_CATCHUP_RETAIN_CHUNKS).toBeLessThan(AUDIO_WORKER_MAX_QUEUE_FOR_CATCHUP);
        expect(AUDIO_AUTO_FLUSH_MAX_BUFFER_SECONDS).toBeGreaterThan(0);
        expect(AUDIO_AUTO_FLUSH_CHECK_INTERVAL_MS).toBeGreaterThan(0);
    });
});
