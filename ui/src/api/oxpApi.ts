/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query';
import {
  ApplicationAgents,
  ApplicationMetrics,
  ApplicationSessions,
  SessionTimeline,
  SessionLatentSpaceResponse,
  AgentMetricType,
  AgentMetrics,
  StaticTopology,
  SpanStatefulEval,
  SemanticGroup,
  NormalBehaviourReport,
  ConsistencyReport,
  SemanticGroupDetails,
  AnomalyReport,
  ApplicationSummaryMetrics,
  ImpactAssessment,
  SessionStatefulEval,
  WasteEstimationSemanticGroup,
  CostEfficiencyGrouppedSessions,
  WastefulSession,
  WastedResourcesFeatureScore,
  SemanticGroupsInsight,
  SessionInsight,
  ReasoningPathResponse,
  AppReasoningPathResponse,
  TimelineReasoningPathResponse,
  AgenticProtocolsMetrics,
  SpanDetails,
  SessionsWithCognitiveObservability,
  SessionL9Protocols,
  SessionsWithL9Protocols
} from '@/types/oxp.type';
import {
  ApplicationsResponse,
  ApplicationStatefulEvalTotals,
  LiveSession,
  LiveSessionsResponse,
  LiveTopologySessionResponse,
  SessionsCountResponse
} from '@/types/oxpApi.type';
import { mockSessionsWithCognitiveObservability } from './mock/sessionsWithCognitiveObservability';
import { mockSessionL9Protocols } from './mock/sessionL9Protocols';
import { mockSessionsWithL9Protocols } from './mock/sessionsWithL9Protocols';

const OCE_API_BASE_URL = window.restApiUrl ?? import.meta.env.VITE_REST_API_URL;
// const OCE_API_BASE_URL = 'http://localhost:8000/api/v1';

// const OCE_API_BASE_URL_DEV = 'http://localhost:10000';

const fetchApplications = async (): Promise<ApplicationsResponse> => {
  const response = await fetch(`${OCE_API_BASE_URL}/ui/applications`);

  if (!response.ok) {
    throw new Error(`Failed to fetch applications: ${response.statusText}`);
  }

  const data = await response.json();

  return data;
};

export const useApplications = () => {
  return useQuery<ApplicationsResponse>({
    queryKey: ['applications'],
    queryFn: () => fetchApplications()
  });
};

const fetchApplicationMetrics = async (
  applicationId: string,
  startTime: number,
  endTime: number
): Promise<ApplicationMetrics> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}?start_time=${startTime}&end_time=${endTime}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application metrics: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useApplicationMetrics = (
  applicationId: string,
  startTime: number,
  endTime: number
) => {
  return useQuery<ApplicationMetrics>({
    queryKey: ['applicationMetrics', applicationId, startTime, endTime],
    queryFn: () => fetchApplicationMetrics(applicationId, startTime, endTime)
  });
};

const fetchApplicationAgents = async (
  applicationId: string,
  startTime: number,
  endTime: number
): Promise<ApplicationAgents> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/agents?start_time=${startTime}&end_time=${endTime}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application agents: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useApplicationAgents = (
  applicationId: string,
  startTime: number,
  endTime: number
) => {
  return useQuery<ApplicationAgents>({
    queryKey: ['applicationAgents', applicationId, startTime, endTime],
    queryFn: () => fetchApplicationAgents(applicationId, startTime, endTime)
  });
};

const fetchApplicationSessions = async (
  applicationId: string,
  startTime: number,
  endTime: number
): Promise<ApplicationSessions> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/sessions?start_time=${startTime}&end_time=${endTime}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application sessions: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useApplicationSessions = (
  applicationId: string,
  startTime: number,
  endTime: number,
  enabled: boolean = true
) => {
  return useQuery<ApplicationSessions>({
    queryKey: ['applicationSessions', applicationId, startTime, endTime],
    queryFn: () => fetchApplicationSessions(applicationId, startTime, endTime),
    enabled
  });
};

