/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Typography } from '@mui/material';

export interface CircleBadgeProps {
  letter: string;
  color: string;
  size?: 'small' | 'medium';
}

export const CircleBadge = ({ letter, color, size = 'medium' }: CircleBadgeProps) => {
  const isSmall = size === 'small';
  const dimension = isSmall ? '16px' : '24px';
  const borderWidth = isSmall ? '1.5px' : '2px';
  const fontSize = isSmall ? '9px' : '12px';

  return (
    <Box
      sx={{
        width: dimension,
        height: dimension,
        borderRadius: '50%',
        border: `${borderWidth} solid ${color}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      <Typography
        variant="caption"
        sx={{
          color: color,
          fontWeight: 600,
          fontSize: fontSize,
          lineHeight: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        {letter}
      </Typography>
    </Box>
  );
};

export default CircleBadge;
