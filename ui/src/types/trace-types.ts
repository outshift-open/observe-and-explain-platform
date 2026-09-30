/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export type TraceType = 'application' | 'task' | 'agent' | 'agp' | 'connection' | 'chat' | 'tool' | 'workflow' | 'transport' | 'start_end' | 'slim';

export type ExtendedTreeItemProps = {
  traceType?: TraceType;
  duration?: number;
  intentRecognition?: number;
  intentRecognitionReasoning?: string;
  relevance?: number;
  relevanceReasoning?: string;
  groundedness?: number;
  groundednessReasoning?: string;
  id: string;
  parentId?: string;
  label: string;
  isLast?: boolean;
  // Absolute timeline metrics relative to root
  rootDuration?: number;
  rootDurationMultiplier?: number;
  absoluteOffsetMs?: number;
  startTime?: number;
  endTime?: number;
  error?: boolean;
};

// Minimal Span shape used for building the ExecutionTrace tree
export type TraceSpan = {
  spanId: string;
  spanName: string;
  startTime: string;
  endTime?: string;
  duration?: number;
  icon?: TraceType | string;
  childrenSpans?: TraceSpan[] | null;
};
