/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { Spinner, Stack } from '@open-ui-kit/core';
import { useParams } from 'react-router';
import { AgentCostMetrics, AgentMetricType } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface CostTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const CostTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: CostTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataCostMetrics,
    error: errorCostMetrics,
    isLoading
  } = useAgentMetrics(
    applicationId ?? '',
    agentId,
    metricType,
    startTime,
    endTime
  );

  if (isLoading) {
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

  if (errorCostMetrics?.message) {
    return <>An error occurred!</>;
  }

  if (!dataCostMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      agentId={agentId}
      category={'Cost'}
      metricsData={dataCostMetrics as AgentCostMetrics}
    />
  );
};
