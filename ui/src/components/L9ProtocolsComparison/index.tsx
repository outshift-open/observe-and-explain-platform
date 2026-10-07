/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { MenuItem, Select, Slider, Stack, Typography } from '@mui/material';
import { Banner, EmptyState, Skeleton } from '@open-ui-kit/core';
import { format } from 'date-fns';
import dayjs from 'dayjs';
import { IntervalPicker } from '@/components';
import { useSessionsWithL9Protocols } from '@/api/oxpApi';
import { FAILURE_CONFIDENCE_THRESHOLD } from '@/common/cognitiveFailures';
import { useTimeRangeStore } from '@/store';
import { useDebouncedValue } from '@/utils';
import { InfoTooltip, SubSection } from '../L9Protocols/primitives';
import { CohortSummary } from './CohortSummary';
import { ComparisonSections } from './ComparisonSections';
import { SessionsTable } from './SessionsTable';
import { NO_PROTOCOL_COHORT, groupIntoCohorts, hasL9Protocol } from './utils';

const L9ProtocolsComparison = () => {
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();
  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);

  const { data, isLoading, isError } = useSessionsWithL9Protocols(
    debouncedStartDate,
    debouncedEndDate
  );

  // Confidence threshold as a fraction (0-1) for the challenge rates.
  const [threshold, setThreshold] = useState(FAILURE_CONFIDENCE_THRESHOLD);
  const thresholdPercent = Math.round(threshold * 100);
  const [selectedReference, setSelectedReference] = useState<string | null>(
    null
  );

  const sessions = useMemo(() => data?.sessions ?? [], [data?.sessions]);
  const cohorts = useMemo(() => groupIntoCohorts(sessions), [sessions]);
  const protocolSessions = useMemo(
    () => sessions.filter(hasL9Protocol),
    [sessions]
  );

  // The differences are shown against the selected group, by default the
  // sessions without any L9 protocol.
  const referenceLabel =
    cohorts.find((cohort) => cohort.label === selectedReference)?.label ??
    cohorts.find((cohort) => cohort.label === NO_PROTOCOL_COHORT)?.label ??
    cohorts[0]?.label ??
    null;

  const body = () => {
    if (isLoading) {
      return (
        <Stack direction="column" gap="16px">
          <Skeleton variant="rounded" height={96} />
          <Skeleton variant="rounded" height={240} />
          <Skeleton variant="rounded" height={240} />
        </Stack>
      );
    }

    if (isError) {
      return (
        <Banner
          status="negative"
          text="Failed to load the L9 protocols comparison."
        />
      );
    }

    if (sessions.length === 0) {
      return (
        <EmptyState
          title="No sessions in this interval"
          description="Select another time interval."
        />
      );
    }

    return (
      <>
        <Stack direction="column" gap="8px">
          <Typography variant={'h6'}>Groups of sessions</Typography>
          <CohortSummary cohorts={cohorts} totalSessions={sessions.length} />
        </Stack>

        <ComparisonSections
          sessions={sessions}
          cohorts={cohorts}
          referenceLabel={referenceLabel}
          threshold={threshold}
        />

        <SubSection
          title="Sessions with L9 protocols"
          description="The sessions where at least one L9 protocol was enabled. Select one to open its L9 Protocols tab."
        >
          <SessionsTable sessions={protocolSessions} />
        </SubSection>
      </>
    );
  };

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
      </Stack>

      <Stack direction="row" gap="32px" alignItems="center" flexWrap="wrap">
        <Stack direction="row" gap="8px" alignItems="center">
          <Typography variant={'body2'} sx={{ whiteSpace: 'nowrap' }}>
            Compare against
          </Typography>
          <InfoTooltip description="The group the differences are shown against, for example the sessions without an L9 protocol, or the sessions with CONCORD alone to see what ACCORD adds." />
          <Select
            size="small"
            value={referenceLabel ?? ''}
            onChange={(event) => setSelectedReference(event.target.value)}
            disabled={cohorts.length === 0}
            sx={{ minWidth: '220px' }}
          >
            {cohorts.map((cohort) => (
              <MenuItem key={cohort.label} value={cohort.label}>
                {cohort.label}
              </MenuItem>
            ))}
          </Select>
        </Stack>

        <Stack
          direction="row"
          gap="12px"
          alignItems="center"
          sx={{ width: '320px' }}
        >
          <Stack direction="row" gap="4px" alignItems="center">
            <Typography variant={'body2'} sx={{ whiteSpace: 'nowrap' }}>
              Confidence threshold
            </Typography>
            <InfoTooltip description="A cognitive failure only counts when its detection confidence is above this value. It drives the challenge rates." />
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

      {body()}
    </Stack>
  );
};

export default L9ProtocolsComparison;
