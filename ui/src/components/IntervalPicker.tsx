/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Button, Popover, PopoverPlacement } from '@open-ui-kit/core';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import { Slider, Stack, Typography, useTheme } from '@mui/material';
import { DateTimePicker } from '@/components/DateTimePicker.tsx';
import { useEffect, useState } from 'react';
import dayjs, { Dayjs } from 'dayjs';

export type IntervalValue =
  | 'second'
  | 'minute'
  | 'hour'
  | 'day'
  | 'week'
  | 'month'
  | 'year';

export type IntervalDisplay =
  | '30sec'
  | '1min'
  | '5min'
  | '12H'
  | '1D'
  | '1W'
  | '1M'
  | '6M'
  | '1Y';

export interface Interval {
  value: number;
  unit: IntervalValue;
  display: IntervalDisplay;
}

export const INTERVALS: Interval[] = [
  {
    value: 30,
    unit: 'second',
    display: '30sec'
  },
  {
    value: 1,
    unit: 'minute',
    display: '1min'
  },
  {
    value: 5,
    unit: 'minute',
    display: '5min'
  },
  {
    value: 1,
    unit: 'month',
    display: '1M'
  }
];

// export const INTERVALS: Interval[] = [
//   {
//     value: 12,
//     unit: 'hour',
//     display: '12H'
//   },
//   {
//     value: 1,
//     unit: 'day',
//     display: '1D'
//   },
//   {
//     value: 1,
//     unit: 'week',
//     display: '1W'
//   },
//   {
//     value: 1,
//     unit: 'month',
//     display: '1M'
//   },
//   {
//     value: 6,
//     unit: 'month',
//     display: '6M'
//   },
//   {
//     value: 1,
//     unit: 'year',
//     display: '1Y'
//   }
// ];

const MINUTES_IN_DAY = 24 * 60;
const MINUTES_PER_STEP = 5;
const STEPS = MINUTES_IN_DAY / MINUTES_PER_STEP;

interface IntervalPickerProps {
  startDate: number; // seconds
  endDate: number; // seconds
  setStartDate: (startTimeSec: number) => void;
  setEndDate: (endTimeSec: number) => void;
  isSliderEnabled?: boolean;
}

