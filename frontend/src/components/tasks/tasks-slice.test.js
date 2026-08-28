import { describe, expect, it, vi } from 'vitest';

import reducer, {
    reconcileTaskSnapshot,
    taskCompleted,
    taskError,
    taskProgress,
    taskStarted,
} from './tasks-slice.jsx';

describe('background task slice', () => {
    it('moves a started task through progress and completion', () => {
        vi.spyOn(Date, 'now').mockReturnValue(1_000);
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, taskStarted({ task_id: 'task-1', name: 'Sync', command: 'sync', args: [], pid: 3, start_time: 1 }));
        state = reducer(state, taskProgress({ task_id: 'task-1', stream: 'stdout', output: 'halfway', progress: 50 }));
        state = reducer(state, taskCompleted({ task_id: 'task-1', status: 'completed', return_code: 0, duration: 2 }));

        expect(state.runningTaskIds).toEqual([]);
        expect(state.completedTaskIds).toEqual(['task-1']);
        expect(state.tasks['task-1']).toMatchObject({ status: 'completed', progress: 50, return_code: 0 });
        expect(state.tasks['task-1'].output_lines).toHaveLength(1);
    });

    it('creates an out-of-order error task and reconciles stale running tasks', () => {
        vi.spyOn(Date, 'now').mockReturnValue(2_000);
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, taskStarted({ task_id: 'stale', name: 'Stale', command: '', args: [], pid: null, start_time: 1 }));
        state = reducer(state, taskError({ task_id: 'late', name: 'Late', error: 'connection lost' }));
        state = reducer(state, reconcileTaskSnapshot({ tasks: [{ task_id: 'late', status: 'failed', end_time: 3 }] }));

        // Zero is a valid reported progress value, so reconciliation must retain it.
        expect(state.tasks.stale).toMatchObject({ status: 'completed', progress: 0 });
        expect(state.tasks.late).toMatchObject({ status: 'failed', error: 'connection lost' });
        expect(state.runningTaskIds).toEqual([]);
        expect(state.completedTaskIds).toEqual(['late', 'stale']);
    });
});
