/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo } from 'react';
import { Stack } from '@mui/material';
import { COGNITIVE_FAILURE_DESCRIPTIONS } from '@/common/cognitiveFailures';
import { SessionWithL9Protocols } from '@/types/oxp.type';
import { SimpleTable, SubSection } from '../L9Protocols/primitives';
import { ComparisonRow, ComparisonTable } from './ComparisonTable';
import {
  Cohort,
  formatMetricValue,
  getCognitiveMetrics,
  getConcordStats,
  getFailureNames,
  getFailureRate,
  getMetricAverage,
  getMetricKind,
  getUsageAverage
} from './utils';

interface ComparisonSectionsProps {
  sessions: SessionWithL9Protocols[];
  cohorts: Cohort[];
  referenceLabel: string | null;
  // Failures count only when their confidence is above this fraction (0-1).
  threshold: number;
}

export const ComparisonSections = ({
  sessions,
  cohorts,
  referenceLabel,
  threshold
}: ComparisonSectionsProps) => {
  const thresholdPercent = Math.round(threshold * 100);

  const challengeRows = useMemo<ComparisonRow[]>(
    () => [
      {
        key: 'any-failure',
        label: 'Any cognitive failure',
        description: `Sessions with at least one cognitive failure above ${thresholdPercent}% detection confidence.`,
        kind: 'rate',
        getValue: (cohort) => getFailureRate(cohort.sessions, threshold)
      },
      ...getFailureNames(sessions, threshold).map(
        (name): ComparisonRow => ({
          key: name,
          label: name,
          description: COGNITIVE_FAILURE_DESCRIPTIONS[name],
          kind: 'rate',
          getValue: (cohort) => getFailureRate(cohort.sessions, threshold, name)
        })
      )
    ],
    [sessions, threshold, thresholdPercent]
  );

  const metricRows = useMemo<ComparisonRow[]>(
    () =>
      getCognitiveMetrics(sessions).map(
        ({ name, unit }): ComparisonRow => ({
          key: name,
          label: name,
          kind: getMetricKind(unit),
          getValue: (cohort) => getMetricAverage(cohort.sessions, name)
        })
      ),
    [sessions]
  );

  const usageRows = useMemo<ComparisonRow[]>(
    () => [
      {
        key: 'tokens',
        label: 'Tokens per session',
        kind: 'count',
        getValue: (cohort) => getUsageAverage(cohort.sessions, 'tokens')
      },
      {
        key: 'cost',
        label: 'Cost per session',
        kind: 'cost',
        getValue: (cohort) => getUsageAverage(cohort.sessions, 'cost')
      },
      {
        key: 'duration',
        label: 'Duration per session',
        kind: 'duration',
        getValue: (cohort) => getUsageAverage(cohort.sessions, 'duration')
      }
    ],
    []
  );

  const concord = useMemo(() => getConcordStats(sessions), [sessions]);

  return (
    <Stack direction="column" gap="16px">
      <SubSection
        title="Cognitive failure rate"
        description={`The share of sessions in each group with that cognitive failure above ${thresholdPercent}% detection confidence. Sessions without cognitive observability data are left out of the share.`}
      >
        <ComparisonTable
          cohorts={cohorts}
          referenceLabel={referenceLabel}
          rows={challengeRows}
        />
      </SubSection>

      <SubSection
        title="Cognitive observability metrics"
        description="The average value of each metric over the sessions of each group that have it."
      >
        <ComparisonTable
          cohorts={cohorts}
          referenceLabel={referenceLabel}
          rows={metricRows}
        />
      </SubSection>

      <SubSection
        title="Session usage"
        description="The average tokens, cost and duration of a session in each group."
      >
        <ComparisonTable
          cohorts={cohorts}
          referenceLabel={referenceLabel}
          rows={usageRows}
        />
      </SubSection>

      {concord.sessionCount > 0 && (
        <SubSection
          title="CONCORD sessions"
          description="Only the sessions where CONCORD was activated."
        >
          <SimpleTable
            headers={['Metric', 'Value']}
            rows={[
              [
                'Sessions with CONCORD activated',
                formatMetricValue('count', concord.sessionCount)
              ],
              [
                'Ended in COMMIT',
                formatMetricValue('rate', concord.commitShare)
              ],
              [
                'Ended in BEST_EFFORT',
                formatMetricValue('rate', concord.bestEffortShare)
              ],
              [
                'Average worst-off satisfaction',
                formatMetricValue('number', concord.averageWorstOffSatisfaction)
              ]
            ]}
          />
        </SubSection>
      )}
    </Stack>
  );
};
