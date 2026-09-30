/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, SxProps, Typography, useTheme } from '@mui/material';
export interface DotLabelProps {
  caption?: React.ReactNode;
  dotColor: string;
  dotSize?: string;
  label?: React.ReactNode;
  labelSx?: SxProps;
}
export const DotLabel = ({ caption, dotColor, dotSize, label, labelSx = {} }: DotLabelProps) => {
  const theme = useTheme();

  return (
    <Box display="inline-flex" alignItems="center">
      <Box
        sx={{
          height: dotSize ?? '8px',
          width: dotSize ?? '8px',
          borderRadius: '50%',
          backgroundColor: dotColor
        }}
      />
      {label && (
        <Box display="flex" flexDirection="column" textTransform="capitalize" ml={1}>
          <Typography variant={'body2'} color={theme.palette.vars.baseTextStrong} sx={labelSx}>
            {label}
          </Typography>
          <Typography variant="caption" color={theme.palette.vars.baseTextStrong} lineHeight={1}>
            {caption}
          </Typography>
        </Box>
      )}
    </Box>
  );
};
