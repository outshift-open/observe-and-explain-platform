/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Typography, useTheme } from '@mui/material';
import { COGNITIVE_FAILURE_DESCRIPTIONS } from '@/common/cognitiveFailures';

// Widget tooltip content for a failure: its explanation (when known) followed
// by the suggested remediations, with the label highlighted.
export const CognitiveFailureDescription = ({
  name,
  remediations
}: {
  name: string;
  remediations?: string[] | null;
}) => {
  const theme = useTheme();
  const description = COGNITIVE_FAILURE_DESCRIPTIONS[name];

  return (
    <Typography variant={'caption'} sx={{ whiteSpace: 'pre-line' }}>
      {description && `${description}\n\n`}
      <Box
        component={'span'}
        sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
      >
        Suggested remediations:
      </Box>
      {` ${remediations?.length ? remediations.join(', ') : 'None'}`}
    </Typography>
  );
};