const fetchApplicationSessionsWithStatefulEval = async (
  applicationId: string,
  startTime: number,
  endTime: number,
  semanticGroupId?: string
): Promise<ApplicationSessions> => {
  const params = new URLSearchParams({
    start_time: String(startTime),
    end_time: String(endTime)
  });
  if (semanticGroupId) {
    params.set('semantic_group_id', semanticGroupId);
  }

  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/sessions_with_stateful_eval?${params}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application sessions with stateful eval: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useApplicationSessionsWithStatefulEval = (
  applicationId: string,
  startTime: number,
  endTime: number,
  enabled: boolean = true,
  semanticGroupId?: string
) => {
  return useQuery<ApplicationSessions>({
    queryKey: [
      'applicationSessionsWithStatefulEval',
      applicationId,
      startTime,
      endTime,
      semanticGroupId
    ],
    queryFn: () =>
      fetchApplicationSessionsWithStatefulEval(
        applicationId,
        startTime,
        endTime,
        semanticGroupId
      ),
    enabled
  });
};

const fetchSessionStatefulEval = async (
  sessionId: string
): Promise<SessionStatefulEval> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/metrics/sessions/${sessionId}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch session stateful eval: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useSessionStatefulEval = (sessionId: string) => {
  return useQuery<SessionStatefulEval>({
    queryKey: ['sessionStatefulEval', sessionId],
    queryFn: () => fetchSessionStatefulEval(sessionId)
  });
};

const fetchSpanStatefulEval = async (
  sessionId: string,
  spanId: string
): Promise<SpanStatefulEval> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/metrics/sessions/${sessionId}/spans/${spanId}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch span stateful eval: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useSpanListStatefulEval = (
  sessionId: string,
  spanIds: string[]
) => {
  return useQueries({
    queries: spanIds.map((spanId) => {
      return {
        queryKey: ['spanStatefulEval', sessionId, spanId],
        queryFn: () => fetchSpanStatefulEval(sessionId, spanId)
      };
    })
  });
};

const fetchSessionTimeline = async (
  sessionId: string
): Promise<SessionTimeline> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/sessions/${sessionId}/timeline-waterfall`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch session timeline: ${response.statusText}`);
  }

  const data = await response.json();

  return data;
};

export const useSessionTimeline = (sessionId: string) => {
  return useQuery<SessionTimeline>({
    queryKey: ['sessionTimeline', sessionId],
    queryFn: () => fetchSessionTimeline(sessionId)
  });
};

const fetchSessionLatentSpace = async (
  sessionId: string
): Promise<SessionLatentSpaceResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/sessions/${sessionId}/latent-space`
  );
  //const response = await fetch(`${OCE_API_BASE_URL_GRAPH}/graph/latent-space/${sessionId}`);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch session latent space: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useSessionLatentSpace = (sessionId: string) => {
  return useQuery<SessionLatentSpaceResponse>({
    queryKey: ['sessionLatentSpace', sessionId],
    queryFn: () => fetchSessionLatentSpace(sessionId),
    enabled: !!sessionId
  });
};

const fetchAgentMetrics = async (
  applicationId: string,
  agentId: string,
  chartType: AgentMetricType,
  startTime: number,
  endTime: number
): Promise<AgentMetrics> => {
  // const url = `${OCE_API_BASE_URL}/applications/${applicationId}/agent/${agentId}/charts?chart_type=${chartType}&start_time=${startTime}&end_time=${endTime}`;
  const url = `${OCE_API_BASE_URL}/metrics/applications/${applicationId}/category/${chartType}?agent_id=${agentId}&start_time=${startTime}&end_time=${endTime}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch agent general metrics: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useAgentMetrics = (
  applicationId: string,
  agentId: string,
  chartType: AgentMetricType,
  startTime: number,
  endTime: number
) => {
  return useQuery<AgentMetrics>({
    queryKey: [
      'agentMetrics',
      applicationId,
      agentId,
      chartType,
      startTime,
      endTime
    ],
    queryFn: () =>
      fetchAgentMetrics(applicationId, agentId, chartType, startTime, endTime)
  });
};

export const fetchStaticTopology = async (
  applicationId: string
): Promise<StaticTopology> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/topology`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch static topology: ${response.statusText}`);
  }

  const data = await response.json();

  return data;
};

