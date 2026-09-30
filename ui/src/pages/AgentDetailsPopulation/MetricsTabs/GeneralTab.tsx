/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { useParams } from 'react-router';
import { Spinner, Stack } from '@open-ui-kit/core';
import { AgentGeneralMetrics, AgentMetricType } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface GeneralTabProps {
  startTime: number;
  endTime: number;
  agentId: string;
  metricType: AgentMetricType;
}

export const GeneralTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: GeneralTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataGeneralMetrics,
    error: errorGeneralMetrics,
    isLoading: fetchingGeneralMetrics
  } = useAgentMetrics(
    applicationId ?? '',
    agentId,
    metricType,
    startTime,
    endTime
  );

  if (fetchingGeneralMetrics) {
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

  if (errorGeneralMetrics?.message) {
    return <>An error occurred!</>;
  }

  if (!dataGeneralMetrics) {
    return null;
  }

  return (
    <MetricsGrid
      metricsData={dataGeneralMetrics as AgentGeneralMetrics}
      category={'General'}
      agentId={agentId}
    />
  );
};
