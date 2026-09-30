/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography, Box } from '@open-ui-kit/core';
import type { YAxisProps } from 'recharts';
import { useTheme, SxProps } from '@mui/material';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { formatDurationMs, formatTwoDecimals, getDisplayedResultsCount, getDisplayedResultsCountDollar } from '@/utils';
import MetricLineChart from '@/components/MetricLineChart';
import { TimelineData, Unit } from '@/types/oxp.type';
import { Operation } from '@/api/metrics';
import { CustomTooltip } from './CustomTooltip';
import { formatMetricValue, getResultCount, getScoreColor } from '@/utils/metrics';
import { unitSuffix } from '@/common/constants';

export interface MetricChartProps {
  data: TimelineData[];
  metricKey: string;
  metricDef: {
    name: string;
    description?: string;
  };
  chartSuffix: string;
  operation: Operation;
  containerSx?: SxProps;
}

export const MetricChart = ({ data, metricKey, metricDef, chartSuffix, operation, containerSx }: MetricChartProps) => {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chartHeight, setChartHeight] = useState<number>(150);

  const unit = data?.[0]?.value?.unit ?? Unit.Scalar;
  const isPercentage = unit === Unit.Percentage;

  chartSuffix = chartSuffix ? chartSuffix : unitSuffix[unit];

  // Reserve space at left for long tick labels based on unit
  const yAxisWidth = isPercentage ? 40 : unit === Unit.Dollar ? 72 : 56;
  const yAxisProps: YAxisProps = isPercentage
    ? {
        domain: [0, 100],
        tickFormatter: (v: number) => `${v}%`,
        width: yAxisWidth,
        tickMargin: 8
      }
    : {
        domain: ([, dataMax]: [number, number]) => [0, dataMax > 0 ? dataMax : 1],
        width: yAxisWidth,
        tickMargin: 8
      };

  const chartData = data.map((item) => ({
    date: item.timestamp,
    [metricKey]: isPercentage ? Math.round(item.value.value * 100) : item.value.value
  }));

  // Measure container height and compute the chart area height below the header
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const headerApprox = 92; // title + value + paddings

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      const h = entry.contentRect.height;
      const computed = Math.max(120, Math.floor(h - headerApprox));
      setChartHeight(computed);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const resultCount = useMemo(() => getResultCount(data, operation), [data, operation]);

  const getLineColor = () => {
    if (unit === Unit.Percentage) {
      return getScoreColor(Number(resultCount * 100), theme);
    }
    return;
  };

  return (
    <Stack
      direction={'column'}
      gap={'16px'}
      sx={{
        borderRadius: '8px',
        backgroundColor: theme.palette.vars.baseBackgroundWeak,
        height: '100%',
        minHeight: 160,
        // allow parent to override and enable full-size in GridStack
        ...containerSx
      }}
      ref={containerRef}
    >
      <Stack direction={'column'} sx={{ marginLeft: '8px' }}>
        <Stack direction={'row'} alignItems={'center'} sx={{ margin: '16px 0 0 0' }} gap={'8px'}>
          <Typography variant={'captionSemibold'}>{metricDef.name}</Typography>
          {metricDef.description && (
            <CustomTooltip title={metricDef.description} placement={'top'} sx={{ maxWidth: '500px' }}>
              <InfoOutlineIcon sx={{ width: '16px', height: '16px', cursor: 'pointer' }} />
            </CustomTooltip>
          )}
        </Stack>

        <Typography variant={'h6'} sx={{ textAlign: 'left' }}>
          {formatMetricValue(resultCount, unit)}
        </Typography>
      </Stack>

      <Box sx={{ width: '100%', flex: 1, minHeight: 0 }}>
        <Stack
          direction={'column'}
          gap={'16px'}
          sx={{
            flex: 1,
            minHeight: `${chartHeight}px`,
            height: `${chartHeight}px`,
            padding: '0 24px 0 0',
            width: '100%',
            marginLeft: '8px'
          }}
        >
          <MetricLineChart
            data={chartData}
            metricKey={metricKey}
            chartSuffix={chartSuffix}
            agentId={''}
            metricName={metricDef.name}
            yAxisProps={yAxisProps}
            lineColor={getLineColor()}
            unit={unit}
          />
        </Stack>
      </Box>
    </Stack>
  );
};

export default MetricChart;