export const useStaticTopology = (applicationId: string) => {
  return useQuery<StaticTopology>({
    queryKey: ['staticTopology', applicationId],
    queryFn: () => fetchStaticTopology(applicationId)
  });
};

const fetchSemanticGroups = async (
  applicationId: string
): Promise<SemanticGroup[]> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/semanticgroups/table`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch semantic groups: ${response.statusText}`);
  }

  const data = await response.json();

  return data?.nodes;
};

export const useSemanticGroups = (applicationId: string) => {
  return useQuery<SemanticGroup[]>({
    queryKey: ['semanticGroups', applicationId],
    queryFn: () => fetchSemanticGroups(applicationId)
  });
};

const fetchSemanticGroupsTree = async (
  applicationId: string
): Promise<SemanticGroup[]> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/semanticgroups`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch semantic groups: ${response.statusText}`);
  }

  const data = await response.json();

  return data?.nodes;
};

export const useSemanticGroupsTree = (applicationId: string) => {
  return useQuery<SemanticGroup[]>({
    queryKey: ['semanticGroupsTree', applicationId],
    queryFn: () => fetchSemanticGroupsTree(applicationId)
  });
};

const fetchNormalBehaviourReport = async (
  semanticGroupId: string
): Promise<NormalBehaviourReport> => {
  // const response = await fetch(`${OCE_API_BASE_URL_DEV}/semantic-groups/${semanticGroupId}/normal-behaviour-report`);
  const response = await fetch(
    `${OCE_API_BASE_URL}/semanticgroups/${semanticGroupId}/normal_behavior`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch normal behaviour report: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useNormalBehaviourReport = (semanticGroupId: string) => {
  return useQuery<NormalBehaviourReport>({
    queryKey: ['normalBehaviourReport', semanticGroupId],
    queryFn: () => fetchNormalBehaviourReport(semanticGroupId)
  });
};

export const useNormalBehaviourReportList = (semanticGroupIds: string[]) => {
  return useQueries({
    queries: semanticGroupIds.map((semanticGroupId) => {
      return {
        queryKey: ['normalBehaviourReportList', semanticGroupId],
        queryFn: () => fetchNormalBehaviourReport(semanticGroupId)
      };
    })
  });
};

const fetchConsistencyReport = async (
  semanticGroupId: string
): Promise<ConsistencyReport> => {
  // const response = await fetch(`${OCE_API_BASE_URL_DEV}/semantic-groups/${semanticGroupId}/consistency-report`);
  const response = await fetch(
    `${OCE_API_BASE_URL}/semanticgroups/${semanticGroupId}/consistency_report`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch consistency report: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data;
};

export const useConsistencyReport = (semanticGroupId: string) => {
  return useQuery<ConsistencyReport>({
    queryKey: ['consistencyReport', semanticGroupId],
    queryFn: () => fetchConsistencyReport(semanticGroupId)
  });
};

const fetchSemanticGroupDetails = async (
  semanticGroupId: string
): Promise<SemanticGroupDetails> => {
  //const response = await fetch(`${OCE_API_BASE_URL_DEV}/semantic-groups/${semanticGroupId}`);
  const response = await fetch(
    `${OCE_API_BASE_URL}/semanticgroups/${semanticGroupId}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch semantic group details: ${response.statusText}`
    );
  }

  const data = await response.json();
  return data;
};

export const useSemanticGroupDetails = (semanticGroupId: string) => {
  return useQuery<SemanticGroupDetails>({
    queryKey: ['semanticGroupDetails', semanticGroupId],
    queryFn: () => fetchSemanticGroupDetails(semanticGroupId),
    enabled: !!semanticGroupId
  });
};

export const useSemanticGroupListDetails = (semanticGroupIds: string[]) => {
  return useQueries({
    queries: semanticGroupIds.map((semanticGroupId) => {
      return {
        queryKey: ['semanticGroupDetails', semanticGroupId],
        queryFn: () => fetchSemanticGroupDetails(semanticGroupId)
      };
    })
  });
};

const fetchAnomalyReport = async (
  semanticGroupId: string
): Promise<AnomalyReport> => {
  // const response = await fetch(`${OCE_API_BASE_URL_DEV}/semantic-groups/${semanticGroupId}/anomaly-report`);
  const response = await fetch(
    `${OCE_API_BASE_URL}/semanticgroups/${semanticGroupId}/anomaly_report`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch anomaly report: ${response.statusText}`);
  }

  const data = await response.json();

  return data;
};

export const useAnomalyReport = (semanticGroupId: string) => {
  return useQuery<AnomalyReport>({
    queryKey: ['anomalyReport', semanticGroupId],
    queryFn: () => fetchAnomalyReport(semanticGroupId)
  });
};

export const useAnomalyReportList = (semanticGroupIds: string[]) => {
  return useQueries({
    queries: semanticGroupIds.map((semanticGroupId) => {
      return {
        queryKey: ['anomalyReport', semanticGroupId],
        queryFn: () => fetchAnomalyReport(semanticGroupId)
      };
    })
  });
};

export const fetchApplicationSummaryMetrics = async (
  applicationId: string,
  startTime?: number,
  endTime?: number
): Promise<ApplicationSummaryMetrics> => {
  const params = new URLSearchParams();
  if (startTime !== undefined) params.set('start_time', String(startTime));
  if (endTime !== undefined) params.set('end_time', String(endTime));
  const query = params.toString();

  const response = await fetch(
    `${OCE_API_BASE_URL}/metrics/applications/${applicationId}/summary${
      query ? `?${query}` : ''
    }`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application summary metrics: ${response.statusText}`
    );
  }

  const data = await response.json();

  return { applicationName: applicationId, ...data };
};

export const useApplicationSummaryMetrics = (
  applicationId: string,
  startTime?: number,
  endTime?: number
) => {
  return useQuery<ApplicationSummaryMetrics>({
    queryKey: ['applicationSummaryMetrics', applicationId, startTime, endTime],
    queryFn: () =>
      fetchApplicationSummaryMetrics(applicationId, startTime, endTime)
  });
};

export const useApplicationListSummaryMetrics = (applicationIds: string[]) => {
  return useQueries({
    queries: applicationIds.map((applicationId) => {
      return {
        queryKey: ['applicationSummaryMetrics', applicationId],
        queryFn: () => fetchApplicationSummaryMetrics(applicationId)
      };
    })
  });
};

const fetchAgenticProtocolsMetrics = async (
  applicationId: string,
  startTime: number,
  endTime: number
): Promise<AgenticProtocolsMetrics> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/agentic-protocols-metrics?application=${encodeURIComponent(applicationId)}&start_time=${startTime}&end_time=${endTime}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch agentic protocols metrics: ${response.statusText}`
    );
  }

  return response.json();
};

export const useAgenticProtocolsMetrics = (
  applicationId: string,
  startTime: number,
  endTime: number,
  enabled = true
) => {
  return useQuery<AgenticProtocolsMetrics>({
    queryKey: ['agenticProtocolsMetrics', applicationId, startTime, endTime],
    queryFn: () =>
      fetchAgenticProtocolsMetrics(applicationId, startTime, endTime),
    enabled
  });
};

const fetchSpanDetails = async (spanId: string): Promise<SpanDetails> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/spans/${encodeURIComponent(spanId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch span details: ${response.statusText}`);
  }

  const data = await response.json();
  return data.spanDetails;
};

