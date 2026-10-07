/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Button, Stack } from '@open-ui-kit/core';
import { useDebouncedValue } from '@/utils';
import { Typography, useTheme } from '@mui/material';
import { IntervalPicker } from '@/components/IntervalPicker';
import { useTimeRangeStore } from '@/store';
import { format } from 'date-fns';
import dayjs from 'dayjs';
import { Spinner } from '@open-ui-kit/core';
import { WidgetCard } from '@/components';
import { BiaxialMetricChart } from '@/components/BiaxialMetricChart';
import {
  getDisplayedResultsCount,
  formatTwoDecimals,
  formatDurationMs
} from '@/utils';
import {
  useApplicationMetrics,
  useApplicationSummaryMetrics,
  useAgenticProtocolsMetrics
} from '@/api/oxpApi';
import { useParams } from 'react-router';
import { useMemo } from 'react';
import { Box } from '@mui/material';
import { unitSuffix } from '@/common/constants';
import { Unit } from '@/types/oxp.type';
import {
  computeOverallQuality,
  computeOverallReliability,
  computeOverallPerformance
} from '@/utils/metrics';
import { ApplicationLevelMetricCategory } from '@/api/applicationLevelMetrics';
import ApplicationLevelMetricDrawer from '@/components/ApplicationLevelMetricDrawer';
import { ApplicationMetricScoreCard } from './ApplicationMetricScoreCard';

const totalCostCharDef = {
  name: 'Avg Total Cost',
  description: 'Average total cost of LLM and Tools operations.'
};

