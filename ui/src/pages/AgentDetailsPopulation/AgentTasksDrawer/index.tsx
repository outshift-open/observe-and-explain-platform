/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, SideDrawer, Spinner, Stack } from '@open-ui-kit/core';
import { DrawerTitle } from './DrawerTitle';
import { DrawerContent } from './DrawerContent';
import { Task } from '@/types/oxp.type';

interface AgentTasksDrawerProps {
  onClose: () => void;
  tasks: Task[];
}

const AgentTasksDrawer = ({ tasks, onClose }: AgentTasksDrawerProps) => {
  return (
    <SideDrawer
      open={Boolean(tasks)}
      onClose={onClose}
      titleNode={<DrawerTitle tasks={tasks} />}
      copyURL={''}
      hideTitleAction={true}
      hidePrev={true}
      hideNext={true}
      hideActionButtons={true}
      hideFooter={true}
      customDividerStyle={{ display: 'none' }}
      paperProps={{
        width: '980px',
        '&.MuiPaper-root > .MuiBox-root': {
          width: '980px'
        }
      }}
    >
      <DrawerContent tasks={tasks} />
    </SideDrawer>
  );
};

export default AgentTasksDrawer;
