import { describe, it, expect } from 'vitest';
import { determineAzimuthArcFlags, normalizeAzimuthForGauge } from '../rotator-gauges.jsx';

describe('normalizeAzimuthForGauge', () => {
  it('maps the 360° endpoint to the equivalent 0° gauge position', () => {
    expect(normalizeAzimuthForGauge(360)).toBe(0);
  });

  it('keeps values within the circular display range', () => {
    expect(normalizeAzimuthForGauge(359.5)).toBe(359.5);
    expect(normalizeAzimuthForGauge(450)).toBe(90);
    expect(normalizeAzimuthForGauge(-10)).toBe(350);
  });

  it('does not render non-finite readings', () => {
    expect(normalizeAzimuthForGauge(Number.NaN)).toBeNull();
  });
});

describe('determineAzimuthArcFlags', () => {
  it('chooses short clockwise arc when peak is on that arc', () => {
    expect(determineAzimuthArcFlags(90, 180, 179.9)).toEqual([0, 1]);
  });

  it('includes end boundary peak and keeps correct short arc', () => {
    expect(determineAzimuthArcFlags(90, 180, 180)).toEqual([0, 1]);
  });

  it('includes start boundary peak and keeps correct short arc', () => {
    expect(determineAzimuthArcFlags(180, 90, 180)).toEqual([0, 0]);
  });

  it('handles north crossing with endpoint peak', () => {
    expect(determineAzimuthArcFlags(350, 10, 10)).toEqual([0, 1]);
  });

  it('falls back to shortest arc when peak is missing', () => {
    expect(determineAzimuthArcFlags(270, 90, null)).toEqual([0, 1]);
  });
});
