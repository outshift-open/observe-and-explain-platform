/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { Stack, Typography } from '@open-ui-kit/core';
import { Chip, Slider } from '@mui/material';
import { format } from 'date-fns';
import dayjs from 'dayjs';
import { CognitiveObservabilityTable } from './CognitiveObservabilityTable';
import { CognitiveObservabilityOverview } from './CognitiveObservabilityOverview';
import { getFailuresAboveThreshold } from './utils';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { CustomTooltip, IntervalPicker } from '@/components';
import { useDebouncedValue } from '@/utils';
import { useTimeRangeStore } from '@/store';
import { useSessionsWithCognitiveObservability } from '@/api/oxpApi';
import { FAILURE_CONFIDENCE_THRESHOLD } from '@/common/cognitiveFailures';

const CognitiveObservability = () => {
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);

  const {
    data: sessionsWithCognitiveObservability,
    isLoading,
    refetch
  } = useSessionsWithCognitiveObservability(
    debouncedStartDate,
    debouncedEndDate
  );

  const [selectedFailure, setSelectedFailure] = useState<string | null>(null);
  // Confidence threshold as a fraction (0-1); drives counts and filtering.
  const [threshold, setThreshold] = useState(FAILURE_CONFIDENCE_THRESHOLD);
  const thresholdPercent = Math.round(threshold * 100);

  // Only sessions with at least one failure above the threshold are listed,
  // narrowed to the selected failure when a card is selected.
  const filteredSessions = useMemo(() => {
    if (!sessionsWithCognitiveObservability) return undefined;
    return {
      ...sessionsWithCognitiveObservability,
      sessions: sessionsWithCognitiveObservability.sessions.filter(
        (session) => {
          const failures = getFailuresAboveThreshold(session, threshold);
          return selectedFailure
            ? failures.some((failure) => failure.name === selectedFailure)
            : failures.length > 0;
        }
      )
    };
  }, [sessionsWithCognitiveObservability, selectedFailure, threshold]);

  return (
    <Stack direction="column" gap="16px" sx={{ width: '100%' }}>
      <Stack direction="row" gap="16px" alignItems="center">
        <IntervalPicker
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
        />
        {startDate && endDate ? (
          <Stack direction="row" gap={'8px'} alignItems={'center'}>
            <Typography variant={'body2Semibold'}>
              {format(dayjs.unix(startDate).toDate(), 'MMM d, yyyy HH:mm:ss')}
            </Typography>
            <Typography variant={'body2Semibold'}>-</Typography>
            <Typography variant={'body2Semibold'}>
              {format(dayjs.unix(endDate).toDate(), 'MMM d, yyyy HH:mm:ss')}
            </Typography>
          </Stack>
        ) : null}
        <Stack
          direction="row"
          gap="12px"
          alignItems="center"
          sx={{ marginLeft: 'auto', width: '320px' }}
        >
          <Stack direction="row" gap="4px" alignItems="flex-start">
            <Typography variant={'body2'} sx={{ whiteSpace: 'nowrap' }}>
              Confidence threshold
            </Typography>
            <CustomTooltip
              title={
                <Typography variant={'caption'}>
                  A cognitive failure only counts when its confidence is above
                  this value. It drives the summary and the sessions listed in
                  the table.
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
          <Slider
            size="small"
            min={50}
            max={100}
            step={5}
            value={thresholdPercent}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => `${value}%`}
            onChange={(_, value) =>
              setThreshold((Array.isArray(value) ? value[0] : value) / 100)
            }
          />
          <Typography variant={'body2Semibold'} sx={{ minWidth: '36px' }}>
            {`${thresholdPercent}%`}
          </Typography>
        </Stack>
      </Stack>

      <CognitiveObservabilityOverview
        sessionsWithCognitiveObservability={sessionsWithCognitiveObservability}
        threshold={threshold}
        selectedFailure={selectedFailure}
        onSelectFailure={setSelectedFailure}
      />

      <Stack direction="column" gap="8px">
        {selectedFailure && (
          <Stack direction="row">
            <Chip
              size="small"
              label={`Filtered by: ${selectedFailure}`}
              onDelete={() => setSelectedFailure(null)}
              color="primary"
              variant="outlined"
            />
          </Stack>
        )}
        <CognitiveObservabilityTable
          sessionsWithCognitiveObservability={filteredSessions}
          threshold={threshold}
          selectedFailure={selectedFailure}
          isLoading={isLoading}
          onReload={() => refetch()}
          onClearFilter={() => setSelectedFailure(null)}
        />
      </Stack>
    </Stack>
  );
};

export default CognitiveObservability;
