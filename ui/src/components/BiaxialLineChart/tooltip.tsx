/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Typography, useTheme } from '@mui/material';
import { TooltipProps } from 'recharts';
import { formatISODate } from './utils.ts';
import { tooltipStyles } from './tooltipStyles.ts';
import { formatTwoDecimals } from '@/utils/stringUtils.ts';
// unit suffix handled via value formatters passed from parent

export interface BiaxialLineChartTooltipProps extends TooltipProps<number, string> {
  subject?: string;
  valueFormatterLeft?: (value?: number) => string;
  valueFormatterRight?: (value?: number) => string;
  leftName?: string;
  rightName?: string;
  leftLabel?: string;
  rightLabel?: string;
}

export const BiaxialLineChartTooltip = ({
  active,
  payload,
  label,
  subject,
  valueFormatterLeft,
  valueFormatterRight,
  leftName,
  rightName,
  leftLabel,
  rightLabel
}: BiaxialLineChartTooltipProps) => {
  const theme = useTheme();
  if (!active || !payload?.length) return null;

  return (
    <Box sx={tooltipStyles(theme).mainContainer}>
      <Typography component="div" variant="caption" sx={tooltipStyles(theme).title}>
        {subject ?? formatISODate(label as string, 'LLL dd, yyyy')} - {formatISODate(label as string, 'hh:mmaaa')}
      </Typography>
      <Box sx={tooltipStyles(theme).categoriesContainer}>
        {payload.map((category) => {
          const isLeft = leftName && (category.name === leftName || (category as any).dataKey === leftName);
          const isRight = rightName && (category.name === rightName || (category as any).dataKey === rightName);
          const formatter = isLeft ? valueFormatterLeft : isRight ? valueFormatterRight : undefined;
          const formatted = formatter ? formatter(category.value as number | undefined) : `${formatTwoDecimals?.(category.value)}`;
          const displayName = isLeft && leftLabel ? leftLabel : isRight && rightLabel ? rightLabel : category.name;
          return (
            <Typography key={category.name} component="span" variant="caption" sx={tooltipStyles(theme).categoryEntry(category.color)}>
              {displayName}: {formatted}
            </Typography>
          );
        })}
      </Box>
    </Box>
  );
};
