/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography } from '@mui/material';
import { WidgetCard } from '@/components';
import { Cohort, NO_PROTOCOL_COHORT } from './utils';

const getCohortDescription = (cohort: Cohort): string => {
  if (cohort.label === NO_PROTOCOL_COHORT) {
    return 'Sessions where no L9 protocol was enabled.';
  }
  if (cohort.activatedCount === 0) {
    return 'Sessions where an L9 protocol was enabled but never activated.';
  }
  return 'Sessions where exactly these protocols were activated.';
};

// One card per group of sessions, with how many sessions it holds.
export const CohortSummary = ({
  cohorts,
  totalSessions
}: {
  cohorts: Cohort[];
  totalSessions: number;
}) => (
  <Box
    sx={{
      width: '100%',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
      gap: '8px'
    }}
  >
    {cohorts.map((cohort) => {
      const size = cohort.sessions.length;
      return (
        <WidgetCard
          key={cohort.label}
          title={cohort.label}
          description={getCohortDescription(cohort)}
          cardSx={{ width: '100%' }}
          content={
            <Stack direction="row" gap="4px" alignItems="baseline">
              <Typography variant={'h6'}>{size}</Typography>
              <Typography variant={'caption'}>
                {`${size === 1 ? 'session' : 'sessions'} (${
                  totalSessions > 0
                    ? Math.round((size / totalSessions) * 100)
                    : 0
                }%)`}
              </Typography>
            </Stack>
          }
        />
      );
    })}
  </Box>
);
