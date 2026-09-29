/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { PageWithTitle } from '@/components';
import { pageGradientSx, pageGradientContentSx } from '@/common/styles';
import { Box, Stack, Typography, useTheme } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import { EmptyState } from '@open-ui-kit/core';

const Dashboard = () => {
  const theme = useTheme();

  const getCostContent = () => {
    return (
      <Stack direction={'row'} gap={'4px'} alignItems={'center'}>
        <Typography variant="h5">$103</Typography>
        <TrendingUpIcon sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }} />
        <Typography variant={'body2Semibold'}>1%</Typography>
        <Typography variant={'body2Semibold'}>yesterday</Typography>
      </Stack>
    );
  };

  const getModelUsageContent = () => {
    return (
      <Stack direction={'row'} gap={'4px'} alignItems={'center'}>
        <Typography variant="h5">100K tokens</Typography>
        <TrendingDownIcon sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }} />
        <Typography variant={'body2Semibold'}>1%</Typography>
        <Typography variant={'body2Semibold'}>yesterday</Typography>
      </Stack>
    );
  };

  return (
    <Box sx={pageGradientSx}>
      <PageWithTitle
        title={
          <Typography variant={'h5'} sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}>
            Dashboard
          </Typography>
        }
        sx={pageGradientContentSx}
      >
        <Stack direction={'column'} gap={'24px'}>
          <EmptyState
            actionCallback={() => {}}
            actionTitle="Customize Dashboard"
            description="Integrate essential metrics into your dashboard for smarter monitoring and deeper analysis."
            title=""
          />
        </Stack>
      </PageWithTitle>
    </Box>
  );
};

export default Dashboard;
