import React from 'react';
import { useCallback, useMemo } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import PassTimeline from '../passes/timeline/pass-timeline.jsx';
import CelestialPassTimeline from '../celestial/celestial-pass-timeline.jsx';
import { useSocket } from '../common/socket.jsx';
import { fetchTargetCelestialScene } from '../celestial/celestial-slice.jsx';
import {
    buildTargetCelestialPayload,
    buildTargetKeyFromTrackingState,
    buildTargetSceneRequestKey,
    clampTargetPassHours,
    filterPassesForTargetWindow,
    normalizeTargetType,
    resolveTargetDisplayName,
} from './celestial-target-utils.js';

const TargetPassTimelineComponent = (props) => {
    const dispatch = useDispatch();
    const { socket } = useSocket();
    const satellitePasses = useSelector((state) => state.targetSatTrack.satellitePasses);
    const activePass = useSelector((state) => state.targetSatTrack.activePass);
    const gridEditable = useSelector((state) => state.targetSatTrack.gridEditable);
    const trackingState = useSelector((state) => state.targetSatTrack.trackingState || {});
    const satelliteDetails = useSelector((state) => state.targetSatTrack.satelliteData?.details || {});
    const trackerInstances = useSelector((state) => state.trackerInstances?.instances || []);
    const nextPassesHours = useSelector((state) => state.targetSatTrack.nextPassesHours || 24.0);
    const monitoredRows = useSelector((state) => state.celestialMonitored?.monitored || []);
    const groundStationLocation = useSelector((state) => state.location.location);
    const timezone = useSelector(
        (state) => {
            const timezonePref = state.preferences.preferences.find((pref) => pref.name === 'timezone');
            return timezonePref ? timezonePref.value : 'UTC';
        },
        (prev, next) => prev === next,
    );
    const targetType = normalizeTargetType(trackingState);
    const isSatelliteTarget = targetType === 'satellite';
    const targetKey = useMemo(
        () => buildTargetKeyFromTrackingState(trackingState),
        [trackingState],
    );
    const nonSatelliteSceneRequestKey = useMemo(
        () => buildTargetSceneRequestKey({ trackingState, nextPassesHours }),
        [nextPassesHours, trackingState],
    );
    const targetScene = useSelector((state) => (
        state.celestial?.targetScenesByKey?.[nonSatelliteSceneRequestKey] || null
    ));
    const targetName = useMemo(() => {
        return resolveTargetDisplayName({
            trackingState,
            satelliteDetails,
            monitoredRows,
            celestialRows: targetScene?.celestialTracks?.celestial || [],
        });
    }, [monitoredRows, satelliteDetails, targetScene?.celestialTracks?.celestial, trackingState]);
    const nonSatellitePayload = useMemo(
        () => buildTargetCelestialPayload({
            trackingState,
            targetName,
            nextPassesHours,
        }),
        [nextPassesHours, targetName, trackingState],
    );
    const nonSatellitePasses = useMemo(
        () => filterPassesForTargetWindow({
            passes: targetScene?.celestialTracks?.celestial_passes || [],
            targetKey,
            nextPassesHours,
        }),
        [nextPassesHours, targetKey, targetScene?.celestialTracks?.celestial_passes],
    );
    const handleRefreshNonSatelliteTimeline = useCallback(async () => {
        if (!socket || !nonSatellitePayload) return;
        await dispatch(fetchTargetCelestialScene({
            socket,
            payload: nonSatellitePayload,
            requestKey: nonSatelliteSceneRequestKey,
        }));
    }, [dispatch, nonSatellitePayload, nonSatelliteSceneRequestKey, socket]);

    if (!isSatelliteTarget) {
        return (
            <CelestialPassTimeline
                passes={nonSatellitePasses}
                loading={Boolean(targetScene?.loading)}
                gridEditable={gridEditable}
                projectionFutureHours={clampTargetPassHours(nextPassesHours)}
                selectedTargetKey={targetKey}
                onRefresh={handleRefreshNonSatelliteTimeline}
            />
        );
    }

    return (
        <PassTimeline
            {...props}
            passes={satellitePasses}
            activePass={activePass}
            gridEditable={gridEditable}
            groundStationLocation={groundStationLocation}
            timezone={timezone}
            noTargetsConfigured={trackerInstances.length === 0}
        />
    );
};

export const SatellitePassTimeline = React.memo(TargetPassTimelineComponent);

export default SatellitePassTimeline;
