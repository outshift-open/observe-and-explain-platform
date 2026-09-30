/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { LineChart } from '@open-ui-kit/core';
import { ClickableDot } from '../pages/AgentDetailsPopulation/MetricsGrid/CustomDot.tsx';
import CustomChartTooltip from '../pages/AgentDetailsPopulation/MetricsGrid/CustomChartTooltip.tsx';
import { YAxisProps } from 'recharts';
import { getDisplayedResultsCountDollar } from '@/utils/stringUtils.ts';
import { Unit } from '@/types/oxp.type';
import { formatMetricValue } from '@/utils/metrics.tsx';

interface MetricLineChartProps {
  data: { date: string; [key: string]: number | string }[];
  metricKey: string;
  chartSuffix?: string;
  agentId: string;
  metricName: string;
  yAxisProps?: YAxisProps;
  lineColor?: string;
  unit?: Unit;
}

export const MetricLineChart = ({ data, metricKey, chartSuffix = '', agentId, metricName, yAxisProps, lineColor, unit }: MetricLineChartProps) => {
  const valueFormatter = (v: number | undefined) => {
    if (!v) return '';
    return formatMetricValue(v, unit ?? Unit.Scalar);
  };

  const lineChartProps = {
    data,
    categories: [{ name: metricKey, color: lineColor ?? 'red' }],
    valueFormatter,
    xAxisProps: {
      tick: false,
      label: {
        value: 'Time',
        position: 'bottomCenter',
        style: { fontSize: 12 }
      }
    },
    yAxisProps,
    lineProps: {
      activeDot: <ClickableDot agentId={agentId ?? ''} />
    },
    gridProps: { strokeDasharray: '4 4' },
    // subject: 'No. events per 5m',
    customTooltip: <CustomChartTooltip suffix={chartSuffix} metricName={metricName} unit={unit} />
  };

  return <LineChart {...lineChartProps} />;
};

export default MetricLineChart;
