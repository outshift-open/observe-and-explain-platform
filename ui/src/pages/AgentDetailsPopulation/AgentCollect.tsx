/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  IntervalPicker,
  PageWithTitle,
  SessionsTable,
  SessionDetails
} from '@/components';

import { useNavigate, useParams } from 'react-router-dom';
import type { Session } from '@/types/oxp.type';
import { Stack, Typography, useTheme } from '@mui/material';
import { PATHS } from '@/routes/routes';
import { useTimeRangeStore } from '@/store';
import {
  formatDurationMs,
  formatTwoDecimals,
  getDisplayedResultsCount
} from '@/utils';
import { Spinner } from '@open-ui-kit/core';
import { useDebouncedValue } from '@/utils';
import { useApplicationAgents, useApplicationSessions } from '@/api/oxpApi';
import { useMemo } from 'react';
import { DEFAULT_END_DATE, DEFAULT_START_DATE } from '@/common/constants';
import { TAB_NAMES } from '@/pages/ApplicationDetails/MonitorTab';

export const AgentCollect = () => {
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  // const [startDate, setStartDate] = useState<number>(Math.floor(dayjs().subtract(DEFAULT_INTERVAL.value, DEFAULT_INTERVAL.unit).valueOf() / 1000));
  // const [endDate, setEndDate] = useState<number>(Math.floor(dayjs().valueOf() / 1000));
  const theme = useTheme();
  const { applicationId, agentId, sessionId } = useParams();
  const navigate = useNavigate();

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);
  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    error: sessionsError
  } = useApplicationSessions(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );

  const {
    data: agentsData,
    error: agentsError,
    isLoading: agentsLoading
  } = useApplicationAgents(
    applicationId ?? '',
    DEFAULT_START_DATE,
    DEFAULT_END_DATE
  );

  const agent = useMemo(() => {
    return agentsData?.agents?.find((agent) => agent.id === agentId);
  }, [agentsData?.agents, agentId]);

  const handleSessionClick = (session: Session) => {
    navigate(
      PATHS.agentCollectSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':agentId', agentId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
    );
  };

  if (sessionsError || agentsError) {
    return <>An error occurred!</>;
  }

  if (agentsLoading) {
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

  return (
    <PageWithTitle
      breadcrumbItems={[
        { text: 'Applications', link: PATHS.applications },
        {
          text: applicationId ?? '',
          link: `${PATHS.applications}/${applicationId}`
        },
        {
          text: 'Agents',
          link: `${PATHS.applicationMonitorSubTab}`
            .replace(':applicationId', applicationId ?? '')
            .replace(':monitorTab', TAB_NAMES[1])
        },
        {
          text: agent?.name ?? '',
          link: `${PATHS.applications}/${applicationId}/agents/${agentId}`
        },
        {
          text: 'Monitor',
          link: `${PATHS.applications}/${applicationId}/agents/${agentId}/monitor`
        }
      ]}
      title={
        <Typography
          variant={'h5'}
          sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
        >
          {applicationId}
        </Typography>
      }
    >
      {!sessionId && (
        <>
          <IntervalPicker
            startDate={startDate}
            endDate={endDate}
            setStartDate={setStartDate}
            setEndDate={setEndDate}
          />
          {applicationId && (
            <SessionsTable
              applicationId={applicationId}
              startDate={startDate}
              endDate={endDate}
              onSessionClick={handleSessionClick}
              agentId={agentId}
            />
          )}
        </>
      )}

      {sessionId &&
        (sessionsLoading ? (
          <Stack
            alignItems={'center'}
            justifyContent={'center'}
            sx={{ width: '100%', height: '100%', minHeight: '100px' }}
          >
            <Spinner />
          </Stack>
        ) : (
          <SessionDetails
            costDollars={formatTwoDecimals(
              sessionsData?.sessionList.find(
                (session) => session.sessionId === sessionId
              )?.cost
            )}
            totalTokens={getDisplayedResultsCount(
              sessionsData?.sessionList.find(
                (session) => session.sessionId === sessionId
              )?.tokens ?? 0
            )}
            duration={formatDurationMs(
              sessionsData?.sessionList.find(
                (session) => session.sessionId === sessionId
              )?.duration
            )}
          />
        ))}
    </PageWithTitle>
  );
};
