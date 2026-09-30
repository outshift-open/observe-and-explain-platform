/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack } from '@open-ui-kit/core';
import { Task } from '@/types/oxp.type';
import { TasksTable } from '@/components/TasksTable';

interface DrawerContentProps {
  tasks: Task[];
}

export const DrawerContent = ({ tasks }: DrawerContentProps) => {
  return (
    <Stack direction={'column'} gap={'16px'} sx={{ width: '100%' }}>
      <TasksTable data={tasks} />
    </Stack>
  );
};
