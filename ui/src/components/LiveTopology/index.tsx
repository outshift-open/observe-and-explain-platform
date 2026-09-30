/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Box, CircularProgress, Typography, useTheme } from '@mui/material';
import { useParams } from 'react-router';
import { GenericGraph } from '../GenericGraph/GenericGraph';
import {
  StaticTopology as StaticTopologyType,
  StaticTopologyTool
} from '@/types/oxp.type';
import { useStaticTopology, useLiveTopologySession } from '@/api/oxpApi';
import { TagBackgroundColorVariants } from '@open-ui-kit/core';
import { isToolDataArray } from '@/utils';
import type { LiveTopologyNode, LiveTopologyEdge } from '@/types/oxpApi.type';
import type { Graph } from '@antv/g6';

const FILTERED_NODE_IDS: string[] = ['__start__', '__end__'];

const transformTopologyToGraphData = (
  topology: StaticTopologyType,
  liveNodes: Map<string, LiveTopologyNode>,
  liveEdges: LiveTopologyEdge[] = []
) => {
  // Build a set of agent→tool connections from live edges to determine which tools were actually invoked
  const liveToolInvocations = new Set<string>();
  liveEdges.forEach((edge) => {
    if (edge.label === 'tool_invocation') {
      liveToolInvocations.add(`${edge.source}->${edge.target}`);
    }
  });
  const nodesArray = Object.values(topology.nodes).filter(
    (node) => !FILTERED_NODE_IDS.includes(node.id)
  );

  const toolNodeIds = new Set<string>();
  const toolNodeToAgentMap = new Map<string, string>();

  nodesArray.forEach((node) => {
    if (isToolDataArray(node.data)) {
      toolNodeIds.add(node.id);
    }
  });

  // Build a mapping from tool nodes to their associated agent nodes.
  // Edges go from agent → tool_node, so the source is the agent and target is the tool node.
  topology.edges.forEach((edge) => {
    if (toolNodeIds.has(edge.target) && !toolNodeIds.has(edge.source)) {
      toolNodeToAgentMap.set(edge.target, edge.source);
    }
  });

  const nodes: Array<{
    id: string;
    label: string;
    type: 'agent' | 'tool';
    data: {
      nodeType: 'agent' | 'tool';
      parentAgentId?: string;
      description: string;
      tools?: StaticTopologyTool[];
      active: boolean;
      liveStatus?: string;
      liveData?: LiveTopologyNode;
    };
  }> = [];

  const expandedToolNodes: Array<{
    id: string;
    label: string;
    agentId: string;
    description: string;
  }> = [];

  // Process each node: expand tool nodes into individual tools, keep agent nodes as-is
  nodesArray.forEach((node) => {
    if (toolNodeIds.has(node.id)) {
      // For tool nodes, create individual nodes for each tool in the data array
      const agentId = toolNodeToAgentMap.get(node.id);
      if (agentId && isToolDataArray(node.data)) {
        node.data.forEach((tool) => {
          expandedToolNodes.push({
            id: `tool-${node.id}-${tool.name}`,
            label: tool.name,
            agentId,
            description: tool.description
          });
        });
      }
    } else {
      // For non-tool nodes (agents), add them directly to the nodes array
      // Special case: "finalize" in static topology maps to "finalize_on_error" in live topology
      const liveNodeId = node.id === 'finalize' ? 'finalize_on_error' : node.id;
      const liveNode = liveNodes.get(liveNodeId) || liveNodes.get(node.id);
      const isActive = liveNodes.has(liveNodeId) || liveNodes.has(node.id);
      const description = node.description
        ? node.description
        : typeof node.data === 'string'
          ? node.data
          : '';

      nodes.push({
        id: node.id,
        label: node.name,
        type: 'agent',
        data: {
          nodeType: 'agent',
          description,
          active: isActive,
          liveStatus: liveNode?.status,
          liveData: liveNode
        }
      });
    }
  });

  // Add expanded tool nodes to the nodes array
  expandedToolNodes.forEach((toolNode) => {
    // Tool graph IDs are "tool-{parentId}-{toolName}", live topology uses just the tool name
    const liveToolNode = liveNodes.get(toolNode.label);
    // Only mark active if the parent agent has an edge to this tool in the live topology
    const parentInvokedTool = liveToolInvocations.has(`${toolNode.agentId}->${toolNode.label}`);
    nodes.push({
      id: toolNode.id,
      label: toolNode.label,
      type: 'tool',
      data: {
        nodeType: 'tool',
        parentAgentId: toolNode.agentId,
        description: toolNode.description,
        active: parentInvokedTool ? true : !liveNodes.size ? true : false,
        liveStatus: parentInvokedTool ? liveToolNode?.status : undefined,
        liveData: parentInvokedTool ? liveToolNode : undefined
      }
    });
  });

  const edges: Array<{
    id: string;
    source: string;
    target: string;
    data: {
      isToolEdge: boolean;
      conditional: boolean;
      label: string | null;
    };
  }> = [];

  let edgeIndex = 0;

  // Add edges between agent nodes, excluding any edges involving tool nodes
  topology.edges
    .filter(
      (edge) =>
        !FILTERED_NODE_IDS.includes(edge.source) &&
        !FILTERED_NODE_IDS.includes(edge.target) &&
        !toolNodeIds.has(edge.source) &&
        !toolNodeIds.has(edge.target)
    )
    .forEach((edge) => {
      edges.push({
        id: `edge-${edgeIndex++}`,
        source: edge.source,
        target: edge.target,
        data: {
          isToolEdge: false,
          conditional: edge.conditional,
          label: edge.data
        }
      });
    });

  // Create edges from agents to their expanded tool nodes
  expandedToolNodes.forEach((toolNode) => {
    edges.push({
      id: `edge-${edgeIndex++}`,
      source: toolNode.agentId,
      target: toolNode.id,
      data: {
        isToolEdge: true,
        conditional: false,
        label: null
      }
    });
  });

  return { nodes, edges };
};

