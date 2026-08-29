import { describe, expect, it } from 'vitest';
import celestialReducer, {
  fetchTargetCelestialScene,
  setTargetCelestialLivePointing,
  setCelestialTracksLive,
} from '../celestial-slice';

describe('target celestial scenes', () => {
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
