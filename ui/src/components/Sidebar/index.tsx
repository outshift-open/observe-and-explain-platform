/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Drawer, Stack, useTheme } from '@mui/material';
import { SideBarItemList } from './SideBarItemList';
import { sideBarDrawerStyle, sideBarPaperStyle } from './styles';
import { useMatch } from 'react-router-dom';
import { PATHS } from '@/routes/routes.tsx';

export const Sidebar = () => {
  const theme = useTheme();

  const isInAgentDetails = !!useMatch(`${PATHS.agent}/*`);

  return (
    <Box sx={sideBarDrawerStyle(theme, isInAgentDetails)}>
      <Drawer
        variant="permanent"
        anchor="left"
        slotProps={{
          paper: {
            sx: sideBarPaperStyle(theme, isInAgentDetails)
          }
        }}
        sx={sideBarDrawerStyle(theme, isInAgentDetails)}
        data-testid="sidebar"
      >
        <Stack
          direction="column"
          gap={'16px'}
          sx={{ height: '100%', paddingLeft: '8px', paddingRight: '8px' }}
        >
          <SideBarItemList />
        </Stack>
      </Drawer>
    </Box>
  );
};
