/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import type {
  CognitiveFailure,
  SessionWithCognitiveObservability
} from '@/types/oxp.type';

// All the failures of a session, highest confidence first.
export const getSortedFailures = (
  session: SessionWithCognitiveObservability
): CognitiveFailure[] =>
  [...(session.cognitiveFailures ?? [])].sort(
    (a, b) => b.confidence - a.confidence
  );

// The failures of a session whose confidence is above the threshold.
export const getFailuresAboveThreshold = (
  session: SessionWithCognitiveObservability,
  threshold: number
): CognitiveFailure[] =>
  getSortedFailures(session).filter(
    (failure) => failure.confidence > threshold
  );

// Union of the remediations of the failures above the threshold.
export const getRemediationsAboveThreshold = (
  session: SessionWithCognitiveObservability,
  threshold: number
): string[] =>
  Array.from(
    new Set(
      getFailuresAboveThreshold(session, threshold).flatMap(
        (failure) => failure.remediations ?? []
      )
    )
  ).sort();
