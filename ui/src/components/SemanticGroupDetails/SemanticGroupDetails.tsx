/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Spinner, Typography, Box } from '@open-ui-kit/core';
import { IntervalPicker, SessionsTable } from '@/components';
import { useMemo } from 'react';
import { OutlierSessions } from '../OutlierSessions';
import {
  useAnomalyReport,
  useApplicationSessionsWithStatefulEval,
  useConsistencyReport,
  useImpactAssessmentSemanticGroup,
  useNormalBehaviourReport,
  useNormalBehaviourReportList,
  useSemanticGroups
} from '@/api/oxpApi';
import {
  OutlierSession,
  OutlierMetric,
  Unit,
  Session,
  SessionWithMetrics,
  SessionWithStatefulEval,
  SessionMetric,
  ImpactAssessmentAgent
} from '@/types/oxp.type';
import { useNavigate } from 'react-router-dom';
import { PATHS } from '@/routes/routes';
import { metricCatalog } from '@/common';
import { formatMetricValue } from '@/utils/metrics';
import { MetricSelectorDropdown, useMetricSelector } from '../MetricSelector';
import { MetricCard } from './MetricCard';
import { AgentImpactChart } from '../AgentImpactChart';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { useTimeRangeStore } from '@/store';
import { useDebouncedValue } from '@/utils';

function parseMetricName(metadata: string): string {
  return JSON.parse(metadata).metric;
}

function formatConsistencyMean(mean: number | string): string {
  return `${Math.round(Number(mean) * 100)}%`;
}

interface SemanticGroupDetailsProps {
  semanticGroupId: string;
  applicationId: string;
}

