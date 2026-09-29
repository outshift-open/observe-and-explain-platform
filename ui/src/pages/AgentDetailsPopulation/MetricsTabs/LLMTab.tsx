/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { useParams } from 'react-router';
import { Spinner, Stack } from '@open-ui-kit/core';
import { AgentLLMMetrics, AgentMetricType } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface LLMTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const LLMTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: LLMTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataLLMMetrics,
    error: errorLLMMetrics,
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

  if (errorLLMMetrics) {
    return <>An error occurred!</>;
  }

  if (!dataLLMMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      agentId={agentId}
      category={'LLM'}
      metricsData={dataLLMMetrics as AgentLLMMetrics}
    />
  );
};
