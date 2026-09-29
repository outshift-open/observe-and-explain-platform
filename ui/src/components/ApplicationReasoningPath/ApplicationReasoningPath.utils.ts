/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import ELK from 'elkjs/lib/elk.bundled.js';
import { MarkerType, type Node, type Edge } from '@xyflow/react';
import type { AppReasoningNode, ReasoningEdge } from '@/types/oxp.type';

const NODE_WIDTH = 300;
const NODE_HEIGHT = 160;

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
  'elk.layered.spacing.nodeNodeBetweenLayers': '180',
  'elk.layered.spacing.edgeNodeBetweenLayers': '60',
  'elk.spacing.nodeNode': '80',
  'elk.spacing.edgeNode': '40',
  'elk.spacing.edgeEdge': '24',
  'elk.nodeSize.constraints': 'MINIMUM_SIZE',
  'elk.portAlignment.default': 'CENTER'
};

const HIGH_CARDINALITY_THRESHOLD = 8;

export function isHighCardinality(node: AppReasoningNode): boolean {
  return (
    node.tier === 'entity' &&
    node.distinctValueCount > HIGH_CARDINALITY_THRESHOLD
  );
}

export function getDominantStatus(
  distribution: Record<string, number>
): string | null {
  if (Object.keys(distribution).length === 0) return null;
  let maxKey: string | null = null;
  let maxCount = 0;
  for (const [key, count] of Object.entries(distribution)) {
    if (count > maxCount) {
      maxCount = count;
      maxKey = key;
    }
  }
  return maxKey;
}

export function getDistributionColor(value: string): string {
  const lower = value.toLowerCase();
  if (lower === 'satisfied' || lower === 'true') return '#4caf50';
  if (lower === 'violated' || lower === 'false') return '#f44336';
  if (lower === 'not_applicable') return '#9e9e9e';
  if (lower === 'pending' || lower === 'unresolved') return '#ff9800';

  // For arbitrary string values (e.g. "itinerary_planning", "single_definitive"),
  // deterministically pick a color from the palette using a simple string hash.
  // This ensures the same value always gets the same color across renders.
  const palette = [
    '#2196f3',
    '#9c27b0',
    '#00bcd4',
    '#795548',
    '#607d8b',
    '#e91e63',
    '#3f51b5',
    '#cddc39'
  ];
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    /*
      The | 0 (bitwise OR with zero) coerces the result to a 32-bit integer at each step, 
      preventing the number from exceeding safe integer precision. 
      This way single_definitive, multiple_options_listed, decline_to_answer, 
      and partial_answer will each produce a different hash and get distinct colors from the palette.
    */
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return palette[Math.abs(hash) % palette.length];
}

export async function computeLayout(
  apiNodes: AppReasoningNode[],
  apiEdges: ReasoningEdge[]
): Promise<Map<string, { x: number; y: number }>> {
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

  const positions = new Map<string, { x: number; y: number }>();

  try {
    const layoutedGraph = await elk.layout(graph);
    for (const child of layoutedGraph.children ?? []) {
      positions.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
    }
  } catch {
    apiNodes.forEach((node, index) => {
      positions.set(node.id, { x: 0, y: index * (NODE_HEIGHT + 40) });
    });
  }

  // Apply avgLastTrajectoryIndex as an X offset so nodes that are evaluated
  // later in the trajectory sit further to the right, reflecting temporal order
  // const X_SCALE = 120;
  // for (const node of apiNodes) {
  //   const pos = positions.get(node.id);
  //   if (pos && node.avgLastTrajectoryIndex !== null) {
  //     pos.x += node.avgLastTrajectoryIndex * X_SCALE;
  //   }
  // }

  return positions;
}

export function computeEdges(
  apiEdges: ReasoningEdge[],
  apiNodes: AppReasoningNode[]
): Edge[] {
  const nodeMap = new Map(apiNodes.map((n) => [n.id, n]));

  return apiEdges.map((edge, index) => {
    const dependentNode = nodeMap.get(edge.source);
    let hasViolations = false;
    if (
      dependentNode &&
      (dependentNode.tier === 'alignment' || dependentNode.tier === 'process')
    ) {
      const dist = dependentNode.distribution;
      hasViolations = (dist['violated'] ?? 0) > 0 || (dist['false'] ?? 0) > 0;
    }

    return {
      id: `e-${index}-${edge.target}-${edge.source}`,
      source: edge.target,
      target: edge.source,
      type: 'default',
      animated: hasViolations,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: hasViolations ? '#f44336' : '#9e9e9e'
      },
      style: {
        stroke: hasViolations ? '#f44336' : '#9e9e9e',
        strokeWidth: hasViolations ? 2 : 1
      }
    };
  });
}

export { NODE_WIDTH, NODE_HEIGHT };
