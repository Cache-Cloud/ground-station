import { describe, expect, it } from 'vitest';
import {
    hasAssignedHardwareId,
    isRigWarningStatus,
    isRotatorWarningStatus,
    resolveAssignedHardwareId,
    resolveRigLedStatus,
    resolveRotatorLedStatus,
    resolveTabHardwareLedStatus,
} from '../hardware-status.js';

describe('resolveAssignedHardwareId', () => {
    it('falls back when preferred source is empty string', () => {
        expect(resolveAssignedHardwareId('', 'rig-2', 'rig-3')).toBe('rig-2');
    });

    it('keeps explicit "none" assignment', () => {
        expect(resolveAssignedHardwareId('none', 'rig-2')).toBe('none');
    });

    it('returns "none" when every source is unset', () => {
        expect(resolveAssignedHardwareId('', null, undefined)).toBe('none');
    });
});

describe('hasAssignedHardwareId', () => {
    it('treats normal IDs as assigned', () => {
        expect(hasAssignedHardwareId('rig-2')).toBe(true);
    });

    it('treats "none" as unassigned', () => {
        expect(hasAssignedHardwareId('none')).toBe(false);
    });
});

describe('hardware LED status', () => {
    it('uses the documented priority for rotator state', () => {
        expect(resolveRotatorLedStatus({ rotatorId: 'none' })).toBe('none');
        expect(resolveRotatorLedStatus({ rotatorId: 'rot-1', rotatorData: { connected: false, tracking: true } })).toBe('disconnected');
        expect(resolveRotatorLedStatus({ rotatorId: 'rot-1', rotatorData: { parked: true } })).toBe('parked');
        expect(resolveRotatorLedStatus({ rotatorId: 'rot-1', rotatorData: { outofbounds: true } })).toBe('outofbounds');
        expect(resolveRotatorLedStatus({ rotatorId: 'rot-1', trackingState: { rotator_state: 'tracking' } })).toBe('tracking');
        expect(resolveRotatorLedStatus({ rotatorId: 'rot-1' })).toBe('unknown');
    });

    it('uses rig status when a rotator is unavailable', () => {
        expect(resolveRigLedStatus({ rigId: 'rig-1', rigData: { connected: true } })).toBe('connected');
        expect(resolveTabHardwareLedStatus({
            rotatorId: 'none',
            rigId: 'rig-1',
            trackingState: { rig_state: 'tracking' },
        })).toMatchObject({ source: 'rig', status: 'tracking', usedRigFallback: true });
    });

    it('marks only rotator attention states as warnings', () => {
        expect(isRotatorWarningStatus('parked')).toBe(true);
        expect(isRotatorWarningStatus('tracking')).toBe(false);
        expect(isRigWarningStatus('tracking')).toBe(false);
    });
});
