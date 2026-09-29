/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Tooltip } from '@mui/material';
import Slider from '@mui/material/Slider';
import { styled } from '@mui/material/styles';
import React from 'react';

export interface GradientScoreSliderProps {
  value: number;
  min?: number;
  max?: number;
  height?: number;
  gradient?: string;
  sx?: any;
  tooltipTitle?: React.ReactNode;
}

const createGradient = (custom?: string) => custom ?? 'linear-gradient(90deg, #FF3B30 0%, #FF9500 25%, #FFD60A 50%, #34C759 100%)';

const createStyledSlider = (heightPx: number, gradientCss: string) =>
  styled(Slider)(({ theme }) => ({
    color: 'transparent',
    height: heightPx,
    padding: `${Math.max(0, Math.floor(heightPx / 2) - 2)}px 0`,
    pointerEvents: 'none',
    '& .MuiSlider-rail': {
      opacity: 1,
      height: heightPx,
      borderRadius: heightPx / 2,
      background: gradientCss
    },
    '& .MuiSlider-track': {
      display: 'none'
    },
    '& .MuiSlider-thumb': {
      width: 2,
      height: heightPx + 4,
      borderRadius: 1,
      backgroundColor: theme.palette.mode === 'dark' ? theme.palette.common.white : theme.palette.common.black,
      border: `1px solid ${theme.palette.divider}`,
      boxShadow: 'none',
      pointerEvents: 'none'
    }
  }));

export const GradientScoreSlider: React.FC<GradientScoreSliderProps> = ({ value, min = 0, max = 100, height = 12, gradient, sx, tooltipTitle }) => {
  const gradientCss = createGradient(gradient);
  const StyledSlider = React.useMemo(() => createStyledSlider(height, gradientCss), [height, gradientCss]);

  const sliderValue = Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : min;

  return (
    <Box sx={{ width: '100%', ...sx }}>
      <Tooltip title={tooltipTitle ?? ''} placement={'top'} arrow>
        <Box>
          <StyledSlider value={sliderValue} min={min} max={max} step={1} disabled aria-label="score" />
        </Box>
      </Tooltip>
    </Box>
  );
};

export default GradientScoreSlider;
