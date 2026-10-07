/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router';
import { Box, Stack } from '@mui/material';
import { ReasoningPathGraph, TabPanel } from '@/components';
import { OverviewTab } from './OverviewTab';
import { ExecutionTreeTab } from './ExecutionTreeTab';
import { ConversationTab } from './ConversationTab';
import { SessionAnalysisTab } from './SessionAnalysisTab';
import { CognitiveObservabilityTab } from './CognitiveObservabilityTab';
import { useApplicationSessionsWithStatefulEval } from '@/api/oxpApi';
import { DEFAULT_START_DATE, DEFAULT_END_DATE } from '@/common';
import { SessionWithStatefulEval } from '@/types/oxp.type';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { Tabs, Tab } from '@open-ui-kit/core';

export const SESSION_TAB_KEYS = [
  'overview',
  'analysis',
  'cognitive-observability',
  'reasoning-path',
  'execution-graph',
  'conversation'
] as const;
export type SessionTab = (typeof SESSION_TAB_KEYS)[number];

interface TabConfig {
  key: SessionTab;
  label: string;
  visible: boolean;
  render: () => React.ReactNode;
}

interface SessionDetailsProps {
  costDollars?: string | number;
  totalTokens?: string | number;
  duration?: string | number;
}

const SessionDetails = ({
  costDollars = '0',
  totalTokens = '0',
  duration = '0'
}: SessionDetailsProps) => {
  const { sessionTab, sessionId, applicationId } = useParams<{
    sessionTab?: string;
    sessionId?: string;
    applicationId?: string;
  }>();

  const { data: sessionList } = useApplicationSessionsWithStatefulEval(
    applicationId ?? '',
    DEFAULT_START_DATE,
    DEFAULT_END_DATE
  );

  const navigate = useNavigate();
  const location = useLocation();

  const neurosymbolicEnabled = useFeatureFlag('neurosymbolic_eval');
  const [isReasoningPathTabVisible, setIsReasoningPathTabVisible] =
    useState<boolean>(false);

  useEffect(() => {
    if (!sessionList?.sessionList) return;
    const currentSession = sessionList.sessionList.find(
      (s: SessionWithStatefulEval) => s?.sessionId === sessionId
    );

    if (
      neurosymbolicEnabled &&
      currentSession?.statefulEval?.source === 'SymbolicDiscovery'
    ) {
      setIsReasoningPathTabVisible(true);
    } else {
      setIsReasoningPathTabVisible(false);
    }
  }, [
    sessionList?.sessionList,
    sessionId,
    applicationId,
    neurosymbolicEnabled
  ]);

  const tabConfigs = useMemo<TabConfig[]>(
    () => [
      {
        key: 'overview',
        label: 'Overview',
        visible: true,
        render: () => (
          <OverviewTab
            costDollars={costDollars}
            totalTokens={totalTokens}
            duration={duration}
          />
        )
      },
      {
        key: 'analysis',
        label: 'Analysis',
        visible: true,
        render: () => <SessionAnalysisTab />
      },
      {
        key: 'cognitive-observability',
        label: 'Cognitive Observability',
        visible: true,
        render: () => <CognitiveObservabilityTab />
      },
      {
        key: 'reasoning-path',
        label: 'Reasoning Path',
        visible: isReasoningPathTabVisible,
        render: () => sessionId && <ReasoningPathGraph sessionId={sessionId} />
      },
      {
        key: 'execution-graph',
        label: 'Execution Graph',
        visible: true,
        render: () => <ExecutionTreeTab />
      },
      {
        key: 'conversation',
        label: 'Conversation',
        visible: true,
        render: () => <ConversationTab />
      }
    ],
    [costDollars, totalTokens, duration, isReasoningPathTabVisible, sessionId]
  );

  const visibleTabs = useMemo(
    () => tabConfigs.filter((tab) => tab.visible),
    [tabConfigs]
  );

  const selectedTab = Math.max(
    0,
    visibleTabs.findIndex((tab) => tab.key === sessionTab)
  );

  const handleTabChange = useCallback(
    (_event: React.SyntheticEvent, newValue: number) => {
      const newTab = visibleTabs[newValue]?.key;
      if (!newTab) return;
      const basePath = sessionTab
        ? location.pathname.replace(/\/[^/]+$/, `/${newTab}`)
        : `${location.pathname}/${newTab}`;
      navigate(basePath, { replace: true });
    },
    [navigate, location.pathname, sessionTab, visibleTabs]
  );

  return (
    <Stack direction={'column'} sx={{ width: '100%', height: '100%' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={selectedTab}
          onChange={handleTabChange}
          aria-label="session details tabs"
        >
          {visibleTabs.map((tab, index) => (
            <Tab
              key={tab.key}
              label={tab.label}
              id={`session-tab-${index}`}
              aria-controls={`session-tabpanel-${index}`}
            />
          ))}
        </Tabs>
      </Box>

      {visibleTabs.map((tab, index) => (
        <TabPanel
          key={tab.key}
          value={selectedTab}
          index={index}
          sx={{ flex: 1 }}
        >
          {tab.render()}
        </TabPanel>
      ))}
    </Stack>
  );
};

export default SessionDetails;
