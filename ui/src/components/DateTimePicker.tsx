/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import {
  DateTimePicker as MuiDateTimePicker,
  DateTimePickerProps as MuiDateTimePickerProps
} from '@mui/x-date-pickers/DateTimePicker';
import { useTheme } from '@mui/material';
import { Dayjs } from 'dayjs';

interface DateTimePickerProps extends MuiDateTimePickerProps<Dayjs> {
  label?: string;
}

export const DateTimePicker = ({ ...props }: DateTimePickerProps) => {
  const theme = useTheme();

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <MuiDateTimePicker
        views={['year', 'month', 'day', 'hours', 'minutes']}
        format="MM/DD/YYYY HH:mm"
        {...props}
        slotProps={{
          textField: {
            // placeholder: label,
            // variant: 'standard',
            size: 'small',
            sx: {
              '& .MuiInputBase-root': { marginTop: 0, width: '220px' },
              '& .MuiInputAdornment-root': {
                paddingRight: '8px'
              }
            }
          },
          leftArrowIcon: {
            sx: { color: theme.palette.vars.interactiveSecondaryDefaultDefault }
          },
          rightArrowIcon: {
            sx: { color: theme.palette.vars.interactiveSecondaryDefaultDefault }
          },
          calendarHeader: {
            sx: {
              position: 'relative',
              '& .MuiPickersCalendarHeader-labelContainer': { margin: 'auto' },
              '& .MuiPickersCalendarHeader-label': {
                ...theme.typography.body2Semibold,
                color: theme.palette.vars.interactiveSecondaryDefaultDefault
              },
              '& .MuiPickersArrowSwitcher-previousIconButton': {
                position: 'absolute',
                left: '26px',
                top: '8px'
              },
              '& .MuiPickersArrowSwitcher-nextIconButton': {
                position: 'absolute',
                right: '26px',
                top: '8px'
              }
            }
          },
          switchViewIcon: {
            sx: { color: theme.palette.vars.interactiveSecondaryDefaultDefault }
          },
          day: {
            sx: {
              ...theme.typography.subtitle2,
              color: theme.palette.vars.interactiveTextInDefault
            }
          },
          desktopPaper: {
            sx: {
              border: `2px solid ${theme.palette.vars.controlBorderActive}`,
              padding: '0 0 16px 0',

              backgroundColor: theme.palette.vars.controlBackgroundWeak,
              '& .MuiDayCalendar-weekDayLabel': {
                ...theme.typography.body2,
                color: theme.palette.vars.baseTextDefault
              },

              '& .MuiPickersDay-root': {
                color: theme.palette.vars.baseTextDefault,
                borderRadius: '4px'
              },
              '& .MuiPickersMonth-monthButton, & .MuiPickersYear-yearButton': {
                margin: '4px 0',
                width: `calc(100% - 4px)`,
                backgroundColor: `${theme.palette.vars.controlBackgroundDefault} !important`,
                border: `1px solid ${theme.palette.vars.interactiveSecondaryWeakDefault}`,
                borderRadius: '4px'
              },
              '& .MuiMultiSectionDigitalClockSection-root': {
                padding: '8px 4px 0 0'
              },
              '& .MuiMultiSectionDigitalClockSection-item.Mui-selected, & .MuiPickersDay-root.Mui-selected, & .MuiPickersMonth-monthButton.Mui-selected, & .MuiPickersYear-yearButton.Mui-selected':
                {
                  backgroundColor: `${theme.palette.vars.controlBackgroundDefault}`,
                  border: `1px solid ${theme.palette.vars.interactiveTertiaryActive}`,
                  color: theme.palette.vars.baseTextDefault
                },
              '& .MuiMultiSectionDigitalClockSection-item.Mui-selected:focus, & .MuiPickersDay-root.Mui-selected:focus, & .MuiPickersMonth-monthButton.Mui-selected:focus, & .MuiPickersYear-yearButton.Mui-selected:focus':
                {
                  backgroundColor: `${theme.palette.vars.controlBackgroundDefault}`,
                  border: `1px solid ${theme.palette.vars.interactiveTertiaryActive}`,
                  color: theme.palette.vars.baseTextDefault
                },
              '& .MuiMultiSectionDigitalClockSection-item.Mui-disabled, & .MuiPickersDay-root.Mui-disabled, & .MuiPickersMonth-monthButton.Mui-disabled, & .MuiPickersYear-yearButton.Mui-disabled':
                {
                  color: theme.palette.vars.interactiveTextInDisabled
                },

              '& .MuiMultiSectionDigitalClockSection-item:hover, & .MuiPickersDay-root:hover, & .MuiPickersMonth-monthButton:hover, & .MuiPickersYear-yearButton:hover':
                {
                  backgroundColor: `${theme.palette.vars.baseBackgroundHover} !important`
                }
            }
          },
          popper: {
            modifiers: [
              {
                name: 'offset',
                options: {
                  offset: [0, 12]
                }
              }
            ]
          },
          actionBar: {
            sx: {
              '& .MuiButton-root, & .MuiButton-root:hover': {
                ...theme.typography.body2Semibold,
                backgroundColor: `${theme.palette.vars.interactiveSecondaryDefaultDefault} !important`,
                color: theme.palette.vars.baseTextInverse,
                marginRight: '16px'
              }
            }
          }
        }}
      />
    </LocalizationProvider>
  );
};
