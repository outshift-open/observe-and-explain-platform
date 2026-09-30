/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useSpanDetails } from '@/api/oxpApi';
import { Box, SideDrawer, Spinner, Stack } from '@open-ui-kit/core';
import { SpanDrawerTitle } from './SpanDrawerTitle';
import { SpanDrawerContent } from './SpanDrawerContent';
import { useEffect } from 'react';

interface SpanDrawerWrapper {
  onClose: () => void;
  spanId: string;
  spanDuration: number;
  startTime: number;
  endTime: number;
}

const SpanDrawerWrapper = ({
  spanId,
  onClose,
  spanDuration,
  startTime,
  endTime
}: SpanDrawerWrapper) => {
  const {
    data: spanDetailsData,
    error: spanDetailsError,
    isLoading: spanDetailsFetching
  } = useSpanDetails(spanId);

  useEffect(() => {
    if (spanDetailsError) {
      onClose();
    }
  }, [spanDetailsError, onClose]);

  return (
    <SideDrawer
      open={Boolean(spanId)}
      onClose={onClose}
      titleNode={
        spanDetailsData && !spanDetailsFetching ? (
          <SpanDrawerTitle span={spanDetailsData} />
        ) : null
      }
      copyURL={''}
      hideTitleAction={true}
      hidePrev={true}
      hideNext={true}
      hideActionButtons={true}
      hideFooter={true}
      paperProps={{
        '&.MuiPaper-root': {
          width: '600px',
          minWidth: '600px',
          overflowX: 'hidden',
          overflowY: 'auto'
        },

        '&.MuiPaper-root > .MuiBox-root': {
          width: '600px',
          padding: '16px 8px 24px 16px'
        },
        '&.MuiPaper-root > .MuiBox-root:nth-child(2)': {
          height: '100%',
          padding: '0 16px',
          overflowX: 'hidden',
          overflowY: 'auto'
        }
      }}
      customDividerStyle={{ display: 'none' }}
    >
      <Box
        sx={{
          width: '571px',
          height: '100%',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        {spanDetailsFetching ? (
          <Stack
            justifyContent={'center'}
            alignItems={'center'}
            sx={{ width: '100%', height: '100%' }}
          >
            <Spinner />
          </Stack>
        ) : spanDetailsData ? (
          <SpanDrawerContent
            span={spanDetailsData}
            spanDuration={spanDuration}
            startTime={startTime}
            endTime={endTime}
          />
        ) : null}
      </Box>
    </SideDrawer>
  );
};

export default SpanDrawerWrapper;
