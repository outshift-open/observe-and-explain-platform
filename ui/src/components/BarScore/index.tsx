/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography, useTheme } from '@mui/material';
import { getScoreColor } from '@/utils/metrics';

export interface BarScoreProps {
  score: number;
  subtitle: string;
}

export const BarScore = ({ score, subtitle }: BarScoreProps) => {
  const theme = useTheme();
  const clampedScore = Math.max(0, Math.min(100, score));
  const displayScore = (clampedScore / 100).toFixed(2);
  const barColor = getScoreColor(clampedScore, theme);

  return (
    <Stack direction="column" gap="4px" sx={{ width: '100%' }}>
      <Typography variant="caption" sx={{ color: theme.palette.vars.baseTextMedium }}>
        {subtitle}
      </Typography>
      <Stack direction="row" gap="8px" alignItems="center">
        <Box
          sx={{
            flex: 1,
            height: '6px',
            backgroundColor: theme.palette.vars.baseBackgroundMedium,
            borderRadius: '3px',
            overflow: 'hidden'
          }}
        >
          <Box
            sx={{
              width: `${clampedScore}%`,
              height: '100%',
              backgroundColor: barColor,
              borderRadius: '3px',
              transition: 'width 0.3s ease-in-out'
            }}
          />
        </Box>
      </Stack>
      <Typography variant="caption" sx={{ color: barColor, fontWeight: 500, alignSelf: 'flex-end' }}>
        {displayScore}
      </Typography>
    </Stack>
  );
};

export default BarScore;
