/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export type {
  ReasoningPathResponse,
  ReasoningNode,
  ReasoningEdge,
  ReasoningHistoryValueEntry
} from '@/types/oxp.type';

export type NodeTier = 'entity' | 'process' | 'alignment';

export type ValueStatus =
  | 'satisfied'
  | 'violated'
  | 'not_applicable'
  | 'no_value';
