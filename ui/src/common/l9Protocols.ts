/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  L9AccordProtocol,
  L9ConcordProtocol,
  L9Protocol
} from '@/types/oxp.type';

export const L9_CONCORD = 'L9-CONCORD';
export const L9_ACCORD = 'L9-ACCORD';

export const isConcordProtocol = (
  protocol: L9Protocol
): protocol is L9ConcordProtocol => protocol.protocol === L9_CONCORD;

export const isAccordProtocol = (
  protocol: L9Protocol
): protocol is L9AccordProtocol => protocol.protocol === L9_ACCORD;

// Display order of the CONCORD cost phases; unknown phases go last.
export const CONCORD_PHASE_ORDER = [
  'pre_concord',
  'init',
  'anchors',
  'seeds',
  'scores',
  'commit_and_after'
];

// Display order of the ACCORD phases; unknown phases go last.
export const ACCORD_PHASE_ORDER = [
  'CONVENE',
  'FRAME',
  'GROUND',
  'VERIFY',
  'LOCK'
];

// CONCORD terminal states. The success state is named `COMMIT` or `SUCCESS`
// depending on the source, so both are accepted.
export const isCommitState = (state?: string | null): boolean =>
  state === 'COMMIT' || state === 'SUCCESS';

export const isBestEffortState = (state?: string | null): boolean =>
  state === 'BEST_EFFORT';

// `info` is for informational values that are neither good nor bad; `neutral`
// (grey) is for absence of a signal.
export type L9Tone = 'positive' | 'warning' | 'negative' | 'info' | 'neutral';

// Verdict labels are not confirmed yet: this is an extensible mapping, and any
// label that is not listed is displayed with a neutral tone.
export const L9_VERDICT_TONES: Record<string, L9Tone> = {
  ACTIVATED: 'positive',
  INCORRECTLY_ACTIVATED: 'negative',
  SATISFACTORY: 'positive',
  MIXED: 'warning',
  FAIR: 'positive',
  INSUFFICIENT_DATA: 'neutral'
};

export const getVerdictTone = (label: string): L9Tone =>
  L9_VERDICT_TONES[label.toUpperCase()] ?? 'neutral';

// 'INCORRECTLY_ACTIVATED' -> 'Incorrectly activated'
export const humanizeLabel = (label: string): string => {
  const text = label.replace(/[_-]+/g, ' ').trim().toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};