export const useSpanDetails = (spanId: string) => {
  return useQuery<SpanDetails>({
    queryKey: ['spanDetails', spanId],
    queryFn: () => fetchSpanDetails(spanId),
    enabled: !!spanId
  });
};

export const fetchImpactAssessmentSession = async (
  sessionId: string
): Promise<ImpactAssessment[]> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/sessions/sessions/${sessionId}/impact_assessment`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch impact assessment session: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data?.impact_report.map((item: ImpactAssessment) => ({
    ...item,
    session_id: sessionId
  }));
};

export const useImpactAssessmentSession = (
  sessionId: string,
  enabled: boolean = true
) => {
  return useQuery<ImpactAssessment[]>({
    queryKey: ['impactAssessmentSession', sessionId],
    queryFn: () => fetchImpactAssessmentSession(sessionId),
    enabled
  });
};

export const useImpactAssessmentSessionList = (sessionIds: string[]) => {
  return useQueries({
    queries: sessionIds.map((sessionId) => {
      return {
        queryKey: ['impactAssessmentSession', sessionId],
        queryFn: () => fetchImpactAssessmentSession(sessionId)
      };
    })
  });
};

export const fetImpactAssessmenentSemanticGroup = async (
  applicationId: string,
  semanticGroupId: string
): Promise<ImpactAssessment[]> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/applications/${applicationId}/semanticgroups/${semanticGroupId}/impact_assessment`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch impact assessment semantic group: ${response.statusText}`
    );
  }

  const data = await response.json();

  return data?.impact_report;
};

export const useImpactAssessmentSemanticGroup = (
  applicationId: string,
  semanticGroupId: string,
  enabled: boolean = true
) => {
  return useQuery<ImpactAssessment[]>({
    queryKey: ['impactAssessmentSemanticGroup', applicationId, semanticGroupId],
    queryFn: () =>
      fetImpactAssessmenentSemanticGroup(applicationId, semanticGroupId),
    enabled
  });
};

const fetchTopWastefulSessions = async (
  applicationName: string,
  startTime: number,
  endTime: number,
  threshold?: number,
  limit?: number
): Promise<WastefulSession[]> => {
  const params = new URLSearchParams();
  params.set('start_time', String(startTime));
  params.set('end_time', String(endTime));
  if (threshold !== undefined) params.set('threshold', String(threshold));
  if (limit !== undefined) params.set('limit', String(limit));

  const url = `${OCE_API_BASE_URL}/waste-estimation/${encodeURIComponent(applicationName)}/top-wasteful-sessions${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch top wasteful sessions: ${response.statusText}`
    );
  }

  return response.json();
};

export const useTopWastefulSessions = (
  applicationName: string,
  startTime: number,
  endTime: number,
  threshold?: number,
  limit?: number,
  enabled: boolean = true
) => {
  return useQuery<WastefulSession[]>({
    queryKey: ['topWastefulSessions', applicationName, threshold, limit],
    queryFn: () =>
      fetchTopWastefulSessions(
        applicationName,
        startTime,
        endTime,
        threshold,
        limit
      ),
    enabled: enabled && !!applicationName
  });
};

const fetchWasteEstimationsSemanticGroups = async (): Promise<
  WasteEstimationSemanticGroup[]
> => {
  const url = `${OCE_API_BASE_URL}/waste-estimation/waste-estimations-semantic-groups`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch waste estimations semantic groups: ${response.statusText}`
    );
  }

  return response.json();
};

