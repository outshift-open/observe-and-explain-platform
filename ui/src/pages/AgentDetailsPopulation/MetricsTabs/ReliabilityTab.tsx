/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { Spinner, Stack } from '@open-ui-kit/core';
import { useParams } from 'react-router';
import {
  AgentMetricType,
  AgentReliabilityAndSafetyMetrics
} from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface ReliabilityTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const ReliabilityTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: ReliabilityTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataReliabilityAndSafetyMetrics,
    error: errorReliabilityAndSafetyMetrics,
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

  if (errorReliabilityAndSafetyMetrics?.message) {
    return <>An error occurred!</>;
  }

  if (!dataReliabilityAndSafetyMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      agentId={agentId}
      category={'Reliability & Safety'}
      metricsData={
        dataReliabilityAndSafetyMetrics as AgentReliabilityAndSafetyMetrics
      }
    />
  );
};
