/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography, useTheme } from '@mui/material';
import type { StackProps, Theme, TypographyProps } from '@mui/material';
import { IndicatorBadge } from '@open-ui-kit/core';

type IndicatorValue = 0 | 1 | 2 | 3 | 4;

export interface ScoreSeverityBadgeLevel {
  color: string;
  // Number of filled bars, filled from bottom to top.
  value: IndicatorValue;
  label: string;
  // Inclusive upper bound of the score bucket.
  threshold: number;
}

export interface ScoreSeverityBadgeLabelProps {
  // Score from 0 to 100 where a higher score is better.
  score: number;
  // Custom text shown instead of the level label.
  label?: string;
  // Ordered (ascending threshold) levels; defaults to getDefaultLevels.
  levels?: ScoreSeverityBadgeLevel[];
  containerStackProps?: StackProps;
  labelTypographyProps?: TypographyProps;
}

// Counterpart of the kit's SeverityBadge score system, but inverted: the better
// the score, the more bars are filled and the greener they are.
const getDefaultLevels = (theme: Theme): ScoreSeverityBadgeLevel[] => [
  {
    color: theme.palette.vars.negativeBackgroundActive,
    value: 1,
    label: 'Poor',
    threshold: 50
  },
  {
    color: theme.palette.vars.severeWarningBackgroundDefault,
    value: 2,
    label: 'Fair',
    threshold: 70
  },
  {
    color: theme.palette.vars.warningBackgroundActive,
    value: 3,
    label: 'Good',
    threshold: 85
  },
  {
    color: theme.palette.vars.successBackgroundDefault,
    value: 4,
    label: 'Excellent',
    threshold: 100
  }
];

// Severity-style badge (segmented bars + label) for scores where higher is
// better, e.g. a confidence or an average metric score.
export const ScoreSeverityBadgeLabel = ({
  score,
  label,
  levels,
  containerStackProps,
  labelTypographyProps
}: ScoreSeverityBadgeLabelProps) => {
  const theme = useTheme();
  const scale = levels ?? getDefaultLevels(theme);
  const level = scale.find((item) => score <= item.threshold) ??
    scale[scale.length - 1] ?? {
      color: theme.palette.vars.baseTextDisabled,
      value: 0 as IndicatorValue,
      label: 'N/A'
    };

  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      {...containerStackProps}
    >
      <IndicatorBadge color={level.color} value={level.value} />
      <Typography variant="body2" {...labelTypographyProps}>
        {label ?? level.label}
      </Typography>
    </Stack>
  );
};
