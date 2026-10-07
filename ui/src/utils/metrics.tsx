/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { SingleValueData, TimelineData, Unit } from '@/types/oxp.type';
import {
  formatDurationMs,
  formatTwoDecimals,
  getDisplayedResultsCount,
  getDisplayedResultsCountDollar
} from './stringUtils';
import { Operation } from '@/api/metrics';
import { Theme } from '@mui/material/styles';
import {
  ApplicationSummaryQualityMetric,
  ApplicationSummaryReliabilityMetric
} from '@/types/oxp.type';
import { Stack, Typography } from '@mui/material';
import { unitSuffix } from '@/common/constants';
import { metricCatalog, SemanticGroupMetric } from '@/common';

export const generateLineData = (
  name: string
): { date: string; [key: string]: number | string }[] => {
  const count = 25;
  const stepMs = 5 * 60 * 1000;

  const startTimeMs = new Date().getTime();

  const data = Array.from({ length: count }, (_, i) => {
    const date = new Date(startTimeMs + i * stepMs).toISOString();
    return {
      date,
      [name]: parseFloat((Math.random() * 10).toFixed(1))
    };
  });

  return data;
};

// Generate random TimelineData[] for testing charts that expect GraphQL-shaped data
export const generateTimelineData = (
  count: number = 25,
  magnitude: number = 10,
  startTimeMs?: number
): TimelineData[] => {
  const nowMs = new Date().getTime();
  const startMs = startTimeMs ?? nowMs;
  const stepMs = 5 * 60 * 1000;

  const data: TimelineData[] = Array.from({ length: count }, (_, i) => {
    const timestamp = new Date(startMs + i * stepMs).toISOString();
    const randomValue = parseFloat((Math.random() * magnitude).toFixed(2));
    return {
      __typename: 'TimelineData',
      sessionIDs: [],
      timestamp,
      value: {
        __typename: 'SingleValueData',
        unit: Unit.Scalar,
        value: randomValue
      }
    };
  });

  return data;
};

const computeSum = (data: TimelineData[]) => {
  return data.reduce((acc, curr) => acc + curr.value.value, 0);
};

const computeAverage = (data: TimelineData[]) => {
  const dataWithSessions = data.filter((item) => item.sessionIDs.length > 0);

  if (dataWithSessions.length === 0) {
    return 0;
  }

  return (
    dataWithSessions.reduce((acc, curr) => acc + curr.value.value, 0) /
    dataWithSessions.length
  );
};

export const getResultCount = (data: TimelineData[], operation: Operation) => {
  return operation === 'sum' ? computeSum(data) : computeAverage(data);
};

export const getScoreColor = (score: number, theme: Theme): string => {
  if (score >= 85) {
    return theme.palette.vars.successIconDefault;
  }
  if (score >= 50) {
    return theme.palette.vars.severeWarningIconDefault;
  }
  return theme.palette.vars.negativeIconDefault;
};

export const getScoreVariant = (score: number): 'teal' | 'amber' | 'blue' => {
  if (score >= 85) return 'teal';
  if (score >= 50) return 'blue';
  return 'amber';
};

export const computeOverallQuality = (
  quality: ApplicationSummaryQualityMetric[]
): number => {
  if (quality.length === 0) return 0;

  const metricAverages = quality.map((metric) => {
    const values = metric.values ?? [];
    if (values.length === 0) return 0;
    const sum = values.reduce((acc, [, pointValue]) => acc + pointValue, 0);
    return sum / values.length;
  });

  const overallAvg =
    metricAverages.reduce((acc, avg) => acc + avg, 0) / metricAverages.length;
  return Math.round(overallAvg * 100);
};

export const computeOverallReliability = (
  reliability: ApplicationSummaryReliabilityMetric[]
): number => {
  if (reliability.length === 0) return 0;

  const sum = reliability.reduce((acc, entry) => acc + entry.value, 0);
  return Math.round((sum / reliability.length) * 100);
};

export const computeOverallPerformance = (
  performance: ApplicationSummaryQualityMetric[]
): number => {
  if (performance.length === 0) return 0;

  const avgByName: Record<string, number> = {};
  for (const metric of performance) {
    const values = metric.values ?? [];
    if (values.length === 0) {
      avgByName[metric.metric_name] = 0;
      continue;
    }
    avgByName[metric.metric_name] =
      values.reduce((acc, [, v]) => acc + v, 0) / values.length;
  }

  const llmErr = avgByName['LLMErrorRate'] ?? 0;
  const toolErr = avgByName['ToolErrorRate'] ?? 0;
  const wfEff = avgByName['WorkflowEfficiency'] ?? 0;
  const cycles = avgByName['CyclesCount'] ?? 0;

  const score = (1 - llmErr + (1 - toolErr) + wfEff + 1 / (1 + cycles)) / 4;
  return Math.round(score * 100);
};

