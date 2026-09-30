/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography, Box, Tooltip } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { getDisplayedResultsCount } from '@/utils';
import { BiaxialLineChart } from './BiaxialLineChart';
import { SxProps } from '@mui/material';

interface BiaxialMetricChartProps {
  data: { date: string; [key: string]: number | string }[];
  // dataLeft: TimelineData[];
  // dataRight: TimelineData[];
  metricKeyLeft: string;
  metricKeyRight: string;
  metricDef: {
    name: string;
    description?: string;
  };
  chartSuffixLeft: string;
  chartSuffixRight: string;
  operationLeftValue: number;
  operationRightValue: number;
  valueFormatterLeft?: (value?: number) => string;
  valueFormatterRight?: (value?: number) => string;
  legendLabelLeft?: string;
  legendLabelRight?: string;
  containerSx?: SxProps;
}

export const BiaxialMetricChart = ({
  data,
  // dataLeft,
  // dataRight,
  metricKeyLeft,
  metricKeyRight,
  metricDef,
  chartSuffixLeft,
  chartSuffixRight,
  operationLeftValue,
  operationRightValue,
  valueFormatterLeft,
  valueFormatterRight,
  legendLabelLeft,
  legendLabelRight,
  containerSx
}: BiaxialMetricChartProps) => {
  const theme = useTheme();

  // const chartDataLeft = dataLeft.map((item) => ({
  //   date: item.timestamp,
  //   [metricKeyLeft]: item.value.value
  // }));
  // const chartDataRight = dataRight.map((item) => ({
  //   date: item.timestamp,
  //   [metricKeyRight]: item.value.value
  // }));

  return (
    <Stack
      direction={'column'}
      gap={'16px'}
      sx={{
        borderRadius: '8px',
        height: '316px',
        padding: '16px',
        ...containerSx
      }}
    >
      <Stack direction={'column'}>
        <Stack direction={'row'} alignItems={'center'} gap={'8px'}>
          <Typography variant={'captionSemibold'}>{metricDef.name}</Typography>
          {metricDef.description && (
            <Tooltip
              title={metricDef.description}
              placement={'top'}
              sx={{ maxWidth: '400px' }}
            >
              <InfoOutlineIcon
                sx={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
            </Tooltip>
          )}
        </Stack>

        <Stack direction={'row'} gap={'8px'}>
          <Typography variant={'h6'}>
            {getDisplayedResultsCount(operationLeftValue)}
            {chartSuffixLeft}
          </Typography>
          <Typography variant={'h6'}>/</Typography>
          <Typography variant={'h6'}>
            {getDisplayedResultsCount(operationRightValue)}
            {chartSuffixRight}
          </Typography>
        </Stack>

        <Stack direction={'row'} gap={'16px'} mt={'4px'}>
          <Stack direction={'row'} alignItems={'center'} gap={'6px'}>
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor:
                  theme.palette.mode === 'dark'
                    ? theme.palette.vars.accentEWeak
                    : '#8884d8'
              }}
            />
            <Typography variant={'caption'} color={'text.secondary'}>
              {legendLabelLeft ?? metricKeyLeft}
            </Typography>
          </Stack>
          <Stack direction={'row'} alignItems={'center'} gap={'6px'}>
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor:
                  theme.palette.mode === 'dark'
                    ? theme.palette.vars.accentDWeak
                    : '#82ca9d'
              }}
            />
            <Typography variant={'caption'} color={'text.secondary'}>
              {legendLabelRight ?? metricKeyRight}
            </Typography>
          </Stack>
        </Stack>
      </Stack>

      <Box
        sx={{
          width: '100%'
        }}
      >
        <Stack
          direction={'column'}
          gap={'16px'}
          sx={{
            height: '220px',
            padding: '0 24px 0 0',
            width: '100%'
          }}
        >
          <BiaxialLineChart
            data={data}
            // dataLeft={data}
            // dataRight={data}
            leftCategory={{
              name: metricKeyLeft,
              color:
                theme.palette.mode === 'dark'
                  ? theme.palette.vars.accentEWeak
                  : '#8884d8'
            }}
            rightCategory={{
              name: metricKeyRight,
              color:
                theme.palette.mode === 'dark'
                  ? theme.palette.vars.accentDWeak
                  : '#82ca9d'
            }}
            valueFormatterLeft={valueFormatterLeft}
            valueFormatterRight={valueFormatterRight}
            leftLabel={legendLabelLeft}
            rightLabel={legendLabelRight}
            xAxisProps={{
              tick: false,
              label: {
                value: 'Time',
                position: 'bottomCenter',
                style: { fontSize: 12 }
              }
            }}
            yAxisRightProps={{
              domain: [0, 'auto']
            }}
          />
        </Stack>
      </Box>
    </Stack>
  );
};

export default BiaxialMetricChart;
