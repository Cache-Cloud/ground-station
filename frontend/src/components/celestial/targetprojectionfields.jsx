import React from 'react';
import {
    Box,
    Divider,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Typography,
} from '@mui/material';
import ScheduleRoundedIcon from '@mui/icons-material/ScheduleRounded';
import { useTranslation } from 'react-i18next';
import ProjectionSelector from './projectionselector.jsx';

export const TARGET_PROJECTION_PAST_OPTIONS = [1, 6, 12, 24, 72, 168];
export const TARGET_PROJECTION_FUTURE_OPTIONS = [1, 6, 12, 24, 72, 168, 336, 720];
export const TARGET_PROJECTION_STEP_OPTIONS = [5, 10, 15, 30, 60, 120, 360, 720, 1440];

const formatHourOption = (value) => ({
    value,
    label: value >= 24 && value % 24 === 0 ? `${value / 24}d` : `${value}h`,
});

const TARGET_PROJECTION_PAST_SLIDER_OPTIONS = TARGET_PROJECTION_PAST_OPTIONS.map(formatHourOption);
const TARGET_PROJECTION_FUTURE_SLIDER_OPTIONS = TARGET_PROJECTION_FUTURE_OPTIONS.map(formatHourOption);

const TargetProjectionFields = ({
    values,
    onChange,
    disabled = false,
    showHeading = false,
    idPrefix = 'target-projection',
}) => {
    const { t } = useTranslation('celestial');
    const fields = [
        {
            key: 'projectionPastHours',
            label: t('monitored.projection.past', { defaultValue: 'Past duration' }),
            options: TARGET_PROJECTION_PAST_OPTIONS,
            suffix: 'h',
        },
        {
            key: 'projectionFutureHours',
            label: t('monitored.projection.future', { defaultValue: 'Future duration' }),
            options: TARGET_PROJECTION_FUTURE_OPTIONS,
            suffix: 'h',
        },
        {
            key: 'projectionStepMinutes',
            label: t('monitored.projection.step', { defaultValue: 'Sample interval' }),
            options: TARGET_PROJECTION_STEP_OPTIONS,
            suffix: 'm',
        },
    ];

    return (
        <Box
            sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
                bgcolor: 'action.hover',
                p: 2,
            }}
        >
            <Stack direction="row" spacing={1.25} alignItems="flex-start" sx={{ mb: 2 }}>
                <Box
                    sx={{
                        display: 'grid',
                        placeItems: 'center',
                        width: 34,
                        height: 34,
                        borderRadius: '50%',
                        bgcolor: 'primary.main',
                        color: 'primary.contrastText',
                        flexShrink: 0,
                    }}
                >
                    <ScheduleRoundedIcon fontSize="small" />
                </Box>
                <Box>
                    <Typography variant={showHeading ? 'subtitle1' : 'subtitle2'} sx={{ fontWeight: 700 }}>
                        {t('monitored.projection.title', { defaultValue: 'Time projection' })}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        {t('monitored.projection.description', {
                            defaultValue: 'Choose how far to calculate before and after now.',
                        })}
                    </Typography>
                </Box>
            </Stack>

            <ProjectionSelector
                pastHours={values?.projectionPastHours}
                futureHours={values?.projectionFutureHours}
                pastLabel={t('topbar.projection.past')}
                futureLabel={t('topbar.projection.future')}
                nowLabel={t('topbar.projection.now')}
                disabled={disabled}
                pastOptions={TARGET_PROJECTION_PAST_SLIDER_OPTIONS}
                futureOptions={TARGET_PROJECTION_FUTURE_SLIDER_OPTIONS}
                onPastHoursChange={(value) => onChange?.('projectionPastHours', value)}
                onFutureHoursChange={(value) => onChange?.('projectionFutureHours', value)}
            />

            <Divider sx={{ my: 2 }} />
            <Typography
                variant="overline"
                color="text.secondary"
                sx={{ display: 'block', mb: 1, lineHeight: 1.2, letterSpacing: '0.08em' }}
            >
                {t('monitored.projection.exact_settings', { defaultValue: 'Exact settings' })}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
                {fields.map((field) => (
                    <FormControl key={field.key} fullWidth size="small">
                        <InputLabel id={`${idPrefix}-${field.key}-label`}>{field.label}</InputLabel>
                        <Select
                            labelId={`${idPrefix}-${field.key}-label`}
                            value={values?.[field.key]}
                            label={field.label}
                            disabled={disabled}
                            onChange={(event) => onChange?.(field.key, Number(event.target.value))}
                        >
                            {field.options.map((value) => (
                                <MenuItem key={value} value={value}>{value}{field.suffix}</MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                ))}
            </Stack>
            <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1.5, mb: 0 }}>
                {t('monitored.projection.help', {
                    defaultValue: 'Smaller intervals produce denser paths. Very long windows are capped at 1,000 samples.',
                })}
            </Typography>
        </Box>
    );
};

export default TargetProjectionFields;
