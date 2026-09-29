/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Unit } from '@/types/oxp.type';

const TOPOLOGY_NODE_WIDTH = 182;
const TOPOLOGY_NODE_HEIGHT = 26;

const THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60;

export const DEFAULT_END_DATE = Math.floor(Date.now() / 1000);
export const DEFAULT_START_DATE = DEFAULT_END_DATE - THIRTY_DAYS_SECONDS;

export { TOPOLOGY_NODE_HEIGHT, TOPOLOGY_NODE_WIDTH };

export const unitSuffix: Record<Unit, string> = {
  [Unit.Dollar]: '$',
  [Unit.Milliseconds]: 'ms',
  [Unit.Percentage]: '%',
  [Unit.Scalar]: ''
};

export enum RepositorySortOption {
  mostRecent = 'mostRecent',
  oldest = 'oldest'
}

export const RepositorySortOptionLabel: Record<RepositorySortOption, string> = {
  [RepositorySortOption.mostRecent]: 'Most Recent',
  [RepositorySortOption.oldest]: 'Oldest'
};
