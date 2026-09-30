/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export function compareDatesAsc(a: unknown, b: unknown): number {
  const aTime = new Date(a as string | number | Date).getTime();
  const bTime = new Date(b as string | number | Date).getTime();
  const aNaN = Number.isNaN(aTime);
  const bNaN = Number.isNaN(bTime);
  if (aNaN && bNaN) return 0;
  if (aNaN) return 1; // push invalid dates to the end
  if (bNaN) return -1;
  return aTime - bTime;
}

export function sortByDateAccessorAsc<T>(items: Array<T | null | undefined>, accessor: (item: T) => string | number | Date | null | undefined): T[] {
  return items
    .filter(Boolean)
    .map((i) => i as T)
    .slice()
    .sort((a, b) => compareDatesAsc(accessor(a), accessor(b)));
}

export function sortByDateKeyAsc<T extends Record<string, unknown>>(items: Array<T | null | undefined>, key: keyof T): T[] {
  return sortByDateAccessorAsc(items as Array<T | null | undefined>, (item) => item?.[key] as string | number | Date | null | undefined);
}
