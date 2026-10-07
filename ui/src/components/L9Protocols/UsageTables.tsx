/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { L9Bound, L9PhaseUsage, L9UsageSummary } from '@/types/oxp.type';
import {
  NotAvailable,
  SimpleTable,
  formatBound,
  formatCost,
  formatCount,
  formatDollars
} from './primitives';

export const UsageSummaryTable = ({
  usage
}: {
  usage?: L9UsageSummary | null;
}) => {
  if (!usage) return <NotAvailable text="No usage data" />;

  return (
    <SimpleTable
      compact
      headers={['Metric', 'Tokens', 'Cost ($)']}
      rows={[
        [
          'Total input tokens (fresh)',
          formatCount(usage.inputTokens),
          formatDollars(usage.inputCost)
        ],
        [
          'Total output tokens',
          formatCount(usage.outputTokens),
          formatDollars(usage.outputCost)
        ],
        [
          'Cache read tokens',
          formatCount(usage.cacheReadTokens),
          formatDollars(usage.cacheReadCost)
        ],
        [
          'Cache creation tokens',
          formatCount(usage.cacheCreationTokens),
          formatDollars(usage.cacheCreationCost)
        ]
      ]}
      footer={[
        'TOTAL',
        formatCount(usage.totalTokens),
        formatDollars(usage.totalCost)
      ]}
    />
  );
};

// Sum of a column; N/A as soon as one row has no value, so that a partial sum
// is never presented as the total.
const sumColumn = (
  rows: L9PhaseUsage[],
  pick: (row: L9PhaseUsage) => number | null | undefined
): number | null => {
  let total = 0;
  for (const row of rows) {
    const value = pick(row);
    if (value === null || value === undefined || Number.isNaN(value)) {
      return null;
    }
    total += value;
  }
  return total;
};

export const PhaseUsageTable = ({
  phases,
  phaseOrder
}: {
  phases?: L9PhaseUsage[] | null;
  phaseOrder: string[];
}) => {
  if (!phases?.length) return <NotAvailable text="No per-phase usage data" />;

  const rank = (phase: string) => {
    const index = phaseOrder.indexOf(phase);
    return index === -1 ? phaseOrder.length : index;
  };
  const sorted = [...phases].sort((a, b) => rank(a.phase) - rank(b.phase));

  return (
    <SimpleTable
      headers={[
        'Phase',
        'LLM calls',
        'Input',
        'Output',
        'Cache rd',
        'Cache wr',
        'Cost ($)'
      ]}
      rows={sorted.map((row) => [
        row.phase,
        formatCount(row.llmCalls),
        formatCount(row.inputTokens),
        formatCount(row.outputTokens),
        formatCount(row.cacheReadTokens),
        formatCount(row.cacheCreationTokens),
        formatCost(row.cost)
      ])}
      footer={[
        'Total',
        formatCount(sumColumn(sorted, (r) => r.llmCalls)),
        formatCount(sumColumn(sorted, (r) => r.inputTokens)),
        formatCount(sumColumn(sorted, (r) => r.outputTokens)),
        formatCount(sumColumn(sorted, (r) => r.cacheReadTokens)),
        formatCount(sumColumn(sorted, (r) => r.cacheCreationTokens)),
        formatCost(sumColumn(sorted, (r) => r.cost))
      ]}
    />
  );
};

export const BoundsTable = ({ bounds }: { bounds?: L9Bound[] | null }) => {
  if (!bounds?.length) return <NotAvailable text="No bounds reported" />;

  return (
    <SimpleTable
      headers={['Resource', 'Achieved / bound']}
      rows={bounds.map((bound) => [
        bound.name,
        formatBound(bound.achieved, bound.bound)
      ])}
    />
  );
};
