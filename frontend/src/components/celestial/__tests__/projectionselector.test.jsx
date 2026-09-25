/**
 * @license
 * Copyright (c) 2026 Efstratios Goudelis
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ProjectionSelector from '../projectionselector.jsx';

describe('ProjectionSelector', () => {
    it('previews snapped values and commits each side independently', () => {
        const onPastHoursChange = vi.fn();
        const onFutureHoursChange = vi.fn();

        render(
            <ProjectionSelector
                pastHours={24}
                futureHours={72}
                pastLabel="Past"
                futureLabel="Future"
                nowLabel="Now"
                onPastHoursChange={onPastHoursChange}
                onFutureHoursChange={onFutureHoursChange}
            />,
        );

        const pastSlider = screen.getByRole('slider', { name: 'Past projection' });
        const futureSlider = screen.getByRole('slider', { name: 'Future projection' });
        expect(screen.getByText('−1d')).toBeInTheDocument();
        expect(screen.getByText('+3d')).toBeInTheDocument();

        fireEvent.change(pastSlider, { target: { value: 4 } });
        fireEvent.keyUp(pastSlider);
        expect(screen.getByText('−6h')).toBeInTheDocument();
        expect(onPastHoursChange).toHaveBeenCalledWith(6);
        expect(onFutureHoursChange).not.toHaveBeenCalled();

        fireEvent.change(futureSlider, { target: { value: 5 } });
        fireEvent.keyUp(futureSlider);
        expect(screen.getByText('+14d')).toBeInTheDocument();
        expect(onFutureHoursChange).toHaveBeenCalledWith(336);
    });
});
