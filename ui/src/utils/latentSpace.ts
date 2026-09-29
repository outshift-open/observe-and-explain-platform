/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import type {
  SessionLatentSpaceResponse,
  LatentSpaceNode,
  LatentSpaceEdge,
  SessionLatentSpaceData
} from '@/types/oxp.type';

export function transformLatentSpaceResponse(response: SessionLatentSpaceResponse): SessionLatentSpaceData {
  const SCALE_FACTOR = 3;

  const nodes: LatentSpaceNode[] = response.nodes.map((node) => ({
    id: node.id,
    label: node.label,
    type: node.type,
    x: node.x * SCALE_FACTOR,
    y: node.y * SCALE_FACTOR,
    data: {
      state_id: node.data.state_id,
      content: node.data.content,
      semantic_type: node.data.semantic_type,
      path: node.data.path
    },
    metadata: {
      hierarchy_levels: ['agent']
    }
  }));

  const nodeIds = new Set(nodes.map((node) => node.id));
  const nodePositions = new Map(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));

  const edges: LatentSpaceEdge[] = (response.edges || [])
    .filter((edge) => {
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
        return false;
      }
      const sourcePos = nodePositions.get(edge.source);
      const targetPos = nodePositions.get(edge.target);
      if (sourcePos && targetPos && sourcePos.x === targetPos.x && sourcePos.y === targetPos.y) {
        return false;
      }
      return true;
    })
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      type: edge.type,
      data: {
        transition_id: edge.data.transition_id,
        duration: edge.data.duration,
        edge_type: edge.data.edge_type,
        entity_name: edge.data.entity_name,
        entity_type: edge.data.entity_type
      },
      metadata: {
        hierarchy_level: 'agent'
      }
    }));

  const hasFinalState = nodes.some((node) => node.data.semantic_type === 'final');

  return {
    nodes,
    edges,
    session_id: response.session_id,
    hierarchy_level: 'agent',
    metadata: {
      graph_type: response.metadata.graph_type,
      node_count: response.metadata.node_count,
      edge_count: edges.length,
      source: response.metadata.projection_method,
      isTimeout: !hasFinalState
    }
  };
}
