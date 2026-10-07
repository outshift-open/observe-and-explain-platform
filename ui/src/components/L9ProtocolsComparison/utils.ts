/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { isBestEffortState, isCommitState } from '@/common/l9Protocols';
import { SessionWithL9Protocols, Unit } from '@/types/oxp.type';
import { formatDurationMs } from '@/utils';
import { NO_DATA } from '../L9Protocols/primitives';

export const NO_PROTOCOL_COHORT = 'No L9 protocol';
export const ENABLED_NOT_ACTIVATED_COHORT = 'Enabled, not activated';

// ---------------------------------------------------------------------------
// Cohorts: sessions grouped by the protocols that were activated in them.
// Nothing is hardcoded: the groups come from the protocols the API reports.
// ---------------------------------------------------------------------------

export interface Cohort {
  label: string;
  // Number of activated protocols, used to order the groups.
  activatedCount: number;
  sessions: SessionWithL9Protocols[];
}

export const shortProtocolName = (protocol: string): string =>
  protocol.replace(/^L9-/, '');

const getActivatedProtocols = (session: SessionWithL9Protocols): string[] =>
  (session.l9Protocols ?? [])
    .filter((protocol) => protocol.activated)
    .map((protocol) => shortProtocolName(protocol.protocol))
    .sort();

export const getCohortLabel = (session: SessionWithL9Protocols): string => {
  const activated = getActivatedProtocols(session);
  if (activated.length > 0) return activated.join(' + ');
  if ((session.l9Protocols ?? []).some((protocol) => protocol.enabled)) {
    return ENABLED_NOT_ACTIVATED_COHORT;
  }
  return NO_PROTOCOL_COHORT;
};

// Whether any L9 protocol was enabled or activated in the session.
export const hasL9Protocol = (session: SessionWithL9Protocols): boolean =>
  (session.l9Protocols ?? []).some(
    (protocol) => protocol.enabled || protocol.activated
  );

const cohortRank = (cohort: Cohort): number => {
  if (cohort.label === NO_PROTOCOL_COHORT) return 0;
  if (cohort.label === ENABLED_NOT_ACTIVATED_COHORT) return 1;
  return 2;
};

export const groupIntoCohorts = (
  sessions: SessionWithL9Protocols[]
): Cohort[] => {
  const cohorts = new Map<string, Cohort>();

  sessions.forEach((session) => {
    const label = getCohortLabel(session);
    const cohort = cohorts.get(label) ?? {
      label,
      activatedCount: getActivatedProtocols(session).length,
      sessions: []
    };
    cohort.sessions.push(session);
    cohorts.set(label, cohort);
  });

  return Array.from(cohorts.values()).sort(
    (a, b) =>
      cohortRank(a) - cohortRank(b) ||
      a.activatedCount - b.activatedCount ||
      a.label.localeCompare(b.label)
  );
};

// ---------------------------------------------------------------------------
// Statistics. A missing value is never counted as a zero: sessions without the
// data are left out of the figure, which is `null` when no session has it.
// ---------------------------------------------------------------------------

const mean = (values: number[]): number | null =>
  values.length === 0
    ? null
    : values.reduce((sum, value) => sum + value, 0) / values.length;

const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

// Share of the sessions (with cognitive observability data) that have a
// failure above the threshold. Restricted to one failure when a name is given.
export const getFailureRate = (
  sessions: SessionWithL9Protocols[],
  threshold: number,
  failureName?: string
): number | null => {
  const withData = sessions.filter((session) => session.cognitiveFailures);
  if (withData.length === 0) return null;

  const affected = withData.filter((session) =>
    (session.cognitiveFailures ?? []).some(
      (failure) =>
        failure.confidence > threshold &&
        (failureName === undefined || failure.name === failureName)
    )
  );
  return affected.length / withData.length;
};

