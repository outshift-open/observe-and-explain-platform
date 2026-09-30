/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Button, GaugeChart, Card } from '@open-ui-kit/core';
import { Box, Grid, Typography } from '@mui/material';
import { useMemo } from 'react';
import { MetricChart, WidgetCard } from '@/components';
import { TimelineData, Unit } from '@/types/oxp.type';
import { getScoreVariant, getInsightMessage } from '@/utils';
import {
  ApplicationLevelMetricCategory,
  ApplicationLevelMetricCategoryLabels,
  applicationLevelMetrics
} from '@/api/applicationLevelMetrics';
import {
  ApplicationSummaryMetrics,
  ApplicationSummaryMetricsValue,
  ApplicationSummaryQualityMetric
} from '@/types/oxp.type';
import { PATHS } from '@/routes/routes';
import { useNavigate } from 'react-router-dom';

const apiMetricNameToDefKey: Record<string, string> = {
  Groundedness: 'answerGroundedness',
  AnswerRelevancy: 'answerRelevancy',
  ResponseCompleteness: 'completeness',
  ToolUtilizationAccuracy: 'toolUtilizationAccuracy',
  IntentRecognitionAccuracy: 'intentRecognitionAccuracy',
  LLMErrorRate: 'llmErrorRate',
  ToolErrorRate: 'toolErrorRate',
  CyclesCount: 'cyclesCount',
  WorkflowEfficiency: 'workflowEfficiency',
  MetricConsistency: 'metricConsistency',
  TextConsistency: 'textConsistency',
  GraphConsistency: 'graphConsistency',
  CompletionRate: 'completionRate'
};

const scalarMetrics = new Set(['CyclesCount']);

const toTimelineData = (
  values: ApplicationSummaryMetricsValue[],
  apiMetricName: string
): TimelineData[] => {
  const isScalar = scalarMetrics.has(apiMetricName);
  return values.map(([timestamp, pointValue]) => ({
    timestamp: new Date(timestamp * 1000).toISOString(),
    sessionIDs: ['_'],
    value: isScalar
      ? { unit: Unit.Scalar, value: pointValue }
      : { unit: Unit.Percentage, value: Math.round(pointValue) }
  }));
};

interface DrawerContentProps {
  metricCategory: ApplicationLevelMetricCategory;
  applicationSummaryMetrics: ApplicationSummaryMetrics;
  aggregatedReliabilityValue?: number;
  aggregatedQualityValue?: number;
  aggregatedPerformanceValue?: number;
}
const cardGridSize = { xxl: 4, xl: 4, lg: 4, md: 4, sm: 6, xs: 12 };
const chartGridSize = { xxl: 6, xl: 12, lg: 12, md: 12, sm: 12, xs: 12 };

export const DrawerContent = ({
  metricCategory,
  applicationSummaryMetrics,
  aggregatedReliabilityValue,
  aggregatedQualityValue,
  aggregatedPerformanceValue
}: DrawerContentProps) => {
  const metricDefs = applicationLevelMetrics[metricCategory];

  const navigate = useNavigate();

  const aggregatedMetricValue = useMemo(() => {
    if (metricCategory === 'reliability') return aggregatedReliabilityValue;
    if (metricCategory === 'quality') return aggregatedQualityValue;
    if (metricCategory === 'performance') return aggregatedPerformanceValue;
    return 0;
  }, [
    metricCategory,
    aggregatedReliabilityValue,
    aggregatedQualityValue,
    aggregatedPerformanceValue
  ]);

  const chartDataMap = useMemo(() => {
    const map: Record<string, TimelineData[]> = {};

    if (metricCategory === 'quality' || metricCategory === 'performance') {
      const metrics = (applicationSummaryMetrics?.[metricCategory] ??
        []) as ApplicationSummaryQualityMetric[];
      for (const metric of metrics) {
        const defKey =
          apiMetricNameToDefKey[metric.metric_name] ?? metric.metric_name;
        map[defKey] = toTimelineData(metric.values, metric.metric_name);
      }
    }

    return map;
  }, [applicationSummaryMetrics, metricCategory]);

  const scalarValueMap = useMemo(() => {
    const map: Record<string, number> = {};

    if (metricCategory === 'reliability') {
      const metrics = applicationSummaryMetrics?.reliability ?? [];
      for (const metric of metrics) {
        const defKey = apiMetricNameToDefKey[metric.name] ?? metric.name;
        map[defKey] = metric.value;
      }
    }

    return map;
  }, [applicationSummaryMetrics, metricCategory]);

  return (
    <Stack direction={'column'} gap={'32px'} sx={{ width: '100%' }}>
      <Stack direction={'row'} gap={'32px'} alignItems={'center'}>
        <Box sx={{ marginLeft: '16px' }}>
          <GaugeChart
            data={[
              {
                name: ApplicationLevelMetricCategoryLabels[metricCategory],
                value: aggregatedMetricValue ?? 0
              }
            ]}
            variant={getScoreVariant(aggregatedMetricValue ?? 0)}
          />
        </Box>
        <Card glow>
          <Typography variant={'body2'}>
            {getInsightMessage(aggregatedMetricValue ?? 0, metricCategory)}
          </Typography>
        </Card>
      </Stack>
      <Grid container spacing={'16px'}>
        {metricCategory === 'reliability'
          ? Object.entries(metricDefs).map(([key, def]) => (
              <Grid size={cardGridSize} key={key}>
                <WidgetCard
                  title={def.name}
                  description={def.description}
                  content={
                    <Typography variant={'h6'}>
                      {Math.round((scalarValueMap[key] ?? 0) * 100)}%
                    </Typography>
                  }
                />
              </Grid>
            ))
          : Object.entries(metricDefs).map(([key, def]) => (
              <Grid size={chartGridSize} key={key}>
                <MetricChart
                  data={chartDataMap[key] ?? []}
                  metricKey={key}
                  metricDef={def}
                  chartSuffix={''}
                  operation={def.operation ?? 'average'}
                />
              </Grid>
            ))}
      </Grid>

      <Stack direction="row" justifyContent="flex-end">
        <Button
          variant="gradient"
          size="small"
          onClick={() => {
            navigate(
              PATHS.applicationAnalyze.replace(
                ':applicationId',
                applicationSummaryMetrics.applicationName ?? ''
              )
            );
          }}
        >
          Learn More
        </Button>
      </Stack>
    </Stack>
  );
};
