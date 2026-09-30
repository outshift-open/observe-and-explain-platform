/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useState } from 'react';
import { WastefulSession } from '@/types/oxp.type';
import { useTopWastefulSessions } from '@/api/oxpApi';
import { Stack, Typography } from '@mui/material';
import { EmptyState, Spinner } from '@open-ui-kit/core';
import { InefficientSessionCard } from './InefficientSessionCard';
import { FeatureImpactChart } from './FeatureImpactChart';
import { CustomTooltip } from '../CustomTooltip';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';

interface LeastEfficientSessionsProps {
  applicationId?: string;
  startDate: number | null;
  endDate: number | null;
  enableSearch?: boolean;
  onSessionClick?: (session: WastefulSession) => void;
  onGroupClick?: (groupId: string) => void;
  showDateInterval?: boolean;
}

export const LeastEfficientSessions = ({
  applicationId,
  startDate,
  endDate,
  enableSearch = false,
  onSessionClick,
  onGroupClick,
  showDateInterval = true
}: LeastEfficientSessionsProps) => {
  const {
    data: wastefulSessionsData,
    isLoading: isWastefulSessionsLoading,
    isError
  } = useTopWastefulSessions(applicationId ?? '', startDate ?? 0, endDate ?? 0);
  const [selectedSession, setSelectedSession] =
    useState<WastefulSession | null>(null);
  const handleSessionSelect = (session: WastefulSession) => {
    setSelectedSession(session);
  };

  useEffect(() => {
    if (wastefulSessionsData && wastefulSessionsData.length > 0) {
      setSelectedSession(wastefulSessionsData[0]);
    }
  }, [wastefulSessionsData]);

  if (isWastefulSessionsLoading) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{
          width: '100%',
          height: '100%',
          minHeight: '100px'
        }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Typography variant="h6">Error loading wasteful sessions</Typography>
    );
  }

  if (wastefulSessionsData?.length === 0) {
    return (
      <Stack direction="column" gap={'32px'} width="100%">
        <SectionHeader />
        <EmptyState title="No data found" description="" />
      </Stack>
    );
  }

  return (
    <Stack direction="column" gap={'32px'} width="100%">
      <SectionHeader />
      <Stack direction="row" gap={'8px'} width="100%" sx={{ height: '600px' }}>
        <Stack
          direction="column"
          gap={'8px'}
          sx={{
            height: '600px',
            overflow: 'auto',
            minWidth: '318px'
          }}
        >
          {wastefulSessionsData?.map((session) => (
            <InefficientSessionCard
              key={session.sessionId}
              session={session}
              isSelected={selectedSession?.sessionId === session.sessionId}
              onSessionClick={handleSessionSelect}
            />
          ))}
        </Stack>
        <FeatureImpactChart
          session={selectedSession}
          onGroupClick={onGroupClick}
          onSessionClick={onSessionClick}
        />
      </Stack>
    </Stack>
  );
};

const LEAST_EFFICIENT_TITLE = 'Least Efficient Sessions';
const LEAST_EFFICIENT_TOOLTIP =
  'Top sessions with the highest estimated waste. ' +
  'Select a session to view the feature impact chart, which shows which features contribute most to inefficiency.';

const SectionHeader = () => (
  <Stack direction="row" alignItems="flex-start" gap="4px">
    <Typography variant="h6">{LEAST_EFFICIENT_TITLE}</Typography>
    <CustomTooltip
      title={LEAST_EFFICIENT_TOOLTIP}
      placement="top"
      sx={{ maxWidth: '550px' }}
    >
      <InfoOutlineIcon
        sx={{ width: '16px', height: '16px', cursor: 'pointer' }}
      />
    </CustomTooltip>
  </Stack>
);
