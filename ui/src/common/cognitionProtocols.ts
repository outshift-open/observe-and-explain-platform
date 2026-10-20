/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  CognitionAccordProtocol,
  CognitionConcordProtocol,
  CognitionProtocol
} from '@/types/oxp.type';

export const COGNITION_CONCORD = 'L9-CONCORD';
export const COGNITION_ACCORD = 'L9-ACCORD';

export const isConcordProtocol = (
  protocol: CognitionProtocol
): protocol is CognitionConcordProtocol => protocol.protocol === COGNITION_CONCORD;

export const isAccordProtocol = (
  protocol: CognitionProtocol
): protocol is CognitionAccordProtocol => protocol.protocol === COGNITION_ACCORD;

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
export type CognitionTone = 'positive' | 'warning' | 'negative' | 'info' | 'neutral';

// Verdict labels are not confirmed yet: this is an extensible mapping, and any
// label that is not listed is displayed with a neutral tone.
export const COGNITION_VERDICT_TONES: Record<string, CognitionTone> = {
  ACTIVATED: 'positive',
  INCORRECTLY_ACTIVATED: 'negative',
  SATISFACTORY: 'positive',
  MIXED: 'warning',
  FAIR: 'positive',
  INSUFFICIENT_DATA: 'neutral'
};

export const getVerdictTone = (label: string): CognitionTone =>
  COGNITION_VERDICT_TONES[label.toUpperCase()] ?? 'neutral';

// 'INCORRECTLY_ACTIVATED' -> 'Incorrectly activated'
export const humanizeLabel = (label: string): string => {
  const text = label.replace(/[_-]+/g, ' ').trim().toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};
