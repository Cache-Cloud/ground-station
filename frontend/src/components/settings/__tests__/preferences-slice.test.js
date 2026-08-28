import { describe, it, expect } from 'vitest';
import preferencesReducer, {
  fetchPreferences,
  fetchSystemPreferences,
  setPreference,
  updatePreferences,
} from '../preferences-slice';

describe('preferences slice', () => {
  it('merges persisted user preferences with defaults and retains unknown saved values', () => {
    let state = preferencesReducer(undefined, { type: '@@INIT' });
    state = preferencesReducer(state, fetchPreferences.pending('request'));
    state = preferencesReducer(state, fetchPreferences.fulfilled([
      { id: 12, name: 'language', value: 'el_GR' },
      { id: 13, name: 'custom_preference', value: 'enabled' },
    ], 'request'));

    expect(state.status).toBe('succeeded');
    expect(state.userPreferences).toEqual(expect.arrayContaining([
      { id: 12, name: 'language', value: 'el_GR' },
      { id: 13, name: 'custom_preference', value: 'enabled' },
      { id: null, name: 'theme', value: 'auto' },
    ]));
  });

  it('updates known preferences locally and keeps user and system failures separate', () => {
    let state = preferencesReducer(undefined, { type: '@@INIT' });
    state = preferencesReducer(state, setPreference({ name: 'theme', value: 'dark' }));
    state = preferencesReducer(state, setPreference({ name: 'unknown', value: 'ignored' }));
    state = preferencesReducer(state, updatePreferences.rejected(null, 'request', undefined, 'Could not save'));
    state = preferencesReducer(state, fetchSystemPreferences.rejected(
      null,
      'request',
      undefined,
      'System unavailable'
    ));

    expect(state.userPreferences.find((preference) => preference.name === 'theme')).toMatchObject({
      value: 'dark',
    });
    expect(state.preferences.find((preference) => preference.name === 'unknown')).toBeUndefined();
    expect(state).toMatchObject({
      status: 'failed',
      error: 'Could not save',
      systemStatus: 'failed',
      systemError: 'System unavailable',
    });
  });
});
