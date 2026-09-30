/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Typography, Stack } from '@open-ui-kit/core';
import { useMemo } from 'react';
import type { SxProps } from '@mui/material';
import { SpiderChart, SpiderChartProps } from '@/components';
import { metricCatalog } from '@/common';
import { ImpactAssessment } from '@/types/oxp.type';

const COLOR_PALETTE = ['#B80B98', '#0BB2B8', '#FF9000', '#3B82F6'];

interface AgentSpiderChartProps {
  agentName: string;
  metrics: { metricKey: string; value: number }[];
  index: number;
  containerSx?: SxProps;
}

const AgentSpiderChart = ({ agentName, metrics, index, containerSx }: AgentSpiderChartProps) => {
  const data: SpiderChartProps['data'] = metrics.map((m) => {
    const catalogEntry = metricCatalog[m.metricKey as keyof typeof metricCatalog];
    const label = catalogEntry?.name ?? m.metricKey;
    return {
      subject: label,
      variableA: Math.round(m.value * 100)
    };
  });

  if (data.length === 0) return null;

  const color = COLOR_PALETTE[index % COLOR_PALETTE.length];

  return (
    <Stack direction="column" alignItems="flex-start" sx={{ width: 460, height: 280, ...containerSx }}>
      <Typography variant="h6">{agentName}</Typography>
      <Box sx={{ width: '100%', height: '100%', overflow: 'hidden' }}>
        <SpiderChart data={data} fillColor={color} strokeColor={color} />
      </Box>
    </Stack>
  );
};

export interface AgentImpactChartProps {
  impactAssessmentData: ImpactAssessment[] | undefined;
  selectedMetricKeys: string[];
  title?: string;
  containerSx?: SxProps;
}

export const AgentImpactChart = ({ impactAssessmentData, selectedMetricKeys, title = 'Agent Impact', containerSx }: AgentImpactChartProps) => {
  const agentImpactData = useMemo(() => {
    if (!impactAssessmentData) return [];

    const agentMap = new Map<string, { metricKey: string; value: number }[]>();

    for (const metric of impactAssessmentData) {
      if (!selectedMetricKeys.includes(metric.metric_name)) continue;

      for (const agent of metric.agents) {
        if (!agentMap.has(agent.agent_name)) {
          agentMap.set(agent.agent_name, []);
        }
        agentMap.get(agent.agent_name)!.push({
          metricKey: metric.metric_name,
          value: agent.value.value
        });
      }
    }

    return Array.from(agentMap.entries()).map(([agentName, metrics]) => ({
      agentName,
      metrics
    }));
  }, [impactAssessmentData, selectedMetricKeys]);

  const filteredAgents = agentImpactData.filter(
    (agent) => agent.agentName !== 'user' && agent.agentName !== 'finalize_on_error'
  );

  if (filteredAgents.length === 0) return null;

  return (
    <Stack direction="column" gap="16px">
      <Typography variant="h5">{title}</Typography>
      <Stack direction="row" gap="16px" sx={{ flexWrap: 'wrap' }}>
        {filteredAgents.map((agent, idx) => (
          <Box key={agent.agentName}>
            <AgentSpiderChart agentName={agent.agentName} metrics={agent.metrics} index={idx} containerSx={containerSx} />
          </Box>
        ))}
      </Stack>
    </Stack>
  );
};
