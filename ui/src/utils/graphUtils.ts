/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  StateMachineResponse,
  AgentNetworkResponse,
  HierarchyResponse
} from '@/api/kgInspectorApi';
import type { NodeData, EdgeData, GraphData } from '@antv/g6';
import type { GenericGraphData } from '@/components/KGInspectorGraph/types';

export const transformDataToG6Graph = (
  data:
    | StateMachineResponse
    | AgentNetworkResponse
    | HierarchyResponse
    | GenericGraphData
): GraphData => {
  const nodes: NodeData[] = [];
  const edges: EdgeData[] = [];

  // Check if data has nodes and edges properties
  if (data && typeof data === 'object') {
    // Handle different possible data structures
    const graphData = data as any;

    // Extract nodes
    if (graphData.nodes && Array.isArray(graphData.nodes)) {
      graphData.nodes.forEach((node: any) => {
        nodes.push({
          id: node.id || node.node_id || String(nodes.length),
          data: {
            label: node.label || node.name || node.id || 'Unknown',
            type: node.type || node.node_type,
            status: node.status,
            ...node
          }
        });
      });
    }

    // Extract edges
    if (graphData.edges && Array.isArray(graphData.edges)) {
      graphData.edges.forEach((edge: any, index: number) => {
        edges.push({
          id: edge.id || `edge-${index}`,
          source: edge.source || edge.from || edge.source_id,
          target: edge.target || edge.to || edge.target_id,
          data: {
            label: edge.label || edge.relationship,
            ...edge
          }
        });
      });
    }

    // If no nodes/edges found, try to extract from other common structures
    if (nodes.length === 0) {
      // Try to extract from state machine structure
      if (graphData.states && Array.isArray(graphData.states)) {
        graphData.states.forEach((state: any, index: number) => {
          nodes.push({
            id: state.id || `state-${index}`,
            data: {
              label: state.name || state.id || `State ${index}`,
              type: 'state',
              status: state.status,
              ...state
            }
          });
        });
      }

      // Try to extract transitions as edges
      if (graphData.transitions && Array.isArray(graphData.transitions)) {
        graphData.transitions.forEach((transition: any, index: number) => {
          edges.push({
            id: `transition-${index}`,
            source: transition.from || transition.source,
            target: transition.to || transition.target,
            data: {
              label: transition.event || transition.action,
              ...transition
            }
          });
        });
      }
    }
  }

  // If still no nodes, create a single node with the data
  if (nodes.length === 0) {
    nodes.push({
      id: 'root',
      data: {
        label: 'Root Node',
        type: 'root',
        ...data
      }
    });
  }

  return { nodes, edges };
};

// Get color for hierarchy level using spark theme tokens
export const getHierarchyColor = (level: string, theme: any): string => {
  switch (level) {
    case 'session':
      return '#139BEB';
    case 'mas':
      return '#12275C';
    case 'agent':
      return '#9747FF';
    case 'task':
      return '#FF9000';
    case 'call':
      return '#FFE659';
    default:
      return '#FF007F';
  }
};

// Get status color based on node status
export const getStatusColor = (status?: string, isDark = false): string => {
  switch (status) {
    case 'completed':
    case 'success':
      return isDark ? '#66bb6a' : '#4caf50'; // green
    case 'error':
    case 'failed':
      return isDark ? '#f44336' : '#d32f2f'; // red
    case 'running':
    case 'in_progress':
      return isDark ? '#42a5f5' : '#1976d2'; // blue
    default:
      return isDark ? '#9e9e9e' : '#757575'; // grey
  }
};