export const useWasteEstimationsSemanticGroups = (enabled: boolean = true) => {
  return useQuery<WasteEstimationSemanticGroup[]>({
    queryKey: ['wasteEstimationsSemanticGroups'],
    queryFn: () => fetchWasteEstimationsSemanticGroups(),
    enabled
  });
};

const fetchCostEfficiencyGrouppedSessions = async (
  applicationName: string
): Promise<CostEfficiencyGrouppedSessions[]> => {
  const url = `${OCE_API_BASE_URL}/waste-estimation/${encodeURIComponent(applicationName)}/cost-efficiency-groupped-sessions`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch cost efficiency groupped sessions: ${response.statusText}`
    );
  }

  return response.json();
};

export const useCostEfficiencyGrouppedSessions = (
  applicationName: string,
  enabled: boolean = true
) => {
  return useQuery<CostEfficiencyGrouppedSessions[]>({
    queryKey: ['costEfficiencyGrouppedSessions', applicationName],
    queryFn: () => fetchCostEfficiencyGrouppedSessions(applicationName),
    enabled: enabled && !!applicationName
  });
};

const fetchWastedResourcesFeatureScores = async (
  sessionId: string
): Promise<WastedResourcesFeatureScore[]> => {
  const url = `${OCE_API_BASE_URL}/waste-estimation/wasted-resources-features-score?session_id=${sessionId}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch wasted resources feature scores: ${response.statusText}`
    );
  }

  return response.json();
};

export const useWastedResourcesFeatureScores = (
  sessionId: string,
  enabled: boolean = true
) => {
  return useQuery<WastedResourcesFeatureScore[]>({
    queryKey: ['wastedResourcesFeatureScores', sessionId],
    queryFn: () => fetchWastedResourcesFeatureScores(sessionId),
    enabled
  });
};

const fetchSemanticGroupsInsights = async (
  applicationName: string,
  startTime: number,
  endTime: number
): Promise<SemanticGroupsInsight[]> => {
  const params = new URLSearchParams({
    start_time: String(startTime),
    end_time: String(endTime)
  });
  const url = `${OCE_API_BASE_URL}/waste-estimation/${encodeURIComponent(applicationName)}/semantic-groups-insights?${params.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch semantic group insights: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSemanticGroupsInsights = (
  applicationName: string,
  startTime: number,
  endTime: number
) => {
  return useQuery<SemanticGroupsInsight[]>({
    queryKey: ['semanticGroupsInsights', applicationName, startTime, endTime],
    queryFn: () =>
      fetchSemanticGroupsInsights(applicationName, startTime, endTime),
    enabled: !!applicationName
  });
};

const fetchSessionsInsights = async (
  applicationName: string,
  startTime: number,
  endTime: number,
  semanticGroupId?: string
): Promise<SessionInsight[]> => {
  const params = new URLSearchParams();
  params.set('start_time', String(startTime));
  params.set('end_time', String(endTime));
  if (semanticGroupId) {
    params.set('semantic_group_id', semanticGroupId);
  }
  const url = `${OCE_API_BASE_URL}/waste-estimation/${encodeURIComponent(applicationName)}/sessions-insights?${params.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch sessions insights: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSessionsInsights = (
  applicationName: string,
  startTime: number,
  endTime: number,
  semanticGroupId?: string
) => {
  return useQuery<SessionInsight[]>({
    queryKey: [
      'sessionsInsights',
      applicationName,
      startTime,
      endTime,
      semanticGroupId
    ],
    queryFn: () =>
      fetchSessionsInsights(
        applicationName,
        startTime,
        endTime,
        semanticGroupId
      ),
    enabled: !!applicationName
  });
};

const SESSIONS_INSIGHTS_PAGE_SIZE = 20;

const fetchSessionsInsightsPaginated = async (
  applicationName: string,
  startTime: number,
  endTime: number,
  offset: number,
  limit: number,
  semanticGroupId?: string
): Promise<SessionInsight[]> => {
  const params = new URLSearchParams();
  params.set('start_time', String(startTime));
  params.set('end_time', String(endTime));
  params.set('offset', String(offset));
  params.set('limit', String(limit));

  if (semanticGroupId) {
    params.set('semantic_group_id', semanticGroupId);
  }
  const url = `${OCE_API_BASE_URL}/waste-estimation/${encodeURIComponent(applicationName)}/sessions-insights?${params.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch sessions insights: ${response.statusText}`
    );
  }

  return response.json();
};

export const useInfiniteSessionsInsights = (
  applicationName: string,
  startTime: number,
  endTime: number,
  semanticGroupId?: string
) => {
  return useInfiniteQuery({
    queryKey: [
      'sessionsInsightsInfinite',
      applicationName,
      startTime,
      endTime,
      semanticGroupId
    ],
    queryFn: ({ pageParam }) =>
      fetchSessionsInsightsPaginated(
        applicationName,
        startTime,
        endTime,
        pageParam,
        SESSIONS_INSIGHTS_PAGE_SIZE,
        semanticGroupId
      ),
    initialPageParam: 0,
    getNextPageParam: (
      lastPage: SessionInsight[],
      allPages: SessionInsight[][]
    ) => {
      if (lastPage.length < SESSIONS_INSIGHTS_PAGE_SIZE) return undefined;
      return allPages.flat().length;
    }
  });
};

const fetchSingleSessionInsights = async (
  startTime: number,
  endTime: number,
  offset: number,
  limit: number,
  sessionId: string
): Promise<SessionInsight[]> => {
  const params = new URLSearchParams();
  params.set('start_time', String(startTime));
  params.set('end_time', String(endTime));
  params.set('offset', String(offset));
  params.set('limit', String(limit));
  params.set('session_id', sessionId);

  const url = `${OCE_API_BASE_URL}/waste-estimation/session-insights?${params.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch sessions insights: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSingleSessionInsights = (
  startTime: number,
  endTime: number,
  sessionId: string
) => {
  return useInfiniteQuery({
    queryKey: ['singleSessionInsights', startTime, endTime, sessionId],
    queryFn: ({ pageParam }) =>
      fetchSingleSessionInsights(
        startTime,
        endTime,
        pageParam,
        SESSIONS_INSIGHTS_PAGE_SIZE,
        sessionId
      ),
    initialPageParam: 0,
    getNextPageParam: (
      lastPage: SessionInsight[],
      allPages: SessionInsight[][]
    ) => {
      if (lastPage.length < SESSIONS_INSIGHTS_PAGE_SIZE) return undefined;
      return allPages.flat().length;
    }
  });
};

const fetchReasoningPath = async (
  sessionId: string
): Promise<ReasoningPathResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/session-reasoning-path?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch reasoning path: ${response.statusText}`);
  }

  return response.json();
};

export const useReasoningPath = (sessionId: string) => {
  return useQuery<ReasoningPathResponse>({
    queryKey: ['reasoningPath', sessionId],
    queryFn: () => fetchReasoningPath(sessionId),
    enabled: !!sessionId
  });
};

const fetchApplicationReasoningPath = async (
  masName: string
): Promise<AppReasoningPathResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/application-reasoning-path?mas_name=${encodeURIComponent(masName)}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch application reasoning path: ${response.statusText}`
    );
  }

  return response.json();
};

export const useApplicationReasoningPath = (masName: string) => {
  return useQuery<AppReasoningPathResponse>({
    queryKey: ['applicationReasoningPath', masName],
    queryFn: () => fetchApplicationReasoningPath(masName),
    enabled: !!masName
  });
};

const fetchTimelineReasoningPath = async (
  sessionId: string
): Promise<TimelineReasoningPathResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/timeline-reasoning-path?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch timeline reasoning path: ${response.statusText}`
    );
  }

  return response.json();
};

export const useTimelineReasoningPath = (sessionId: string) => {
  return useQuery<TimelineReasoningPathResponse>({
    queryKey: ['timelineReasoningPath', sessionId],
    queryFn: () => fetchTimelineReasoningPath(sessionId),
    enabled: !!sessionId
  });
};

const fetchLiveSessions = async (
  applicationName: string
): Promise<LiveSessionsResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/live_topology/${encodeURIComponent(applicationName)}/sessions`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch live sessions: ${response.statusText}`);
  }

  const data: LiveSessionsResponse = await response.json();
  return {
    ...data,
    sessions: data.sessions.filter((s) => s.status === 'active')
  };
};

export const useLiveSessions = (
  applicationName: string,
  enabled: boolean = true
) => {
  return useQuery<LiveSessionsResponse>({
    queryKey: ['liveSessions', applicationName],
    queryFn: () => fetchLiveSessions(applicationName),
    enabled: enabled && !!applicationName,
    refetchInterval: 2000
  });
};

const fetchLiveTopologySession = async (
  sessionId: string
): Promise<LiveTopologySessionResponse> => {
  const response = await fetch(
    `${OCE_API_BASE_URL}/live_topology/sessions/${encodeURIComponent(sessionId)}/topology`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch live topology session: ${response.statusText}`
    );
  }

  return response.json();
};

