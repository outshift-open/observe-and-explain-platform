/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, CircularProgress, Typography, useTheme } from '@mui/material';
import { useParams } from 'react-router';
import { GenericGraph } from '../GenericGraph/GenericGraph';
import {
  StaticTopology as StaticTopologyType,
  StaticTopologyTool
} from '@/types/oxp.type';
import { useStaticTopology } from '@/api/oxpApi';
import { TagBackgroundColorVariants } from '@open-ui-kit/core';
import { isToolDataArray } from '@/utils';

const FILTERED_NODE_IDS: string[] = ['__start__', '__end__', 'finalize'];

const transformTopologyToGraphData = (topology: StaticTopologyType) => {
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
      description: string;
      tools?: StaticTopologyTool[];
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
          description
        }
      });
    }
  });

  // Add expanded tool nodes to the nodes array
  expandedToolNodes.forEach((toolNode) => {
    nodes.push({
      id: toolNode.id,
      label: toolNode.label,
      type: 'tool',
      data: {
        nodeType: 'tool',
        description: toolNode.description
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

export const StaticTopology = () => {
  const theme = useTheme();
  const { applicationId } = useParams();
  const {
    data: topology,
    isLoading,
    error
  } = useStaticTopology(applicationId ?? '');

  if (isLoading) {
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

  if (error || !topology || !topology.nodes) {
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

  const graphData = transformTopologyToGraphData(topology);

  const getNodeFill = (d: any) => {
    const nodeType = d.data?.data?.nodeType || d.data?.type;
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
        data={graphData as any}
        layout={{
          type: 'dagre',
          rankdir: 'TB',
          nodesep: 60,
          ranksep: 80,
          nodeSize: 180
        }}
        /*
        layout={{
          type: 'd3-force',
          nodeSize: 180,
          manyBody: {
            strength: -2000,
            distanceMax: 1000
          },
          collide: {
            radius: 150,
            strength: 1,
            iterations: 10
          },
          link: {
            distance: 400
          }
        }}
        */
        nodeProps={{
          style: {
            fill: getNodeFill,
            stroke: getNodeStroke
          }
        }}
        edgeProps={{
          style: {
            stroke: getEdgeStroke,
            endArrowFill: getEdgeStroke,
            lineDash: getEdgeLineDash
          }
        }}
        waitForLayout
      />
    </Box>
  );
};
