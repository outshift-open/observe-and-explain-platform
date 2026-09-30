/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Divider, Stack } from '@mui/material';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Typography } from '@mui/material';
import { useTimeRangeStore } from '@/store';
import { useInfiniteSessionsInsights } from '@/api/oxpApi';
import { GeneralSize, Spinner, Tag } from '@open-ui-kit/core';
import { SessionInsight } from '@/types/oxp.type';
import { format } from 'date-fns';
import { colorTokens } from '@/theme/colors';
import { CustomTooltip } from '../CustomTooltip';
import { useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/routes/routes';

export const SessionsInsightsList = () => {
  const { startDate, endDate } = useTimeRangeStore();
  const { applicationId } = useParams();

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteSessionsInsights(applicationId ?? '', startDate, endDate);

  const sessionsInsights = useMemo(() => data?.pages.flat() ?? [], [data]);

  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage]
  );

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(handleObserver, {
      rootMargin: '200px'
    });
    observer.observe(sentinel);

    return () => observer.disconnect();
  }, [handleObserver]);

  const navigate = useNavigate();
  const onSessionClick = (session: SessionInsight) => {
    navigate(
      PATHS.applicationCollectSession
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
    );
  };

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

  if (isError) {
    return (
      <Typography variant={'body2'}>Error loading sessions insights</Typography>
    );
  }

  if (sessionsInsights.length === 0) {
    return (
      <Stack direction={'column'} gap={'24px'} sx={{ paddingTop: '24px' }}>
        <Typography variant={'h6'}>Key Events</Typography>
        <Stack
          alignItems={'flex-start'}
          justifyContent={'flex-start'}
          sx={{ width: '300px', height: '100%' }}
        >
          <Typography variant={'body2'}>No sessions insights found</Typography>
        </Stack>
      </Stack>
    );
  }

  return (
    <Stack direction={'column'} gap={'24px'} sx={{ paddingTop: '24px' }}>
      <Typography variant={'h6'}>Key Events</Typography>

      <Stack
        direction={'column'}
        sx={{
          width: '300px',
          minWidth: '300px',
          height: 'calc(100vh - 400px)',
          overflow: 'auto',
          borderRadius: '8px',
          paddingRight: '4px'
        }}
      >
        <Stack
          direction={'row'}
          justifyContent={'space-between'}
          sx={{ position: 'relative' }}
        >
          <Stack direction={'column'}>
            {sessionsInsights.map((insight: SessionInsight) => (
              <Stack
                key={insight.insightId}
                direction={'column'}
                gap={'4px'}
                sx={{ height: '116px' }}
              >
                <CustomTooltip
                  title={insight.sessionId}
                  placement="top"
                  enterDelay={500}
                  enterNextDelay={500}
                >
                  <Box
                    onClick={() => onSessionClick?.(insight)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <Tag
                      sx={{
                        width: '92px',
                        backgroundColor: colorTokens.accentBlueBackground,
                        color: colorTokens.accentBlueText
                      }}
                      size={GeneralSize.Medium}
                    >
                      {insight.sessionId}
                    </Tag>
                  </Box>
                </CustomTooltip>

                <CustomTooltip
                  title={insight.name}
                  placement="top"
                  enterDelay={500}
                  enterNextDelay={500}
                >
                  <Typography
                    variant={'captionSemibold'}
                    sx={{
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      maxWidth: '124px'
                    }}
                  >
                    {insight.name}
                  </Typography>
                </CustomTooltip>
              </Stack>
            ))}
          </Stack>

          <Box sx={{ position: 'relative', display: 'flex' }}>
            <Divider orientation="vertical" sx={{ marginTop: '14px' }} />

            {/* Dots are centered on the divider by anchoring to this wrapper
                (whose width is just the divider), not the full row. */}
            <Stack
              direction={'column'}
              sx={{
                position: 'absolute',
                top: 0,
                left: '50%',
                marginTop: '7px',
                transform: 'translateX(-50%)'
              }}
            >
              {sessionsInsights.map((insight: SessionInsight) => (
                <Box key={insight.insightId} sx={{ height: '116px' }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      backgroundColor: colorTokens.successBackground
                    }}
                  />
                </Box>
              ))}
            </Stack>
          </Box>

          <Stack direction={'column'} sx={{ marginTop: '4px' }}>
            {sessionsInsights.map((insight: SessionInsight) => (
              <Typography
                key={insight.insightId}
                variant={'captionSemibold'}
                sx={{ height: '116px' }}
              >
                {format(new Date(insight.createdAt), 'MMM d, yyyy HH:mm')}
              </Typography>
            ))}
          </Stack>
        </Stack>

        <Box ref={sentinelRef} sx={{ height: '1px' }} />
      </Stack>
    </Stack>
  );
};