export const useLiveTopologySession = (sessionId: string) => {
  return useQuery<LiveTopologySessionResponse>({
    queryKey: ['liveTopologySession', sessionId],
    queryFn: () => fetchLiveTopologySession(sessionId),
    enabled: !!sessionId,
    refetchInterval: 2000
  });
};

const fetchSessionsCount = async (
  applicationId: string,
  startTime?: number,
  endTime?: number
): Promise<SessionsCountResponse> => {
  const params = new URLSearchParams();
  params.set('application_id', applicationId);
  if (startTime != null) params.set('start_time', String(startTime));
  if (endTime != null) params.set('end_time', String(endTime));

  const response = await fetch(
    `${OCE_API_BASE_URL}/sessions/count?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch sessions count: ${response.statusText}`);
  }

  return response.json();
};

export const useSessionsCount = (
  applicationId: string,
  startTime?: number,
  endTime?: number
) => {
  return useQuery<SessionsCountResponse>({
    queryKey: ['sessionsCount', applicationId, startTime, endTime],
    queryFn: () => fetchSessionsCount(applicationId, startTime, endTime),
    enabled: !!applicationId,
    refetchInterval: 2000
  });
};

const fetchApplicationsWithStatefulEval = async (
  startTime?: number,
  endTime?: number
): Promise<ApplicationStatefulEvalTotals[]> => {
  const params = new URLSearchParams();
  if (startTime != null) params.set('start_time', String(startTime));
  if (endTime != null) params.set('end_time', String(endTime));

  const response = await fetch(
    `${OCE_API_BASE_URL}/applications-with-stateful-eval?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch applications with stateful eval: ${response.statusText}`
    );
  }

  return response.json();
};

