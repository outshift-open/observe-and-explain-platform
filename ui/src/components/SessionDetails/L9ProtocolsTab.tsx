/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useParams } from 'react-router';
import { Stack } from '@mui/material';
import { Banner, EmptyState, Skeleton } from '@open-ui-kit/core';
import { useSessionL9Protocols } from '@/api/oxpApi';
import { L9Protocols, hasListedProtocols } from '../L9Protocols';

export const L9ProtocolsTab = () => {
  const { sessionId } = useParams();
  const { data, isLoading, isError } = useSessionL9Protocols(sessionId);

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
      <Banner status="negative" text="Failed to load L9 protocols data." />
    );
  }

  const protocols = data?.protocols ?? [];

  if (!hasListedProtocols(protocols)) {
    return (
      <EmptyState
        title="No L9 protocols in this session"
        description="Neither a protocol was enabled nor expected for this session."
      />
    );
  }

  return (
    <Stack direction="column" sx={{ paddingTop: '16px' }}>
      <L9Protocols protocols={protocols} />
    </Stack>
  );
};
