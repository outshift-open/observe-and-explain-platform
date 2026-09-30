/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { TabPanel } from '@/components/TabPanel';
import { Tabs, Tab, Stack } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import { useEffect, useMemo } from 'react';
import type { SyntheticEvent } from 'react';
import OverviewTab from './OverviewTab';
import MonitorTab from './MonitorTab';
import AnalyzeTab from './AnalyzeTab';
import CollectTab from './CollectTab';
import { useMatch, useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/routes/routes';

export const ApplicationTabs = () => {
  const navigate = useNavigate();
  const { applicationId } = useParams();

  const matchOverview = useMatch('/applications/:applicationId/overview');
  const matchCollectWithSession = useMatch(PATHS.applicationCollectSession);
  const matchCollectLiveSession = useMatch(PATHS.applicationCollectLiveSession);
  const matchCollect = useMatch(PATHS.applicationCollect);
  const matchCollectCompleted = useMatch(PATHS.applicationCollectCompleted);
  const matchCollectLiveSessions = useMatch(
    PATHS.applicationCollectLiveSessions
  );
  const matchAnalyze = useMatch(PATHS.applicationAnalyze);
  const matchAnalyzeSubTab = useMatch(
    '/applications/:applicationId/analyze/:analyzeTab'
  );
  const matchAnalyzeSemanticGroup = useMatch(
    '/applications/:applicationId/analyze/:analyzeTab/:semanticGroup'
  );
  const matchMonitor = useMatch(PATHS.applicationMonitor);
  const matchMonitorSubTab = useMatch(
    '/applications/:applicationId/monitor/:monitorTab'
  );

  const tabOrder = ['overview', 'analyze', 'monitor', 'collect'] as const;

  const tabIndex = useMemo(() => {
    if (matchOverview) return 0;
    if (matchMonitor || matchMonitorSubTab) return 2;
    if (matchAnalyze || matchAnalyzeSubTab || matchAnalyzeSemanticGroup)
      return 1;
    if (
      matchCollectWithSession ||
      matchCollectLiveSession ||
      matchCollect ||
      matchCollectCompleted ||
      matchCollectLiveSessions
    )
      return 3;
    return 0;
  }, [
    matchOverview,
    matchMonitor,
    matchMonitorSubTab,
    matchCollectWithSession,
    matchCollectLiveSession,
    matchCollect,
    matchCollectCompleted,
    matchCollectLiveSessions,
    matchAnalyze,
    matchAnalyzeSubTab,
    matchAnalyzeSemanticGroup
  ]);

  useEffect(() => {
    if (matchAnalyze && !matchAnalyzeSubTab && !matchAnalyzeSemanticGroup) {
      navigate(`/applications/${applicationId}/analyze/overview`, {
        replace: true
      });
    }
  }, [
    matchAnalyze,
    matchAnalyzeSubTab,
    matchAnalyzeSemanticGroup,
    applicationId,
    navigate
  ]);

  useEffect(() => {
    if (matchMonitor && !matchMonitorSubTab) {
      navigate(`/applications/${applicationId}/monitor/application`, {
        replace: true
      });
    }
  }, [matchMonitor, matchMonitorSubTab, applicationId, navigate]);

  useEffect(() => {
    if (
      matchCollect &&
      !matchCollectCompleted &&
      !matchCollectLiveSessions &&
      !matchCollectWithSession &&
      !matchCollectLiveSession
    ) {
      navigate(`/applications/${applicationId}/collect/completed`, {
        replace: true
      });
    }
  }, [
    matchCollect,
    matchCollectCompleted,
    matchCollectLiveSessions,
    matchCollectWithSession,
    matchCollectLiveSession,
    applicationId,
    navigate
  ]);

  const handleTabChange = (_event: SyntheticEvent, value: number) => {
    const next = tabOrder[value] ?? 'overview';
    if (next === 'analyze') {
      navigate(
        PATHS.applicationAnalyzeOverview.replace(
          ':applicationId',
          applicationId ?? ''
        )
      );
    } else if (next === 'collect') {
      navigate(`/applications/${applicationId}/collect/completed`);
    } else {
      navigate(`/applications/${applicationId}/${next}`);
    }
  };

  const theme = useTheme();

  return (
    <Stack
      direction={'column'}
      sx={{ width: '100%', height: '100%' }}
      gap={'24px'}
    >
      <Stack direction={'row'} sx={{ width: '100%' }} alignItems={'flex-end'}>
        <Tabs
          value={tabIndex}
          onChange={handleTabChange}
          slotProps={{
            indicator: {
              sx: {
                backgroundColor: `${theme.palette.vars.neutralTextDefault} !important`
              }
            }
          }}
        >
          <Tab label={'Overview'} />
          <Tab label={'Explain'} />
          <Tab label={'Monitor'} />
          <Tab label={'Inspect'} />
        </Tabs>
      </Stack>
      <TabPanel value={tabIndex} index={0} sx={{ height: '100%' }}>
        <OverviewTab />
      </TabPanel>
      <TabPanel value={tabIndex} index={1} sx={{ height: '100%' }}>
        <AnalyzeTab />
      </TabPanel>
      <TabPanel value={tabIndex} index={2} sx={{ height: '100%' }}>
        <MonitorTab />
      </TabPanel>
      <TabPanel value={tabIndex} index={3} sx={{ height: '100%' }}>
        <CollectTab />
      </TabPanel>
    </Stack>
  );
};
