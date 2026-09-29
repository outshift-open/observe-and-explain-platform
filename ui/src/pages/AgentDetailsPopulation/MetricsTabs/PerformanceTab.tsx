/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import MetricsGrid from '../MetricsGrid';
import { Box, Spinner, Stack } from '@open-ui-kit/core';
import { useParams } from 'react-router';
import AgentErrorBreakdown from '@/components/AgentErrorBreakdown';
import { AgentMetricType, AgentPerformanceMetrics } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';

interface PerformanceTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

export const PerformanceTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: PerformanceTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataPerformanceMetrics,
    error: errorPerformanceMetrics,
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

  if (errorPerformanceMetrics) {
    return <>An error occurred!</>;
  }

  if (!dataPerformanceMetrics) {
    return null;
  }

  return (
    <Stack direction={'column'} gap={'24px'}>
      <MetricsGrid
        agentId={agentId}
        category={'Performance'}
        metricsData={dataPerformanceMetrics as AgentPerformanceMetrics}
      />
      <Box
        sx={{
          '& > .MuiPaper-root': {
            padding: 0
          }
        }}
      >
        <AgentErrorBreakdown
          data={
            (dataPerformanceMetrics as AgentPerformanceMetrics)
              .errorsBreakdown ?? []
          }
        />
      </Box>
    </Stack>
  );
};
