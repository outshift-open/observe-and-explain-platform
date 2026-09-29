/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useMemo, useState } from 'react';
import { Chart } from '@antv/g2';
import { Box, Stack, Typography } from '@mui/material';
import { CostEfficiencyGrouppedSessions } from '@/types/oxp.type';
import { formatTwoDecimals } from '@/utils/stringUtils';
import {
  SemanticGroupOption,
  useSingleSemanticGroupSelector,
  SingleSemanticGroupSelectorDropdown
} from '@/components/SemanticGroupSelector';
import { CostEfficiencyRangeFilter } from '@/components/CostEfficiencyRangeFilter';
import { buildColorMap } from '@/utils/chartUtils';
import { CustomTooltip } from '../CustomTooltip';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { EmptyState } from '@open-ui-kit/core';

const formatTimestamp = (timestamp: number): string => {
  const ms = timestamp * 1000;
  return new Date(ms).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

interface SessionsCostEfficiencyDistributionProps {
  data: CostEfficiencyGrouppedSessions[];
  allGroups: SemanticGroupOption[];
}

const CHART_WIDTH = 800;

export const SessionsCostEfficiencyDistribution = ({
  data,
  allGroups
}: SessionsCostEfficiencyDistributionProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const selectorState = useSingleSemanticGroupSelector(allGroups);

  const dataRange = useMemo(() => {
    if (!data || data.length === 0) return { min: 0, max: 0 };
    let min = Infinity;
    let max = -Infinity;
    for (const item of data) {
      if (item.costEfficiency < min) min = item.costEfficiency;
      if (item.costEfficiency > max) max = item.costEfficiency;
    }
    return { min: parseFloat(min.toFixed(2)), max: parseFloat(max.toFixed(2)) };
  }, [data]);

  const [minCE, setMinCE] = useState(0);
  const [maxCE, setMaxCE] = useState(0);

  // Initialize min/max from data range
  useEffect(() => {
    if (dataRange.min !== 0 || dataRange.max !== 0) {
      setMinCE(dataRange.min);
      setMaxCE(dataRange.max);
    }
  }, [dataRange]);

  const colorMap = useMemo(() => buildColorMap(allGroups), [allGroups]);

  const chartData = useMemo(() => {
    if (
      data.length === 0 ||
      allGroups.length === 0 ||
      !selectorState.selectedGroupId
    )
      return [];

    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));

    return data
      .filter(
        (item) =>
          item.groupId === selectorState.selectedGroupId &&
          groupMap.has(item.groupId) &&
          // margin of error to avoid floating point precision issues
          item.costEfficiency >= minCE - 0.01 &&
          item.costEfficiency <= maxCE + 0.01
      )
      .map((item) => ({
        group: groupMap.get(item.groupId)!,
        startTime: item.startTime,
        costEfficiency: item.costEfficiency,
        sessionId: item.sessionId
      }));
  }, [data, allGroups, selectorState.selectedGroupId, minCE, maxCE]);

  useEffect(() => {
    if (!containerRef.current || chartData.length === 0) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const chart = new Chart({
      container: containerRef.current,
      width: CHART_WIDTH,
      autoFit: true,
      paddingLeft: 60,
      paddingRight: 0
    });

    chart
      .point()
      .data(chartData)
      .encode('x', 'startTime')
      .encode('y', 'costEfficiency')
      .encode('color', 'group')
      .encode('shape', 'point')
      .scale('x', { type: 'linear' })
      .scale('y', { nice: true })
      .scale('color', { domain: colorMap.domain, range: colorMap.range })
      .axis('x', {
        title: 'Timestamp',
        label: false,
        style: { titleFill: '#ffffff' }
      })
      .axis('y', {
        title: 'Cost Efficiency',
        style: { titleFill: '#ffffff', labelFill: '#ffffff' }
      })
      .tooltip({
        title: 'group',
        items: [
          {
            field: 'costEfficiency',
            name: 'Cost Efficiency',
            valueFormatter: (val: number) => formatTwoDecimals(val)
          },
          { field: 'sessionId', name: 'Session' },
          {
            field: 'startTime',
            name: 'Start Time',
            valueFormatter: (val: number) => formatTimestamp(val)
          }
        ]
      })
      .legend(false)
      .style({
        size: 4,
        fillOpacity: 0.7,
        stroke: 'transparent'
      });

    chart.render();
    chartRef.current = chart;

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [chartData]);

  if (data.length === 0) {
    return (
      <Stack direction="column" gap="12px">
        <SectionHeader />
        <EmptyState title="No data found" description="" />
      </Stack>
    );
  }

  return (
    <Stack direction="column" gap="12px">
      <SectionHeader />
      <Stack direction="row" alignItems="center" gap="12px">
        <SingleSemanticGroupSelectorDropdown {...selectorState} />
        <CostEfficiencyRangeFilter
          min={minCE}
          max={maxCE}
          onMinChange={setMinCE}
          onMaxChange={setMaxCE}
        />
      </Stack>
      <Box
        ref={containerRef}
        sx={{
          width: CHART_WIDTH,
          height: 400
        }}
      />
    </Stack>
  );
};

const SECTION_TITLE = 'Cost Efficiency Distribution by Sessions';
const SECTION_TOOLTIP =
  'Scatter plot of cost efficiency scores for individual sessions within a selected topic. ' +
  'Use the topic selector to pick a group, ' +
  'and the cost efficiency range filter to narrow sessions to a specific score range.';

const SectionHeader = () => (
  <Stack direction="row" alignItems="flex-start" gap="4px">
    <Typography variant="h6">{SECTION_TITLE}</Typography>
    <CustomTooltip
      title={SECTION_TOOLTIP}
      placement="top"
      sx={{ maxWidth: '550px' }}
    >
      <InfoOutlineIcon
        sx={{ width: '16px', height: '16px', cursor: 'pointer' }}
      />
    </CustomTooltip>
  </Stack>
);
