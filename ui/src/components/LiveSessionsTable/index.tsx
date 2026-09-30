/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, SxProps } from '@mui/material';
import { useLiveSessions } from '@/api/oxpApi';
import { LiveSessionsTable } from './LiveSessionsTable';
import type { LiveSession } from '@/types/oxpApi.type';
import { useParams } from 'react-router-dom';

interface LiveSessionsTableWrapperProps {
  onSessionClick?: (session: LiveSession) => void;
  title?: string;
  containerSx?: SxProps;
}

export const LiveSessionsTableWrapper = ({
  onSessionClick,
  title,
  containerSx
}: LiveSessionsTableWrapperProps) => {
  const { applicationId } = useParams();
  const { data, error, isLoading } = useLiveSessions(applicationId ?? '');

  return (
    <Stack direction="column" gap={'8px'} sx={containerSx}>
      <LiveSessionsTable
        data={data?.sessions ?? []}
        isLoading={isLoading}
        isError={Boolean(error)}
        onSessionClick={onSessionClick}
        title={title}
      />
    </Stack>
  );
};