export type MetricPulseScore = 'success' | 'warning' | 'fatal';

export const getMetricPulseColor = (
  score: MetricPulseScore,
  theme: Theme
): string => {
  switch (score) {
    case 'success':
      return theme.palette.vars.successIconDefault;
    case 'warning':
      return theme.palette.vars.warningIconDefault;
    case 'fatal':
      return theme.palette.vars.negativeIconDefault;
  }
  return theme.palette.vars.successIconDefault;
};

type InsightCategory = 'reliability' | 'quality' | 'performance';

const insightMessages: Record<
  InsightCategory,
  Record<'high' | 'medium' | 'low', [string, string]>
> = {
  reliability: {
    high: [
      'Consistent outputs and high completion rate.',
      'Workflows follow stable, repeatable paths.'
    ],
    medium: [
      'Some inconsistencies in responses or paths.',
      'Review text and graph consistency metrics.'
    ],
    low: [
      'Low consistency or completion rate detected.',
      'Investigate metric, text, and graph stability.'
    ]
  },
  quality: {
    high: [
      'Responses are grounded, relevant, and complete.',
      'Intent recognition and tool usage are accurate.'
    ],
    medium: [
      'Minor gaps in relevancy or groundedness.',
      'Consider inspecting semantics groups for more information.'
    ],
    low: [
      'Quality issues across multiple metrics.',
      'Review groundedness, relevancy, and intent accuracy.'
    ]
  },
  performance: {
    high: [
      'Low error rates and efficient workflows.',
      'Minimal redundant cycles detected.'
    ],
    medium: [
      'Moderate LLM or tool errors observed.',
      'Check for unnecessary cycles and workflow steps.'
    ],
    low: [
      'High error rates or workflow inefficiencies.',
      'Reduce LLM/tool errors and optimize cycle count.'
    ]
  }
};

export const getInsightMessage = (
  score: number,
  category: InsightCategory = 'reliability'
) => {
  const tier = score >= 85 ? 'high' : score >= 50 ? 'medium' : 'low';
  const [line1, line2] = insightMessages[category][tier];

  return (
    <Stack direction={'column'} alignItems={'center'} gap={0}>
      <Typography variant={'captionSemibold'}>{line1}</Typography>
      <Typography variant={'captionSemibold'}>{line2}</Typography>
    </Stack>
  );
};

export const formatMetricValue = (value: number, unit: Unit) => {
  let formattedValue: string | number = '';

  switch (unit) {
    case Unit.Milliseconds:
      formattedValue = `${formatDurationMs(Number(value))}`;
      break;
    case Unit.Dollar:
      formattedValue = `${formatTwoDecimals(Number(value))}${unitSuffix[unit]}`;
      break;
    case Unit.Percentage:
      const tmpMetricValue = Number(value) * 100;
      if (tmpMetricValue === 100) {
        formattedValue = '100%';
      } else if (tmpMetricValue === 0) {
        formattedValue = '0%';
      } else {
        formattedValue = `${formatTwoDecimals(tmpMetricValue)}%`;
      }
      break;
    default:
      formattedValue = `${formatTwoDecimals(value)} ${unitSuffix[unit]}`;
      break;
  }
  return formattedValue;
};

// Percentages are shown as whole numbers (e.g. 82%); other units keep the
// default formatting.
export const formatRoundedMetricValue = ({
  value,
  unit
}: SingleValueData): string =>
  unit === Unit.Percentage
    ? `${Math.round(Number(value) * 100)}%`
    : String(formatMetricValue(value, unit));

export const formatMetricValueLineChartTooltip = (
  value: number,
  unit: Unit
) => {
  let formattedValue: string | number = '';

  switch (unit) {
    case Unit.Milliseconds:
      formattedValue = `${formatDurationMs(Number(value))}`;
      break;
    case Unit.Dollar:
      formattedValue = `${formatTwoDecimals(Number(value))}${unitSuffix[unit]}`;
      break;
    case Unit.Percentage:
      const tmpMetricValue = Number(value);
      if (tmpMetricValue === 100) {
        formattedValue = '100%';
      } else if (tmpMetricValue === 0) {
        formattedValue = '0%';
      } else {
        formattedValue = `${formatTwoDecimals(tmpMetricValue)}%`;
      }
      break;
    default:
      formattedValue = `${formatTwoDecimals(value)} ${unitSuffix[unit]}`;
      break;
  }
  return formattedValue;
};

export const findMetricCatalogEntry = (
  key: string
): SemanticGroupMetric | undefined => {
  const entry = Object.entries(metricCatalog).find(
    ([k]) => k.toLowerCase() === key.toLowerCase()
  );
  return entry ? entry[1] : undefined;
};
