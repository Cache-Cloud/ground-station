/**
 * @license
 * Copyright (c) 2025 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import { describe, expect, it } from 'vitest';
import { buildEphemerisSyncFailure, describeHorizonsFailure } from '../ephemeris-errors.js';

describe('ephemeris synchronization errors', () => {
    it('builds an actionable network failure from the refresh response', () => {
        const failure = buildEphemerisSyncFailure({
            count: 2,
            refreshed: 0,
            failed: 2,
            provider_status: {
                reason: 'dns_failure',
                circuit: 'open',
                retry_at_utc: '2026-09-22T08:45:00+00:00',
            },
            errors: [
                {
                    target_key: 'body:mars',
                    target_name: 'Mars',
                    error_code: 'dns_failure',
                    error: 'NASA JPL Horizons could not be reached',
                },
            ],
        }, 'Command failed');

        expect(failure.title).toBe('Could not reach NASA JPL Horizons');
        expect(failure.summary).toBe(
            '0 of 2 targets refreshed; 2 failed. Existing cached snapshots were left available.',
        );
        expect(failure.cause).toBe('The backend could not resolve ssd.jpl.nasa.gov.');
        expect(failure.retryAtUtc).toBe('2026-09-22T08:45:00+00:00');
        expect(failure.errors[0]).toMatchObject({
            targetKey: 'body:mars',
            targetName: 'Mars',
            errorCode: 'dns_failure',
        });
    });

    it('describes a generic connection failure without exposing an error code', () => {
        expect(describeHorizonsFailure('connection_failure')).toBe(
            'The backend could not establish a network connection to ssd.jpl.nasa.gov.',
        );
    });
});
