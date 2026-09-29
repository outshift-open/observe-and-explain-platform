/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useSemanticGroupsInsights } from '@/api/oxpApi';
import { Spinner, Stack } from '@open-ui-kit/core';
import { SemanticGroupsInsightsTable } from './SemanticGroupsInsightsTable';
import { IntervalPicker } from '@/components/IntervalPicker';
import dayjs from 'dayjs';
import { useTimeRangeStore } from '@/store';
import { useParams } from 'react-router-dom';

export const SemanticGroupsInsightsTableWrapper = () => {
  const { applicationId } = useParams();
  const { startDate, endDate, setStartDate, setEndDate } = useTimeRangeStore();

  const {
    data: semanticGroupsInsights,
    isLoading: isSemanticGroupsInsightsLoading,
    isError: isSemanticGroupsInsightsError
  } = useSemanticGroupsInsights(applicationId ?? '', startDate, endDate);

  if (isSemanticGroupsInsightsLoading) {
    return (
      <Stack
        justifyContent={'center'}
        alignItems={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (isSemanticGroupsInsightsError) {
    return <div>Error loading semantic groups insights</div>;
  }

  return (
    <Stack direction="column" gap={'16px'}>
      <IntervalPicker
        startDate={startDate}
        endDate={endDate}
        setStartDate={setStartDate}
        setEndDate={setEndDate}
      />
      <SemanticGroupsInsightsTable
        data={semanticGroupsInsights ?? []}
        isLoading={isSemanticGroupsInsightsLoading}
        startDate={dayjs.unix(startDate)}
        endDate={dayjs.unix(endDate)}
        startDateUnix={startDate}
        endDateUnix={endDate}
      />
    </Stack>
  );
};
