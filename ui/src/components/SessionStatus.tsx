/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { CustomTooltip } from './CustomTooltip';
import { CheckCircleOutline, CloseCircleOutline } from '@/assets/icons';
import { Box } from '@mui/material';

interface SessionStatusProps {
  status: number;
}

export const SessionStatus = ({ status }: SessionStatusProps) => {
  switch (status) {
    case 1:
      return (
        <CustomTooltip
          title="Session completed successfully with all user intents fulfilled."
          placement="top"
        >
          <Box sx={{ display: 'inline-flex' }}>
            <CheckCircleOutline fill={'green'} />
          </Box>
        </CustomTooltip>
      );
    case 0:
      return (
        <CustomTooltip
          title="Session failed due to an unresolved user intent or a critical error."
          placement="top"
        >
          <Box sx={{ display: 'inline-flex' }}>
            <CloseCircleOutline fill={'red'} />
          </Box>
        </CustomTooltip>
      );
    default:
      return (
        <CustomTooltip
          title="Session completed successfully with all user intents fulfilled."
          placement="top"
        >
          <Box sx={{ display: 'inline-flex' }}>
            <CheckCircleOutline fill={'green'} />
          </Box>
        </CustomTooltip>
      );
  }
};
