/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo } from 'react';
import { Stack, CircularProgress } from '@mui/material';
import {
  CostEfficiencyGrouppedSessions,
  SessionsCostEfficiencyDistribution,
  LeastEfficientSessions
} from '@/components';
import { DEFAULT_END_DATE, DEFAULT_START_DATE } from '@/common/constants';
import { useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/routes/routes';
import { useCostEfficiencyGrouppedSessions } from '@/api/oxpApi';

export const ResourcesUsage = () => {
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useCostEfficiencyGrouppedSessions(
    applicationId ?? ''
  );

  // Top 10 groups by highest max costEfficiency across all sessions
  const top10Groups = useMemo(() => {
    if (!data || data.length === 0) return [];

    const grouped = new Map<
      string,
      { label: string; maxCostEfficiency: number }
    >();
    for (const item of data) {
      const label = item.groupName;
      if (!label) continue;
      const existing = grouped.get(item.groupId);
      if (!existing) {
        grouped.set(item.groupId, {
          label,
          maxCostEfficiency: item.costEfficiency
        });
      } else if (item.costEfficiency > existing.maxCostEfficiency) {
        existing.maxCostEfficiency = item.costEfficiency;
      }
    }

    return [...grouped.entries()]
      .sort((a, b) => b[1].maxCostEfficiency - a[1].maxCostEfficiency)
      .slice(0, 10)
      .map(([groupId, g]) => ({ groupId, label: g.label }));
  }, [data]);

  if (isLoading) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ height: 300 }}>
        <CircularProgress size={32} />
      </Stack>
    );
  }

  if (isError) {
    return 'An error occurred!';
  }

  return (
    <Stack direction={'column'} gap={'24px'}>
      <CostEfficiencyGrouppedSessions
        data={data ?? []}
        allGroups={top10Groups ?? []}
      />
      <SessionsCostEfficiencyDistribution
        data={data ?? []}
        allGroups={top10Groups ?? []}
      />
      <LeastEfficientSessions
        startDate={DEFAULT_START_DATE}
        endDate={DEFAULT_END_DATE}
        onSessionClick={(session) => {
          navigate(
            PATHS.applicationCollectSession
              .replace(':applicationId', applicationId ?? '')
              .replace(':sessionId', encodeURIComponent(session.sessionId))
          );
        }}
        onGroupClick={(groupId) => {
          navigate(
            `/applications/${applicationId}/analyze/overview/${encodeURIComponent(groupId)}`
          );
        }}
        showDateInterval={false}
        applicationId={applicationId ?? ''}
      />
    </Stack>
  );
};
