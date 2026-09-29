/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  IntervalPicker,
  LiveSessionsTable,
  SessionDetails,
  SessionsTable,
  WidgetCard,
  SessionsInsightsList
} from '@/components';
import LiveSessionDetails from '@/components/LiveSessionDetails';
import { Spinner, Tabs, Tab } from '@open-ui-kit/core';
import { Box, Stack, Typography, useTheme } from '@mui/material';
import { TabPanel } from '@/components/TabPanel';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useEffect, type SyntheticEvent } from 'react';
import type { Session } from '@/types/oxp.type';
import type { LiveSession } from '@/types/oxpApi.type';
import { useTimeRangeStore } from '@/store';
import {
  formatDurationMs,
  getDisplayedResultsCount,
  formatTwoDecimals
} from '@/utils';
import { useApplicationSessionsWithStatefulEval } from '@/api/oxpApi';
import { useDebouncedValue } from '@/utils';
import { PATHS } from '@/routes/routes';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { format } from 'date-fns';
import dayjs from 'dayjs';

export const COLLECT_TAB_NAMES = ['completed', 'live-sessions'] as const;

const CollectTab = () => {
  const theme = useTheme();
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  const navigate = useNavigate();
  const { applicationId, sessionId, liveSessionId } = useParams();
  const location = useLocation();

  const liveTopologyEnabled = useFeatureFlag('live_topology');
  const insightsEnabled = useFeatureFlag('insights');

  const collectTab = location.pathname.endsWith('/live-sessions')
    ? 'live-sessions'
    : location.pathname.endsWith('/completed')
      ? 'completed'
      : null;
  const activeTab =
    liveTopologyEnabled && collectTab === 'live-sessions' ? 1 : 0;

  const handleTabChange = (_event: SyntheticEvent, value: number) => {
    navigate(
      `/applications/${applicationId}/collect/${COLLECT_TAB_NAMES[value]}`
    );
  };

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);
  const { data, error, isLoading } = useApplicationSessionsWithStatefulEval(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );

  const handleSessionClick = (session: Session) => {
    navigate(
      PATHS.applicationCollectSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
    );
  };

  const handleLiveSessionClick = (session: LiveSession) => {
    navigate(
      PATHS.applicationCollectLiveSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':liveSessionId', encodeURIComponent(session.session_id))
    );
  };

  // Live topology is gated: when disabled, keep users out of the live-sessions
  // tab and any live-session detail route.
  useEffect(() => {
    if (
      !liveTopologyEnabled &&
      (collectTab === 'live-sessions' || liveSessionId)
    ) {
      navigate(`/applications/${applicationId}/collect/completed`, {
        replace: true
      });
    }
  }, [liveTopologyEnabled, collectTab, liveSessionId, applicationId, navigate]);

  if (error) {
    return <>An error occurred!</>;
  }

  if (liveSessionId) {
    return liveTopologyEnabled ? <LiveSessionDetails /> : null;
  }

  if (sessionId) {
    return isLoading ? (
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
          data?.sessionList.find((session) => session.sessionId === sessionId)
            ?.cost
        )}
        totalTokens={getDisplayedResultsCount(
          data?.sessionList.find((session) => session.sessionId === sessionId)
            ?.tokens ?? 0
        )}
        duration={formatDurationMs(
          data?.sessionList.find((session) => session.sessionId === sessionId)
            ?.duration
        )}
      />
    );
  }

  return (
    <Stack
      direction={'row'}
      gap={'32px'}
      justifyContent={'space-between'}
      sx={{ width: '100%' }}
    >
      <Stack direction={'column'} sx={{ flex: 1, height: '100%' }}>
        {liveTopologyEnabled && (
          <Stack
            direction={'row'}
            sx={{ width: '100%' }}
            alignItems={'flex-end'}
          >
            <Tabs
              value={activeTab}
              onChange={handleTabChange}
              slotProps={{
                indicator: {
                  sx: {
                    backgroundColor: `${theme.palette.vars.neutralTextDefault} !important`
                  }
                }
              }}
            >
              <Tab label="Completed Sessions" />
              <Tab label="Live Sessions" />
            </Tabs>
          </Stack>
        )}

        <TabPanel value={activeTab} index={0} sx={{ height: '100%' }}>
          <Stack
            direction={'row'}
            gap={'32px'}
            justifyContent={'space-between'}
            sx={{ width: '100%' }}
          >
            <Stack
              direction={'column'}
              gap={'12px'}
              sx={{ height: '100%', width: '100%', paddingTop: '24px' }}
            >
              <IntervalPicker
                startDate={startDate}
                endDate={endDate}
                setStartDate={setStartDate}
                setEndDate={setEndDate}
              />
              <Stack direction="row" gap={'8px'} alignItems={'center'}>
                <Typography variant={'body2Semibold'}>
                  {startDate
                    ? format(
                        dayjs.unix(startDate).toDate(),
                        'MMM d, yyyy HH:mm:ss'
                      )
                    : ''}
                </Typography>
                <Typography variant={'body2Semibold'}>-</Typography>
                <Typography variant={'body2Semibold'}>
                  {endDate
                    ? format(
                        dayjs.unix(endDate).toDate(),
                        'MMM d, yyyy HH:mm:ss'
                      )
                    : ''}
                </Typography>
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
                <>
                  <Stack direction={'row'} gap={'16px'}>
                    <WidgetCard
                      title={'Duration (avg)'}
                      content={
                        <Typography variant="h5">
                          {formatDurationMs(data?.avgDuration ?? 0)}
                        </Typography>
                      }
                    />
                    <WidgetCard
                      title={'Success Rate (avg)'}
                      content={
                        <Typography variant="h5">
                          {data?.successRate ?? 0}%
                        </Typography>
                      }
                    />
                    <WidgetCard
                      title={'Error Rate (avg)'}
                      content={
                        <Typography variant="h5">
                          {data?.errorRate ?? 0}%
                        </Typography>
                      }
                    />
                  </Stack>

                  <Box sx={{ width: '100%', overflow: 'auto' }}>
                    <SessionsTable
                      containerSx={{ maxWidth: 'calc(100vw - 564px)' }}
                      startDate={startDate}
                      endDate={endDate}
                      enableSearch={true}
                      onSessionClick={handleSessionClick}
                      defaultHiddenColumns={[
                        'agents',
                        'llms',
                        'tokens',
                        'duration'
                      ]}
                      showDateInterval={false}
                      title={'Session List'}
                    />
                  </Box>
                </>
              )}
            </Stack>

            {insightsEnabled && <SessionsInsightsList />}
          </Stack>
        </TabPanel>

        {liveTopologyEnabled && (
          <TabPanel value={activeTab} index={1} sx={{ height: '100%' }}>
            <Box sx={{ width: '100%', overflow: 'auto' }}>
              <LiveSessionsTable
                title={''}
                onSessionClick={handleLiveSessionClick}
              />
            </Box>
          </TabPanel>
        )}
      </Stack>
    </Stack>
  );
};

export default CollectTab;
