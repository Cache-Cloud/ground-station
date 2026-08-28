import { afterEach, describe, expect, it, vi } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';

import reducer, {
    createUser,
    deleteUser,
    loadAuthStatus,
    loginUser,
    logoutUser,
    setShowLogoutConfirmation,
    updateUser,
} from './auth-slice.jsx';

const createStore = () => configureStore({ reducer: { auth: reducer } });

describe('auth slice', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('bootstraps the authenticated session and setup recovery mode from the API', async () => {
        const fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                authenticated: true,
                setup_required: true,
                setup_mode: 'admin_recovery',
                user: { id: 'admin-1', username: 'admin' },
                station: { id: 'station-1', name: 'Home' },
            }),
        });
        vi.stubGlobal('fetch', fetch);
        const store = createStore();

        await store.dispatch(loadAuthStatus());

        expect(fetch).toHaveBeenCalledWith('/api/auth/status', {
            method: 'GET',
            headers: {},
            credentials: 'same-origin',
        });
        expect(store.getState().auth).toMatchObject({
            authenticated: true,
            setupRequired: true,
            setupMode: 'admin_recovery',
            loadingStatus: false,
            statusInitialized: true,
            user: { username: 'admin' },
            station: { name: 'Home' },
        });
    });

    it('keeps a server login error and clears local state even when logout cannot reach the server', async () => {
        const fetch = vi
            .fn()
            .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Invalid credentials' }) })
            .mockRejectedValueOnce(new Error('network unavailable'));
        vi.stubGlobal('fetch', fetch);
        const store = createStore();

        await store.dispatch(loginUser({ username: 'admin', password: 'bad' }));
        await store.dispatch(loadAuthStatus.fulfilled({ authenticated: true, user: { id: 'admin-1' } }, 'seed'));
        await store.dispatch(logoutUser());

        expect(store.getState().auth).toMatchObject({
            authenticated: false,
            user: null,
            loadingAction: false,
            error: 'Invalid credentials',
        });
    });

    it('maintains users, management state, and confirmation preferences', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, setShowLogoutConfirmation(false));
        state = reducer(state, createUser.pending('request'));
        state = reducer(state, createUser.fulfilled({ id: 'user-1', username: 'operator', role: 'user' }, 'request'));
        state = reducer(state, updateUser.fulfilled({ id: 'user-1', username: 'operator', role: 'admin' }, 'request'));
        state = reducer(state, deleteUser.fulfilled({ id: 'user-1' }, 'request'));

        expect(state).toMatchObject({
            showLogoutConfirmation: false,
            loadingAction: false,
            error: null,
            users: [],
        });
    });
});
