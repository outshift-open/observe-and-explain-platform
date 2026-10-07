/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useImpactAssessmentSession } from '@/api/oxpApi';
import { OutlierMetric, Unit } from '@/types/oxp.type';
import { OutlierMetricsTable } from './OutlierMetricsTable';
import { useMemo } from 'react';
import { metricCatalog, unitSuffix } from '@/common';
import { formatDurationMs, formatTwoDecimals } from '@/utils/stringUtils';
import { formatMetricValue } from '@/utils/metrics';
import { useParams } from 'react-router';
import { useNormalBehaviourReport } from '@/api/oxpApi';

interface OutlierMetricsTableWrapperProps {
  sessionId: string;
  outlierMetrics: OutlierMetric[];
}

export const OutlierMetricsTableWrapper = ({
  sessionId,
  outlierMetrics
}: OutlierMetricsTableWrapperProps) => {
  const { semanticGroup } = useParams();

  const {
    data: impactAssessmentData,
    isLoading: isLoadingImpactAssessment,
    isError: isErrorImpactAssessment
  } = useImpactAssessmentSession(sessionId);

  const {
    data: normalBehaviourReportData,
    isLoading: isLoadingNormalBehaviourReport,
    isError: isErrorNormalBehaviourReport
  } = useNormalBehaviourReport(semanticGroup ?? '');

  const normalBehaviourByMetric = useMemo(() => {
    const map = new Map<string, string>();
    normalBehaviourReportData?.reports.forEach((report) => {
      const metricName = JSON.parse(report.metadata).metric;
      map.set(metricName, report.centroid);
    });
    return map;
  }, [normalBehaviourReportData]);

  const outlierMetricsData = useMemo(() => {
    const outlierMetricsWithImpactAssessment = impactAssessmentData?.filter(
      (item) =>
        outlierMetrics.some((metric) => metric.metricKey === item.metric_name)
    );
    return outlierMetricsWithImpactAssessment?.map((item) => {
      const metricValue =
        outlierMetrics.find((metric) => metric.metricKey === item.metric_name)
          ?.value?.value ?? 0;
      const metricUnit =
        outlierMetrics.find((metric) => metric.metricKey === item.metric_name)
          ?.value?.unit ?? Unit.Scalar;
      const formattedValue = formatMetricValue(metricValue, metricUnit);

      const centroid = normalBehaviourByMetric.get(item.metric_name);
      const formattedExpectedValue =
        centroid != null ? formatMetricValue(Number(centroid), metricUnit) : '';

      const rootContributorAgent =
        item.agents.find(
          (agent) =>
            agent.value.value ===
            Math.max(...item.agents.map((agent) => agent.value.value))
        )?.agent_name ?? '';

      return {
        metricKey: item.metric_name,
        metricName:
          metricCatalog[item.metric_name as keyof typeof metricCatalog].name,
        metricValue: formattedValue,
        expectedValue: formattedExpectedValue,
        rootContributorAgent: rootContributorAgent
      };
    });
  }, [impactAssessmentData, outlierMetrics, normalBehaviourByMetric]);

  return (
    <OutlierMetricsTable
      data={outlierMetricsData ?? []}
      isLoading={isLoadingImpactAssessment}
      isError={isErrorImpactAssessment}
    />
  );
};
