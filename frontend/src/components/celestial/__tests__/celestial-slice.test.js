import { describe, expect, it } from 'vitest';
import celestialReducer, {
  fetchTargetCelestialScene,
  setCelestialEphemerisProviderStatus,
  setCelestialEphemerisSyncCompleted,
  setCelestialEphemerisSyncFailed,
  setCelestialEphemerisSyncProgress,
  setCelestialEphemerisSyncStarted,
  setTargetCelestialLivePointing,
  setCelestialTracksLive,
} from '../celestial-slice';

describe('target celestial scenes', () => {
  it('clears live tracks and passes when the backend broadcasts an empty state', () => {
    let state = celestialReducer(undefined, setCelestialTracksLive({
      celestial: [{ target_key: 'body:mars', name: 'Mars' }],
      celestial_passes: [{ id: 'mars-pass', target_key: 'body:mars' }],
    }));

    state = celestialReducer(state, setCelestialTracksLive({
      celestial: [],
      celestial_passes: [],
      observer_bodies: [],
    }));

    expect(state.celestialTracks.celestial).toEqual([]);
    expect(state.celestialTracks.celestial_passes).toEqual([]);
    expect(state.celestialTracks.observer_bodies).toEqual([]);
  });

  it('survive a monitored-target live broadcast', () => {
    const requestKey = 'body:venus:0:24:60';
    const requestArgs = { requestKey, payload: {}, socket: {} };
    let state = celestialReducer(
      undefined,
      fetchTargetCelestialScene.pending('venus-request', requestArgs),
    );

    state = celestialReducer(
      state,
      fetchTargetCelestialScene.fulfilled({
        requestKey,
        solarScene: { planets: [] },
        celestialTracks: {
          celestial: [{ target_key: 'body:venus', name: 'Venus' }],
          celestial_passes: [{ target_key: 'body:venus' }],
        },
      }, 'venus-request', requestArgs),
    );

    state = celestialReducer(state, setCelestialTracksLive({
      celestial: [{ target_key: 'body:mars', name: 'Mars' }],
    }));

    expect(state.celestialTracks.celestial).toEqual([
      { target_key: 'body:mars', name: 'Mars' },
    ]);
    expect(state.targetScenesByKey[requestKey].celestialTracks.celestial).toEqual([
      { target_key: 'body:venus', name: 'Venus' },
    ]);
  });

  it('overlays tracker telemetry onto every cached window for the target', () => {
    const requestKey = 'body:venus:0:24:60';
    const requestArgs = { requestKey, payload: {}, socket: {} };
    let state = celestialReducer(
      undefined,
      fetchTargetCelestialScene.pending('venus-request', requestArgs),
    );
    state = celestialReducer(
      state,
      fetchTargetCelestialScene.fulfilled({
        requestKey,
        solarScene: { planets: [] },
        celestialTracks: {
          timestamp_utc: '2026-01-01T00:00:00Z',
          celestial: [{
            target_key: 'body:venus',
            sky_position: { az_deg: 10, el_deg: 20, ra_deg: 30 },
          }],
          celestial_passes: [{ target_key: 'body:venus' }],
        },
      }, 'venus-request', requestArgs),
    );

    state = celestialReducer(state, setTargetCelestialLivePointing({
      targetKey: 'body:venus',
      azDeg: 105.2,
      elDeg: 0.54,
      timestampUtc: '2026-01-01T00:00:05Z',
    }));

    const tracks = state.targetScenesByKey[requestKey].celestialTracks;
    expect(tracks.timestamp_utc).toBe('2026-01-01T00:00:05Z');
    expect(tracks.celestial[0].sky_position).toEqual({ az_deg: 105.2, el_deg: 0.54, ra_deg: 30 });
    expect(tracks.celestial[0].visibility).toMatchObject({ above_horizon: true, visible: true });
    expect(tracks.celestial_passes).toEqual([{ target_key: 'body:venus' }]);
  });
});

describe('celestial ephemeris synchronization state', () => {
  it('tracks progress and clears a previous error when a new sync succeeds', () => {
    let state = celestialReducer(undefined, setCelestialEphemerisSyncStarted());
    expect(state.ephemerisSync.status).toBe('inprogress');

    state = celestialReducer(state, setCelestialEphemerisSyncProgress({
      percent: 50,
      processed: 2,
      total: 4,
      refreshed: 2,
      failed: 0,
      current_target: { key: 'body:mars', name: 'Mars' },
    }));
    expect(state.ephemerisSync).toMatchObject({
      status: 'inprogress',
      progress: 50,
      processed: 2,
      total: 4,
      currentTarget: { key: 'body:mars', name: 'Mars' },
    });

    state = celestialReducer(state, setCelestialEphemerisSyncFailed({
      error: 'Horizons unavailable',
      result: {
        count: 4,
        refreshed: 2,
        failed: 2,
        provider_status: { availability: 'unavailable' },
      },
    }));
    expect(state.ephemerisSync).toMatchObject({
      status: 'failed',
      error: 'Horizons unavailable',
      failed: 2,
      providerStatus: { availability: 'unavailable' },
    });

    state = celestialReducer(state, setCelestialEphemerisSyncStarted());
    state = celestialReducer(state, setCelestialEphemerisSyncCompleted({
      count: 4,
      refreshed: 4,
      failed: 0,
      provider_status: { availability: 'available' },
    }));
    expect(state.ephemerisSync).toMatchObject({
      status: 'complete',
      progress: 100,
      error: null,
      providerStatus: { availability: 'available' },
    });
  });

  it('stores provider availability independently of a manual sync', () => {
    const state = celestialReducer(undefined, setCelestialEphemerisProviderStatus({
      availability: 'unavailable',
      reason: 'connection_failure',
    }));

    expect(state.ephemerisSync.providerStatus).toEqual({
      availability: 'unavailable',
      reason: 'connection_failure',
    });
  });
});
