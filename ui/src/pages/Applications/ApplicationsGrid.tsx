/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  MenuItem,
  Select,
  Grid,
  Stack,
  Typography,
  FormControl,
  useTheme
} from '@mui/material';
import { ApplicationCard } from '@/components';
import { ApplicationWithStatefulEval } from '@/types/oxp.type';
import {
  useApplications,
  useApplicationListSummaryMetrics,
  useApplicationsWithStatefulEval
} from '@/api/oxpApi';
import {
  RepositorySortOption,
  RepositorySortOptionLabel
} from '@/common/constants';
import { SearchInput, Spinner } from '@open-ui-kit/core';
import { useEffect, useMemo, useState } from 'react';
import {
  computeOverallPerformance,
  computeOverallQuality,
  computeOverallReliability
} from '@/utils/metrics';

const size = { xxl: 2, xl: 3, lg: 4, md: 3 };

export const ApplicationsGrid = () => {
  const [sortBy, setSortBy] = useState<RepositorySortOption>(
    RepositorySortOption.mostRecent
  );
  const {
    data: applicationsData,
    error: applicationsError,
    isLoading: applicationsLoading
  } = useApplications();
  const [queryFilter, setQueryFilter] = useState('');
  const [applications, setApplications] = useState<
    ApplicationWithStatefulEval[]
  >([]);

  const {
    data: statefulEvalData,
    error: statefulEvalError,
    isLoading: statefulEvalLoading
  } = useApplicationsWithStatefulEval();

  const applicationListSummaryMetrics = useApplicationListSummaryMetrics(
    applicationsData?.applications?.map(
      (application) => application.applicationName
    ) ?? []
  );
  const applicationListSummaryMetricsLoading =
    applicationListSummaryMetrics.some((q) => q.isLoading);
  const applicationListSummaryMetricsError = applicationListSummaryMetrics.some(
    (q) => q.error
  );

  const healthScoreByApplication = useMemo(() => {
    const scores: Record<string, number> = {};
    for (const q of applicationListSummaryMetrics) {
      const data = q.data;
      if (!data) continue;

      const qualityScore = computeOverallQuality(data.quality);
      const reliabilityScore = computeOverallReliability(data.reliability);
      const performanceScore = computeOverallPerformance(data.performance);
      const overallScore =
        (qualityScore + reliabilityScore + performanceScore) / 3;

      scores[data.applicationName] = Math.round(overallScore);
    }
    return scores;
  }, [applicationListSummaryMetrics]);

  const statefulEvalByApp = useMemo(() => {
    if (statefulEvalLoading || !statefulEvalData) return {};

    const map: Record<string, { fatal: number; minor: number }> = {};
    for (const entry of statefulEvalData) {
      map[entry.applicationName] = {
        fatal: entry.totalFatal,
        minor: entry.totalMinor
      };
    }
    return map;
  }, [statefulEvalLoading, statefulEvalData]);

  const theme = useTheme();

  useEffect(() => {
    if (applicationsData?.applications?.length) {
      const enriched = (applicationsData.applications ?? []).map(
        (application) => {
          const totals = statefulEvalByApp[application.applicationName];
          return {
            ...application,
            fatalFailures: totals?.fatal ?? 0,
            minorFailures: totals?.minor ?? 0
          };
        }
      );

      setApplications(
        (enriched as ApplicationWithStatefulEval[])
          .filter((application) =>
            application.applicationName
              .toLowerCase()
              .includes(queryFilter.toLowerCase())
          )
          .sort((a, b) => {
            if (sortBy === RepositorySortOption.mostRecent) {
              return (
                new Date(b.timestamp ?? 0).getTime() -
                new Date(a.timestamp ?? 0).getTime()
              );
            }
            return (
              new Date(a.timestamp ?? 0).getTime() -
              new Date(b.timestamp ?? 0).getTime()
            );
          })
      );
    }
  }, [applicationsData?.applications, queryFilter, sortBy, statefulEvalByApp]);

  if (
    applicationsLoading ||
    statefulEvalLoading ||
    applicationListSummaryMetricsLoading
  ) {
    return (
      <Stack
        alignItems={'center'}
        justifyContent={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  console.log(applications);

  if (
    applicationsError ||
    statefulEvalError ||
    applicationListSummaryMetricsError
  ) {
    return <>An error occurred!</>;
  }
  return (
    <Stack direction={'column'} gap={'16px'} sx={{ paddingTop: '24px' }}>
      <SearchInput
        placeholder="Search by application name"
        value={queryFilter}
        onChangeCallback={setQueryFilter}
        sx={{
          '& .MuiInputBase-root': {
            marginTop: 0,
            width: '100%',
            height: '36px'
          }
        }}
      />

      <Stack direction={'row'} justifyContent={'space-between'}>
        <Typography variant={'h6'}>{applications.length} results</Typography>
        <FormControl sx={{ width: '221px' }}>
          <Select
            value={sortBy}
            renderValue={() => RepositorySortOptionLabel[sortBy]}
            onChange={(e) => setSortBy(e.target.value)}
            label="Sort by"
            variant="standard"
            sx={{
              height: '36px',
              marginTop: 0,
              '&.MuiInputBase-root': {
                backgroundColor: theme.palette.vars.controlBackgroundDefault
              },
              '& .MuiSelect-select': {
                backgroundColor: theme.palette.vars.controlBackgroundDefault,
                color: theme.palette.vars.baseTextDefault
              }
            }}
          >
            <MenuItem value={RepositorySortOption.mostRecent}>
              {RepositorySortOptionLabel[RepositorySortOption.mostRecent]}
            </MenuItem>
            <MenuItem value={RepositorySortOption.oldest}>
              {RepositorySortOptionLabel[RepositorySortOption.oldest]}
            </MenuItem>
          </Select>
        </FormControl>
      </Stack>
      <Grid container spacing={'16px'}>
        {applications.map((application) => (
          <Grid size={size} key={application.applicationName}>
            <ApplicationCard
              application={application}
              healthScore={
                healthScoreByApplication[application.applicationName]
              }
            />
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
};

export default ApplicationsGrid;
