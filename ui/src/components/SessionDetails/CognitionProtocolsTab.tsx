/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useParams } from 'react-router';
import { Stack } from '@mui/material';
import { Banner, EmptyState, Skeleton } from '@open-ui-kit/core';
import { useSessionCognitionProtocols } from '@/api/oxpApi';
import { CognitionProtocols, hasListedProtocols } from '../CognitionProtocols';

export const CognitionProtocolsTab = () => {
  const { sessionId } = useParams();
  const { data, isLoading, isError } = useSessionCognitionProtocols(sessionId);

  if (isLoading) {
    return (
      <Stack direction="column" gap="16px" sx={{ paddingTop: '16px' }}>
        <Skeleton variant="rounded" height={48} />
        <Skeleton variant="rounded" height={160} />
        <Skeleton variant="rounded" height={240} />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Banner status="negative" text="Failed to load Cognition protocols data." />
    );
  }

  const protocols = data?.protocols ?? [];

  if (!hasListedProtocols(protocols)) {
    return (
      <EmptyState
        title="No Cognition protocols in this session"
        description="Neither a protocol was enabled nor expected for this session."
      />
    );
  }

  return (
    <Stack direction="column" sx={{ paddingTop: '16px' }}>
      <CognitionProtocols protocols={protocols} />
    </Stack>
  );
};
