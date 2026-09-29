/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { Spinner, Stack } from '@open-ui-kit/core';
import { useParams } from 'react-router';
import {
  AgentMetricType,
  AgentQualityAndReasoningMetrics
} from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface QualityReasoningTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const QualityReasoningTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: QualityReasoningTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataQualityAndReasoningMetrics,
    error: errorQualityAndReasoningMetrics,
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

  if (errorQualityAndReasoningMetrics?.message) {
    return <>An error occurred!</>;
  }

  if (!dataQualityAndReasoningMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      agentId={agentId}
      category={'Quality & Reasoning'}
      metricsData={
        dataQualityAndReasoningMetrics as AgentQualityAndReasoningMetrics
      }
    />
  );
};
