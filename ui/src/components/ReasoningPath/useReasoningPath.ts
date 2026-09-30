/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type {
  ReasoningPathResponse,
  ReasoningNode,
  ReasoningHistoryValueEntry
} from '@/types/oxp.type';
import { useReasoningPath as useReasoningPathQuery } from '@/api/oxpApi';
import {
  computeLayout,
  computeEdges,
  getValueStatus
} from './ReasoningPath.utils';

interface UseReasoningPathGraphResult {
  nodes: Node[];
  edges: Edge[];
  model: ReasoningPathResponse['model'];
  trajectoryScore: number | null;
  evaluationRounds: number[];
  sliderPosition: number | null;
  setSliderPosition: (position: number | null) => void;
  isLoading: boolean;
  error: Error | null;
}

const EMPTY_NODES: Node[] = [];
const EMPTY_EDGES: Edge[] = [];

function getValueAtPosition(
  history: ReasoningHistoryValueEntry[],
  position: number
): ReasoningHistoryValueEntry | null {
  let latest: ReasoningHistoryValueEntry | null = null;
  for (const entry of history) {
    if (entry.trajectoryIndex !== null && entry.trajectoryIndex <= position) {
      latest = entry;
    }
  }
  return latest;
}

function buildNodeData(apiNode: ReasoningNode, position: number | null) {
  if (position === null) {
    const status = getValueStatus(apiNode);
    return { ...apiNode, status, isFresh: false };
  }

  const entry = getValueAtPosition(apiNode.history, position);
  if (!entry) {
    const emptyNode = {
      ...apiNode,
      value: null,
      reason: null,
      trajectoryIndex: null,
      assignmentStrategy: null,
      valueId: null,
      spanId: null,
      executionId: null,
      entityName: null,
      executionLabels: null,
      toolName: null,
      processingName: null,
      llmName: null,
      modelName: null,
      executionTimestamp: null,
      executionDuration: null,
      inputParams: null,
      outputContent: null,
      toolOutput: null
    };
    return {
      ...emptyNode,
      status: getValueStatus(emptyNode as ReasoningNode),
      isFresh: false
    };
  }

  const isFresh = entry.trajectoryIndex === position;
  const nodeAtPosition = {
    ...apiNode,
    value: entry.value,
    reason: entry.reason,
    trajectoryIndex: entry.trajectoryIndex,
    assignmentStrategy: entry.assignmentStrategy,
    valueId: entry.valueId,
    spanId: entry.spanId,
    executionId: entry.executionId,
    entityName: entry.entityName,
    executionLabels: entry.executionLabels,
    toolName: entry.toolName,
    processingName: entry.processingName,
    llmName: entry.llmName,
    modelName: entry.modelName,
    executionTimestamp: entry.executionTimestamp,
    executionDuration: entry.executionDuration,
    inputParams: entry.inputParams,
    outputContent: entry.outputContent,
    toolOutput: entry.toolOutput
  };

  return {
    ...nodeAtPosition,
    status: getValueStatus(nodeAtPosition as ReasoningNode),
    isFresh
  };
}

export function useReasoningPathGraph(
  sessionId: string
): UseReasoningPathGraphResult {
  const { data, isLoading, error } = useReasoningPathQuery(sessionId);
  const [layoutedPositions, setLayoutedPositions] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());
  const [layoutReady, setLayoutReady] = useState(false);
  const [sliderPosition, setSliderPosition] = useState<number | null>(null);

  const effectivePosition = useMemo(() => {
    if (sliderPosition !== null) return sliderPosition;
    if (data && data.evaluationRounds.length > 0) {
      return data.evaluationRounds[data.evaluationRounds.length - 1];
    }
    return null;
  }, [sliderPosition, data]);

  useEffect(() => {
    if (!data) {
      setLayoutedPositions(new Map());
      setLayoutReady(false);
      return;
    }
    let cancelled = false;
    computeLayout(data.nodes, data.edges).then((layoutNodes) => {
      if (!cancelled) {
        const positions = new Map<string, { x: number; y: number }>();
        for (const node of layoutNodes) {
          positions.set(node.id, node.position);
        }
        setLayoutedPositions(positions);
        setLayoutReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [data]);

  const nodes: Node[] = useMemo(() => {
    if (!data || !layoutReady) return EMPTY_NODES;
    return data.nodes.map((apiNode) => {
      const pos = layoutedPositions.get(apiNode.id) ?? { x: 0, y: 0 };
      const nodeData = buildNodeData(apiNode, effectivePosition);
      return {
        id: apiNode.id,
        type: 'reasoningNode',
        position: pos,
        data: nodeData,
        width: 260,
        height: 130
      };
    });
  }, [data, layoutReady, layoutedPositions, effectivePosition]);

  const edges: Edge[] = useMemo(() => {
    if (!data) return EMPTY_EDGES;
    return computeEdges(data.edges, data.nodes, effectivePosition);
  }, [data, effectivePosition]);

  const evaluationRounds = useMemo(() => data?.evaluationRounds ?? [], [data]);

  const handleSetSliderPosition = useCallback((position: number | null) => {
    setSliderPosition(position);
  }, []);

  return {
    nodes,
    edges,
    model: data?.model ?? null,
    trajectoryScore: data?.trajectoryScore ?? null,
    evaluationRounds,
    sliderPosition: effectivePosition,
    setSliderPosition: handleSetSliderPosition,
    isLoading,
    error: error as Error | null
  };
}
