/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { List, Stack, useTheme } from '@mui/material';
import { SideBarItem } from './SideBarItem';
import { authenticatedRoutes, unauthenticatedRoutes, PATHS } from '@/routes/routes.tsx';
import { useLocation, useMatch } from 'react-router-dom';
import { AppRoute } from '@/routes/types.ts';

export const SideBarItemList = () => {
  const { pathname } = useLocation();
  const theme = useTheme();

  //  const { authInfo } = useAuth();
  // const isUserAuthenticated = Boolean(authInfo?.accessToken?.accessToken);

  const isUserAuthenticated = true;

  const allRoutes = [...unauthenticatedRoutes, ...(isUserAuthenticated ? authenticatedRoutes : [])];

  const isInAgentDetails = !!useMatch(`${PATHS.agent}/*`);

  const isParentRouteSelected = (route: AppRoute) => {
    // if (route.children?.length) {
    //   return false;
    // }

    if (route.path === '/') {
      return pathname === '/';
    } else return pathname.startsWith(route.path);
  };

  return (
    <List
      sx={{
        gap: '4px',
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      {allRoutes
        .map((parentRoute) => {
          return parentRoute.sideBarProps ? (
            <Stack direction={'column'} gap={'4px'} key={parentRoute.sideBarProps.title}>
              <SideBarItem
                {...parentRoute.sideBarProps}
                selected={isParentRouteSelected(parentRoute)}
                to={parentRoute.path}
                compact={isInAgentDetails}
              />
            </Stack>
          ) : null;
        })
        .filter(Boolean)}
    </List>
  );
};
