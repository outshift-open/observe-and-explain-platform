/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography, useTheme } from '@mui/material';
import {
  InfoTooltip,
  NotAvailable,
  SimpleTable
} from '../L9Protocols/primitives';
import {
  Cohort,
  MetricKind,
  formatDifference,
  formatMetricValue
} from './utils';

export interface ComparisonRow {
  key: string;
  label: string;
  description?: string;
  kind: MetricKind;
  getValue: (cohort: Cohort) => number | null;
}

const cohortHeader = (cohort: Cohort, isReference: boolean): string => {
  const details = [
    `n=${cohort.sessions.length}`,
    ...(isReference ? ['reference'] : [])
  ];
  return `${cohort.label} (${details.join(', ')})`;
};

// One column per group of sessions. Next to each figure, the difference to the
// reference group is shown when both have data. The differences only compare
// groups of sessions, they do not tell what caused them.
export const ComparisonTable = ({
  cohorts,
  referenceLabel,
  rows
}: {
  cohorts: Cohort[];
  referenceLabel: string | null;
  rows: ComparisonRow[];
}) => {
  const theme = useTheme();
  const reference = cohorts.find((cohort) => cohort.label === referenceLabel);

  if (rows.length === 0) return <NotAvailable text="No data" />;

  return (
    <SimpleTable
      headers={[
        'Metric',
        ...cohorts.map((cohort) => cohortHeader(cohort, cohort === reference))
      ]}
      rows={rows.map((row) => {
        const referenceValue = reference ? row.getValue(reference) : null;

        return [
          <Stack
            key={`${row.key}-label`}
            direction="row"
            alignItems="center"
            gap="4px"
          >
            <Typography variant={'body2'}>{row.label}</Typography>
            {row.description && <InfoTooltip description={row.description} />}
          </Stack>,
          ...cohorts.map((cohort) => {
            const value = row.getValue(cohort);
            const difference =
              cohort === reference
                ? null
                : formatDifference(row.kind, value, referenceValue);

            return (
              <Stack
                key={`${row.key}-${cohort.label}`}
                direction="column"
                alignItems="flex-end"
              >
                {value === null ? (
                  <NotAvailable />
                ) : (
                  <Typography variant={'body2'}>
                    {formatMetricValue(row.kind, value)}
                  </Typography>
                )}
                {difference && (
                  <Typography
                    variant={'caption'}
                    sx={{ color: theme.palette.vars.baseTextWeak }}
                  >
                    {difference}
                  </Typography>
                )}
              </Stack>
            );
          })
        ];
      })}
    />
  );
};
