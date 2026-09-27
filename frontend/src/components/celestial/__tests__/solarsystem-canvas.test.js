import { describe, expect, it } from 'vitest';
import { calculateTargetPathViewport } from '../solarsystem-canvas.jsx';

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
