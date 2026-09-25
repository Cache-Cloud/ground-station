import { describe, expect, it } from 'vitest';
import {
  buildTargetCelestialPayload,
  buildTargetKeyFromCelestialRow,
  buildTargetSceneRequestKey,
  buildTargetSlotNumberByTargetKey,
  parseTargetSlotNumber,
  replaceCelestialTargetKey,
} from '../celestial-target-utils';

describe('buildTargetCelestialPayload', () => {
  it('preserves backend-owned mission and body target keys', () => {
    const missionPayload = buildTargetCelestialPayload({
      trackingState: {
        target_type: 'mission',
        target_key: 'mission:catalog:42',
        command: 'Juno',
      },
      targetName: 'Juno',
    });
    expect(missionPayload).toEqual(expect.objectContaining({
      allow_network_fetch: true,
    }));
    expect(missionPayload.celestial[0]).toEqual(expect.objectContaining({
      target_type: 'mission',
      target_key: 'mission:catalog:42',
      command: 'Juno',
    }));

    const bodyPayload = buildTargetCelestialPayload({
      trackingState: {
        target_type: 'body',
        target_key: 'body:catalog:venus',
        body_id: 'Venus',
      },
      targetName: 'Venus',
    });
    expect(bodyPayload).toEqual(expect.objectContaining({
      allow_network_fetch: true,
    }));
    expect(bodyPayload.celestial[0]).toEqual(expect.objectContaining({
      target_type: 'body',
      target_key: 'body:catalog:venus',
      body_id: 'venus',
    }));
  });
});

describe('parseTargetSlotNumber', () => {
  it('parses target slot numbers from target tracker IDs', () => {
    expect(parseTargetSlotNumber('target-1')).toBe(1);
    expect(parseTargetSlotNumber(' target-27 ')).toBe(27);
  });

  it('returns null for non-target tracker IDs', () => {
    expect(parseTargetSlotNumber('obs-1')).toBeNull();
    expect(parseTargetSlotNumber('default')).toBeNull();
    expect(parseTargetSlotNumber('target-0')).toBeNull();
  });
});

describe('buildTargetKeyFromCelestialRow', () => {
  it('prefers explicit target keys when available', () => {
    expect(buildTargetKeyFromCelestialRow({ target_key: 'mission:voyager_1' })).toBe('mission:voyager_1');
    expect(buildTargetKeyFromCelestialRow({ targetKey: 'body:rhea' })).toBe('body:rhea');
  });

  it('does not derive identities from metadata', () => {
    expect(buildTargetKeyFromCelestialRow({ target_type: 'mission', mission_id: 'voyager-1' })).toBe('');
    expect(buildTargetKeyFromCelestialRow({ target_type: 'mission', command: 'Voyager 1' })).toBe('');
    expect(buildTargetKeyFromCelestialRow({ targetType: 'body', bodyId: 'Rhea' })).toBe('');
    expect(buildTargetKeyFromCelestialRow({ command: 'Cassini' })).toBe('');
  });
});

describe('replaceCelestialTargetKey', () => {
  it('replaces a tracker patch identity instead of retaining the previous target key', () => {
    expect(replaceCelestialTargetKey({
      target_type: 'mission',
      target_key: 'mission:old_target',
      command: 'Dawn',
    }, ' mission:dawn ')).toEqual({
      target_type: 'mission',
      target_key: 'mission:dawn',
      command: 'Dawn',
    });
  });

  it('writes an empty identity so the backend can derive it from the new metadata', () => {
    expect(replaceCelestialTargetKey({ target_type: 'body', body_id: 'mars' }))
      .toEqual({ target_type: 'body', body_id: 'mars', target_key: '' });
  });
});

describe('buildTargetSceneRequestKey', () => {
  it('keeps celestial target results isolated by target and projection window', () => {
    expect(buildTargetSceneRequestKey({
      trackingState: { target_type: 'body', body_id: 'Venus', target_key: 'body:venus' },
      nextPassesHours: 24,
    })).toBe('body:venus:0:24:60');
    expect(buildTargetSceneRequestKey({
      trackingState: { target_type: 'body', body_id: 'venus', target_key: 'body:venus' },
      nextPassesHours: 12,
    })).toBe('body:venus:0:12:60');
  });
});

describe('buildTargetSlotNumberByTargetKey', () => {
  it('maps mission/body targets to their slot number and ignores non-target trackers', () => {
    const mapping = buildTargetSlotNumberByTargetKey([
      {
        tracker_id: 'target-3',
        tracking_state: {
          target_type: 'mission',
          mission_id: 'voyager-1',
          target_key: 'mission:voyager-1',
        },
      },
      {
        tracker_id: 'target-2',
        tracking_state: {
          target_type: 'body',
          body_id: 'rhea',
          target_key: 'body:rhea',
        },
      },
      {
        tracker_id: 'obs-1',
        tracking_state: {
          target_type: 'mission',
          command: 'Ignored',
          target_key: 'mission:ignored',
        },
      },
      {
        tracker_id: 'target-9',
        tracking_state: {
          target_type: 'satellite',
          norad_id: 25544,
        },
      },
    ]);

    expect(mapping).toEqual({
      'mission:voyager-1': 3,
      'body:rhea': 2,
    });
  });

  it('keeps the lowest slot number when duplicate assignments exist', () => {
    const mapping = buildTargetSlotNumberByTargetKey([
      {
        tracker_id: 'target-8',
        tracking_state: {
          target_type: 'mission',
          mission_id: 'voyager-1',
          target_key: 'mission:voyager-1',
        },
      },
      {
        tracker_id: 'target-1',
        tracking_state: {
          target_type: 'mission',
          mission_id: 'voyager-1',
          target_key: 'mission:voyager-1',
        },
      },
      {
        tracker_id: 'target-5',
        tracking_state: {
          target_type: 'mission',
          mission_id: 'voyager-1',
          target_key: 'mission:voyager-1',
        },
      },
    ]);

    expect(mapping['mission:voyager-1']).toBe(1);
  });
});
