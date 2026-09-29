/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { PageWithTitle } from '@/components';
import { PATHS } from '@/routes/routes';
import { Stack, Typography, useTheme } from '@mui/material';
import { useParams } from 'react-router-dom';
import { TAB_NAMES } from '@/pages/ApplicationDetails/MonitorTab';
import {
  useApplicationAgents,
  useAnomalyReportList,
  useSemanticGroupListDetails,
  useSemanticGroups,
  useApplicationSessions,
  useImpactAssessmentSessionList
} from '@/api/oxpApi';
import { DEFAULT_START_DATE, DEFAULT_END_DATE } from '@/common/constants';
import { useMemo } from 'react';
import { Spinner } from '@open-ui-kit/core';
import { AgentAnalyzeImpactAssessment } from './types';
import { AgentImpactAssessmentTable } from './AgentImpactAssessmentTable';

export const AgentAnalyze = () => {
  const { applicationId, agentId } = useParams();
  const theme = useTheme();

  const { data: semanticGroupsData, error: semanticGroupsError, isLoading: semanticGroupsLoading } = useSemanticGroups(applicationId ?? '');

  const applicationSessions = useApplicationSessions(applicationId ?? '', DEFAULT_START_DATE, DEFAULT_END_DATE);
  console.log(
    'applicationSessions',
    applicationSessions.data?.sessionList.map((session) => session.sessionId)
  );

  const currentAgentSessions = useMemo(() => {
    const agentSessions = applicationSessions.data?.sessionList.filter((session) => session.agents?.some((agent) => agent === agentId));
    if (!agentSessions) return [];

    const sessionToGroup = new Map<string, string>();
    for (const group of semanticGroupsData ?? []) {
      for (const sid of group.session_ids) {
        sessionToGroup.set(sid, group.id);
      }
    }

    return agentSessions?.map((session) => session.sessionId) ?? [];
  }, [applicationSessions.data?.sessionList, agentId, semanticGroupsData]);

  console.log('currentAgentSessions', currentAgentSessions);

  const {
    data: agentsData,
    error: agentsError,
    isLoading: agentsLoading
  } = useApplicationAgents(applicationId ?? '', DEFAULT_START_DATE, DEFAULT_END_DATE);

  const agent = useMemo(() => {
    return agentsData?.agents?.find((agent) => agent.id === agentId);
  }, [agentsData?.agents, agentId]);

  const anomalyReportList = useAnomalyReportList(semanticGroupsData?.map((group) => group.id) ?? []);

  const sessionOutlierMetrics = useMemo(() => {
    const result = new Map<string, Set<string>>();
    for (const query of anomalyReportList) {
      if (!query.data?.reports) continue;
      for (const report of query.data.reports) {
        try {
          const metadata = JSON.parse(report.metadata) as { metric: string };
          for (const sessionId of report.outliers_values) {
            if (!result.has(sessionId)) {
              result.set(sessionId, new Set());
            }
            result.get(sessionId)!.add(metadata.metric);
          }
        } catch {
          continue;
        }
      }
    }
    return result;
  }, [anomalyReportList]);

  const impactAssessmentSessionList = useImpactAssessmentSessionList(currentAgentSessions ?? []);

  const impactAssessmentSessionListData = useMemo<AgentAnalyzeImpactAssessment[]>(() => {
    if (!agentId) return [];

    const metricToField: Record<string, keyof Omit<AgentAnalyzeImpactAssessment, 'sessionId' | 'outlierMetrics'>> = {
      Cost: 'cost',
      ToolUtilizationAccuracy: 'toolUtilizationAccuracy',
      ResponseCompleteness: 'responseCompleteness',
      IntentRecognitionAccuracy: 'intentRecognitionAccuracy',
      AnswerRelevancy: 'answerRelevancy',
      Groundedness: 'groundedness'
    };

    const sessionMap = new Map<string, AgentAnalyzeImpactAssessment>();

    for (const query of impactAssessmentSessionList) {
      if (!query.data) continue;
      for (const item of query.data) {
        const field = metricToField[item.metric_name];
        if (!field) continue;

        const agentEntry = item.agents.find((a) => a.agent_name === agentId);
        if (!agentEntry) continue;

        let entry = sessionMap.get(item.session_id);
        if (!entry) {
          const outliers = sessionOutlierMetrics.get(item.session_id);
          entry = {
            sessionId: item.session_id,
            cost: 0,
            toolUtilizationAccuracy: 0,
            responseCompleteness: 0,
            intentRecognitionAccuracy: 0,
            answerRelevancy: 0,
            groundedness: 0,
            outlierMetrics: outliers ? [...outliers] : []
          };
          sessionMap.set(item.session_id, entry);
        }
        entry[field] = agentEntry.value.value;
      }
    }

    return [...sessionMap.values()];
  }, [impactAssessmentSessionList, agentId, sessionOutlierMetrics]);

  console.log('impactAssessmentSessionListData', impactAssessmentSessionListData);

  if (agentsError) {
    return <>An error occurred!</>;
  }

  if (agentsLoading) {
    return (
      <Stack alignItems={'center'} justifyContent={'center'} sx={{ width: '100%', height: '100%' }}>
        <Spinner />
      </Stack>
    );
  }

  return (
    <PageWithTitle
      breadcrumbItems={[
        { text: 'Applications', link: PATHS.applications },
        {
          text: applicationId ?? '',
          link: `${PATHS.applications}/${applicationId}`
        },
        {
          text: 'Agents',
          link: `${PATHS.applicationMonitorSubTab}`.replace(':applicationId', applicationId ?? '').replace(':monitorTab', TAB_NAMES[1])
        },
        { text: agent?.name ?? '', link: `${PATHS.applications}/${applicationId}/agents/${agentId}` },
        { text: 'Monitor', link: `${PATHS.applications}/${applicationId}/agents/${agentId}/monitor` }
      ]}
      title={
        <Typography variant={'h5'} sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}>
          {applicationId}
        </Typography>
      }
    >
      <AgentImpactAssessmentTable
        data={impactAssessmentSessionListData}
        isLoading={impactAssessmentSessionList.some((item) => item.isLoading)}
        isError={impactAssessmentSessionList.some((item) => item.isError)}
      />
    </PageWithTitle>
  );
};
