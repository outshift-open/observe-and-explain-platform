/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import ELK from 'elkjs/lib/elk.bundled.js';
import { MarkerType, type Node, type Edge } from '@xyflow/react';
import type { ReasoningNode, ReasoningEdge, ReasoningHistoryValueEntry, ValueStatus } from './ReasoningPath.types';

const NODE_WIDTH = 260;
const NODE_HEIGHT = 130;

const elk = new ELK();

const elkOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'SPLINES',
  'elk.portConstraints': 'FIXED_SIDE',
  'elk.layered.cycleBreaking.strategy': 'GREEDY',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
  'elk.layered.nodePlacement.favorStraightEdges': 'true',
  'elk.layered.crossingMinimization.semiInteractive': 'true',
  'elk.layered.mergeEdges': 'false',
  'elk.layered.spacing.baseValue': '80',
  'elk.layered.spacing.nodeNodeBetweenLayers': '160',
  'elk.layered.spacing.edgeNodeBetweenLayers': '60',
  'elk.spacing.nodeNode': '80',
  'elk.spacing.edgeNode': '40',
  'elk.spacing.edgeEdge': '24',
  'elk.nodeSize.constraints': 'MINIMUM_SIZE',
  'elk.portAlignment.default': 'CENTER'
};

export function getValueStatus(node: ReasoningNode): ValueStatus {
  if (node.value === null || node.value === undefined) return 'no_value';
  if (node.tier === 'alignment') {
    if (node.value === 'not_applicable') return 'not_applicable';
    if (node.value === 'satisfied' || node.value === true) return 'satisfied';
    if (node.value === 'violated' || node.value === false) return 'violated';
  }
  if (typeof node.value === 'boolean') return node.value ? 'satisfied' : 'violated';
  if (typeof node.value === 'string') {
    const lower = node.value.toLowerCase();
    if (lower === 'satisfied' || lower === 'true') return 'satisfied';
    if (lower === 'violated' || lower === 'false') return 'violated';
    if (lower === 'not_applicable') return 'not_applicable';
  }
  return 'no_value';
}

export function getStatusColor(status: ValueStatus): string {
  switch (status) {
    case 'satisfied':
      return '#4caf50';
    case 'violated':
      return '#f44336';
    case 'not_applicable':
      return '#9e9e9e';
    case 'no_value':
      return '#9e9e9e';
  }
}

export async function computeLayout(apiNodes: ReasoningNode[], apiEdges: ReasoningEdge[]): Promise<Node[]> {
  // Edges are "DEPENDS_ON" (alignment → dependency).
  // Reverse for layout: entity (left) → process (middle) → alignment (right)
  const graph = {
    id: 'root',
    layoutOptions: elkOptions,
    children: apiNodes.map((node) => ({
      id: node.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT
    })),
    edges: apiEdges.map((edge, index) => ({
      id: `elk-e-${index}`,
      sources: [edge.target],
      targets: [edge.source]
    }))
  };

  let layoutedGraph;
  try {
    layoutedGraph = await elk.layout(graph);
  } catch {
    return apiNodes.map((node, index) => ({
      id: node.id,
      type: 'reasoningNode',
      position: { x: 0, y: index * (NODE_HEIGHT + 40) },
      data: { ...node, status: getValueStatus(node) },
      width: NODE_WIDTH,
      height: NODE_HEIGHT
    }));
  }

  const positionMap = new Map<string, { x: number; y: number }>();
  for (const child of layoutedGraph.children ?? []) {
    positionMap.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
  }

  return apiNodes.map((node) => {
    const pos = positionMap.get(node.id) ?? { x: 0, y: 0 };
    return {
      id: node.id,
      type: 'reasoningNode',
      position: pos,
      data: { ...node, status: getValueStatus(node) },
      width: NODE_WIDTH,
      height: NODE_HEIGHT
    };
  });
}

function getValueAtPosition(history: ReasoningHistoryValueEntry[], position: number): ReasoningHistoryValueEntry | null {
  let latest: ReasoningHistoryValueEntry | null = null;
  for (const entry of history) {
    if (entry.trajectoryIndex !== null && entry.trajectoryIndex <= position) {
      latest = entry;
    }
  }
  return latest;
}

export function computeEdges(
  apiEdges: ReasoningEdge[],
  apiNodes: ReasoningNode[],
  sliderPosition: number | null = null
): Edge[] {
  const nodeMap = new Map(apiNodes.map((n) => [n.id, n]));

  // Reverse edge direction: show data flow from dependency → dependent
  // entity/process (left) → alignment (right)
  return apiEdges.map((edge, index) => {
    const dependentNode = nodeMap.get(edge.source);
    let isViolated = false;
    if (dependentNode?.tier === 'alignment') {
      if (sliderPosition === null) {
        isViolated = getValueStatus(dependentNode) === 'violated';
      } else {
        const entry = getValueAtPosition(dependentNode.history ?? [], sliderPosition);
        if (entry) {
          const tempNode = { ...dependentNode, value: entry.value } as ReasoningNode;
          isViolated = getValueStatus(tempNode) === 'violated';
        }
      }
    }

    return {
      id: `e-${index}-${edge.target}-${edge.source}`,
      source: edge.target,
      target: edge.source,
      type: 'default',
      animated: isViolated,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isViolated ? '#f44336' : '#9e9e9e'
      },
      style: {
        stroke: isViolated ? '#f44336' : '#9e9e9e',
        strokeWidth: isViolated ? 2 : 1
      }
    };
  });
}
