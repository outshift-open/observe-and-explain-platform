/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useParams } from 'react-router';
import {
  useApplicationAgents,
  useApplicationSessionsWithStatefulEval
} from '@/api/oxpApi';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import {
  AgentCardWithStatefulEval,
  AgentFailingEntity,
  AgentFailingEntityType,
  SessionStatefulEvalMetricFailure,
  SessionWithStatefulEval
} from '@/types/oxp.type';
import { AgentCard } from '@/components/AgentCard';
import { Grid, Spinner, Stack, Typography } from '@open-ui-kit/core';
import { useDebouncedValue } from '@/utils';
import { useTimeRangeStore } from '@/store';
import { IntervalPicker } from '@/components';
import dayjs from 'dayjs';
import { format } from 'date-fns';
import { useMemo } from 'react';

const mapSpanTypeToEntityType = (spanType: string): AgentFailingEntityType => {
  const lowerSpanType = spanType.toLowerCase();
  if (lowerSpanType.includes('tool')) return 'tool';
  if (lowerSpanType.includes('llm')) return 'llm';
  return 'agent';
};

const size = { xxl: 2, xl: 3, lg: 4, md: 3 };

export const AgentsTab = () => {
  const { applicationId } = useParams();
  const statefulEvalEnabled = useFeatureFlag('stateful_eval');
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);

  const { data, error, isLoading } = useApplicationAgents(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );

  const {
    data: sessionsData,
    error: sessionsError,
    isLoading: sessionsLoading
  } = useApplicationSessionsWithStatefulEval(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate,
    statefulEvalEnabled
  );
  const statefulEvalLoading = sessionsLoading;

  const sessionStatefulEvalMap = useMemo(() => {
    const map: Record<
      string,
      {
        fatal: number;
        minor: number;
        trajectoryScore: number;
        fatalFailures: SessionStatefulEvalMetricFailure[];
      }
    > = {};

    if (statefulEvalLoading || !sessionsData?.sessionList) return map;

    for (const session of sessionsData.sessionList as SessionWithStatefulEval[]) {
      const evalData = session.statefulEval;
      if (!evalData) continue;
      try {
        const valueJson =
          typeof evalData.value === 'string'
            ? JSON.parse(evalData.value)
            : evalData;
        const reasoning =
          typeof valueJson?.reasoning === 'string'
            ? JSON.parse(valueJson.reasoning)
            : valueJson?.reasoning;
        if (!reasoning) continue;
        map[session.sessionId] = {
          fatal: (reasoning?.total_fatal as number) ?? 0,
          minor: (reasoning?.total_minor as number) ?? 0,
          trajectoryScore: (reasoning?.trajectory_score as number) ?? 0,
          fatalFailures:
            (reasoning?.fatal_failures as SessionStatefulEvalMetricFailure[]) ??
            []
        };
      } catch {
        // ignore parse errors
      }
    }

    return map;
  }, [statefulEvalLoading, sessionsData]);

  const agentFailuresByName = useMemo(() => {
    const failureMap: Record<
      string,
      {
        fatal: number;
        minor: number;
        trajectoryScore: number;
        totalSessions: number;
        topFailingEntities: AgentFailingEntity[];
      }
    > = {};

    if (!sessionsData?.sessionList) return failureMap;

    for (const session of sessionsData.sessionList) {
      const sessionFailures = sessionStatefulEvalMap[session.sessionId];
      if (!sessionFailures) continue;

      const agents = session.agents ?? [];
      for (const agentName of agents) {
        if (!agentName) continue;
        if (!failureMap[agentName]) {
          failureMap[agentName] = {
            fatal: 0,
            minor: 0,
            trajectoryScore: 0,
            totalSessions: 0,
            topFailingEntities: []
          };
        }
        failureMap[agentName].fatal += sessionFailures.fatal;
        failureMap[agentName].minor += sessionFailures.minor;
        failureMap[agentName].trajectoryScore +=
          sessionFailures.trajectoryScore;
        failureMap[agentName].totalSessions += 1;

        for (const failure of sessionFailures.fatalFailures) {
          const existingEntity = failureMap[agentName].topFailingEntities.find(
            (e) =>
              e.name === failure.entity_name &&
              e.type === mapSpanTypeToEntityType(failure.span_type)
          );
          if (existingEntity) {
            existingEntity.occurrences = (existingEntity.occurrences ?? 0) + 1;
            if (failure.reasoning && !existingEntity.reasoning) {
              existingEntity.reasoning = failure.reasoning;
            }
            if (failure.explanation && !existingEntity.explanation) {
              existingEntity.explanation = failure.explanation;
            }
          } else {
            failureMap[agentName].topFailingEntities.push({
              name: failure.entity_name,
              type: mapSpanTypeToEntityType(failure.span_type),
              occurrences: 1,
              reasoning: failure.reasoning,
              explanation: failure.explanation
            });
          }
        }
      }
    }

    for (const agentName of Object.keys(failureMap)) {
      failureMap[agentName].topFailingEntities.sort(
        (a, b) => (b.occurrences ?? 0) - (a.occurrences ?? 0)
      );
      failureMap[agentName].topFailingEntities = failureMap[
        agentName
      ].topFailingEntities.slice(0, 5);
    }

    return failureMap;
  }, [sessionsData?.sessionList, sessionStatefulEvalMap]);

  const agentsWithStatefulEval = useMemo((): AgentCardWithStatefulEval[] => {
    if (!data?.agents) return [];

    return data.agents
      .filter((agent) => agent.id !== 'finalize_on_error')
      .map((agent) => {
        const failures = agentFailuresByName[agent.id] ??
          agentFailuresByName[agent.name] ?? {
            fatal: 0,
            minor: 0,
            trajectoryScore: 0,
            totalSessions: 0,
            topFailingEntities: []
          };
        return {
          ...agent,
          version: '',
          llm: '',
          trajectoryCount: 0,
          spanCount: 0,
          status: '',
          fatalErrors: failures.fatal,
          minorErrors: failures.minor,
          trajectoryScore: failures.trajectoryScore,
          totalSessions: failures.totalSessions,
          topFailingEntities: failures.topFailingEntities
        } as AgentCardWithStatefulEval;
      });
  }, [data?.agents, agentFailuresByName]);

  if (error || sessionsError) {
    return <>An error occurred!</>;
  }

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

      {isLoading || sessionsLoading ? (
        <Stack
          alignItems={'center'}
          justifyContent={'center'}
          sx={{ width: '100%', height: '100%', minHeight: '100px' }}
        >
          <Spinner />
        </Stack>
      ) : agentsWithStatefulEval.length === 0 ? (
        <Typography variant={'body2Semibold'}>
          No active agents in the selected time range
        </Typography>
      ) : (
        <Grid container spacing={'16px'}>
          {agentsWithStatefulEval.map((agent) => (
            <Grid size={size} key={agent.id}>
              <AgentCard agent={agent} />
            </Grid>
          ))}
        </Grid>
      )}
    </Stack>
  );
};
