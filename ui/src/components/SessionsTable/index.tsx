/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { Session, SessionWithStatefulEval } from '@/types/oxp.type';
import { useApplicationSessionsWithStatefulEval } from '@/api/oxpApi';
import { SessionsTable } from './SessionsTable.tsx';
import { Stack, SxProps, useTheme } from '@mui/material';
import { useDebouncedValue } from '@/utils';
import dayjs, { Dayjs } from 'dayjs';
import { useParams } from 'react-router-dom';

interface SessionsTablePropsWrapper {
  applicationId?: string;
  startDate: number | null;
  endDate: number | null;
  enableSearch?: boolean;
  onSessionClick?: (session: Session) => void;
  defaultHiddenColumns?: string[];
  filteredSessionIds?: string[];
  title?: string;
  showDateInterval?: boolean;
  agentId?: string;
  semanticGroupId?: string;
  containerSx?: SxProps;
}

const AGENTS = ['Assistant', 'Planner', 'Test Executor'];
const LLMs = ['GPT-4', 'Claude'];

const getRandomAgents = () => {
  const shuffled = AGENTS.sort(() => 0.5 - Math.random());

  const size = Math.floor(Math.random() * AGENTS.length) + 1;

  return shuffled.slice(0, size);
};

const getRandomLLMs = () => {
  const shuffled = LLMs.sort(() => 0.5 - Math.random());

  const size = Math.floor(Math.random() * LLMs.length) + 1;

  return shuffled.slice(0, size);
};

export const SessionsTableWrapper = ({
  applicationId,
  startDate,
  endDate,
  enableSearch = false,
  onSessionClick,
  defaultHiddenColumns = [],
  title,
  filteredSessionIds,
  showDateInterval = true,
  agentId,
  semanticGroupId,
  containerSx
}: SessionsTablePropsWrapper) => {
  const { applicationId: applicationIdFromParams } = useParams();

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);
  const {
    data: sessionsData,
    error: sessionsError,
    isLoading: sessionsLoading
  } = useApplicationSessionsWithStatefulEval(
    applicationId ?? applicationIdFromParams ?? '',
    debouncedStartDate,
    debouncedEndDate,
    true,
    semanticGroupId
  );

  const sessionsWithStatefulEval: SessionWithStatefulEval[] = useMemo(() => {
    if (!sessionsData?.sessionList) return [];

    const sessions = sessionsData.sessionList.map((session) => {
      const statefulEval = (session as any).statefulEval;
      if (!statefulEval) return session as SessionWithStatefulEval;

      let parsedValue: any = null;
      try {
        parsedValue =
          typeof statefulEval.value === 'string'
            ? JSON.parse(statefulEval.value)
            : statefulEval;
      } catch {
        parsedValue = null;
      }

      let reasoningJson = null;
      try {
        reasoningJson =
          typeof parsedValue?.reasoning === 'string'
            ? JSON.parse(parsedValue.reasoning)
            : (parsedValue?.reasoning ?? null);
      } catch {
        reasoningJson = null;
      }

      return {
        ...session,
        statefulEval: {
          metric_id: statefulEval.metric_id,
          name: statefulEval.name,
          source: statefulEval.source,
          reasoning: statefulEval.reasoning,
          value: parsedValue?.value,
          reasoningJson
        }
      } as SessionWithStatefulEval;
    });

    const sessionsWithStatefulEvalFiltered: SessionWithStatefulEval[] =
      filteredSessionIds
        ? sessions.filter((session) =>
            filteredSessionIds.includes(session.sessionId)
          )
        : sessions;

    console.log(
      'sessionsWithStatefulEvalFiltered',
      sessionsWithStatefulEvalFiltered
    );

    console.log('agentId', agentId);

    const sessionsWithStatefulEvalFilteredByAgent: SessionWithStatefulEval[] =
      agentId
        ? (sessionsWithStatefulEvalFiltered.filter((session) =>
            session.agents?.some((agent) => agent === agentId)
          ) ?? [])
        : sessionsWithStatefulEvalFiltered;

    console.log(
      'sessionsWithStatefulEvalFilteredByAgent',
      sessionsWithStatefulEvalFilteredByAgent
    );

    return sessionsWithStatefulEvalFilteredByAgent;
  }, [sessionsData?.sessionList, filteredSessionIds, agentId]);

  return (
    <Stack direction="column" gap={'8px'} sx={containerSx}>
      {/*<Insights*/}
      {/*  insights={[*/}
      {/*    {*/}
      {/*      value: '74%',*/}
      {/*      description:*/}
      {/*        'of failed sessions in the last evaluation run showed early signs of Planner role drift, where the Planner agent either generated overly verbose goals or attempted to execute tasks instead of delegating'*/}
      {/*    }*/}
      {/*  ]}*/}
      {/*/>*/}

      {/* {enableSearch && (
        <SearchField
          placeholder="Search by session name, id or external id"
          value={queryFilter}
          onChangeCallback={setQueryFilter}
          sx={{ '& .MuiInputBase-root': { marginTop: 0, width: '444px', height: '36px' } }}
        />
      )} */}

      <SessionsTable
        data={sessionsWithStatefulEval}
        isLoading={sessionsLoading}
        isError={Boolean(sessionsError)}
        startDate={startDate ? dayjs.unix(startDate) : null}
        endDate={endDate ? dayjs.unix(endDate) : null}
        onSessionClick={onSessionClick}
        // onReload={() => executeQuery()}
        defaultHiddenColumns={defaultHiddenColumns}
        title={title}
        showDateInterval={showDateInterval}
      />
    </Stack>
  );
};
