/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo } from 'react';
import { useParams } from 'react-router';
import {
  Banner,
  Divider,
  EmptyState,
  OverflowTooltip,
  Skeleton
} from '@open-ui-kit/core';
import CategoryOutlinedIcon from '@mui/icons-material/CategoryOutlined';
import {
  Box,
  LinearProgress,
  Stack,
  Typography,
  useTheme
} from '@mui/material';
import {
  RemediationTags,
  ScoreSeverityBadgeLabel,
  WidgetCard
} from '@/components';
import { useSessionsWithCognitiveObservability } from '@/api/oxpApi';
import { useTimeRangeStore } from '@/store';
import {
  COGNITIVE_METRIC_GROUPS,
  FAILURE_CONFIDENCE_THRESHOLD
} from '@/common/cognitiveFailures';
import { getScoreColor } from '@/utils/metrics';
import { CognitiveObservabilityMetric, Unit } from '@/types/oxp.type';
import { COGNITIVE_FAILURE_DESCRIPTIONS } from '@/common/cognitiveFailures';

const toScore = (metric: CognitiveObservabilityMetric): number =>
  metric.value.unit === Unit.Percentage
    ? metric.value.value * 100
    : metric.value.value;

const average = (scores: number[]): number =>
  scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;

const formatPercent = (fraction: number) => `${Math.round(fraction * 100)}%`;

