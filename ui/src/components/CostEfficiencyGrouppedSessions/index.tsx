/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useMemo, useState } from 'react';
import { Chart } from '@antv/g2';
import { Box, Stack, Typography } from '@mui/material';
import { CostEfficiencyGrouppedSessions as CostEfficiencyGrouppedSessionsType } from '@/types/oxp.type';
import { formatTwoDecimals } from '@/utils/stringUtils';
import {
  SemanticGroupOption,
  useMultiSemanticGroupSelector,
  MultiSemanticGroupSelectorDropdown
} from '@/components/SemanticGroupSelector';
import { CostEfficiencyRangeFilter } from '@/components/CostEfficiencyRangeFilter';
import { buildColorMap } from '@/utils/chartUtils';
import { CustomTooltip } from '../CustomTooltip';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { CostEfficiencySummary } from './CostEfficiencySummary';
import { EmptyState } from '@open-ui-kit/core';

const MAX_VISIBLE_WIDTH = 850;
const WIDTH_PER_GROUP = 60;
const CHART_HEIGHT = 400;

interface CostEfficiencyGrouppedSessionsProps {
  data: CostEfficiencyGrouppedSessionsType[];
  allGroups: SemanticGroupOption[];
}

export const CostEfficiencyGrouppedSessions = ({
  data,
  allGroups
}: CostEfficiencyGrouppedSessionsProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const selectorState = useMultiSemanticGroupSelector(allGroups);

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

  // Compute min and max costEfficiency per group (from selected groups only)
  const { maxCEByGroup, minCEByGroup } = useMemo(() => {
    if (!data || data.length === 0 || allGroups.length === 0)
      return {
        maxCEByGroup: new Map<string, number>(),
        minCEByGroup: new Map<string, number>()
      };

    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));
    const maxResult = new Map<string, number>();
    const minResult = new Map<string, number>();

    for (const item of data) {
      if (
        !selectorState.selectedGroupIds.has(item.groupId) ||
        !groupMap.has(item.groupId)
      )
        continue;
      const label = groupMap.get(item.groupId)!;
      const curMax = maxResult.get(label) ?? -Infinity;
      if (item.costEfficiency > curMax)
        maxResult.set(label, item.costEfficiency);
      const curMin = minResult.get(label) ?? Infinity;
      if (item.costEfficiency < curMin)
        minResult.set(label, item.costEfficiency);
    }
    return { maxCEByGroup: maxResult, minCEByGroup: minResult };
  }, [data, allGroups, selectorState.selectedGroupIds]);

  // Filter chart data: only groups whose max CE is within [minCE, maxCE]
  const chartData = useMemo(() => {
    if (!data || data.length === 0 || allGroups.length === 0) return [];

    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));
    const qualifyingGroups = new Set<string>();

    for (const [label, groupMax] of maxCEByGroup) {
      const groupMin = minCEByGroup.get(label) ?? groupMax;
      if (groupMin >= minCE - 0.01 && groupMax <= maxCE + 0.01) {
        qualifyingGroups.add(label);
      }
    }

    return data
      .filter(
        (item) =>
          selectorState.selectedGroupIds.has(item.groupId) &&
          groupMap.has(item.groupId) &&
          qualifyingGroups.has(groupMap.get(item.groupId)!)
      )
      .map((item) => ({
        group: groupMap.get(item.groupId)!,
        costEfficiency: item.costEfficiency
      }));
  }, [
    data,
    allGroups,
    selectorState.selectedGroupIds,
    maxCEByGroup,
    minCE,
    maxCE
  ]);

  // FOR DEBUGGING: Log groups with all sessions costEfficiency < threshold
  const COST_EFFICIENCY_THRESHOLD = 1;
  useMemo(() => {
    const maxByGroup = new Map<string, number>();
    for (const d of chartData) {
      const cur = maxByGroup.get(d.group) ?? -Infinity;
      if (d.costEfficiency > cur) maxByGroup.set(d.group, d.costEfficiency);
    }
    const belowThreshold = [...maxByGroup.entries()]
      .filter(([, max]) => max < COST_EFFICIENCY_THRESHOLD)
      .map(([group, max]) => ({ group, max }));
    if (belowThreshold.length > 0) {
      console.log(
        `Groups with all sessions costEfficiency < ${COST_EFFICIENCY_THRESHOLD}:`,
        belowThreshold
      );
    }
  }, [chartData]);
  // END OF DEBUGGING

  // Sort groups left-to-right by their median costEfficiency value (descending)
  const groupOrder = useMemo(() => {
    const valuesByGroup = new Map<string, number[]>();
    for (const d of chartData) {
      const arr = valuesByGroup.get(d.group) ?? [];
      arr.push(d.costEfficiency);
      valuesByGroup.set(d.group, arr);
    }
    const medianByGroup = new Map<string, number>();
    for (const [group, values] of valuesByGroup) {
      values.sort((a, b) => a - b);
      const mid = Math.floor(values.length / 2);
      const median =
        values.length % 2 === 0
          ? (values[mid - 1] + values[mid]) / 2
          : values[mid];
      medianByGroup.set(group, median);
    }
    return [...medianByGroup.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([group]) => group);
  }, [chartData]);

  const colorMap = useMemo(() => buildColorMap(allGroups), [allGroups]);

  const chartWidth = Math.max(
    MAX_VISIBLE_WIDTH,
    groupOrder.length * WIDTH_PER_GROUP
  );

  useEffect(() => {
    if (!containerRef.current || chartData.length === 0) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const chart = new Chart({
      container: containerRef.current,
      width: chartWidth,
      height: CHART_HEIGHT,
      autoFit: false,
      paddingLeft: 60,
      paddingRight: 0,
      paddingBottom: 160
    });

    chart
      .boxplot()
      .data(chartData)
      .encode('x', 'group')
      .encode('y', 'costEfficiency')
      .encode('color', 'group')
      .scale('x', { domain: groupOrder, paddingInner: 0.6, paddingOuter: 0.3 })
      .scale('y', { nice: true })
      .scale('color', { domain: colorMap.domain, range: colorMap.range })
      .axis('x', {
        labelAutoRotate: false,
        labelAutoHide: false,
        title: false,
        line: true,
        style: {
          labelFill: '#ffffff',
          labelFontSize: 11,
          labelTransform: 'rotate(-45)',
          lineStroke: '#ffffff',
          lineStrokeOpacity: 0.15,
          lineLineWidth: 1
        }
      })
      .axis('y', {
        title: 'Cost Efficiency',
        style: { titleFill: '#ffffff', labelFill: '#ffffff' }
      })
      .interaction('tooltip', {
        css: {
          '.g2-tooltip': {
            transform: 'translateY(80px) !important'
          }
        },
        render: (
          _event: unknown,
          {
            title,
            items
          }: { title: string; items: Array<{ name: string; value: unknown }> }
        ) => {
          const fmt = (v: unknown) =>
            typeof v === 'number' ? formatTwoDecimals(v) : v;
          const rows = items
            .map(
              (item) =>
                `<div style="display:flex;align-items:center;gap:8px"><span style="width:6px;height:6px;border-radius:50%;background:${(item as unknown as { color: string }).color || '#3A95FF'};flex-shrink:0"></span><span style="flex:1">${item.name}</span><span>${fmt(item.value)}</span></div>`
            )
            .join('');
          return `<div style="padding:8px 12px;font-size:12px"><div style="margin-bottom:4px;font-weight:600">${title}</div>${rows}</div>`;
        }
      })
      .legend(false)
      .style({
        boxFill: '#3A95FF',
        boxFillOpacity: 0.4,
        boxStroke: '#8EC6FF',
        boxLineWidth: 0.1,
        stroke: '#fff',
        lineWidth: 0.5,
        point: false
      });

    chart.render();
    chartRef.current = chart;

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [chartData, chartWidth, groupOrder]);

  if (data.length === 0) {
    return (
      <Stack direction="column" gap="12px">
        <SectionHeader />
        <EmptyState title="No data found" description="" />
      </Stack>
    );
  }

  return (
    <Stack direction="column" gap="24px">
      <CostEfficiencySummary data={data} allGroups={allGroups} />
      <Stack direction="column" gap="12px">
        <SectionHeader />
        <Stack direction="row" alignItems="center" gap="12px">
          <MultiSemanticGroupSelectorDropdown {...selectorState} />
          <CostEfficiencyRangeFilter
            min={minCE}
            max={maxCE}
            onMinChange={setMinCE}
            onMaxChange={setMaxCE}
          />
        </Stack>
        <Box
          sx={{
            width: chartWidth,
            overflowX: 'auto'
          }}
        >
          <Box
            ref={containerRef}
            sx={{
              width: chartWidth,
              height: CHART_HEIGHT
            }}
          />
        </Box>
      </Stack>
    </Stack>
  );
};

const SECTION_TITLE = 'Cost Efficiency Distribution by Topic';
const SECTION_TOOLTIP = (
  <>
    Cost efficiency scores across the top 10 most cost efficient topics.
    <br />
    Cost efficiency is defined as the ratio of the session&apos;s answer quality
    to the cost of the session.
  </>
);

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
