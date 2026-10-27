/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { CognitionMetric } from '@/types/oxp.type';

// How the numeric result of a metric is displayed.
// - boolean: 1 / 0 as Yes / No
// - pass: 1 / 0 as Pass / Fail
// - percent: a 0..1 ratio
// - count: an integer
// - score: a normalized score, with two decimals
export type CognitionMetricKind = 'boolean' | 'pass' | 'percent' | 'count' | 'score';

export interface CognitionMetricDefinition {
  label: string;
  description?: string;
  kind: CognitionMetricKind;
  // Rows for the table shown under the value, from the parsed `details`.
  detailsRows?: (details: unknown) => Record<string, unknown>[] | null;
  // The reasoning is dropped when it says nothing beyond the value.
  isReasoningRedundant?: (metric: CognitionMetric) => boolean;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const rowsOfObjects = (details: unknown): Record<string, unknown>[] | null =>
  Array.isArray(details) && details.every(isRecord) && details.length > 0
    ? (details as Record<string, unknown>[])
    : null;

// `{ agents: { sre: {...} } }` -> one row per agent.
const rowsPerAgent = (details: unknown): Record<string, unknown>[] | null => {
  const agents = isRecord(details) ? details.agents : null;
  if (!isRecord(agents)) return null;
  const rows = Object.entries(agents)
    .filter((entry): entry is [string, Record<string, unknown>] =>
      isRecord(entry[1])
    )
    .map(([agent, usage]) => ({ agent, ...usage }));
  return rows.length > 0 ? rows : null;
};

const isScalar = (value: unknown): boolean =>
  value === null || ['string', 'number', 'boolean'].includes(typeof value);

// `{ telemetry: 0.9, db: 0.8 }` -> one row per key.
const rowsPerKey =
  (keyLabel: string, valueLabel: string) =>
  (details: unknown): Record<string, unknown>[] | null => {
    if (!isRecord(details)) return null;
    const rows = Object.entries(details)
      .filter(([, value]) => isScalar(value))
      .map(([key, value]) => ({ [keyLabel]: key, [valueLabel]: value }));
    return rows.length > 0 ? rows : null;
  };

// `{ telemetry: { checked: 3, items: [...] } }` -> one row per key, with the
// scalar fields only.
const rowsPerAgentSummary = (
  details: unknown
): Record<string, unknown>[] | null => {
  if (!isRecord(details)) return null;
  const rows = Object.entries(details)
    .filter((entry): entry is [string, Record<string, unknown>] =>
      isRecord(entry[1])
    )
    .map(([agent, fields]) => ({
      agent,
      ...Object.fromEntries(
        Object.entries(fields).filter(([, value]) => isScalar(value))
      )
    }));
  return rows.length > 0 ? rows : null;
};

// `{ ..., agents: { telemetry: 0.9 } }` -> one row per agent.
const rowsOfAgentScores = (
  details: unknown
): Record<string, unknown>[] | null =>
  isRecord(details) ? rowsPerKey('agent', 'score')(details.agents) : null;

// `{ steps: { init: true } }` -> one row per step.
const rowsOfSteps = (details: unknown): Record<string, unknown>[] | null =>
  isRecord(details) ? rowsPerKey('step', 'done')(details.steps) : null;

// `{ llm_calls: 3, prompt_tokens: 10 }` -> a single row, one column per field.
const singleRow = (details: unknown): Record<string, unknown>[] | null => {
  if (!isRecord(details)) return null;
  const row = Object.fromEntries(
    Object.entries(details).filter(([, value]) => isScalar(value))
  );
  return Object.keys(row).length > 0 ? [row] : null;
};

// `{ total: {...}, phases: { init: {...} } }` -> one row per phase, then total.
const rowsPerPhase = (details: unknown): Record<string, unknown>[] | null => {
  if (!isRecord(details)) return null;
  const phases = isRecord(details.phases) ? details.phases : {};
  const rows = Object.entries(phases)
    .filter((entry): entry is [string, Record<string, unknown>] =>
      isRecord(entry[1])
    )
    .map(([phase, usage]) => ({ phase, ...usage }));
  if (isRecord(details.total)) rows.push({ phase: 'total', ...details.total });
  return rows.length > 0 ? rows : null;
};

// Display order of the sections; unknown sections go last.
export const COGNITION_METRIC_SECTIONS: { key: string; title: string }[] = [
  { key: 'convergence', title: 'Convergence' },
  { key: 'contract', title: 'Intent contract' },
  { key: 'cost', title: 'Cost' },
  { key: 'benefits', title: 'Benefits' }
];
export const OTHER_SECTION_TITLE = 'Other metrics';

// Known metrics, by name. Extensible: a metric that is not listed is displayed
// with a label derived from its name, and its value as a plain number.
export const COGNITION_METRIC_DEFINITIONS: Record<string, CognitionMetricDefinition> = {
  AccordConverged: {
    label: 'Converged',
    description: 'Did the agents reach a locked frame?',
    kind: 'boolean'
  },
  AccordPhaseCoverage: {
    label: 'Phase coverage',
    description: 'Share of the protocol phases that were run.',
    kind: 'percent',
    // Full coverage reports an empty "missing:" list.
    isReasoningRedundant: (metric) =>
      metric.value === 1 && metric.reasoning?.trim() === 'missing:'
  },
  AccordLockedTerms: {
    label: 'Locked terms',
    description:
      'Terms locked in the shared glossary, with how many agents defined each of them.',
    kind: 'count',
    detailsRows: rowsOfObjects
  },
  AccordLockPrecision: {
    label: 'Lock precision',
    description: 'Share of the locked terms that are relevant.',
    kind: 'percent'
  },
  AccordLockRecall: {
    label: 'Lock recall',
    description: 'Share of the relevant terms that were locked.',
    kind: 'percent'
  },
  AccordFabricatedLock: {
    label: 'Fabricated locks',
    description: 'Locked terms that no agent actually proposed.',
    kind: 'count'
  },
  AccordOverSelected: {
    label: 'Over-selected terms',
    description: 'Terms locked although they were not needed.',
    kind: 'count'
  },
  AccordUnderSelected: {
    label: 'Under-selected terms',
    description: 'Needed terms that were not locked.',
    kind: 'count'
  },
  AccordTermUtilization: {
    label: 'Term utilization',
    description: 'Share of the locked terms used after the lock.',
    kind: 'percent'
  },
  AccordCanonicalValid: {
    label: 'Canonical contract valid',
    description: 'Is the canonical Intent Contract well-formed?',
    kind: 'pass'
  },
  AccordRelayedValid: {
    label: 'Relayed contract valid',
    description:
      'Is the Intent Contract relayed to the other agents well-formed?',
    kind: 'pass'
  },
  AccordContractWarnings: {
    label: 'Contract warnings',
    description: 'Number of warnings raised on the Intent Contract.',
    kind: 'count'
  },
  AccordProtocolPromptTokens: {
    label: 'Prompt tokens',
    description: 'Prompt tokens used by the agents during the protocol.',
    kind: 'count',
    detailsRows: rowsPerAgent
  },
  AccordProtocolFreshTokens: {
    label: 'Fresh prompt tokens',
    description: 'Prompt tokens that were not served from the cache.',
    kind: 'count'
  },
  AccordProtocolCachedTokens: {
    label: 'Cached prompt tokens',
    description: 'Prompt tokens served from the cache.',
    kind: 'count'
  },
  AccordProtocolCompletionTokens: {
    label: 'Completion tokens',
    description: 'Tokens generated by the agents during the protocol.',
    kind: 'count'
  },
  AccordContractOverheadTokens: {
    label: 'Contract overhead tokens',
    description:
      'Estimated prompt tokens taken by the Intent Contract kept in the agents’ context.',
    kind: 'count'
  },
  AccordContractOverheadShare: {
    label: 'Contract overhead share',
    description: 'Estimated share of the prompts taken by the contract.',
    kind: 'percent'
  },
  AccordContractOverheadPerCall: {
    label: 'Contract overhead per call',
    description: 'Estimated contract tokens per LLM call.',
    kind: 'count'
  },
  AccordGlossaryInfluence: {
    label: 'Glossary influence',
    description:
      'Share of the agents’ handling of the locked terms that followed the shared glossary.',
    kind: 'percent'
  },
  AccordGlossaryUptake: {
    label: 'Glossary uptake',
    description: 'Share of the locked terms the agents picked up and used.',
    kind: 'percent'
  },
  // ---- CONCORD ----
  ConcordCommitted: {
    label: 'Committed',
    description: 'Did the run end on a commit?',
    kind: 'boolean'
  },
  ConcordReachedEnd: {
    label: 'Reached the end',
    description: 'Did the protocol run to its terminal state?',
    kind: 'boolean'
  },
  ConcordAllSteps: {
    label: 'All steps followed',
    description: 'Were all the steps of the protocol carried out?',
    kind: 'pass',
    detailsRows: rowsOfSteps
  },
  ConcordUsedAllCandidates: {
    label: 'All candidates scored',
    description: 'Did every agent score every candidate?',
    kind: 'pass'
  },
  ConcordRounds: {
    label: 'Rounds',
    description: 'Rounds the run took.',
    kind: 'count',
    detailsRows: rowsPerKey('item', 'value')
  },
  ConcordRepairRounds: {
    label: 'Repair rounds',
    description: 'Repair rounds run after scoring and after mark-missing.',
    kind: 'count'
  },
  ConcordRepairsAfterMarkMissing: {
    label: 'Repairs after mark-missing',
    description: 'Repair rounds run after a candidate was marked missing.',
    kind: 'count'
  },
  ConcordBudgetUsed: {
    label: 'Repair budget used',
    description: 'Share of the repair-round budget that was used.',
    kind: 'percent'
  },
  ConcordWorstOffSatisfaction: {
    label: 'Worst-off agent satisfaction',
    description: 'Final satisfaction of the least satisfied agent.',
    kind: 'score',
    detailsRows: rowsOfAgentScores
  },
  ConcordWorstOffAboveTau: {
    label: 'Worst-off agent above threshold',
    description:
      'Is the least satisfied agent above the satisfaction floor (tau)?',
    kind: 'boolean'
  },
  ConcordMeanSatisfaction: {
    label: 'Mean satisfaction',
    description: 'Average satisfaction of the agents, with each agent’s score.',
    kind: 'score',
    detailsRows: rowsPerKey('agent', 'score')
  },
  ConcordSatisfiedAgents: {
    label: 'Satisfied agents',
    description: 'Share of the agents whose outcome is satisfactory.',
    kind: 'percent',
    detailsRows: rowsOfObjects
  },
  ConcordOutcomeSatisfied: {
    label: 'Outcome satisfied',
    description: 'Is every agent satisfied with the outcome?',
    kind: 'boolean'
  },
  ConcordScoreFair: {
    label: 'Scores fair',
    description: 'Were the scores the agents gave fair across candidates?',
    kind: 'boolean',
    detailsRows: rowsPerAgentSummary
  },
  ConcordUnfairScoreShare: {
    label: 'Unfair scores',
    description: 'Share of the judged scores that were unfair.',
    kind: 'percent',
    detailsRows: rowsPerKey('agent', 'unfair')
  },
  ConcordSelfPreferenceGap: {
    label: 'Self-preference gap',
    description:
      'How much more the agents favor their own candidate than the others do.',
    kind: 'score',
    detailsRows: rowsPerKey('agent', 'gap')
  },
  ConcordRunTokens: {
    label: 'Run tokens',
    description: 'Tokens used by the whole run, by phase.',
    kind: 'count',
    detailsRows: rowsPerPhase
  },
  ConcordProtocolTokens: {
    label: 'Protocol tokens',
    description: 'Tokens used by the protocol itself, by step.',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordProtocolShare: {
    label: 'Protocol share of tokens',
    description: 'Share of the run’s tokens used by the protocol.',
    kind: 'percent'
  },
  ConcordTokensBeforeConcord: {
    label: 'Tokens before CONCORD',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordTokensAnchors: {
    label: 'Tokens: anchors',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordTokensSeeds: {
    label: 'Tokens: seeds',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordTokensScores: {
    label: 'Tokens: scores',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordTokensRepair: {
    label: 'Tokens: repair',
    kind: 'count',
    detailsRows: singleRow
  },
  ConcordTokensAfterCommit: {
    label: 'Tokens after commit',
    kind: 'count',
    detailsRows: singleRow
  }
};

// 'AccordSomeMetric' -> 'Accord some metric'
export const getMetricLabel = (metric: CognitionMetric): string => {
  const known = COGNITION_METRIC_DEFINITIONS[metric.name]?.label;
  if (known) return known;
  const text = metric.name
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};