export const CognitiveObservabilityTab = () => {
  const theme = useTheme();
  const { sessionId } = useParams();
  const { startDate, endDate } = useTimeRangeStore();

  const { data, isLoading, isError } = useSessionsWithCognitiveObservability(
    startDate,
    endDate
  );

  const session = useMemo(
    () => data?.sessions?.find((s) => s.sessionId === sessionId),
    [data?.sessions, sessionId]
  );

  const failures = useMemo(
    () =>
      [...(session?.cognitiveFailures ?? [])].sort(
        (a, b) => b.confidence - a.confidence
      ),
    [session?.cognitiveFailures]
  );

  const highConfidenceFailures = failures.filter(
    (failure) => failure.confidence > FAILURE_CONFIDENCE_THRESHOLD
  ).length;

  // Metrics split into the configured groups; metrics outside every group go
  // into an extra "Other" column so none is hidden.
  const metricGroups = useMemo(() => {
    const metrics = session?.cognitiveObservabilityMetrics ?? [];
    const byName = new Map(metrics.map((m) => [m.name.toLowerCase(), m]));
    const used = new Set<string>();

    const groups = COGNITIVE_METRIC_GROUPS.map((group) => {
      const groupMetrics = group.metrics.flatMap((name) => {
        const metric = byName.get(name.toLowerCase());
        if (!metric) return [];
        used.add(name.toLowerCase());
        return [metric];
      });
      return {
        title: group.title,
        icon: group.icon,
        metrics: groupMetrics,
        score: average(groupMetrics.map(toScore))
      };
    });

    const other = metrics.filter((m) => !used.has(m.name.toLowerCase()));
    return other.length > 0
      ? [
          ...groups,
          {
            title: 'Other',
            icon: CategoryOutlinedIcon,
            metrics: other,
            score: average(other.map(toScore))
          }
        ]
      : groups;
  }, [session?.cognitiveObservabilityMetrics]);

  if (isLoading) {
    return (
      <Stack direction="column" gap="16px" sx={{ paddingTop: '16px' }}>
        <Skeleton variant="rounded" height={48} />
        <Stack direction="row" gap="16px">
          <Skeleton variant="rounded" width={300} height={120} />
          <Skeleton variant="rounded" width={300} height={120} />
          <Skeleton variant="rounded" width={300} height={120} />
        </Stack>
        <Skeleton variant="rounded" height={240} />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Banner
        status="negative"
        text="Failed to load cognitive observability data."
      />
    );
  }

  if (!session) {
    return <EmptyState title="No data found" description="" />;
  }

  return (
    <Stack direction="column" gap="24px" sx={{ paddingTop: '16px' }}>
      <Banner
        status={
          highConfidenceFailures > 0
            ? 'warning'
            : failures.length > 0
              ? 'info'
              : 'success'
        }
        text={
          failures.length === 0
            ? 'No cognitive failures detected for this session.'
            : `${failures.length} cognitive failure${
                failures.length === 1 ? '' : 's'
              } detected, ${highConfidenceFailures} with confidence above ${
                FAILURE_CONFIDENCE_THRESHOLD * 100
              }%.`
        }
      />

      <Stack direction="column" gap="8px">
        <Typography variant={'h6'}>Cognitive Failures</Typography>
        {failures.length === 0 ? (
          <Typography variant={'body2'}>
            No cognitive failures detected for this session.
          </Typography>
        ) : (
          <Stack direction="row" gap="8px" sx={{ flexWrap: 'wrap' }}>
            {failures.map((failure) => (
              <WidgetCard
                key={failure.name}
                title={failure.name}
                description={COGNITIVE_FAILURE_DESCRIPTIONS[failure.name]}
                content={
                  <Stack direction="column" gap="8px" sx={{ width: '100%' }}>
                    <ScoreSeverityBadgeLabel
                      score={failure.confidence * 100}
                      label={formatPercent(failure.confidence)}
                    />
                    <RemediationTags remediations={failure.remediations} />
                  </Stack>
                }
                cardSx={{ width: '350px' }}
              />
            ))}
          </Stack>
        )}
      </Stack>

      <Stack direction="column" gap="8px">
        <Typography variant={'h6'}>Cognitive Metrics</Typography>
        {metricGroups.every((group) => group.metrics.length === 0) ? (
          <Typography variant={'body2'}>
            No cognitive metrics available for this session.
          </Typography>
        ) : (
          <Stack direction="row" gap="24px" alignItems="stretch">
            {metricGroups.map((group, index) => (
              <Stack
                key={group.title}
                direction="row"
                gap="24px"
                sx={{ flex: 1, minWidth: 0 }}
              >
                {index > 0 && <Divider orientation="vertical" flexItem />}
                <Stack
                  direction="column"
                  gap="12px"
                  sx={{ flex: 1, minWidth: 0 }}
                >
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                    sx={{
                      paddingBottom: '8px',
                      borderBottom: `1px solid ${theme.palette.vars.baseBorderWeak}`
                    }}
                  >
                    <Stack direction="row" alignItems="center" gap="8px">
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: 24,
                          height: 24,
                          borderRadius: '50%',
                          fontSize: 14,
                          color:
                            theme.palette.vars.interactivePrimaryDefaultDefault,
                          backgroundColor:
                            theme.palette.vars.controlBackgroundMedium
                        }}
                      >
                        <group.icon fontSize="inherit" />
                      </Box>
                      <Typography
                        variant={'caption'}
                        sx={{
                          color: theme.palette.vars.baseTextWeak,
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          fontWeight: 600
                        }}
                      >
                        {group.title}
                      </Typography>
                    </Stack>
                    <ScoreSeverityBadgeLabel
                      score={group.score}
                      label={`${Math.round(group.score)}% avg`}
                    />
                  </Stack>
                  {group.metrics.length === 0 ? (
                    <Typography variant={'body2'}>No metrics.</Typography>
                  ) : (
                    group.metrics.map((metric) => {
                      const score = toScore(metric);
                      const color = getScoreColor(score, theme);
                      return (
                        <Stack key={metric.name} direction="column" gap="4px">
                          <Stack
                            direction="row"
                            justifyContent="space-between"
                            gap="8px"
                          >
                            <OverflowTooltip value={metric.name}>
                              <Typography variant={'body2'}>
                                {metric.name}
                              </Typography>
                            </OverflowTooltip>
                            <Typography variant={'body2Semibold'}>
                              {`${Math.round(score)}%`}
                            </Typography>
                          </Stack>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(100, Math.max(0, score))}
                            sx={{
                              height: 6,
                              borderRadius: 3,
                              backgroundColor:
                                theme.palette.vars.controlBackgroundMedium,
                              '& .MuiLinearProgress-bar': {
                                backgroundColor: color,
                                borderRadius: 3
                              }
                            }}
                          />
                        </Stack>
                      );
                    })
                  )}
                </Stack>
              </Stack>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
};
