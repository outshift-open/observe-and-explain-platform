/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export const equalsIgnoreCase = (str1: string, str2: string) => {
  return str1?.toUpperCase() === str2?.toUpperCase();
};

export const getDisplayedResultsCount = (count: number) => {
  return Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
    maximumFractionDigits: 2
  }).format(count);
};

export const getDisplayedResultsCountDollar = (count: number) => {
  return Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
    maximumFractionDigits: 7
  }).format(count);
};

export const getDisplayedResultsCountTooltip = (count: number) => {
  return Intl.NumberFormat('en-US').format(count);
};

export const capitalizeFirstLetter = (str: string) => {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
};

export const formatDurationMs = (milliseconds?: number | null, options?: { fractionDigits?: number }) => {
  const valueMs = typeof milliseconds === 'number' ? milliseconds : 0;
  if (valueMs < 1000) {
    return `${Math.round(valueMs)}ms`;
  }

  const units = [
    { label: 'd', ms: 86_400_000 },
    { label: 'h', ms: 3_600_000 },
    { label: 'm', ms: 60_000 },
    { label: 's', ms: 1_000 }
  ];

  for (const unit of units) {
    if (valueMs >= unit.ms) {
      const raw = valueMs / unit.ms;
      const fractionDigits = options?.fractionDigits ?? (raw < 10 ? 1 : 0);
      return `${raw.toFixed(fractionDigits)}${unit.label}`;
    }
  }

  return `${Math.round(valueMs)}ms`;
};

export const formatTwoDecimals = (v?: number): string => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '');
