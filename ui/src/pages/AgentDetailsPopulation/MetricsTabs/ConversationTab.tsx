/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Spinner, Stack } from '@open-ui-kit/core';
import MetricsGrid from '../MetricsGrid';
import { useParams } from 'react-router';
import { AgentConversationMetrics, AgentMetricType } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface ConversationTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const ConversationTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: ConversationTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataConversationMetrics,
    error: errorConversationMetrics,
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

  if (errorConversationMetrics) {
    return <>An error occurred!</>;
  }

  if (!dataConversationMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      agentId={agentId}
      category={'Conversation'}
      metricsData={dataConversationMetrics as AgentConversationMetrics}
    />
  );
};
