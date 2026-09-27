import { describe, expect, it } from 'vitest';
import {
  calculatePerpendicularPathCap,
  calculateTargetPathViewport,
  collectLiveTrackedTargetKeys,
  shouldSuppressStaticSolarBody,
} from '../solarsystem-canvas.jsx';

describe('solar system path endpoint markers', () => {
  it('builds a centered cap perpendicular to the path start', () => {
    expect(calculatePerpendicularPathCap(10, 20, 20, 20, 8)).toEqual({
      fromX: 10,
      fromY: 16,
      toX: 10,
      toY: 24,
    });
  });
});

describe('solar system target path fitting', () => {
  it('zooms short projected paths using their actual bounds', () => {
    const viewport = calculateTargetPathViewport({
      points: [
        [5, 1, 0],
        [5.001, 1, 0],
      ],
      width: 800,
      height: 600,
    });

    expect(viewport.zoom).toBeCloseTo(576000);
    expect(viewport.panX).toBeCloseTo(-5.0005 * viewport.zoom);
    expect(viewport.panY).toBeCloseTo(viewport.zoom);
  });

  it('uses the changing axis for a vertical path', () => {
    const viewport = calculateTargetPathViewport({
      points: [
        [5, 1, 0],
        [5, 1.002, 0],
      ],
      width: 800,
      height: 600,
    });

    expect(viewport.zoom).toBeCloseTo(216000);
  });
});

describe('solar system monitored body ownership', () => {
  it('suppresses a static marker when the same live target is rendered', () => {
    const liveKeys = collectLiveTrackedTargetKeys([
      { target_key: 'body:io', position_xyz_au: [1, 2, 3] },
      { target_key: 'body:europa', position_xyz_au: null },
    ]);

    expect(shouldSuppressStaticSolarBody({ target_key: 'body:io' }, liveKeys)).toBe(true);
    expect(shouldSuppressStaticSolarBody({ target_key: 'body:europa' }, liveKeys)).toBe(false);
    expect(shouldSuppressStaticSolarBody({ target_key: 'body:io' }, liveKeys, false)).toBe(false);
  });
});
