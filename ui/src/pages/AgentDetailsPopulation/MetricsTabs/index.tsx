/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { TabPanel } from '@/components/TabPanel';
import { Tabs, Tab, Stack } from '@open-ui-kit/core';
import { Divider, useTheme } from '@mui/material';
import { useState } from 'react';
import { TabLabel } from '@/components/TabLabel.tsx';
import { GeneralTab } from './GeneralTab';
import { ReliabilityTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/ReliabilityTab.tsx';
import { LLMTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/LLMTab.tsx';
import { ConversationTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/ConversationTab.tsx';
import { PerformanceTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/PerformanceTab.tsx';
import { QualityReasoningTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/QualityReasoningTab.tsx';
import { CostTab } from '@/pages/AgentDetailsPopulation/MetricsTabs/CostTab.tsx';
import { ToolsTab } from './ToolsTab.tsx';
import { AgentMetricType } from '@/types/oxp.type.ts';

interface MetricsTabsProps {
  agentId: string;
  startTime: number;
  endTime: number;
}

const mapTabToMetricType: Record<number, AgentMetricType> = {
  0: 'general',
  1: 'performance',
  2: 'quality_and_reasoning',
  3: 'reliability_and_safety',
  4: 'cost',
  5: 'tools',
  6: 'conversation',
  7: 'llm'
};

const MetricsTabs = ({ agentId, startTime, endTime }: MetricsTabsProps) => {
  const [tab, setTab] = useState(0);

  const theme = useTheme();

  return (
    <Stack direction={'column'} gap={'16px'} sx={{ height: '100%' }}>
      <Stack direction={'row'} sx={{ width: '100%' }} alignItems={'flex-end'}>
        <Tabs
          value={tab}
          onChange={(_, val) => {
            setTab(val);
          }}
          slotProps={{ indicator: { sx: { backgroundColor: `${theme.palette.vars.neutralTextDefault} !important` } } }}
        >
          <Tab label={'General'} />
          <Tab label={'Performance'} />
          <Tab label={'Quality & Reasoning'} />
          <Tab label={'Reliability & Safety'} />
          <Tab label={'Cost'} />
          <Tab label={'Tools'} />
          <Tab label={'Conversation'} />
          <Tab label={'LLM'} />
        </Tabs>
        <Divider sx={{ borderColor: theme.palette.vars.neutralTextDefault, height: '1px', flex: 1 }} orientation={'horizontal'} />
      </Stack>
      <TabPanel value={tab} index={0} sx={{ height: '100%' }}>
        <GeneralTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={1} sx={{ height: '100%' }}>
        <PerformanceTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={2} sx={{ height: '100%' }}>
        <QualityReasoningTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={3} sx={{ height: '100%' }}>
        <ReliabilityTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={4} sx={{ height: '100%' }}>
        <CostTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={5} sx={{ height: '100%' }}>
        <ToolsTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={6} sx={{ height: '100%' }}>
        <ConversationTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
      <TabPanel value={tab} index={7} sx={{ height: '100%' }}>
        <LLMTab agentId={agentId} startTime={startTime} endTime={endTime} metricType={mapTabToMetricType[tab]} />
      </TabPanel>
    </Stack>
  );
};

export default MetricsTabs;