export const IntervalPicker = ({
  startDate,
  endDate,
  setStartDate,
  setEndDate,
  isSliderEnabled = false
}: IntervalPickerProps) => {
  const [selectedInterval, setSelectedInterval] = useState<Interval | null>();
  const [customIntervalAnchorEl, setCustomIntervalAnchorEl] =
    useState<HTMLButtonElement | null>(null);
  const [isCustomInterval, setIsCustomInterval] = useState(false);
  const [sliderIntervalValue, setSliderIntervalValue] = useState<number[]>([
    0, 72
  ]);
  const [isSliderActive, setIsSliderActive] = useState(false);

  const theme = useTheme();

  useEffect(() => {
    setIsCustomInterval(true);
    setIsSliderActive(false);
  }, []);

  // useEffect(() => {
  //   if (selectedInterval && ['30sec', '1min', '5min'].includes(selectedInterval.display) && !isCustomInterval) {
  //     const intervalId = setInterval(() => {
  //       setStartDate(dayjs().subtract(selectedInterval.value, selectedInterval.unit));
  //       setEndDate(dayjs());
  //     }, 1000); // Update every second
  //
  //     // Cleanup function to clear interval when component unmounts or interval changes
  //     return () => clearInterval(intervalId);
  //   }
  // }, [selectedInterval, setStartDate, setEndDate, isCustomInterval]);

  const handleCustomIntervalClick = (
    event: React.MouseEvent<HTMLButtonElement>
  ) => {
    setCustomIntervalAnchorEl(event.currentTarget);
  };

  const updateInterval = (interval: Interval) => {
    setSelectedInterval(interval);
    const end = dayjs();
    const start = end.subtract(interval.value, interval.unit);
    setStartDate(Math.floor(start.valueOf() / 1000));
    setEndDate(Math.floor(end.valueOf() / 1000));
    setIsCustomInterval(false);
    setIsSliderActive(false);
  };

  const updateCustomInterval = (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent>
  ) => {
    setIsCustomInterval(true);
    handleCustomIntervalClick(e);
    setIsSliderActive(false);
  };

  const convertSliderValueToDate = (value: number) => {
    const minutesFromStart = (STEPS - value) * MINUTES_PER_STEP;
    return dayjs().subtract(minutesFromStart, 'minutes');
  };

  const updateSliderInterval = (
    event: Event,
    newValue: number[],
    activeThumb: number
  ) => {
    const minDistance = 1;
    let finalValues: number[];

    if (activeThumb === 0) {
      finalValues = [
        Math.min(newValue[0], sliderIntervalValue[1] - minDistance),
        sliderIntervalValue[1]
      ];
    } else {
      finalValues = [
        sliderIntervalValue[0],
        Math.max(newValue[1], sliderIntervalValue[0] + minDistance)
      ];
    }

    setSliderIntervalValue(finalValues);
    const start = convertSliderValueToDate(finalValues[0]);
    const end = convertSliderValueToDate(finalValues[1]);
    setStartDate(Math.floor(start.valueOf() / 1000));
    setEndDate(Math.floor(end.valueOf() / 1000));
    setSelectedInterval(null);
    setIsCustomInterval(false);
  };

  const getAriaValueText = (value: number) => {
    return convertSliderValueToDate(value).format('HH:mm');
  };

  const getTimeLabel = (value: number) => {
    return convertSliderValueToDate(value).format('MM/DD/YYYY HH:mm');
  };

  const selectedIntervalButtonStyle = {
    backgroundColor: theme.palette.vars.interactivePrimaryDefaultDefault
  };

  return (
    <Stack direction="row" gap={'12px'} alignItems={'center'}>
      <Stack direction="row">
        {INTERVALS.map((interval, index) => (
          <Button
            variant={
              !isCustomInterval &&
              selectedInterval?.display === interval.display
                ? 'gradient'
                : 'outlined'
            }
            sx={{
              '&.MuiButton-sizeMedium:focus': {
                outline: 'none'
              },
              '&.MuiButton-sizeMedium': {
                height: '36px',
                borderRadius: index === 0 ? '4px 0 0 4px' : '0',
                border: 'none',
                color: theme.palette.vars.baseTextDefault,
                ...(!isCustomInterval &&
                selectedInterval?.display === interval.display
                  ? selectedIntervalButtonStyle
                  : {
                      backgroundColor:
                        theme.palette.vars.interactivePrimaryWeakActive
                    }),
                '&:hover': {
                  border: 'none'
                },
                '&:last-child': { borderRadius: '0 4px 4px 0' }
              }
            }}
            onClick={() => updateInterval(interval)}
            key={interval.display}
          >
            {interval.display}
          </Button>
        ))}
      </Stack>

      {isSliderEnabled && (
        <Stack direction="row" gap={'16px'} alignItems={'center'}>
          <Typography variant={'body2Semibold'}>Past 24hrs</Typography>
          <Slider
            getAriaLabel={() => 'Temperature range'}
            value={sliderIntervalValue}
            onChange={updateSliderInterval}
            valueLabelDisplay="auto"
            valueLabelFormat={getTimeLabel}
            getAriaValueText={getAriaValueText}
            disableSwap
            min={0}
            max={STEPS}
            onMouseDown={() => setIsSliderActive(true)}
            sx={{
              width: '300px',
              '& .MuiSlider-track': {
                backgroundColor: isSliderActive
                  ? theme.palette.vars.interactivePrimaryDefaultDefault
                  : theme.palette.vars.interactivePrimaryWeakActive,
                border: 'none'
              },
              '& .MuiSlider-thumb': {
                backgroundColor: isSliderActive
                  ? theme.palette.vars.interactivePrimaryDefaultDefault
                  : theme.palette.vars.interactivePrimaryWeakActive,
                '&:after': {
                  width: '20px',
                  height: '20px'
                }
              },
              '& .MuiSlider-rail': {
                backgroundColor: theme.palette.grey[300]
              }
            }}
          />
        </Stack>
      )}

      <Button
        variant={isCustomInterval ? 'gradient' : 'outlined'}
        sx={{
          '& .MuiButton-endIcon': { marginLeft: 0 },
          '&.MuiButton-sizeMedium:focus': {
            outline: 'none',
            boxShadow: 'none'
          },
          '&.MuiButton-sizeMedium': {
            height: '36px',
            borderRadius: '4px',
            border: 'none',
            color: theme.palette.vars.baseTextDefault,
            ...(isCustomInterval
              ? selectedIntervalButtonStyle
              : {
                  backgroundColor:
                    theme.palette.vars.interactivePrimaryWeakActive
                }),
            '&:hover': {
              border: 'none',
              backgroundColor:
                theme.palette.vars.interactivePrimaryDefaultDefault,
              color: theme.palette.vars.interactiveInverseTextDefault
            }
          }
        }}
        onClick={updateCustomInterval}
        endIcon={<ArrowDropDownIcon />}
      >
        Custom
      </Button>

      <Popover
        open={Boolean(customIntervalAnchorEl)}
        anchorEl={customIntervalAnchorEl}
        onClose={() => setCustomIntervalAnchorEl(null)}
        placement={PopoverPlacement.Bottom}
        paperSx={{ width: '500px', minWidth: '500px', maxWidth: '500px' }}
      >
        <Stack direction={'row'} gap={'16px'} sx={{ padding: '12px 16px' }}>
          <DateTimePicker
            label={'From'}
            ampm={false}
            timeSteps={{ minutes: 1 }}
            value={dayjs.unix(startDate)}
            onChange={(newValue) => {
              setStartDate(Math.floor((newValue?.valueOf() ?? 0) / 1000));
            }}
          />
          <DateTimePicker
            label={'To'}
            ampm={false}
            timeSteps={{ minutes: 1 }}
            value={dayjs.unix(endDate)}
            onChange={(newValue) => {
              setEndDate(Math.floor((newValue?.valueOf() ?? 0) / 1000));
            }}
          />
        </Stack>
      </Popover>
    </Stack>
  );
};
