/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

// Parses an API timestamp that is either a Unix epoch (seconds or
// milliseconds, possibly as a numeric string) or a date string.
// Returns undefined when it cannot be parsed.
export const parseTimestamp = (
  timestamp?: string | number | null
): Date | undefined => {
  if (timestamp == null || timestamp === '') return undefined;
  const numeric = Number(timestamp);
  const date = Number.isFinite(numeric)
    ? new Date(numeric < 1e11 ? numeric * 1000 : numeric)
    : new Date(timestamp);
  return Number.isNaN(date.getTime()) ? undefined : date;
};
