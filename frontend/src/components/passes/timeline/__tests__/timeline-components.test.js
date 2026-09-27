import { describe, expect, it } from 'vitest';

import { calculateVisibleCurveMidpoint } from '../timeline-components.jsx';

describe('calculateVisibleCurveMidpoint', () => {
  it('interpolates the midpoint of the rendered curve segment', () => {
    expect(calculateVisibleCurveMidpoint([
      [[20, 80], [40, 20], [80, 60]],
    ])).toEqual({ x: 50, y: 30 });
  });

  it('uses the widest visible segment when a curve is split', () => {
    expect(calculateVisibleCurveMidpoint([
      [[5, 90], [10, 80]],
      [[30, 70], [50, 30], [90, 50]],
    ])).toEqual({ x: 60, y: 35 });
  });
});