// Names of the failures above the threshold in at least one session.
export const getFailureNames = (
  sessions: SessionWithL9Protocols[],
  threshold: number
): string[] =>
  Array.from(
    new Set(
      sessions.flatMap((session) =>
        (session.cognitiveFailures ?? [])
          .filter((failure) => failure.confidence > threshold)
          .map((failure) => failure.name)
      )
    )
  ).sort();

export interface CognitiveMetricInfo {
  name: string;
  unit: Unit;
}

export const getCognitiveMetrics = (
  sessions: SessionWithL9Protocols[]
): CognitiveMetricInfo[] => {
  const metrics = new Map<string, CognitiveMetricInfo>();
  sessions.forEach((session) =>
    (session.cognitiveObservabilityMetrics ?? []).forEach((metric) => {
      if (!metrics.has(metric.name)) {
        metrics.set(metric.name, {
          name: metric.name,
          unit: metric.value.unit
        });
      }
    })
  );
  return Array.from(metrics.values()).sort((a, b) =>
    a.name.localeCompare(b.name)
  );
};

export const getMetricAverage = (
  sessions: SessionWithL9Protocols[],
  metricName: string
): number | null =>
  mean(
    sessions.flatMap((session) =>
      (session.cognitiveObservabilityMetrics ?? [])
        .filter((metric) => metric.name === metricName)
        .map((metric) => metric.value.value)
        .filter(isNumber)
    )
  );

export const getUsageAverage = (
  sessions: SessionWithL9Protocols[],
  field: 'tokens' | 'cost' | 'duration'
): number | null =>
  mean(sessions.map((session) => session[field]).filter(isNumber));

// CONCORD figures, over the sessions where CONCORD was activated.
export const getConcordStats = (sessions: SessionWithL9Protocols[]) => {
  const concordSessions = sessions.filter((session) => session.concord);
  const states = concordSessions
    .map((session) => session.concord?.terminalState)
    .filter((state): state is string => typeof state === 'string');
  const satisfactions = concordSessions
    .map((session) => session.concord?.worstOffSatisfaction)
    .filter(isNumber);

  const share = (count: number): number | null =>
    states.length === 0 ? null : count / states.length;

  return {
    sessionCount: concordSessions.length,
    commitShare: share(states.filter(isCommitState).length),
    bestEffortShare: share(states.filter(isBestEffortState).length),
    averageWorstOffSatisfaction: mean(satisfactions)
  };
};

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

// How a figure is shown, and how a difference to the reference is expressed:
//  - rate: a share (0-1), difference in percentage points
//  - number: a plain score, absolute difference
//  - count / cost / duration: relative difference
export type MetricKind = 'rate' | 'number' | 'count' | 'cost' | 'duration';

export const getMetricKind = (unit: Unit): MetricKind =>
  unit === Unit.Percentage ? 'rate' : 'number';

export const formatMetricValue = (
  kind: MetricKind,
  value: number | null
): string => {
  if (value === null) return NO_DATA;
  switch (kind) {
    case 'rate':
      return `${Math.round(value * 100)}%`;
    case 'number':
      return value.toFixed(2);
    case 'count':
      return Math.round(value).toLocaleString();
    case 'cost':
      return `$${value.toFixed(4)}`;
    case 'duration':
      return formatDurationMs(value);
  }
};

// Difference to the reference, or null when either side has no data.
export const formatDifference = (
  kind: MetricKind,
  value: number | null,
  reference: number | null
): string | null => {
  if (value === null || reference === null) return null;
  const difference = value - reference;
  const sign = difference > 0 ? '+' : difference < 0 ? '-' : '';

  if (kind === 'rate') {
    return `${sign}${Math.abs(Math.round(difference * 100))} pp`;
  }
  if (kind === 'number') {
    return `${sign}${Math.abs(difference).toFixed(2)}`;
  }
  // Relative difference: undefined against a reference of zero.
  if (reference === 0) return null;
  return `${sign}${Math.abs(Math.round((difference / reference) * 100))}%`;
};
