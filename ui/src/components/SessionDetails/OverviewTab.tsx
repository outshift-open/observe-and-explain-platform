/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useState } from 'react';
import { Box, Stack, Typography } from '@mui/material';
import {
  ExecutionTrace,
  SingleSessionInsightsList,
  WidgetCard
} from '@/components';
import { ExecutionTimeline } from '@/components/ExecutionTimeline';
import { useParams } from 'react-router';
import { useTimeRangeStore } from '@/store';
import {
  formatDurationMs,
  getDisplayedResultsCount,
  formatTwoDecimals
} from '@/utils';
import { useApplicationSessionsWithStatefulEval } from '@/api/oxpApi';
import { Session } from '@/types/oxp.type';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';

interface OverviewTabProps {
  costDollars?: string | number;
  totalTokens?: string | number;
  duration?: string | number;
}

export const OverviewTab = ({
  costDollars = '0',
  totalTokens = '0',
  duration = '0'
}: OverviewTabProps) => {
  const { sessionId, applicationId } = useParams();
  const { startDate, endDate } = useTimeRangeStore();
  const insightsEnabled = useFeatureFlag('insights');
  const { data: collectData } = useApplicationSessionsWithStatefulEval(
    applicationId ?? '',
    startDate ?? 0,
    endDate ?? 0
  );
  const lastSessionSignatureRef = useRef<string>('');
  const [liveDuration, setLiveDuration] = useState<string | number>(duration);
  const [liveCost, setLiveCost] = useState<string | number>(costDollars);
  const [liveTokens, setLiveTokens] = useState<string | number>(totalTokens);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [sessionId]);

  useEffect(() => {
    if (!collectData?.sessionList) return;
    const currentSession = collectData.sessionList.find(
      (s: Session) => s?.sessionId === sessionId
    );
    const sessionSignature = `${currentSession?.duration}:${currentSession?.tokens}:${currentSession?.cost}`;
    if (sessionSignature === lastSessionSignatureRef.current) return;
    if (currentSession) {
      setLiveCost(formatTwoDecimals(currentSession.cost ?? costDollars));
      setLiveTokens(
        getDisplayedResultsCount(currentSession.tokens ?? totalTokens)
      );
      setLiveDuration(formatDurationMs(currentSession.duration ?? duration));
      lastSessionSignatureRef.current = sessionSignature;
    }
  }, [collectData?.sessionList, sessionId, applicationId, startDate, endDate]);

  return (
    <Stack
      direction={'column'}
      sx={{
        height: '100%',
        paddingRight: '8px',
        minHeight: 0,
        minWidth: 0
      }}
    >
      <Stack direction={'row'} gap={'16px'} justifyContent={'space-between'}>
        <Stack
          direction={'column'}
          sx={{
            height: '100%',
            minHeight: 0,
            minWidth: 0,
            paddingTop: '16px'
          }}
        >
          <Box>
            <Stack direction={'row'} gap={'16px'}>
              <WidgetCard
                title={'Cost'}
                content={<Typography variant="h5">{liveCost}$</Typography>}
              />
              <WidgetCard
                title={'Token Usage'}
                content={
                  <Typography variant="h5">{liveTokens} tokens</Typography>
                }
              />
              <WidgetCard
                title={'Duration'}
                content={<Typography variant="h5">{liveDuration}</Typography>}
              />
            </Stack>
          </Box>

          <Box sx={{ flex: 1, minHeight: 0, minWidth: 0 }}>
            <ExecutionTrace />
          </Box>
        </Stack>

        {sessionId && insightsEnabled && (
          <SingleSessionInsightsList sessionId={sessionId} />
        )}
      </Stack>

      {sessionId && (
        <Box sx={{ minHeight: 0 }}>
          <ExecutionTimeline sessionId={sessionId} height="auto" />
        </Box>
      )}
    </Stack>
  );
};
