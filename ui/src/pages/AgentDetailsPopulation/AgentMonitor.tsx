/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { IntervalPicker, PageWithTitle } from '@/components';
import { Spinner, Stack } from '@open-ui-kit/core';
import { Button, Typography, useTheme } from '@mui/material';
import { DotLabel } from '@/components/DotLabel';
import { PATHS } from '@/routes/routes.tsx';
import { useParams } from 'react-router';
import { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { format } from 'date-fns';
import MetricsTabs from './MetricsTabs';
import { DEFAULT_END_DATE, DEFAULT_START_DATE } from '@/common/constants';
import AgentTasksDrawer from './AgentTasksDrawer';
import { useTimeRangeStore } from '@/store';
import { useApplicationAgents } from '@/api/oxpApi';
import { TAB_NAMES } from '@/pages/ApplicationDetails/MonitorTab';

export const AgentMonitor = () => {
  const { applicationId, agentId } = useParams();

  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  const [isTasksDrawerOpen, setIsTasksDrawerOpen] = useState(false);

  const { data, error, isLoading } = useApplicationAgents(
    applicationId ?? '',
    DEFAULT_START_DATE,
    DEFAULT_END_DATE
  );

  const agent = useMemo(() => {
    return data?.agents?.find((agent) => agent.id === agentId);
  }, [data?.agents, agentId]);

  // const [startTimeSec, setStartDate] = useState<number>(Math.floor(dayjs().subtract(DEFAULT_INTERVAL.value, DEFAULT_INTERVAL.unit).valueOf() / 1000));
  // const [endTimeSec, setEndDate] = useState<number>(Math.floor(dayjs().valueOf() / 1000));

  const theme = useTheme();

  if (error) {
    return <>An error occurred!</>;
  }

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
        <Stack
          direction={'row'}
          alignItems={'flex-start'}
          justifyContent={'space-between'}
          gap={'32px'}
        >
          <Stack direction={'column'} alignItems={'flex-start'} gap={'4px'}>
            <Typography
              variant={'h5'}
              sx={{
                color: theme.palette.vars.interactivePrimaryDefaultDefault
              }}
            >
              {agent?.name}
            </Typography>
          </Stack>

          <Stack
            direction={'row'}
            justifyContent={'flex-end'}
            gap={'24px'}
            sx={{ minWidth: '360px' }}
          >
            <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
              <Typography variant={'body2Semibold'} sx={{ fontWeight: 600 }}>
                Status
              </Typography>
              <DotLabel
                dotColor={theme.palette.vars.brandIconTertiaryMedium}
                label={'In dev'}
              />
            </Stack>

            <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
              <Typography variant={'body2Semibold'} sx={{ fontWeight: 600 }}>
                Last update
              </Typography>
              <Typography variant={'body2'}>
                {format(new Date(Date.now()), 'MMM d, yyyy HH:mm')}
              </Typography>
            </Stack>
          </Stack>
        </Stack>
      }
      // breadcrumbItems={[
      //   { text: 'Applications', link: `${PATHS.monitoring}/${PATHS.applications}` },
      //   {
      //     text: data?.workflowDetailsById?.name ?? '',
      //     link: `${PATHS.monitoring}/${PATHS.applications}/${data?.workflowDetailsById?.name ?? ''}`
      //   },
      //   {
      //     text: agentId ?? '',
      //     link: `${PATHS.monitoring}/${PATHS.applications}/${data?.workflowDetailsById?.name ?? ''}${PATHS.agents}/${agentId}`
      //   }
      // ]}
    >
      <Stack direction={'column'} gap={'24px'} sx={{ height: '100%' }}>
        <Stack direction={'row'} gap={'24px'} justifyContent={'space-between'}>
          <Stack direction={'column'} gap={'8px'}>
            <IntervalPicker
              startDate={startDate}
              endDate={endDate}
              setStartDate={setStartDate}
              setEndDate={setEndDate}
            />

            <Stack direction="row" gap={'8px'}>
              <Typography variant={'body2Semibold'}>
                {startDate
                  ? format(
                      new Date(dayjs.unix(startDate).valueOf()),
                      'MMM d, yyyy HH:mm'
                    )
                  : ''}
              </Typography>
              <Typography variant={'body2Semibold'}>-</Typography>
              <Typography variant={'body2Semibold'}>
                {endDate
                  ? format(
                      new Date(dayjs.unix(endDate).valueOf()),
                      'MMM d, yyyy HH:mm'
                    )
                  : ''}
              </Typography>
            </Stack>
          </Stack>

          <Button
            sx={{
              '&.MuiButton-sizeMedium:focus': {
                outline: 'none'
              },
              '&.MuiButton-sizeMedium': {
                height: '36px',
                border: 'none',
                color: theme.palette.vars.interactiveInverseTextDefault
              }
            }}
            onClick={() => {
              setIsTasksDrawerOpen(true);
            }}
          >
            Task List
          </Button>
        </Stack>
        {agentId && (
          <MetricsTabs
            agentId={agentId}
            startTime={startDate}
            endTime={endDate}
          />
        )}
      </Stack>
      {isTasksDrawerOpen && (
        <AgentTasksDrawer
          tasks={agent?.tasks ?? []}
          onClose={() => setIsTasksDrawerOpen(false)}
        />
      )}
    </PageWithTitle>
  );
};

const LINE_DATA = [
  {
    date: '2020-01-10T08:15:30',
    id: '31f40ef0-a43d-411f-80be-1511ea08401b',
    Latency: 2
  },
  {
    date: '2020-01-10T12:30:45',
    id: 'f11f7ed2-b2c9-40cf-bf2e-d7728a760b6a',
    Latency: 2.1
  },
  {
    date: '2020-01-11T14:05:10',
    id: '0a37f3e9-5140-4b1d-9ecf-7dcf6317b178',
    Latency: 2.3
  },
  {
    date: '2020-01-11T14:05:10',
    id: 'b978c179-9ee0-439f-b418-f289f43a7b1d',
    Latency: 2.3
  },
  {
    date: '2020-01-11T14:05:10',
    id: 'e3735b3d-8a7f-40b6-81ff-1db83f0e30f3',
    Latency: 4.3
  },
  {
    date: '2020-01-11T14:05:10',
    id: '5de9b541-00b4-43f9-a702-3923a1b1b198',
    Latency: 3.3
  },
  {
    date: '2020-01-11T14:05:10',
    id: '0bba2b64-0db6-481a-841f-68a4db6e1f75',
    Latency: 2.3
  },
  {
    date: '2020-01-12T18:20:00',
    id: 'a426a172-b24d-493f-bab3-05b8b9a4e6c7',
    Latency: 2.25
  }
];
