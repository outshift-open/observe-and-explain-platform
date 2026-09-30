/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import { Task } from '@/types/oxp.type';

interface DrawerTitleProps {
  tasks: Task[];
}

export const DrawerTitle = ({ tasks }: DrawerTitleProps) => {
  const theme = useTheme();

  return (
    <Stack direction={'row'} gap={'4px'}>
      <Typography variant={'h5'} sx={{ color: theme.palette.vars.controlIconStrong }}>
        {tasks.length} task{tasks.length > 1 ? 's' : ''}
      </Typography>
    </Stack>
  );
};
