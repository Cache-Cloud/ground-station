import {describe, expect, it} from 'vitest';

import {getSourceSyncPresentation, toFormValues, validateSourceForm} from '../sources-table.jsx';

const t = (key) => key;

describe('sources-table form helpers', () => {
    it('presents persisted source failures as attention required', () => {
        const presentation = getSourceSyncPresentation({
            enabled: true,
            sync_state: {
                suspended_at: '2026-08-25T10:00:00+00:00',
                suspension_reason: 'Connection timed out before an HTTP response.',
            },
        }, t);

        expect(presentation.color).toBe('error');
        expect(presentation.label).toBe('orbital_sources.sync_status_attention');
        expect(presentation.description).toBe('Connection timed out before an HTTP response.');
    });

    it('presents a recent successful CelesTrak request as healthy while deferred', () => {
        const now = Date.parse('2026-08-25T12:00:00+00:00');
        const presentation = getSourceSyncPresentation({
            enabled: true,
            url: 'https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=CSV',
            sync_state: {last_success_at: '2026-08-25T11:00:00+00:00'},
        }, t, now);

        expect(presentation.color).toBe('success');
        expect(presentation.label).toBe('orbital_sources.sync_status_healthy');
        expect(presentation.description).toBe('orbital_sources.sync_status_healthy_deferred_detail');
    });

    it('presents a recent successful non-CelesTrak source as healthy', () => {
        const presentation = getSourceSyncPresentation({
            enabled: true,
            url: 'https://www.space-track.org/basicspacedata/query/class/gp',
            sync_state: {last_success_at: '2026-08-25T11:00:00+00:00'},
        }, t, Date.parse('2026-08-25T12:00:00+00:00'));

        expect(presentation.color).toBe('success');
        expect(presentation.label).toBe('orbital_sources.sync_status_healthy');
    });

    it('presents a persisted non-CelesTrak fetch error as attention required', () => {
        const presentation = getSourceSyncPresentation({
            enabled: true,
            sync_state: {last_error: 'Space-Track login returned HTTP 401.'},
        }, t);

        expect(presentation.color).toBe('error');
        expect(presentation.description).toBe('Space-Track login returned HTTP 401.');
    });

    it('presents an enabled source without sync history as not synced', () => {
        const presentation = getSourceSyncPresentation({enabled: true}, t);

        expect(presentation.color).toBe('default');
        expect(presentation.label).toBe('orbital_sources.sync_status_not_synced');
    });

    it('preserves the dedicated CelesTrak provider in form values', () => {
        const formValues = toFormValues({
            id: 'source-1',
            name: 'Legacy OMM',
            url: 'https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=CSV',
            format: 'omm',
            query_mode: 'url',
            provider: 'celestrak',
            adapter: 'http_omm',
            norad_ids: [25544, 43017],
        });

        expect(formValues.id).toBe('source-1');
        expect(formValues.provider).toBe('celestrak');
        expect(formValues.celestrak_group).toBe('stations');
        expect(formValues.query_mode).toBe('url');
        expect(formValues.norad_ids).toBe('25544, 43017');
    });

    it('keeps an explicitly selected generic provider while its prior URL is CelesTrak', () => {
        const formValues = toFormValues({
            provider: 'generic_http',
            url: 'https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=CSV',
        });

        expect(formValues.provider).toBe('generic_http');
    });

    it('preserves norad text input in form values when already string', () => {
        const formValues = toFormValues({
            provider: 'space_track',
            norad_ids: '25544,43017 57172',
        });

        expect(formValues.norad_ids).toBe('25544,43017 57172');
    });

    it('builds the canonical URL for a selected CelesTrak group', () => {
        const {errors, payload} = validateSourceForm(
            {
                id: null,
                name: 'Legacy OMM',
                url: 'https://example.com/ignored',
                celestrak_group: 'stations',
                format: 'omm',
                query_mode: 'url',
                group_id: 'ignored',
                norad_ids: '25544 43017',
                provider: 'celestrak',
                adapter: 'space_track_gp',
                enabled: true,
                priority: '10',
                central_body: 'earth',
                auth_type: 'none',
                username: '',
                password: '',
            },
            t
        );

        expect(errors).toEqual({});
        expect(payload.query_mode).toBe('url');
        expect(payload.group_id).toBeNull();
        expect(payload.norad_ids).toBeNull();
        expect(payload.provider).toBe('celestrak');
        expect(payload.adapter).toBe('http_omm');
        expect(payload.url).toBe('https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=CSV');
    });

    it('accepts a documented CelesTrak group beyond the initial presets', () => {
        const {errors, payload} = validateSourceForm(
            {
                id: null,
                name: 'CelesTrak Starlink',
                url: '',
                celestrak_group: 'starlink',
                format: 'omm',
                query_mode: 'url',
                group_id: '',
                norad_ids: '',
                provider: 'celestrak',
                adapter: 'http_omm',
                enabled: true,
                priority: '10',
                central_body: 'earth',
                auth_type: 'none',
                username: '',
                password: '',
            },
            t
        );

        expect(errors).toEqual({});
        expect(payload.url).toBe('https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=CSV');
    });

    it('builds normalized payload for valid basic auth source', () => {
        const {errors, payload} = validateSourceForm(
            {
                id: 'source-2',
                name: 'Space-Track GP',
                url: '',
                format: 'omm',
                query_mode: 'url',
                group_id: '',
                norad_ids: '25544, 43017 57172',
                provider: 'space_track',
                adapter: 'space_track_gp',
                enabled: true,
                priority: '5',
                central_body: 'earth',
                auth_type: 'basic',
                username: 'demo',
                password: 'secret',
            },
            t
        );

        expect(errors).toEqual({});
        expect(payload.priority).toBe(5);
        expect(payload.query_mode).toBe('url');
        expect(payload.group_id).toBeNull();
        expect(payload.norad_ids).toEqual([25544, 43017, 57172]);
        expect(payload.url).toBe('https://www.space-track.org/basicspacedata/query/class/gp');
        expect(payload.username).toBe('demo');
        expect(payload.password).toBe('secret');
    });

    it('clears credentials from payload when auth type is none', () => {
        const {errors, payload} = validateSourceForm(
            {
                id: null,
                name: 'Public Source',
                url: 'https://example.com/tle.txt',
                format: '3le',
                query_mode: 'url',
                group_id: 'ignored-group',
                norad_ids: '25544',
                provider: 'generic_http',
                adapter: 'http_3le',
                enabled: true,
                priority: '100',
                central_body: 'earth',
                auth_type: 'none',
                username: 'ignored-user',
                password: 'ignored-pass',
            },
            t
        );

        expect(errors).toEqual({});
        expect(payload.query_mode).toBe('url');
        expect(payload.group_id).toBeNull();
        expect(payload.norad_ids).toBeNull();
        expect(payload.username).toBeNull();
        expect(payload.password).toBeNull();
    });

    it('requires norad ids for space-track sources', () => {
        const {errors} = validateSourceForm(
            {
                id: null,
                name: 'Space-Track Amateur',
                url: '',
                format: 'omm',
                query_mode: 'url',
                group_id: '',
                norad_ids: '',
                provider: 'space_track',
                adapter: 'space_track_gp',
                enabled: true,
                priority: '10',
                central_body: 'earth',
                auth_type: 'basic',
                username: 'demo',
                password: 'secret',
            },
            t
        );

        expect(errors.norad_ids).toBe('orbital_sources.validation.norad_ids_required');
    });

    it('derives space-track auth type from provider', () => {
        const {errors, payload} = validateSourceForm(
            {
                id: 'source-4',
                name: 'Space-Track Direct',
                url: '',
                format: 'omm',
                query_mode: 'url',
                group_id: '',
                norad_ids: '25544',
                provider: 'space_track',
                adapter: '',
                enabled: true,
                priority: '10',
                central_body: 'earth',
                auth_type: 'none',
                username: 'demo',
                password: 'secret',
            },
            t
        );

        expect(errors).toEqual({});
        expect(payload.adapter).toBe('space_track_gp');
        expect(payload.auth_type).toBe('basic');
    });
});
