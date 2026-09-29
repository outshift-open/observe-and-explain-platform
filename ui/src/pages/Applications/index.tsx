/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { PageWithTitle } from '@/components';
import { pageGradientBottomLeftSx, pageGradientContentSx } from '@/common/styles';
import { Box, Typography, useTheme } from '@mui/material';

import { ApplicationsGrid } from './ApplicationsGrid';

const Applications = () => {
  const theme = useTheme();

  return (
    <Box sx={pageGradientBottomLeftSx}>
      <PageWithTitle
        title={
          <Typography variant={'h5'} sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}>
            Applications
          </Typography>
        }
        sx={pageGradientContentSx}
      >
        <ApplicationsGrid />
      </PageWithTitle>
    </Box>
  );
};

export default Applications;
