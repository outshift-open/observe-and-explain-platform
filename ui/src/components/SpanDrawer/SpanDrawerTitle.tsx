/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@open-ui-kit/core';
import { SpanDetails } from '@/types/oxp.type';
import { getIconFromTraceType } from '@/utils';
import { TraceType } from '@/types/trace-types.ts';
import { capitalizeFirstLetter } from '@/utils';
import { useTheme } from '@mui/material';

interface SpanDrawerTitleProps {
  span: SpanDetails;
}

export const SpanDrawerTitle = ({ span }: SpanDrawerTitleProps) => {
  const theme = useTheme();

  const Icon = getIconFromTraceType(span?.spanType as TraceType);

  return (
    <Stack direction={'row'} gap={'4px'}>
      {Icon && <Icon sx={{ color: theme.palette.vars.accentGDefault }} />}
      <Stack direction={'column'}>
        <Typography variant={'body1Semibold'} sx={{ color: theme.palette.vars.controlIconStrong }}>
          {capitalizeFirstLetter(span.spanName)}
        </Typography>
        <Typography variant={'body1'} sx={{ color: theme.palette.vars.controlIconStrong }}>
          {capitalizeFirstLetter(span.spanType)}
        </Typography>
      </Stack>
    </Stack>
  );
};
