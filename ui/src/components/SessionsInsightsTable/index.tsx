/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Spinner, Stack } from '@open-ui-kit/core';
import { Typography } from '@mui/material';
import { useSessionsInsights } from '@/api/oxpApi';
import { SessionsInsightsTable } from './SessionsInsightsTable';
import { SessionInsight } from '@/types/oxp.type';
import { PATHS } from '@/routes/routes';
import { useNavigate, useParams } from 'react-router-dom';

interface SessionsInsightsTableWrapperProps {
  startDate: number;
  endDate: number;
  semanticGroupId?: string;
}

export const SessionsInsightsTableWrapper = ({
  startDate,
  endDate,
  semanticGroupId
}: SessionsInsightsTableWrapperProps) => {
  const { applicationId } = useParams();

  const {
    data: sessionsInsights,
    isLoading,
    isError
  } = useSessionsInsights(applicationId ?? '', startDate, endDate, semanticGroupId);
  const navigate = useNavigate();

  const onSessionClick = (session: SessionInsight) => {
    navigate(
      PATHS.applicationCollectSessionTab
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
        .replace(':sessionTab', 'analysis')
    );
  };
  if (isLoading) {
    return (
      <Stack
        justifyContent={'center'}
        alignItems={'center'}
        sx={{ width: '100%', padding: '24px' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Typography variant={'body2'} sx={{ padding: '16px' }}>
        Error loading sessions insights
      </Typography>
    );
  }

  return (
    <SessionsInsightsTable
      data={sessionsInsights ?? []}
      isLoading={isLoading}
      onSessionClick={onSessionClick}
    />
  );
};