export const LiveTopology = () => {
  const theme = useTheme();
  const { applicationId, liveSessionId } = useParams();
  const graphInstanceRef = useRef<Graph | null>(null);
  const pendingNodesRef = useRef<Set<string>>(new Set());
  const pulseIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveDataMapRef = useRef<Map<string, LiveTopologyNode>>(new Map());

  const {
    data: topology,
    isLoading: isStaticLoading,
    error: staticError
  } = useStaticTopology(applicationId ?? '');

  const { data: liveTopology, isLoading: isLiveLoading } =
    useLiveTopologySession(liveSessionId ?? '');

  const isLoading = isStaticLoading || isLiveLoading;

  // Keep liveDataMapRef always in sync with the latest liveTopology
  if (liveTopology?.nodes) {
    const map = new Map<string, LiveTopologyNode>();
    liveTopology.nodes.forEach((node) => map.set(node.id, node));
    liveDataMapRef.current = map;
  }

  // Compute initial graph data from static topology + first live snapshot
  const initialLiveRef = useRef(liveTopology);
  if (!initialLiveRef.current && liveTopology) {
    initialLiveRef.current = liveTopology;
  }

  const initialGraphData = useMemo(() => {
    if (!topology) return null;
    const liveNodesMap = new Map<string, LiveTopologyNode>();
    if (initialLiveRef.current?.nodes) {
      initialLiveRef.current.nodes.forEach((node) => {
        liveNodesMap.set(node.id, node);
      });
    }
    return transformTopologyToGraphData(topology, liveNodesMap, initialLiveRef.current?.edges ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topology, initialLiveRef.current]);

  // On each live poll, update node data in-place on the G6 graph instance
  useEffect(() => {
    const graph = graphInstanceRef.current;
    if (!graph || !topology || !liveTopology) return;

    try {
      const existingNodes = graph.getNodeData();
      if (!existingNodes || existingNodes.length === 0) return;

      const liveNodesMap = new Map<string, LiveTopologyNode>();
      liveTopology.nodes.forEach((node) => {
        liveNodesMap.set(node.id, node);
      });
      liveDataMapRef.current = liveNodesMap;

      // Build live tool invocations set from edges
      const liveToolInvocations = new Set<string>();
      liveTopology.edges?.forEach((edge) => {
        if (edge.label === 'tool_invocation') {
          liveToolInvocations.add(`${edge.source}->${edge.target}`);
        }
      });

      const newPendingNodes = new Set<string>();

      existingNodes.forEach((existingNode: any) => {
        const nodeId = existingNode.id;
        const nodeType = existingNode.data?.data?.nodeType;

        let liveNode;
        let isActive: boolean;

        if (nodeType === 'tool') {
          const toolName = existingNode.data?.label || nodeId.split('-').slice(2).join('-');
          const parentAgentId = existingNode.data?.data?.parentAgentId;
          const parentInvokedTool = parentAgentId
            ? liveToolInvocations.has(`${parentAgentId}->${toolName}`)
            : false;
          liveNode = parentInvokedTool ? liveNodesMap.get(toolName) : undefined;
          isActive = parentInvokedTool;
        } else {
          const liveNodeId = nodeId === 'finalize' ? 'finalize_on_error' : nodeId;
          liveNode = liveNodesMap.get(liveNodeId) || liveNodesMap.get(nodeId);
          isActive = liveNode
            ? true
            : liveNodesMap.has(nodeId);
        }

        const updatedData = {
          ...existingNode.data,
          data: {
            ...existingNode.data?.data,
            active: isActive,
            liveStatus: liveNode?.status,
            liveData: liveNode
          }
        };

        graph.updateNodeData([{ id: nodeId, data: updatedData }]);

        if (liveNode?.status === 'active' || liveNode?.status === 'running') {
          newPendingNodes.add(nodeId);
        }
      });

      pendingNodesRef.current = newPendingNodes;
      graph.draw();
    } catch {
      // Graph may have been destroyed during re-init
    }
  }, [liveTopology, topology]);

  // Pulse animation loop via setInterval + updateNodeData/draw
  useEffect(() => {
    let frame = 0;

    pulseIntervalRef.current = setInterval(() => {
      const graph = graphInstanceRef.current;
      if (!graph || pendingNodesRef.current.size === 0) return;

      frame++;
      const pulsePhase = (Math.sin(frame * 0.3) + 1) / 2; // 0..1

      try {
        const updates: { id: string; data: any }[] = [];
        pendingNodesRef.current.forEach((nodeId) => {
          const nodeData = graph.getNodeData(nodeId) as any;
          if (nodeData) {
            updates.push({
              id: nodeId,
              data: {
                ...nodeData.data,
                data: { ...nodeData.data?.data, pulsePhase }
              }
            });
          }
        });
        if (updates.length > 0) {
          graph.updateNodeData(updates);
          graph.draw();
        }
      } catch {
        // ignore - graph may have been destroyed
      }
    }, 80);

    return () => {
      if (pulseIntervalRef.current) clearInterval(pulseIntervalRef.current);
    };
  }, []);

  const handleGraphReady = useCallback((graph: Graph) => {
    graphInstanceRef.current = graph;

    // Populate initial pending nodes set
    try {
      const nodes = graph.getNodeData();
      nodes.forEach((node: any) => {
        const liveStatus = node.data?.data?.liveStatus;
        if (liveStatus === 'active' || liveStatus === 'running') {
          pendingNodesRef.current.add(node.id);
        }
      });
    } catch {
      // ignore
    }
  }, []);

  const resolveNodeClickData = useCallback((nodeId: string, nodeData: any) => {
    const nodeType = nodeData.data?.data?.nodeType;
    let liveNode;
    if (nodeType === 'tool') {
      const toolName = nodeData.data?.label || nodeId.split('-').slice(2).join('-');
      const parentAgentId = nodeData.data?.data?.parentAgentId;
      // Only show live data if this tool's parent agent actually invoked it
      const liveEdges = liveTopology?.edges ?? [];
      const parentInvokedTool = parentAgentId && liveEdges.some(
        (e) => e.label === 'tool_invocation' && e.source === parentAgentId && e.target === toolName
      );
      liveNode = parentInvokedTool ? liveDataMapRef.current.get(toolName) : undefined;
    } else {
      const liveNodeId = nodeId === 'finalize' ? 'finalize_on_error' : nodeId;
      liveNode = liveDataMapRef.current.get(liveNodeId) || liveDataMapRef.current.get(nodeId);
    }
    if (liveNode) return liveNode;
    return nodeData.data?._originalData || nodeData.data;
  }, [liveTopology?.edges]);

  if (isLoading || !initialGraphData) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100%',
          minHeight: 500
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (staticError || !topology) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100%',
          minHeight: 500
        }}
      >
        <Typography color="error">Failed to load topology data</Typography>
      </Box>
    );
  }

  const getNodeFill = (d: any) => {
    const nodeType = d.data?.data?.nodeType || d.data?.type;
    const isActive = d.data?.data?.active !== false;

    if (!isActive) {
      return (
        theme.palette.vars?.controlBackgroundDisabled ||
        theme.palette.action.disabledBackground
      );
    }

    if (nodeType === 'tool') {
      return (
        theme.palette.vars[TagBackgroundColorVariants.AccentDWeak] ||
        theme.palette.grey[200]
      );
    }
    return (
      theme.palette.vars?.[TagBackgroundColorVariants.AccentAWeak] ||
      theme.palette.background.paper
    );
  };

  const getNodeStroke = (d: any) => {
    const nodeType = d.data?.data?.nodeType || d.data?.type;
    const isActive = d.data?.data?.active !== false;
    const liveStatus = d.data?.data?.liveStatus;

    if (!isActive) {
      return (
        theme.palette.vars?.controlBorderDisabled ||
        theme.palette.action.disabled
      );
    }

    if (liveStatus === 'completed') {
      return '#81c784';
    }
    if (liveStatus === 'active' || liveStatus === 'running') {
      return '#81d4fa';
    }

    if (nodeType === 'tool') {
      return (
        theme.palette.vars[TagBackgroundColorVariants.AccentDWeak] ||
        theme.palette.secondary.main
      );
    }
    return (
      theme.palette.vars?.[TagBackgroundColorVariants.AccentAWeak] ||
      theme.palette.primary.main
    );
  };

  const getEdgeLineDash = (d: any) => {
    if (d.data?.data?.isToolEdge || d.data?.isToolEdge) {
      return [4, 4];
    }
    return undefined;
  };

  const getEdgeStroke = (d: any) => {
    if (d.data?.data?.isToolEdge || d.data?.isToolEdge) {
      return (
        theme.palette.vars[TagBackgroundColorVariants.AccentDWeak] ||
        theme.palette.secondary.main
      );
    }
    return (
      theme.palette.vars?.interactivePrimaryDefaultDefault ||
      theme.palette.primary.main
    );
  };

  return (
    <Box sx={{ width: '100%', height: '100%', minHeight: 500 }}>
      <GenericGraph
        data={initialGraphData as any}
        layout={{
          type: 'dagre',
          rankdir: 'TB',
          nodesep: 60,
          ranksep: 80,
          nodeSize: 180
        }}
        nodeProps={{
          style: {
            fill: getNodeFill,
            stroke: getNodeStroke,
            fillOpacity: (d: any) => (d.data?.data?.active === false ? 0.4 : 1),
            shadowColor: (d: any) => {
              const liveStatus = d.data?.data?.liveStatus;
              if (liveStatus === 'active' || liveStatus === 'running')
                return '#81d4fa';
              return undefined;
            },
            shadowBlur: (d: any) => {
              const liveStatus = d.data?.data?.liveStatus;
              if (liveStatus === 'active' || liveStatus === 'running') {
                const phase = d.data?.data?.pulsePhase ?? 0;
                return 2 + phase * 28;
              }
              if (d.data?.data?.active === false) return 0;
              return 8;
            },
            strokeOpacity: (d: any) => {
              const liveStatus = d.data?.data?.liveStatus;
              if (liveStatus === 'active' || liveStatus === 'running') {
                const phase = d.data?.data?.pulsePhase ?? 0;
                return 1 - phase * 0.6;
              }
              return 1;
            },
            lineWidth: (d: any) => {
              const liveStatus = d.data?.data?.liveStatus;
              if (liveStatus === 'active' || liveStatus === 'running') {
                const phase = d.data?.data?.pulsePhase ?? 0;
                return 2.5 + phase * 2;
              }
              if (liveStatus === 'completed') return 3;
              return 2;
            }
          }
        }}
        edgeProps={{
          style: {
            stroke: getEdgeStroke,
            endArrowFill: getEdgeStroke,
            lineDash: getEdgeLineDash
          }
        }}
        onGraphReady={handleGraphReady}
        resolveNodeClickData={resolveNodeClickData}
        waitForLayout
      />
    </Box>
  );
};
