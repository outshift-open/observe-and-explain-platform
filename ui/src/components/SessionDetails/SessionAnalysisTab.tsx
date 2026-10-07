/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Grid, Stack, Typography, alpha, useTheme } from '@mui/material';
import { useNavigate, useParams } from 'react-router';
import { useCallback, useMemo } from 'react';
import { SessionLatentSpace } from './SessionLatentSpace';
import { transformLatentSpaceResponse } from '@/utils/latentSpace';
import {
  WidgetCard,
  MetricSelectorDropdown,
  useMetricSelector,
  SingleSessionInsightsList
} from '@/components';
import { formatMetricValue } from '@/utils/metrics';
import {
  useAnomalyReport,
  useImpactAssessmentSession,
  useSemanticGroups,
  useSessionLatentSpace,
  useSessionStatefulEval
} from '@/api/oxpApi';
import { Spinner } from '@open-ui-kit/core';
import { metricCatalog } from '@/common';
import { Unit } from '@/types/oxp.type';
import { PATHS } from '@/routes/routes';
import { AgentImpactChart } from '../AgentImpactChart';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';

export const SessionAnalysisTab = () => {
  const { sessionId, applicationId } = useParams();
  const theme = useTheme();
  const navigate = useNavigate();
  const metricSelector = useMetricSelector();
  const { selectedMetricKeys } = metricSelector;

  const insightsEnabled = useFeatureFlag('insights');
  const impactAssessmentEnabled = useFeatureFlag('impact_assessment');

  const {
    data: latentSpaceResponse,
    isLoading: isLatentSpaceLoading,
    error: latentSpaceError
  } = useSessionLatentSpace(sessionId ?? '');

  const sessionMetricsQuery = useSessionStatefulEval(sessionId ?? '');

  const {
    data: impactAssessmentSession,
    isLoading: isImpactAssessmentSessionLoading,
    error: impactAssessmentSessionError
  } = useImpactAssessmentSession(sessionId ?? '', impactAssessmentEnabled);

  const { data: semanticGroupsData } = useSemanticGroups(applicationId ?? '');

  const sessionSemanticGroupId = useMemo(() => {
    if (!semanticGroupsData || !sessionId) return '';
    return (
      semanticGroupsData.find((group) => group.session_ids.includes(sessionId))
        ?.id ?? ''
    );
  }, [semanticGroupsData, sessionId]);

  const isClickable = !!applicationId && !!sessionSemanticGroupId;

  const cardSxOverride = { width: '100%' };

  const outlierCardSx = {
    ...cardSxOverride,
    // Use the `background` shorthand (not `backgroundColor`): WidgetCard renders
    // its Card with the `connector` treatment, whose own `background` shorthand
    // paints gradient layers that mask a plain `backgroundColor` override.
    background: alpha(theme.palette.vars.negativeBackgroundDefault, 0.6),
    cursor: isClickable ? 'pointer' : 'default',
    '&:hover': isClickable
      ? {
          background: alpha(theme.palette.vars.negativeBackgroundDefault, 0.7)
        }
      : undefined
  };

  const baseCardSx = {
    ...cardSxOverride,
    cursor: isClickable ? 'pointer' : 'default',
    '&:hover': isClickable
      ? { backgroundColor: theme.palette.vars.baseBackgroundMedium }
      : undefined
  };

  const { data: anomalyReportData } = useAnomalyReport(sessionSemanticGroupId);

  const outlierMetricNames = useMemo(() => {
    const metrics = new Set<string>();
    if (!anomalyReportData?.reports || !sessionId) return metrics;

    for (const report of anomalyReportData.reports) {
      if (!report.outliers_values.includes(sessionId)) continue;
      try {
        const metadata = JSON.parse(report.metadata) as { metric: string };
        metrics.add(metadata.metric);
      } catch {
        continue;
      }
    }
    return metrics;
  }, [anomalyReportData, sessionId]);

  const latentSpaceData = useMemo(() => {
    if (!latentSpaceResponse) return null;
    return transformLatentSpaceResponse(latentSpaceResponse);
  }, [latentSpaceResponse]);

  const sessionMetrics = useMemo(() => {
    const metricsData = sessionMetricsQuery.data?.metrics;
    if (!metricsData) return null;

    const result: Record<
      string,
      { value: string | number; unit: Unit; name: string }
    > = {};

    for (const metric of metricsData) {
      const catalogEntry =
        metricCatalog[metric.name as keyof typeof metricCatalog];

      if (!catalogEntry) {
        continue;
      }

      const metricValue = metric.value ?? 0;
      const formattedValue = formatMetricValue(
        Number(metricValue),
        catalogEntry.unit
      );
      result[metric.name] = {
        value: formattedValue,
        unit: catalogEntry.unit,
        name: catalogEntry.name
      };
    }

    return result;
  }, [sessionMetricsQuery.data]);

  const handleMetricCardClick = useCallback(() => {
    if (!applicationId || !sessionSemanticGroupId) return;
    navigate(
      PATHS.applicationAnalyzeOverviewSemanticGroup
        .replace(':applicationId', applicationId)
        .replace(':semanticGroup', sessionSemanticGroupId)
    );
  }, [navigate, applicationId, sessionSemanticGroupId]);

  if (!sessionId) {
    return null;
  }

  if (sessionMetricsQuery.isLoading) {
    return (
      <Stack
        justifyContent={'center'}
        alignItems={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (sessionMetricsQuery.isError) {
    return (
      <Typography variant={'h6'}>Error fetching session metrics</Typography>
    );
  }

  return (
    <Stack direction={'row'}>
      <Stack
        direction={'column'}
        gap={'32px'}
        sx={{ paddingTop: '16px', width: '100%', height: '100%' }}
      >
        <MetricSelectorDropdown {...metricSelector} />

        <Grid container spacing={'8px'} columns={10}>
          {selectedMetricKeys.map((key) => {
            const catalogEntry =
              metricCatalog[key as keyof typeof metricCatalog];
            if (!catalogEntry) return null;
            return (
              <Grid key={key} size={{ md: 5, lg: 2 }}>
                <WidgetCard
                  title={catalogEntry.name}
                  content={
                    <Typography variant={'h6'}>
                      {sessionMetrics?.[key]?.value ?? '—'}
                    </Typography>
                  }
                  cardSx={
                    outlierMetricNames.has(key) ? outlierCardSx : baseCardSx
                  }
                  onClick={handleMetricCardClick}
                />
              </Grid>
            );
          })}
        </Grid>

        {impactAssessmentEnabled &&
          (isImpactAssessmentSessionLoading ? (
            <Stack
              justifyContent={'center'}
              alignItems={'center'}
              sx={{ width: '100%', height: '300px' }}
            >
              <Spinner />
            </Stack>
          ) : impactAssessmentSessionError ? (
            <Typography color="text.secondary">
              An error occurred while loading impact distribution data.
            </Typography>
          ) : (
            <AgentImpactChart
              impactAssessmentData={impactAssessmentSession}
              selectedMetricKeys={selectedMetricKeys}
              title="Agent Impact on Session"
            />
          ))}

        {isLatentSpaceLoading ? (
          <Stack
            justifyContent={'center'}
            alignItems={'center'}
            sx={{ width: '100%', height: '100%' }}
          >
            <Spinner />
          </Stack>
        ) : latentSpaceError ? (
          <>An error occurred while loading latent space data!</>
        ) : latentSpaceData ? (
          <SessionLatentSpace
            data={latentSpaceData}
            title="Session Trajectory in Latent Space"
            width={900}
            height={500}
          />
        ) : (
          <Box sx={{ pt: 2, width: '100%', height: '100%' }}>
            <Typography color="text.secondary">
              No latent space data available for this session.
            </Typography>
          </Box>
        )}
      </Stack>
      {sessionId && insightsEnabled && (
        <SingleSessionInsightsList sessionId={sessionId} />
      )}
    </Stack>
  );
};
