import { configureStore } from '@reduxjs/toolkit';
import { describe, expect, it, vi } from 'vitest';
import monitoredReducer, {
  createMonitoredCelestial,
  setMonitoredFormField,
} from '../monitored-slice.jsx';

describe('monitored target projection settings', () => {
  it('sends the selected projection when creating a target', async () => {
    const socket = {
      emit: vi.fn((event, request, callback) => {
        callback({
          success: true,
          data: {
            id: 'moon-id',
            target_type: request.data.target_type,
            body_id: request.data.body_id,
            display_name: request.data.display_name,
            projection_past_hours: request.data.projection_past_hours,
            projection_future_hours: request.data.projection_future_hours,
            projection_step_minutes: request.data.projection_step_minutes,
          },
        });
      }),
    };
    const store = configureStore({ reducer: { celestialMonitored: monitoredReducer } });

    await store.dispatch(createMonitoredCelestial({
      socket,
      entry: {
        targetType: 'body',
        displayName: 'Moon',
        bodyId: 'moon',
        projectionPastHours: 12,
        projectionFutureHours: 72,
        projectionStepMinutes: 10,
      },
    }));

    expect(socket.emit).toHaveBeenCalledWith(
      'api.call',
      expect.objectContaining({
        data: expect.objectContaining({
          projection_past_hours: 12,
          projection_future_hours: 72,
          projection_step_minutes: 10,
        }),
      }),
      expect.any(Function),
    );
    expect(store.getState().celestialMonitored.monitored[0]).toMatchObject({
      projectionPastHours: 12,
      projectionFutureHours: 72,
      projectionStepMinutes: 10,
    });
  });

  it('accepts projection fields in the add form', () => {
    let state = monitoredReducer(undefined, setMonitoredFormField({
      field: 'projectionStepMinutes',
      value: 15,
    }));

    expect(state.form).toMatchObject({
      projectionPastHours: 1,
      projectionFutureHours: 24,
      projectionStepMinutes: 15,
    });
  });
});