export const ApplicationTab = () => {
  const [showMoreMetrics, setShowMoreMetrics] = useState(false);

  const { applicationId } = useParams();
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);

  const { data, isLoading } = useApplicationMetrics(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );
  const {
    data: agenticProtocolsMetricsData,
    error: errorAgenticProtocolsMetrics,
    isLoading: fetchingAgenticProtocolsMetrics
  } = useAgenticProtocolsMetrics(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate,
    !isLoading
  );

  const [selectedMetricCategory, setSelectedMetricCategory] =
    useState<ApplicationLevelMetricCategory | null>();

  const {
    data: applicationSummaryMetricsData,
    isLoading: isLoadingApplicationSummaryMetrics
  } = useApplicationSummaryMetrics(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );

  const averageCostDollars = useMemo(() => {
    const totalCost = data?.totalCost ?? [];
    const dataWithSessions = totalCost.filter(
      (item) => item.sessionIDs.length > 0
    );

    if (dataWithSessions.length === 0) {
      return 0;
    }

    return (
      dataWithSessions.reduce((acc, curr) => acc + curr.value.value, 0) /
      dataWithSessions.length
    );
  }, [data?.totalCost]);

  const averageTokens = useMemo(() => {
    const totalTokens = data?.totalTokens ?? [];
    const dataWithSessions = totalTokens.filter(
      (item) => item.sessionIDs.length > 0
    );

    if (dataWithSessions.length === 0) {
      return 0;
    }

    return (
      dataWithSessions.reduce((acc, curr) => acc + curr.value.value, 0) /
      dataWithSessions.length
    );
  }, [data?.totalTokens]);

  const totalCostData = useMemo(() => {
    const totalCost = data?.totalCost ?? [];

    return totalCost?.map((item) => ({
      date: item.timestamp,
      totalCost: item.value.value,
      // totalCost: 0,
      totalTokens: Math.round((Number(item.value.value) ?? 0) * 400000)
    }));
  }, [data?.totalCost]);

  const overallQuality = useMemo(
    () => computeOverallQuality(applicationSummaryMetricsData?.quality ?? []),
    [applicationSummaryMetricsData?.quality]
  );

  const overallReliability = useMemo(
    () =>
      computeOverallReliability(
        applicationSummaryMetricsData?.reliability ?? []
      ),
    [applicationSummaryMetricsData?.reliability]
  );

  const overallPerformance = useMemo(
    () =>
      computeOverallPerformance(
        applicationSummaryMetricsData?.performance ?? []
      ),
    [applicationSummaryMetricsData?.performance]
  );

  const getDurationTitleContent = () => {
    return (
      <Typography variant={'h6'}>
        {formatDurationMs(data?.sessionDuration.value)}
      </Typography>
    );
  };

  const getMostFrequentErrorsTooltip = () => {
    if (!data?.mostFrequentErrors.count) {
      return 'Top recurring error examples are not available for this application.';
    }

    const agentErrors = Object.entries(data?.mostFrequentErrors.list ?? []);

    return agentErrors.map(([id, error]) => `${error}`).join('\n');
  };

  return (
    <Stack direction={'column'} gap={'16px'} sx={{ height: '100%' }}>
      <Stack direction={'column'} gap={'16px'}>
        <IntervalPicker
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
        />

        <Stack direction="row" gap={'8px'}>
          <Typography variant={'body2Semibold'}>
            {startDate
              ? format(dayjs.unix(startDate).toDate(), 'MMM d, yyyy HH:mm:ss')
              : ''}
          </Typography>
          <Typography variant={'body2Semibold'}>-</Typography>
          <Typography variant={'body2Semibold'}>
            {endDate
              ? format(dayjs.unix(endDate).toDate(), 'MMM d, yyyy HH:mm:ss')
              : ''}
          </Typography>
        </Stack>
      </Stack>

      {isLoading ? (
        <Stack
          alignItems={'center'}
          justifyContent={'center'}
          sx={{ width: '100%', height: '100%', minHeight: '100px' }}
        >
          <Spinner />
        </Stack>
      ) : (
        <Stack direction={'column'} gap={'16px'}>
          <Stack direction={'row'} gap={'16px'}>
            <ApplicationMetricScoreCard
              category={'reliability'}
              value={overallReliability}
              onSelect={setSelectedMetricCategory}
            />
            <ApplicationMetricScoreCard
              category={'quality'}
              value={overallQuality}
              onSelect={setSelectedMetricCategory}
            />
            <ApplicationMetricScoreCard
              category={'performance'}
              value={overallPerformance}
              onSelect={setSelectedMetricCategory}
            />
          </Stack>
          <Stack
            direction={'row'}
            gap={'16px'}
            justifyContent={'space-between'}
          >
            <Box sx={{ width: '932px' }}>
              <BiaxialMetricChart
                data={totalCostData ?? []}
                // dataLeft={generateTimelineData(25)}
                // dataRight={generateTimelineData(25, 1000)}
                metricKeyLeft={'totalCost'}
                metricKeyRight={'totalTokens'}
                legendLabelLeft={'Total Cost'}
                legendLabelRight={'Total Tokens'}
                metricDef={totalCostCharDef}
                chartSuffixLeft={'$'}
                chartSuffixRight={' tokens'}
                operationLeftValue={averageCostDollars}
                operationRightValue={Math.round(averageTokens)}
                valueFormatterLeft={(v?: number) =>
                  `${formatTwoDecimals(v ?? 0)}$`
                }
                valueFormatterRight={(v?: number) =>
                  `${getDisplayedResultsCount(v ?? 0)} tokens`
                }
              />
            </Box>

            {/* <WidgetCard
              title={'Overall Performance Score'}
              description={
                'Overall application performance score, aggregated from key metrics like Overall task completion, Workflow efficiency, Tool utilisation accuracy score, Answer relevancy and Answer groundness.'
              }
              content={
                <Stack direction={'column'} gap={'8px'}>
                  <Typography variant={'h6'}>{formatTwoDecimals(data?.overallPerformanceScore.value ?? 0)}%</Typography>
                  <PerformanceSpiderChart
                    overallTaskCompletion={data?.overallTaskCompletion.value ?? 0}
                    workflowEfficiency={data?.workflowEfficiency.value ?? 0}
                    toolUtilisationAccuracyScore={data?.toolUtilisationAccuracyScore.value ?? 0}
                    answerRelevancy={data?.answerRelevancy.value ?? 0}
                    answerGroundedness={data?.answerGroundedness.value ?? 0}
                    containerSx={{ width: '520px', height: '250px' }}
                  />
                </Stack>
              }
              cardSx={{ width: 'fit-content' }}
            /> */}
          </Stack>

          <Stack direction={'row'} gap={'16px'} sx={{ flex: 1 }}>
            <WidgetCard
              title={'Session Duration'}
              description={'Average session duration.'}
              content={getDurationTitleContent()}
            />
            <WidgetCard
              title={'Error count'}
              content={
                <Typography variant={'h6'}>
                  {data?.errorCount.value}
                  {unitSuffix[data?.errorCount.unit ?? Unit.Scalar]}
                </Typography>
              }
            />
            <WidgetCard
              title={'Most frequent errors'}
              description={getMostFrequentErrorsTooltip()}
              content={
                <Typography variant={'h6'}>
                  {data?.mostFrequentErrors.count}
                </Typography>
              }
            />
          </Stack>

          {showMoreMetrics && (
            <Stack direction={'column'} gap={'16px'}>
              <Stack direction={'column'} gap={'12px'}>
                <Typography variant={'h6'}>Utilisation</Typography>
                <Stack direction={'row'} gap={'16px'}>
                  <WidgetCard
                    title={'Traces'}
                    description={
                      'The number of traces created by the application.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.traces.value ?? 0)}${unitSuffix[data?.traces.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                  <WidgetCard
                    title={'Sessions'}
                    description={
                      'The number of sessions created by the application.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.sessions.value ?? 0)}${unitSuffix[data?.sessions.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />

                  <WidgetCard
                    title={'Conversation Count'}
                    description={
                      'The number of conversations created by the application.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.totalConversationCount.value ?? 0)}${unitSuffix[data?.totalConversationCount.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                </Stack>

                <Stack direction={'row'} gap={'16px'}>
                  <WidgetCard
                    title={'Avg LLM Calls'}
                    description={'The average number of LLM calls per session.'}
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.llmCalls.value ?? 0)}${unitSuffix[data?.llmCalls.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                  <WidgetCard
                    title={'Avg Tool Calls'}
                    description={
                      'The average number of tool calls per session.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.toolCalls.value ?? 0)}${unitSuffix[data?.toolCalls.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                  <WidgetCard
                    title={'Avg Action Count'}
                    description={
                      'The average sum of LLM and Tools calls per session.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${Math.round(data?.totalActionCount.value ?? 0)}${unitSuffix[data?.totalActionCount.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                </Stack>

                <WidgetCard
                  title={'Most Active Agent'}
                  description={'The agent with the highest activity.'}
                  content={
                    <Typography variant={'h6'}>
                      {data?.mostActiveAgent.agentName} -{' '}
                      {formatTwoDecimals(
                        (data?.mostActiveAgent?.activity?.value ?? 0) / 100
                      )}
                      {
                        unitSuffix[
                          data?.mostActiveAgent?.activity?.unit ??
                            Unit.Percentage
                        ]
                      }
                    </Typography>
                  }
                  cardSx={{ width: 'fit-content' }}
                />
              </Stack>

              <Stack direction={'column'} gap={'8px'}>
                <Typography variant={'h6'}>Graph Metrics</Typography>

                <Stack direction={'row'} gap={'16px'}>
                  <WidgetCard
                    title={'Graph Determinism'}
                    description={
                      'How consistently the system produces the same execution graph (nodes, edges, and ordering). A higher value means runs are structurally identical or near-identical across repeats.'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${formatTwoDecimals(data?.graphDeterminism.value)}${unitSuffix[data?.graphDeterminism.unit ?? Unit.Scalar]}`}</Typography>
                    }
                  />
                  <WidgetCard
                    title={'Graph Dynamism'}
                    description={
                      'The magnitude and frequency of structural change in the execution graph across time or varying inputs. A higher value means the topology changes often (nodes/edges appear/disappear or rewire)'
                    }
                    content={
                      <Typography
                        variant={'h6'}
                      >{`${formatTwoDecimals(data?.graphDynamism.value)}${unitSuffix[data?.graphDynamism.unit ?? Unit.Percentage]}`}</Typography>
                    }
                  />
                </Stack>
              </Stack>

              {fetchingAgenticProtocolsMetrics ? (
                <Stack
                  alignItems={'center'}
                  justifyContent={'center'}
                  sx={{ width: '100%', height: '100%', minHeight: '100px' }}
                >
                  <Spinner />
                </Stack>
              ) : !errorAgenticProtocolsMetrics ? (
                <Stack direction={'column'} gap={'16px'}>
                  <Stack direction={'column'} gap={'8px'}>
                    <Typography variant={'h6'}>SLIM</Typography>

                    <Stack direction={'row'} gap={'16px'}>
                      <WidgetCard
                        title={'SLIM Success Rate'}
                        description={
                          'Success rate of the processed SLIM messages.'
                        }
                        content={
                          <Typography variant={'h6'}>
                            {
                              agenticProtocolsMetricsData?.slimMetrics
                                .successRate.value
                            }
                            {/* @ts-ignore */}
                            {
                              unitSuffix[
                                agenticProtocolsMetricsData?.slimMetrics
                                  .successRate.unit ?? Unit.Percentage
                              ]
                            }
                          </Typography>
                        }
                      />
                      <WidgetCard
                        title={'SLIM Error Rate'}
                        description={
                          'Error rate of the processed SLIM messages.'
                        }
                        content={
                          <Typography variant={'h6'}>
                            {
                              agenticProtocolsMetricsData?.slimMetrics.errorRate
                                .value
                            }
                            {/* @ts-ignore */}
                            {
                              unitSuffix[
                                agenticProtocolsMetricsData?.slimMetrics
                                  .errorRate.unit ?? Unit.Percentage
                              ]
                            }
                          </Typography>
                        }
                      />
                      <WidgetCard
                        title={'Total SLIM Messages Processed'}
                        description={'Total number of SLIM messages processed.'}
                        content={
                          <Typography variant={'h6'}>
                            {
                              agenticProtocolsMetricsData?.slimMetrics
                                .messagesProcessed.value
                            }
                            {/* @ts-ignore */}
                            {
                              unitSuffix[
                                agenticProtocolsMetricsData?.slimMetrics
                                  .messagesProcessed.unit ?? Unit.Scalar
                              ]
                            }
                          </Typography>
                        }
                      />
                      <WidgetCard
                        title={'Average SLIM Processing Time'}
                        description={
                          'Average time for an agent to process a received SLIM message.'
                        }
                        content={
                          <Typography variant={'h6'}>
                            {
                              agenticProtocolsMetricsData?.slimMetrics
                                .processingTime.value
                            }
                            {/* @ts-ignore */}
                            {
                              unitSuffix[
                                agenticProtocolsMetricsData?.slimMetrics
                                  .processingTime.unit ?? Unit.Milliseconds
                              ]
                            }
                          </Typography>
                        }
                      />
                    </Stack>
                  </Stack>

                  <Stack direction={'column'} gap={'8px'}>
                    <Typography variant={'h6'}>A2A</Typography>
                    <Stack direction={'row'} gap={'16px'}>
                      <WidgetCard
                        title={'A2A Success Rate'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                      <WidgetCard
                        title={'A2A Error Rate'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                      <WidgetCard
                        title={'Total A2A messages processed'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                    </Stack>
                  </Stack>

                  <Stack direction={'column'} gap={'8px'}>
                    <Typography variant={'h6'}>MCP</Typography>

                    <Stack direction={'row'} gap={'16px'}>
                      <WidgetCard
                        title={'MCP Success Rate'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                      <WidgetCard
                        title={'MCP Error Rate'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                      <WidgetCard
                        title={'MCP Request Latency'}
                        content={<Typography variant={'h6'}>-</Typography>}
                        disabled
                      />
                    </Stack>
                  </Stack>
                </Stack>
              ) : null}
            </Stack>
          )}

          <Stack
            direction={'row'}
            justifyContent={'flex-end'}
            sx={{ width: '900px' }}
          >
            <Button
              variant="gradient"
              size="small"
              onClick={() => setShowMoreMetrics(!showMoreMetrics)}
              sx={{
                cursor: 'pointer',
                '&:focus, &:focus-visible, &.Mui-focusVisible': {
                  outline: 'none !important',
                  boxShadow: 'none !important'
                }
              }}
              disableRipple
            >
              {showMoreMetrics ? 'Show less' : 'Show more'}
            </Button>
          </Stack>
        </Stack>
      )}

      {selectedMetricCategory && (
        <ApplicationLevelMetricDrawer
          onClose={() => setSelectedMetricCategory(null)}
          metricCategory={selectedMetricCategory}
          applicationSummaryMetrics={
            applicationSummaryMetricsData ?? {
              applicationName: applicationId ?? '',
              quality: [],
              reliability: [],
              performance: []
            }
          }
          aggregatedReliabilityValue={overallReliability}
          aggregatedQualityValue={overallQuality}
          aggregatedPerformanceValue={overallPerformance}
        />
      )}
    </Stack>
  );
};
