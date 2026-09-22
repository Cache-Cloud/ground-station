import { describe, expect, it } from 'vitest';
import { getNavigation } from './navigation.jsx';

describe('administration navigation', () => {
    it('groups satellite and celestial pages under their domain parents', () => {
        const navigation = getNavigation({ isAdmin: true });
        const satelliteData = navigation.find((item) => item.segment === 'admin/satellites');
        const celestialData = navigation.find((item) => item.segment === 'admin/celestial');

        expect(satelliteData.children.map((item) => item.segment)).toEqual([
            'sources',
            'catalog',
            'groups',
        ]);
        expect(celestialData.children.map((item) => item.segment)).toEqual([
            'ephemeris',
            'catalog',
            'targets',
        ]);
        expect(navigation.some((item) => item.segment === 'admin/satellites/catalog')).toBe(false);
        expect(navigation.some((item) => item.segment === 'admin/celestial/catalog')).toBe(false);
    });

    it('does not expose administration groups to non-admin users', () => {
        const navigation = getNavigation({ isAdmin: false });

        expect(navigation.some((item) => item.segment === 'admin/satellites')).toBe(false);
        expect(navigation.some((item) => item.segment === 'admin/celestial')).toBe(false);
    });
});
