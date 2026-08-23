/**
 * Target-page crash diagnostics.
 *
 * This module deliberately records only a small, serializable snapshot.  Keeping
 * the report bounded is important because it is sent while the UI may already be
 * failing and must not include the full Redux state or user-entered credentials.
 */

import {store} from '../common/store.jsx';

const MAX_BREADCRUMBS = 20;
const MAX_TEXT_LENGTH = 8000;
const recentReports = new Map();
const breadcrumbs = [];

const truncate = (value, maxLength = MAX_TEXT_LENGTH) => {
    const text = String(value ?? '');
    return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
};

const stringifyError = (value) => {
    try {
        return JSON.stringify(value);
    } catch {
        return Object.prototype.toString.call(value);
    }
};

const safeBreadcrumbDetails = (details) => {
    try {
        const serialized = JSON.stringify(details);
        if (serialized.length > 1000) {
            return {truncated: truncate(serialized, 1000)};
        }
        return JSON.parse(serialized);
    } catch {
        return {unserializable: Object.prototype.toString.call(details)};
    }
};

const errorDetails = (error) => {
    if (error instanceof Error) {
        return {
            name: error.name || 'Error',
            message: truncate(error.message || 'Unknown error'),
            stack: truncate(error.stack || ''),
        };
    }

    if (typeof error === 'object' && error !== null) {
        return {
            name: truncate(error.name || 'NonErrorThrown', 200),
            message: truncate(error.message || error.statusText || stringifyError(error)),
            stack: truncate(error.stack || ''),
        };
    }

    return {
        name: 'NonErrorThrown',
        message: truncate(error || 'Unknown error'),
        stack: '',
    };
};

const targetContext = () => {
    const state = store.getState();
    const target = state?.targetSatTrack || {};
    const trackingState = target.trackingState || {};
    const position = target.satelliteData?.position || {};

    return {
        trackerId: target.trackerId ?? null,
        targetType: trackingState.target_type ?? null,
        hasTargetName: Boolean(trackingState.target_name),
        satelliteId: target.satelliteId ?? trackingState.norad_id ?? null,
        mapEngine: target.mapEngine ?? null,
        targetViewMode: target.targetViewMode ?? null,
        autoSwitchPlanetariumByVisibility: Boolean(target.autoSwitchPlanetariumByVisibility),
        position: {
            hasAzimuth: Number.isFinite(Number(position.az)),
            hasElevation: Number.isFinite(Number(position.el)),
        },
    };
};

export const recordTargetBreadcrumb = (event, details = {}) => {
    breadcrumbs.push({
        at: new Date().toISOString(),
        event: truncate(event, 200),
        details: safeBreadcrumbDetails(details),
    });
    if (breadcrumbs.length > MAX_BREADCRUMBS) {
        breadcrumbs.splice(0, breadcrumbs.length - MAX_BREADCRUMBS);
    }
};

export const buildTargetDiagnostic = (error, source) => {
    const state = store.getState();
    const version = state?.version?.data || {};

    return {
        kind: 'target-page-client-error',
        source,
        occurredAt: new Date().toISOString(),
        location: window.location.href,
        userAgent: navigator.userAgent,
        build: {
            version: version.version ?? null,
            buildDate: version.buildDate ?? null,
            gitCommit: version.gitCommit ?? null,
        },
        error: errorDetails(error),
        target: targetContext(),
        breadcrumbs: [...breadcrumbs],
    };
};

const reportKey = (report) => `${report.source}:${report.error.name}:${report.error.message}:${report.error.stack}`;

export const sendTargetDiagnostic = (report) => {
    const key = reportKey(report);
    const now = Date.now();
    const lastReported = recentReports.get(key);

    // React may surface a render error through both window.onerror and the route
    // boundary. One report is enough, while a later recurrence is still useful.
    if (lastReported && now - lastReported < 5000) {
        return report;
    }
    recentReports.set(key, now);

    try {
        const payload = JSON.stringify(report);
        fetch('/api/diagnostics/target-error', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: payload,
            keepalive: true,
        }).catch(() => {
            // The report remains available through the on-screen copy action.
        });
    } catch {
        // A broken browser environment must not create a second application error.
    }

    return report;
};

export const reportTargetDiagnostic = (error, source) => sendTargetDiagnostic(
    buildTargetDiagnostic(error, source),
);

export const diagnosticReportText = (report) => JSON.stringify(report, null, 2);
