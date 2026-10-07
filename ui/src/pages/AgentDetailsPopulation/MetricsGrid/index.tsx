/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack } from '@open-ui-kit/core';
import { Grid, Typography } from '@mui/material';
import { metrics } from '@/api/metrics.ts';
import { MetricChart, WidgetCard } from '@/components';
import { SingleValueData, TimelineData, Unit } from '@/types/oxp.type';
import {
  ApplicationCostCharts,
  ApplicationGeneralCharts,
  ApplicationPerformanceCharts,
  ApplicationQualityAndReasoningCharts,
  ApplicationReliabilityAndSafetyCharts,
  ApplicationConversationCharts,
  ApplicationLlmCharts
} from '@/types/agentCharts.type';
import { unitSuffix } from '@/common';

interface MetricsGridProps {
  metricsData: Partial<
    | Omit<ApplicationGeneralCharts, '__typename'>
    | Omit<ApplicationCostCharts, '__typename'>
    | Omit<ApplicationPerformanceCharts, '__typename'>
    | Omit<ApplicationQualityAndReasoningCharts, '__typename'>
    | Omit<ApplicationReliabilityAndSafetyCharts, '__typename'>
    | Omit<ApplicationConversationCharts, '__typename'>
    | Omit<ApplicationLlmCharts, '__typename'>
  >;
  category: string;
  agentId: string;
}

const size = { xxl: 2, xl: 3, lg: 4, md: 4 };

const MetricsGrid = ({ metricsData, category, agentId }: MetricsGridProps) => {
  // const generateMetricCardValue = (metricKey: string) => {

  //   if (metricKey.toLowerCase().includes('score')) {
  //     return Math.floor(Math.random() * 101);
  //   }

  //   if (metricKey.toLowerCase().includes('latency')) {
  //     return Math.floor(Math.random() * 101) + 'ms';
  //   }
  //   return Math.floor(Math.random() * 101) + '%';
  // };

  return (
    <Stack direction={'column'} gap={'16px'}>
      {/*<MetricsGrid />*/}
      <Grid container spacing={'16px'}>
        {Object.entries(metrics[category])
          .filter(([metricKey, metricDef]) => metricDef.isCard)
          .map(([metricKey, metricDef]) => {
            const card = (metricsData as any)?.[metricKey] as SingleValueData;
            const cardValue = card?.value;
            const cardSuffix = card?.unit ? (unitSuffix[card.unit] ?? '') : '';
            let displayValue: string | number = '';

            if (typeof cardValue === 'number' && Number.isFinite(cardValue)) {
              if (metricDef.isRounded) {
                displayValue = Math.round(cardValue).toString();
              } else {
                const valueToTwoDecimals = Number(cardValue.toFixed(2));
                displayValue = valueToTwoDecimals.toString(); // remove trailing zeros
              }
            } else {
              displayValue = cardValue ?? '';
            }

            return (
              <Grid size={size}>
                <WidgetCard
                  title={metricDef.name}
                  description={metricDef.description}
                  content={
                    <Typography variant="h5">{`${displayValue}${displayValue ? cardSuffix : '0'}`}</Typography>
                  }
                  cardSx={{ width: '100%' }}
                />
              </Grid>
            );
          })}
      </Grid>
      <Grid container spacing={'16px'}>
        {Object.entries(metrics[category])
          .filter(([metricKey, metricDef]) => !metricDef.isCard)
          .map(([metricKey, metricDef]) => {
            let chartSuffix = '';

            if ((metricsData as any)[metricKey]) {
              const dataArray = (metricsData as any)[
                metricKey
              ] as TimelineData[];
              const unit = dataArray?.[0]?.value?.unit as Unit | undefined;
              chartSuffix = unit ? (unitSuffix[unit] ?? '') : '';
            }

            return (
              <Grid size={size}>
                <MetricChart
                  data={(metricsData as any)[metricKey] ?? []}
                  metricKey={metricKey}
                  metricDef={metricDef}
                  chartSuffix={chartSuffix}
                  operation={'average'}
                />
              </Grid>
            );
          })}
      </Grid>
    </Stack>
  );
};

export default MetricsGrid;
