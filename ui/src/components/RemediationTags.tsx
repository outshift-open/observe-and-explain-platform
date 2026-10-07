/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { GeneralSize, Tag, Tooltip } from '@open-ui-kit/core';
import BuildOutlinedIcon from '@mui/icons-material/BuildOutlined';
import { Box, Stack, Typography, useTheme } from '@mui/material';
import { getRemediationDescription } from '@/common/cognitiveFailures';

// All the suggested remediations of a failure, labelled, each with a tooltip
// explaining the protocol. Renders nothing when there are none.
export const RemediationTags = ({
  remediations
}: {
  remediations?: string[] | null;
}) => {
  const theme = useTheme();
  if (!remediations?.length) return null;

  return (
    <Stack direction="column" gap="4px">
      <Typography
        variant={'caption'}
        sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
      >
        Suggested remediations
      </Typography>
      <Stack direction="row" gap="8px" sx={{ flexWrap: 'wrap' }}>
        {remediations.map((name) => {
          const description = getRemediationDescription(name);
          const tag = (
            <Tag
              size={GeneralSize.Medium}
              icon={<BuildOutlinedIcon sx={{ fontSize: 14 }} />}
              sx={{
                backgroundColor: theme.palette.vars.controlBackgroundMedium,
                cursor: 'pointer'
              }}
            >
              {name}
            </Tag>
          );
          return description ? (
            <Tooltip
              key={name}
              title={<Typography variant={'caption'}>{description}</Typography>}
              placement={'top'}
              slotProps={{ tooltip: { sx: { maxWidth: 520 } } }}
            >
              <Box>{tag}</Box>
            </Tooltip>
          ) : (
            <Box key={name}>{tag}</Box>
          );
        })}
      </Stack>
    </Stack>
  );
};
