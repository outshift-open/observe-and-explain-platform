/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  StateMachineResponse,
  AgentNetworkResponse,
  HierarchyResponse
} from '@/api/kgInspectorApi';
import type {
  LayoutOptions,
  NodeData,
  EdgeData,
  GraphData,
  NodeOptions,
  EdgeOptions,
  Graph
} from '@antv/g6';

// Partial node style options for overriding defaults
export type NodeStyleOverrides = Partial<NodeOptions['style']>;
export type NodeStateOverrides = Partial<NodeOptions['state']>;

// Partial edge style options for overriding defaults
export type EdgeStyleOverrides = Partial<EdgeOptions['style']>;
export type EdgeStateOverrides = Partial<EdgeOptions['state']>;

export interface NodePropsOverrides {
  type?: NodeOptions['type'];
  style?: NodeStyleOverrides;
  state?: NodeStateOverrides;
}

export interface EdgePropsOverrides {
  type?: EdgeOptions['type'];
  style?: EdgeStyleOverrides;
  state?: EdgeStateOverrides;
}

// Generic graph data structure with nodes and edges
export interface GenericGraphData {
  nodes: Array<{ id: string; [key: string]: unknown }>;
  edges: Array<{ source: string; target: string; [key: string]: unknown }>;
  [key: string]: unknown;
}

export interface GenericGraphProps {
  data:
    | StateMachineResponse
    | AgentNetworkResponse
    | HierarchyResponse
    | GenericGraphData;
  layout?: LayoutOptions;
  nodeProps?: NodePropsOverrides;
  edgeProps?: EdgePropsOverrides;
  /** If true, shows a loading spinner until the layout finishes computing (useful for force layouts) */
  waitForLayout?: boolean;
  /** Callback fired with the Graph instance after render completes */
  onGraphReady?: (graph: Graph) => void;
  /** Custom resolver for node click data shown in drawer. If provided, overrides the default. */
  resolveNodeClickData?: (nodeId: string, nodeData: any) => any;
}

// Re-export G6 types for convenience
export type { NodeData, EdgeData, GraphData };

// Static Topology types
export type StaticTopologyNodeType = 'agent' | 'tool';

export interface StaticTopologyNode {
  id: string;
  type: StaticTopologyNodeType;
  name: string;
  description: string;
  hasTools: boolean;
}

export interface StaticTopologyEdge {
  source: string;
  target: string;
}

export interface StaticTopologyData {
  nodes: StaticTopologyNode[];
  edges: StaticTopologyEdge[];
}
