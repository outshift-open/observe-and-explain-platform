/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import '@open-ui-kit/core/typography.css';
import type { Preview } from '@storybook/react-vite';
import React from 'react';
import { ThemeProvider } from '@open-ui-kit/core';
import { ThemeProvider as MuiThemeProvider, useTheme } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { createLocalTheme } from '../src/theme/theme';

const LocalThemeLayer = ({ children }: { children: React.ReactNode }) => {
  const outerTheme = useTheme();
  const localTheme = createLocalTheme(outerTheme);
  return <MuiThemeProvider theme={localTheme}>{children}</MuiThemeProvider>;
};

const preview: Preview = {
  globalTypes: {
    theme: {
      description: 'Theme mode',
      toolbar: {
        title: 'Theme',
        icon: 'mirror',
        items: ['dark', 'light'],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    theme: 'dark',
  },
  decorators: [
    (Story, context) => {
      const isDark = context.globals.theme !== 'light';
      return (
        <ThemeProvider isDarkMode={isDark}>
          <LocalThemeLayer>
            <CssBaseline />
            <Story />
          </LocalThemeLayer>
        </ThemeProvider>
      );
    },
  ],
};

export default preview;
