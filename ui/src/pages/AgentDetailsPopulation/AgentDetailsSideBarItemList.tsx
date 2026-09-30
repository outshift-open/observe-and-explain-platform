/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { List, Stack, useTheme } from '@mui/material';
import { SideBarItem } from './SideBarItem';
import { Navigate, useLocation } from 'react-router-dom';
import { AppRoute } from '@/routes/types.ts';
import { AiAgent, Observability, RuntimeEvents } from '@/assets/icons';
import { AgentMonitor } from '@/pages/AgentDetailsPopulation/AgentMonitor.tsx';
import { AgentCollect } from '@/pages/AgentDetailsPopulation/AgentCollect.tsx';
import { AgentAnalyze } from '@/pages/AgentDetailsPopulation/AgentAnalyze/AgentAnalyze';

const PATHS = {
  agentMonitor: 'monitor',
  agentCollect: 'collect',
  agentAnalyze: 'analyze'
};

export const agentDetailsRoutes = [
  {
    name: 'DefaultAgentDetailsRedirect',
    path: '',
    element: <Navigate to={PATHS.agentMonitor} replace />
  },
  {
    name: 'Monitor',
    path: PATHS.agentMonitor,
    element: (
      //   <ProtectedRoute>
      <AgentMonitor />
      //   </ProtectedRoute>
    ),
    sideBarProps: {
      title: 'Monitor',
      icon: Observability
    }
  },
  {
    name: 'Collect',
    path: PATHS.agentCollect,
    element: (
      //   <ProtectedRoute>
      <AgentCollect />
      //   </ProtectedRoute>
    ),
    sideBarProps: {
      title: 'Collect',
      icon: RuntimeEvents
    }
  },
  {
    name: 'CollectSessionTab',
    path: `${PATHS.agentCollect}/:sessionId/:sessionTab`,
    element: (
      //   <ProtectedRoute>
      <AgentCollect />
      //   </ProtectedRoute>
    )
  },
  {
    name: 'CollectSession',
    path: `${PATHS.agentCollect}/:sessionId`,
    element: (
      //   <ProtectedRoute>
      <AgentCollect />
      //   </ProtectedRoute>
    )
  },
  {
    name: 'Analyze',
    path: PATHS.agentAnalyze,
    element: (
      //   <ProtectedRoute>
      <AgentAnalyze />
      //   </ProtectedRoute>
    ),
    sideBarProps: {
      title: 'Analyze',
      icon: AiAgent
    }
  }
];

export const AgentDetailsSideBarItemList = () => {
  const { pathname } = useLocation();
  const theme = useTheme();

  //  const { authInfo } = useAuth();
  // const isUserAuthenticated = Boolean(authInfo?.accessToken?.accessToken);

  const isUserAuthenticated = true;

  const isParentRouteSelected = (route: AppRoute) => {
    const segments = pathname.split('/').filter((segment) => segment.length > 0);

    return segments.includes(route.path ?? '');
  };

  return (
    <List
      sx={{
        gap: '4px',
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${theme.palette.vars.baseBorderDefault}`,
        padding: '24px'
      }}
    >
      {agentDetailsRoutes
        .map((route) => {
          return route.sideBarProps ? (
            <Stack key={route.sideBarProps.title} direction={'column'} gap={'4px'}>
              <SideBarItem {...route.sideBarProps} selected={isParentRouteSelected(route)} to={route.path} />
            </Stack>
          ) : null;
        })
        .filter(Boolean)}
    </List>
  );
};
