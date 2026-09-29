/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack } from '@mui/material';
import { AgentDetailsSideBarItemList } from './AgentDetailsSideBarItemList.tsx';
import { Outlet } from 'react-router-dom';

const AgentDetailsPopulation = ({}) => {
  return (
    <Stack direction={'row'} sx={{ height: '100%' }}>
      <AgentDetailsSideBarItemList />
      <Outlet />
    </Stack>
  );
};

export default AgentDetailsPopulation;
