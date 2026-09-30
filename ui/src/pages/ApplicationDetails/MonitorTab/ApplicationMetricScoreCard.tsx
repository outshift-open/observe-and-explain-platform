/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Typography } from '@mui/material';
import { Button, Card, GaugeChart, Stack } from '@open-ui-kit/core';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { CustomTooltip } from '@/components/CustomTooltip';
import { getInsightMessage, getScoreVariant } from '@/utils/metrics';
import {
  ApplicationLevelMetricCategory,
  ApplicationLevelMetricCategoryDescription,
  ApplicationLevelMetricCategoryLabels
} from '@/api/applicationLevelMetrics';

interface ApplicationMetricScoreCardProps {
  category: ApplicationLevelMetricCategory;
  value: number;
  onSelect: (category: ApplicationLevelMetricCategory) => void;
}

export const ApplicationMetricScoreCard = ({
  category,
  value,
  onSelect
}: ApplicationMetricScoreCardProps) => {
  const title = ApplicationLevelMetricCategoryLabels[category];
  const description = ApplicationLevelMetricCategoryDescription[category];

  return (
    <Stack
      direction={'column'}
      alignItems={'flex-start'}
      justifyContent={'center'}
      gap={'8px'}
      sx={{ cursor: 'pointer' }}
      onClick={() => onSelect(category)}
    >
      <Stack direction={'row'} alignItems={'center'} gap={'4px'}>
        <Typography variant={'captionSemibold'}>{title}</Typography>
        <CustomTooltip
          title={
            <Typography variant={'caption'} sx={{ whiteSpace: 'pre-line' }}>
              {description}
            </Typography>
          }
          placement={'top'}
          sx={{ maxWidth: '550px' }}
        >
          <InfoOutlineIcon
            sx={{ width: '14px', height: '14px', cursor: 'pointer' }}
          />
        </CustomTooltip>
      </Stack>

      <Stack
        direction={'row'}
        justifyContent={'center'}
        gap={'8px'}
        sx={{ width: '100%' }}
      >
        <Box
          sx={{
            position: 'relative',
            margin: '16px 0',
            height: 172,
            width: 172
          }}
        >
          <GaugeChart
            data={[{ name: title, value }]}
            variant={getScoreVariant(value)}
          />
          <Button
            variant={'gradientOutlined'}
            size={'small'}
            disableRipple
            onClick={(e) => {
              e.stopPropagation();
              onSelect(category);
            }}
            sx={{
              position: 'absolute',
              bottom: '40px',
              left: '50%',
              transform: 'translateX(-50%)',
              textTransform: 'none',
              '&:focus, &:focus-visible, &.Mui-focusVisible': {
                outline: 'none !important',
                boxShadow: 'none !important'
              }
            }}
          >
            View More
          </Button>
        </Box>
      </Stack>

      <Card glow>
        <Typography variant={'body2'}>
          {getInsightMessage(value, category)}
        </Typography>
      </Card>
    </Stack>
  );
};

export default ApplicationMetricScoreCard;
