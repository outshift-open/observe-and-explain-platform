/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import { ApplicationLevelMetricCategory, ApplicationLevelMetricCategoryLabels } from '@/api/applicationLevelMetrics';
import { CustomTooltip } from '../CustomTooltip';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';

interface DrawerTitleProps {
  metricCategory: ApplicationLevelMetricCategory;
  description?: string;
}

export const DrawerTitle = ({ metricCategory, description }: DrawerTitleProps) => {
  const theme = useTheme();

  return (
    <Stack direction={'row'} gap={'4px'}>
      <Typography variant={'h5'} sx={{ color: theme.palette.vars.controlIconStrong }}>
        {ApplicationLevelMetricCategoryLabels[metricCategory]}
      </Typography>

      {description && (
        <CustomTooltip
          title={
            typeof description === 'string' ? (
              <Typography variant={'caption'} sx={{ whiteSpace: 'pre-line' }}>
                {description}
              </Typography>
            ) : (
              description
            )
          }
          placement={'top'}
          sx={{ maxWidth: '550px' }}
        >
          <InfoOutlineIcon
            sx={{
              width: '14px',
              height: '14px',
              cursor: 'pointer'
            }}
          />
        </CustomTooltip>
      )}
    </Stack>
  );
};
