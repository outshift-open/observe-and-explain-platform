/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { TabPanel } from '@/components/TabPanel';
import { Tabs, Tab, Stack } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import type { SyntheticEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApplicationTab } from './ApplicationTab';
import { AgentsTab } from './AgentsTab';

export const TAB_NAMES = ['application', 'agents'] as const;

const MonitorTab = () => {
  const navigate = useNavigate();
  const { applicationId, monitorTab } = useParams();
  const activeTab = TAB_NAMES.indexOf(monitorTab as (typeof TAB_NAMES)[number]);
  const currentTab = activeTab >= 0 ? activeTab : 0;

  const handleTabChange = (_event: SyntheticEvent, value: number) => {
    navigate(`/applications/${applicationId}/monitor/${TAB_NAMES[value]}`);
  };

  const theme = useTheme();

  return (
    <Stack
      direction={'column'}
      sx={{ width: '100%', height: '100%' }}
      gap={'24px'}
    >
      <Stack direction={'row'} sx={{ width: '100%' }} alignItems={'flex-end'}>
        <Tabs
          value={currentTab}
          onChange={handleTabChange}
          slotProps={{
            indicator: {
              sx: {
                backgroundColor: `${theme.palette.vars.neutralTextDefault} !important`
              }
            }
          }}
        >
          <Tab label={'Application Level'} />
          <Tab label={'Agents'} />
        </Tabs>
      </Stack>
      <TabPanel value={currentTab} index={0} sx={{ height: '100%' }}>
        <ApplicationTab />
      </TabPanel>
      <TabPanel value={currentTab} index={1} sx={{ height: '100%' }}>
        <AgentsTab />
      </TabPanel>
    </Stack>
  );
};

export default MonitorTab;