export const useApplicationsWithStatefulEval = (
  startTime?: number,
  endTime?: number
) => {
  return useQuery<ApplicationStatefulEvalTotals[]>({
    queryKey: ['applicationsWithStatefulEval', startTime, endTime],
    queryFn: () => fetchApplicationsWithStatefulEval(startTime, endTime)
  });
};

const fetchSessionsWithCognitiveObservability = async (
  startTime?: number,
  endTime?: number
): Promise<SessionsWithCognitiveObservability> => {
  const params = new URLSearchParams();
  if (startTime != null) params.set('start_time', String(startTime));
  if (endTime != null) params.set('end_time', String(endTime));

  // TODO: Remove this once the API is implemented
  // const response = await fetch(
  //   `${OCE_API_BASE_URL}/sessions-with-cognitive-observability?${params.toString()}`
  // );

  const response = {
    ok: true,
    json: () => mockSessionsWithCognitiveObservability,
    statusText: 'OK'
  };

  if (!response.ok) {
    throw new Error(
      `Failed to fetch sessions with cognitive observability: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSessionsWithCognitiveObservability = (
  startTime?: number,
  endTime?: number
) => {
  return useQuery<SessionsWithCognitiveObservability>({
    queryKey: ['sessionsWithCognitiveObservability', startTime, endTime],
    queryFn: () => fetchSessionsWithCognitiveObservability(startTime, endTime)
  });
};

const fetchSessionL9Protocols = async (
  sessionId: string
): Promise<SessionL9Protocols> => {
  // TODO: Remove this once the API is implemented
  // const response = await fetch(
  //   `${OCE_API_BASE_URL}/sessions/${sessionId}/l9-protocols`
  // );

  const response = {
    ok: true,
    json: () =>
      // Sessions without any L9 protocol have an empty list.
      mockSessionL9Protocols[sessionId] ?? { sessionId, protocols: [] },
    statusText: 'OK'
  };

  if (!response.ok) {
    throw new Error(
      `Failed to fetch session L9 protocols: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSessionL9Protocols = (sessionId?: string) => {
  return useQuery<SessionL9Protocols>({
    queryKey: ['sessionL9Protocols', sessionId],
    queryFn: () => fetchSessionL9Protocols(sessionId ?? ''),
    enabled: !!sessionId
  });
};

const fetchSessionsWithL9Protocols = async (
  startTime?: number,
  endTime?: number
): Promise<SessionsWithL9Protocols> => {
  const params = new URLSearchParams();
  if (startTime != null) params.set('start_time', String(startTime));
  if (endTime != null) params.set('end_time', String(endTime));

  // TODO: Remove this once the API is implemented
  // const response = await fetch(
  //   `${OCE_API_BASE_URL}/sessions-with-l9-protocols?${params.toString()}`
  // );

  const response = {
    ok: true,
    json: () => mockSessionsWithL9Protocols,
    statusText: 'OK'
  };

  if (!response.ok) {
    throw new Error(
      `Failed to fetch sessions with L9 protocols: ${response.statusText}`
    );
  }

  return response.json();
};

export const useSessionsWithL9Protocols = (
  startTime?: number,
  endTime?: number
) => {
  return useQuery<SessionsWithL9Protocols>({
    queryKey: ['sessionsWithL9Protocols', startTime, endTime],
    queryFn: () => fetchSessionsWithL9Protocols(startTime, endTime)
  });
};
