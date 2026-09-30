/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export const ellipsisTypographyStyle = {
  textOverflow: 'ellipsis',
  overflow: 'hidden',
  whiteSpace: 'nowrap'
};

export const linkStyle = () => ({
  margin: '0',
  fontSize: '14px',
  letterSpacing: '0.25px',
  color: 'grey',
  textDecoration: 'none'
});

export const GLOBAL_BACKGROUND_COLOR = '#000000';
export const GLOBAL_BORDER_COLOR = '#2F3032';
export const GLOBAL_TEXT_COLOR = '#FFFFFF';

const GRADIENT_BOTTOM_LEFT = [
  'radial-gradient(ellipse 45% 60% at 3% 105%, rgba(0, 80, 255, 0.5) 0%, transparent 70%)',
  'radial-gradient(ellipse 50% 50% at 10% 98%, rgba(0, 150, 220, 0.25) 0%, transparent 60%)'
];

const GRADIENT_TOP_RIGHT = [
  'radial-gradient(ellipse 60% 70% at 100% 15%, rgba(255, 0, 127, 0.12) 0%, transparent 75%)',
  'radial-gradient(ellipse 55% 65% at 95% 25%, rgba(255, 144, 0, 0.06) 0%, transparent 70%)',
  'radial-gradient(ellipse 70% 80% at 90% 20%, rgba(100, 30, 80, 0.15) 0%, transparent 70%)'
];

const gradientBase = {
  position: 'relative' as const,
  height: '100%',
  width: '100%',
  overflow: 'hidden',
  background: '#060a0f'
};

const gradientBeforeBase = {
  content: '""',
  position: 'absolute' as const,
  inset: 0,
  pointerEvents: 'none' as const
};

export const pageGradientContentSx = {
  position: 'relative',
  zIndex: 1
} as const;

export const pageGradientSx = {
  ...gradientBase,
  '&::before': {
    ...gradientBeforeBase,
    background: [...GRADIENT_BOTTOM_LEFT, ...GRADIENT_TOP_RIGHT].join(', ')
  }
};

const GRADIENT_BOTTOM_SPREAD = [
  'radial-gradient(ellipse 60% 40% at 50% 105%, rgba(140, 50, 120, 0.35) 0%, transparent 70%)',
  'radial-gradient(ellipse 40% 35% at 40% 105%, rgba(100, 40, 140, 0.25) 0%, transparent 65%)',
  'radial-gradient(ellipse 30% 30% at 90% 105%, rgba(255, 144, 0, 0.15) 0%, transparent 60%)'
];

export const pageGradientBottomLeftSx = {
  ...gradientBase,
  '&::before': {
    ...gradientBeforeBase,
    background: GRADIENT_BOTTOM_LEFT.join(', ')
  }
};

export const pageGradientBottomSx = {
  ...gradientBase,
  '&::before': {
    ...gradientBeforeBase,
    background: GRADIENT_BOTTOM_SPREAD.join(', ')
  }
};
