/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack } from '@mui/material';
import { useParams } from 'react-router';
import { LiveTopology } from '../LiveTopology';

const LiveSessionDetails = () => {
  const { sessionId } = useParams<{
    sessionId?: string;
  }>();

  return (
    <Stack direction={'column'} sx={{ width: '100%', height: '100%' }}>
      <LiveTopology />
    </Stack>
  );
};

export default LiveSessionDetails;