export const SemanticGroupDetails = ({
  semanticGroupId,
  applicationId
}: SemanticGroupDetailsProps) => {
  const impactAssessmentEnabled = useFeatureFlag('impact_assessment');

  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);

  const {
    data: anomalyReportData,
    isLoading: anomalyReportLoading,
    error: anomalyReportError
  } = useAnomalyReport(semanticGroupId);

  const {
    data: impactAssessmentSemanticGroupData,
    isLoading: impactAssessmentSemanticGroupLoading,
    error: impactAssessmentSemanticGroupError
  } = useImpactAssessmentSemanticGroup(
    applicationId,
    semanticGroupId,
    impactAssessmentEnabled
  );

  const {
    data: statefulEvalSessionsData,
    isLoading: statefulEvalSessionsLoading,
    error: statefulEvalSessionsError
  } = useApplicationSessionsWithStatefulEval(
    applicationId,
    debouncedStartDate,
    debouncedEndDate,
    true,
    semanticGroupId
  );

  const {
    data: consistencyReportData,
    isLoading: consistencyReportLoading,
    error: consistencyReportError
  } = useConsistencyReport(semanticGroupId ?? '');

  const metricSelector = useMetricSelector();
  const { selectedMetricKeys } = metricSelector;

  const {
    data: applicationSemanticGroupsData,
    isLoading: applicationSemanticGroupsLoading,
    error: applicationSemanticGroupsError
  } = useSemanticGroups(applicationId);

  const normalBehaviourReportList = useNormalBehaviourReportList(
    applicationSemanticGroupsData?.map((group) => group.id) ?? []
  );

  const {
    data: normalBehaviourReportData,
    isLoading: normalBehaviourReportLoading,
    isError: normalBehaviourReportError
  } = useNormalBehaviourReport(semanticGroupId ?? '');

  const normalBehaviourMetrics = useMemo(() => {
    return (
      normalBehaviourReportData?.reports.map((report) => {
        const metricJSON = JSON.parse(report.metadata);
        const metric = metricJSON.metric;

        return {
          metric: metric,
          centroid: report.centroid
        };
      }) ?? []
    );
  }, [normalBehaviourReportData]);

  const applicationAverageMetrics = useMemo(() => {
    const sums = new Map<string, { total: number; count: number }>();

    for (const query of normalBehaviourReportList) {
      const reports = query.data?.reports;
      if (!reports) continue;

      for (const report of reports) {
        const metricJSON = JSON.parse(report.metadata);
        const metric: string = metricJSON.metric;
        const centroid = Number(report.centroid);
        const entry = sums.get(metric);
        if (entry) {
          entry.total += centroid;
          entry.count += 1;
        } else {
          sums.set(metric, { total: centroid, count: 1 });
        }
      }
    }

    const averages = new Map<string, number>();
    for (const [metric, { total, count }] of sums) {
      averages.set(metric, total / count);
    }
    return averages;
  }, [normalBehaviourReportList]);

  const navigate = useNavigate();

  const statefulEvalSessionsList =
    statefulEvalSessionsData?.sessionList ??
    ([] as SessionWithStatefulEval[] | undefined);

  const outlierSessions = useMemo((): OutlierSession[] => {
    if (!anomalyReportData?.reports || !statefulEvalSessionsList?.length) {
      return [];
    }

    const outlierSessionIdsWithMetrics = new Map<string, Set<string>>();

    for (const report of anomalyReportData.reports) {
      try {
        const metadata = JSON.parse(report.metadata) as {
          model_name: string;
          metric: string;
        };
        const metricName = metadata.metric;

        for (const sessionId of report.outliers_values) {
          if (!outlierSessionIdsWithMetrics.has(sessionId)) {
            outlierSessionIdsWithMetrics.set(sessionId, new Set());
          }
          outlierSessionIdsWithMetrics.get(sessionId)?.add(metricName);
        }
      } catch {
        continue;
      }
    }

    const sessionMetricsMap = new Map<string, SessionMetric[]>();
    for (const session of statefulEvalSessionsList) {
      if (session.session_metrics?.length) {
        sessionMetricsMap.set(session.sessionId, session.session_metrics);
      }
    }

    const result: OutlierSession[] = [];

    for (const [
      sessionId,
      outlierMetricNames
    ] of outlierSessionIdsWithMetrics) {
      const sessionMetrics = sessionMetricsMap.get(sessionId);

      const outlierMetrics: OutlierMetric[] = [];

      for (const metricName of outlierMetricNames) {
        const catalogEntry =
          metricCatalog[metricName as keyof typeof metricCatalog];

        if (!catalogEntry) {
          continue;
        }

        const metricData = sessionMetrics?.find((m) => m.name === metricName);

        if (metricData) {
          outlierMetrics.push({
            metricName: catalogEntry.name,
            metricKey: metricName,
            value: {
              value: metricData.value ?? 0,
              unit: catalogEntry.unit
            }
          });
        } else {
          outlierMetrics.push({
            metricName: catalogEntry.name,
            metricKey: metricName,
            value: {
              value: 0,
              unit: catalogEntry.unit
            }
          });
        }
      }

      if (outlierMetrics.length > 0) {
        result.push({ sessionId, metrics: outlierMetrics });
      }
    }

    return result;
  }, [anomalyReportData, statefulEvalSessionsList]);

  const sessionsWithMetric = useMemo((): SessionWithMetrics[] => {
    if (!statefulEvalSessionsList) return [];

    return statefulEvalSessionsList
      .filter((session) => session.session_metrics?.length)
      .map((session) => ({
        ...session,
        semanticGroupMetrics: session.session_metrics!.map((m) => ({
          name: m.name,
          value: m.value
        }))
      }));
  }, [statefulEvalSessionsList]);

  const onSessionClick = (session: Session) => {
    navigate(
      PATHS.applicationCollectSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
    );
  };

  const onOutlierSessionClick = (session: OutlierSession) => {
    navigate(
      PATHS.applicationCollectSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
    );
  };

  if (
    impactAssessmentSemanticGroupLoading ||
    applicationSemanticGroupsLoading ||
    normalBehaviourReportLoading ||
    consistencyReportLoading ||
    statefulEvalSessionsLoading
  ) {
    return (
      <Stack
        alignItems={'center'}
        justifyContent={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  return (
    <Stack direction={'column'} gap={'32px'} sx={{ width: '100%' }}>
      <Stack
        direction={'row'}
        justifyContent={'flex-start'}
        alignItems={'flex-start'}
        gap={'12px'}
        sx={{ flexWrap: 'wrap' }}
      >
        <MetricSelectorDropdown {...metricSelector} />
        <IntervalPicker
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
        />
      </Stack>
      <Stack direction={'row'} gap={'12px'} sx={{ flexWrap: 'wrap' }}>
        {selectedMetricKeys.map((key) => (
          <MetricCard
            key={key}
            title={metricCatalog[key as keyof typeof metricCatalog].name}
            normalBehavior={formatMetricValue(
              Number(
                normalBehaviourMetrics?.find((m) => m.metric === key)
                  ?.centroid ?? 0
              ),
              metricCatalog[key as keyof typeof metricCatalog].unit
            )}
            applicationAverage={formatMetricValue(
              Number(applicationAverageMetrics.get(key) ?? 0),
              metricCatalog[key as keyof typeof metricCatalog].unit
            )}
            consistency={
              formatConsistencyMean(
                consistencyReportData?.reports?.find(
                  (report) => parseMetricName(report.metadata) === key
                )?.mean ?? 0
              ) ?? 0
            }
            confidence={
              consistencyReportData?.reports?.find(
                (report) => parseMetricName(report.metadata) === key
              )?.confidence_indicator ?? 'High'
            }
            sessionsWithMetric={sessionsWithMetric}
            targetMetricName={key}
            metricUnit={metricCatalog[key as keyof typeof metricCatalog].unit}
            outlierSessionIds={outlierSessions
              .filter((os) =>
                os.metrics.some(
                  (m) =>
                    m.metricName ===
                    metricCatalog[key as keyof typeof metricCatalog].name
                )
              )
              .map((os) => os.sessionId)}
            mostImpactfulAgent={
              impactAssessmentSemanticGroupData
                ?.find((impact) => impact.metric_name === key)
                ?.agents.reduce<
                  ImpactAssessmentAgent | undefined
                >((best, agent) => (!best || agent.value.value > best.value.value ? agent : best), undefined)
                ?.agent_name ?? ''
            }
            mostImpactfulAgentValue={formatMetricValue(
              impactAssessmentSemanticGroupData
                ?.find((impact) => impact.metric_name === key)
                ?.agents.reduce<
                  ImpactAssessmentAgent | undefined
                >((best, agent) => (!best || agent.value.value > best.value.value ? agent : best), undefined)
                ?.value.value ?? 0,
              Unit.Percentage
            )}
          />
        ))}
      </Stack>
      {/* <SemanticGroupNormalBehaviour semanticGroupId={semanticGroupId} selectedMetricKeys={selectedMetricKeys} />

      <SemanticGroupConsistencyReport semanticGroupId={semanticGroupId} selectedMetricKeys={selectedMetricKeys} />

      <ImpactDistribution data={impactAssessmentSemanticGroupData ?? []} title="Agent impact distribution" /> */}
      {impactAssessmentEnabled && !impactAssessmentSemanticGroupError && (
        <AgentImpactChart
          impactAssessmentData={impactAssessmentSemanticGroupData}
          selectedMetricKeys={selectedMetricKeys}
          title="Agent Impact on Semantic Group"
        />
      )}
      <SessionsTable
        title={'Member Sessions'}
        startDate={startDate}
        endDate={endDate}
        onSessionClick={onSessionClick}
        defaultHiddenColumns={['llms', 'tokens', 'status']}
        semanticGroupId={semanticGroupId}
      />
      <OutlierSessions
        title={'Outliers Sessions'}
        startDate={null}
        endDate={null}
        onSessionClick={onOutlierSessionClick}
        data={outlierSessions}
        isLoading={anomalyReportLoading || statefulEvalSessionsLoading}
        isError={
          Boolean(anomalyReportError) || Boolean(statefulEvalSessionsError)
        }
        showDateInterval={false}
        defaultHiddenColumns={['llms', 'tokens', 'status']}
      />
    </Stack>
  );
};
