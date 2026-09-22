/**
 * @license
 * Copyright (c) 2025 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

const HORIZONS_FAILURES = {
    unavailable: 'NASA JPL Horizons is temporarily unavailable.',
    connect_timeout: 'The connection to NASA JPL Horizons timed out.',
    read_timeout: 'NASA JPL Horizons did not respond before the request timed out.',
    dns_failure: 'The backend could not resolve ssd.jpl.nasa.gov.',
    connection_failure: 'The backend could not establish a network connection to ssd.jpl.nasa.gov.',
    tls_failure: 'The secure connection to NASA JPL Horizons could not be established.',
    rate_limited: 'NASA JPL Horizons is temporarily rate limiting requests.',
    server_error: 'NASA JPL Horizons returned a server error.',
    invalid_response: 'NASA JPL Horizons returned an invalid response.',
    invalid_target: 'One or more targets do not have a valid Horizons command.',
    target_error: 'NASA JPL Horizons did not return usable ephemeris data for one or more targets.',
};

const CONNECTION_FAILURES = new Set([
    'connect_timeout',
    'read_timeout',
    'dns_failure',
    'connection_failure',
    'tls_failure',
]);

const translated = (t, key, defaultValue, options = {}) => (
    typeof t === 'function' ? t(key, { defaultValue, ...options }) : defaultValue
);

export const describeHorizonsFailure = (reason, t = null) => translated(
    t,
    `admin.ephemeris.failure.reasons.${reason || 'default'}`,
    HORIZONS_FAILURES[reason] || 'NASA JPL Horizons could not complete the request.',
);

const asCount = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

export const buildEphemerisSyncFailure = (result, fallbackMessage, t = null) => {
    const response = result && typeof result === 'object' ? result : {};
    const errors = Array.isArray(response.errors) ? response.errors : [];
    const providerStatus = response.provider_status && typeof response.provider_status === 'object'
        ? response.provider_status
        : {};
    const refreshed = asCount(response.refreshed);
    const failed = asCount(response.failed || errors.length);
    const total = asCount(response.count || (refreshed + failed));
    const reason = providerStatus.reason
        || errors.find((entry) => entry?.error_code)?.error_code
        || null;
    const hasCounts = total > 0 || refreshed > 0 || failed > 0;

    let summary = fallbackMessage || translated(
        t,
        'admin.ephemeris.failure.default_summary',
        'The ephemeris synchronization could not be completed.',
    );
    if (hasCounts) {
        summary = translated(
            t,
            'admin.ephemeris.failure.count_summary',
            `${refreshed} of ${total || refreshed + failed} targets refreshed; ${failed} failed. `
                + 'Existing cached snapshots were left available.',
            { refreshed, total: total || refreshed + failed, failed },
        );
    }

    return {
        title: CONNECTION_FAILURES.has(reason)
            ? translated(
                t,
                'admin.ephemeris.failure.connection_title',
                'Could not reach NASA JPL Horizons',
            )
            : translated(
                t,
                'admin.ephemeris.failure.incomplete_title',
                'Ephemeris synchronization incomplete',
            ),
        summary,
        cause: reason ? describeHorizonsFailure(reason, t) : fallbackMessage,
        reason,
        retryAtUtc: providerStatus.retry_at_utc || null,
        lastFailureAtUtc: providerStatus.last_failure_at_utc || null,
        circuit: providerStatus.circuit || null,
        failed,
        total,
        errors: errors.map((entry) => ({
            targetKey: entry?.target_key || 'unknown',
            targetName: entry?.target_name || entry?.target_key || translated(
                t,
                'admin.common.unknown_target',
                'Unknown target',
            ),
            errorCode: entry?.error_code || null,
            message: entry?.error_code && typeof t === 'function'
                ? describeHorizonsFailure(entry.error_code, t)
                : entry?.error || translated(
                    t,
                    'admin.common.unknown_error',
                    'Unknown error',
                ),
        })),
    };
};
