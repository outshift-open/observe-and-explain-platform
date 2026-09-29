/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import '@open-ui-kit/core/typography.css';
import '@xyflow/react/dist/style.css';
import { ThemeProvider, ThemeMode as KitThemeMode } from '@open-ui-kit/core';

import { BrowserRouter as Router } from 'react-router-dom';
import { Box, CssBaseline } from '@mui/material';
import { TopBar } from '@/components';
import { ErrorBoundary } from 'react-error-boundary';
import appRoutes from '@/routes/routes.tsx';

import { QueryClientProvider } from '@/provider';

const ErrorFallback = () => <div>Something went wrong!</div>;

const App = () => {
  return (
    <ErrorBoundary fallback={<ErrorFallback />}>
      <QueryClientProvider>
        <ThemeProvider defaultMode={KitThemeMode.Midnight}>
          <CssBaseline />
          <Router>
            <Box
              sx={{
                height: '100%',
                width: '100%',
                display: 'flex',
                flexDirection: 'column'
              }}
            >
              <TopBar />
              <Box sx={{ flex: 1 }}>{appRoutes}</Box>
            </Box>
          </Router>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};

export default App;
