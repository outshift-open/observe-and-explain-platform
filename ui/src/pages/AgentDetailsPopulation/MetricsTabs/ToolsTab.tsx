/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Spinner, Stack, Typography } from '@open-ui-kit/core';
import { useParams } from 'react-router';
import { MetricChart, WidgetCard } from '@/components';
import { generateTimelineData } from '@/utils';
import { unitSuffix } from '@/common/constants';
import { Unit } from '@/types/oxp.type';
import { useAgentMetrics } from '@/api/oxpApi';
import { AgentMetricType, AgentToolsMetrics } from '@/types/oxp.type';

interface ToolsTabProps {
  agentId: string;
  startTime: number;
  endTime: number;
  metricType: AgentMetricType;
}

const size = { xxl: 2, xl: 3, lg: 4, md: 4 };

const toolMetrics = [
  {
    name: 'Evaluate Expression',
    description: `This tool evaluates mathematical expressions provided in string format.
    Input: A string containing a Python formatted mathematical expression (e.g., "3**2 + 1").
    Output: The result of evaluating the expression (e.g., "10").`,
    metrics: {
      toolUtilisation: '93%',
      toolErrorRate: '10%',
      toolSuccessRate: '90%',
      toolRetryRate: '5%',
      toolUtilizationAccuracyScore: '90%',
      toolDuration: generateTimelineData(25, 10)
    }
  }
];

export const ToolsTab = ({
  agentId,
  startTime,
  endTime,
  metricType
}: ToolsTabProps) => {
  const { applicationId } = useParams();

  const {
    data: dataToolsMetrics,
    error: errorToolsMetrics,
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

  if (errorToolsMetrics?.message) {
    return <>An error occurred!</>;
  }

  if (!dataToolsMetrics) {
    return null;
  }

  return (
    <Stack direction={'row'} gap={'12px'} sx={{ overflow: 'auto' }}>
      {(dataToolsMetrics as AgentToolsMetrics).toolDetails?.length > 0 ? (
        <Stack direction={'row'} gap={'8px'}>
          {(dataToolsMetrics as AgentToolsMetrics).toolDetails.map((tool) => (
            <Stack direction={'column'} gap={'12px'}>
              <WidgetCard
                title={'Name'}
                content={
                  <Typography variant={'h5'}>{tool.toolName}</Typography>
                }
                cardSx={{ width: '452px' }}
              />

              <WidgetCard
                title={'Tool Utilisation'}
                description={'The percentage of times the tool was used.'}
                content={
                  <Typography variant={'h5'}>
                    {tool.utilization.value}
                    {unitSuffix[tool.utilization.unit ?? Unit.Percentage]}
                  </Typography>
                }
                cardSx={{ width: '452px' }}
              />

              <MetricChart
                data={tool.toolDuration ?? []}
                metricKey={'toolDuration'}
                metricDef={{
                  name: 'Tool Duration',
                  description:
                    'The average time taken for the tool to execute and return a result.'
                }}
                chartSuffix={'s'}
                operation={'average'}
                containerSx={{ width: '452px' }}
              />

              <WidgetCard
                title={'Tool Error Rate'}
                description={'The rate at which tool calls fail.'}
                content={
                  <Typography variant={'h5'}>
                    {tool.errorRate.value}
                    {unitSuffix[tool.errorRate.unit ?? Unit.Percentage]}
                  </Typography>
                }
                cardSx={{ width: '452px' }}
              />

              <WidgetCard
                title={'Tool Success Rate'}
                description={'The rate at which tool calls succeed.'}
                content={
                  <Typography variant={'h5'}>
                    {tool.successRate.value}
                    {unitSuffix[tool.successRate.unit ?? Unit.Percentage]}
                  </Typography>
                }
                cardSx={{ width: '452px' }}
              />

              <WidgetCard
                title={'Tool Retry Rate'}
                description={'The rate at which tool calls are retried.'}
                content={
                  <Typography variant={'h5'}>
                    {tool.retryRate.value}
                    {unitSuffix[tool.retryRate.unit ?? Unit.Percentage]}
                  </Typography>
                }
                cardSx={{ width: '452px' }}
              />

              <WidgetCard
                title={'Tool Utilization Accuracy Score'}
                description={
                  'A score reflecting the quality and correctness of the output received from a tool.'
                }
                content={
                  <Typography variant={'h5'}>
                    {tool.utilizationAccuracyScore.value}
                    {
                      unitSuffix[
                        tool.utilizationAccuracyScore.unit ?? Unit.Percentage
                      ]
                    }
                  </Typography>
                }
                cardSx={{ width: '452px' }}
              />
            </Stack>
          ))}
        </Stack>
      ) : (
        <Typography variant={'h5'}>No tools found</Typography>
      )}
    </Stack>
  );
};
