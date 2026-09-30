/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@mui/material';
import { ConfidenceLevel, SessionWithMetrics, Unit } from '@/types/oxp.type';
import { SessionDistributionChart } from './SessionDistributionChart';
import { GeneralSize, Tag, TagBackgroundColorVariants } from '@open-ui-kit/core';
import { capitalizeFirstLetter } from '@/utils/stringUtils';
import { useTheme } from '@mui/material';
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from '@/common/styles';

interface MetricCardProps {
  title: string;
  normalBehavior: string;
  applicationAverage: string;
  consistency: string;
  confidence: string;
  sessionsWithMetric: SessionWithMetrics[];
  targetMetricName: string;
  outlierSessionIds: string[];
  metricUnit: Unit;
  mostImpactfulAgent: string;
  mostImpactfulAgentValue: string;
}

const confidenceColor = (confidence: ConfidenceLevel) => {
  if (confidence.toLowerCase() === ConfidenceLevel.High.toLowerCase()) return TagBackgroundColorVariants.AccentEWeak;
  if (confidence.toLowerCase() === ConfidenceLevel.Medium.toLowerCase()) return TagBackgroundColorVariants.AccentGWeak;
  return TagBackgroundColorVariants.AccentFWeak;
};

export const MetricCard = ({
  title,
  normalBehavior,
  applicationAverage,
  consistency,
  confidence,
  sessionsWithMetric,
  targetMetricName,
  outlierSessionIds,
  metricUnit,
  mostImpactfulAgent,
  mostImpactfulAgentValue
}: MetricCardProps) => {
  const theme = useTheme();
  return (
    <Stack
      direction={'column'}
      gap={'16px'}
      sx={{
        width: '328px',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        border: `1px solid ${GLOBAL_BORDER_COLOR}`,
        borderRadius: '8px',
        padding: '8px',
        color: '#F5F8FD'
      }}
    >
      <Typography variant={'h6'}>{title}</Typography>

      <Stack direction={'column'}>
        <Typography variant={'body2Semibold'}>Group Performance vs Application Avg</Typography>
        <Stack direction={'row'} gap={'2px'}>
          <Typography variant={'h6'}>{normalBehavior}</Typography>|
          <Typography variant={'h6'} sx={{ color: theme.palette.vars.excellentBackgroundDefault }}>
            {applicationAverage}
          </Typography>
        </Stack>
      </Stack>

      <Stack direction={'column'}>
        <Typography variant={'body2Semibold'}>Consistency Across Sessions</Typography>
        <Stack direction={'row'} gap={'2px'} justifyContent={'space-between'} alignItems={'center'}>
          <Typography variant={'h6'}>{consistency}</Typography>
          <Stack direction={'row'} gap={'4px'} alignItems={'center'}>
            <Typography variant={'body2'}>Confidence</Typography>
            <Tag color={confidenceColor(confidence as ConfidenceLevel)} size={GeneralSize.Small} sx={{ borderRadius: '4px' }}>
              {capitalizeFirstLetter(confidence)}
            </Tag>
          </Stack>
        </Stack>
      </Stack>

      <SessionDistributionChart
        data={sessionsWithMetric}
        targetMetricName={targetMetricName}
        outlierSessionIds={outlierSessionIds}
        metricUnit={metricUnit}
      />

      {mostImpactfulAgent && (
        <Stack direction={'column'} gap={'4px'}>
          <Typography variant={'body2Semibold'}>Agent with Highest Impact</Typography>
          <Stack
            direction={'row'}
            gap={'16px'}
            alignItems={'center'}
            sx={{ border: `1px solid #1E3A52`, borderRadius: '16px', padding: '4px 16px', width: 'fit-content' }}
          >
            <Typography variant={'body1Semibold'}>{mostImpactfulAgent}</Typography>
            <Tag color={TagBackgroundColorVariants.AccentEWeak} size={GeneralSize.Small}>
              {mostImpactfulAgentValue}
            </Tag>
          </Stack>
        </Stack>
      )}
    </Stack>
  );
};
