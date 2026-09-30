/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material';
import { KGGraph } from '@/components/KGInspectorGraph';
import type { LayoutOptions } from '@antv/g6';
import { useSemanticGroupsTree } from '@/api/oxpApi';
import { useParams } from 'react-router-dom';
import { Spinner } from '@open-ui-kit/core';
import { useMemo } from 'react';
import type { SemanticGroup } from '@/types/oxp.type';

const FONT_SIZE = 14;
const PADDING_X = 24;
const NODE_HEIGHT = 40;
const MAX_NODE_WIDTH = 300;

const measureTextWidth = (text: string, fontSize: number): number => {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) return text.length * fontSize * 0.6;
  context.font = `600 ${fontSize}px sans-serif`;
  return context.measureText(text).width;
};

const getNodeSize = (d: any): [number, number] => {
  const label = d.data?.label || d.data?.id || 'Unknown';
  const textWidth = measureTextWidth(label, FONT_SIZE);
  const width = Math.min(
    MAX_NODE_WIDTH,
    Math.max(120, textWidth + PADDING_X * 2)
  );
  return [width, NODE_HEIGHT];
};

const TREE_LAYOUT: LayoutOptions = {
  type: 'dagre',
  rankdir: 'TB',
  nodesep: 40,
  ranksep: 60
};

interface GraphNode {
  id: string;
  label: string;
  group_name: string;
  group_summary: string;
  n_sessions: number;
  medioid_session_id: string;
  session_ids: string[];
  split_distance: number;
  [key: string]: unknown;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  [key: string]: unknown;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  [key: string]: unknown;
}

const transformSemanticGroupsToGraph = (groups: SemanticGroup[]): GraphData => {
  if (!groups || groups.length === 0) {
    return { nodes: [], edges: [] };
  }

  const nodeIds = new Set(groups.map((g) => g.id));

  const nodes: GraphNode[] = groups.map((group) => ({
    id: group.id,
    label: group.group_name,
    group_name: group.group_name,
    group_summary: group.group_summary,
    n_sessions: group.n_sessions,
    medioid_session_id: group.medioid_session_id,
    session_ids: group.session_ids,
    split_distance: group.split_distance
  }));

  const edges: GraphEdge[] = [];
  let edgeIndex = 0;

  groups.forEach((group) => {
    if (group.children_nodes && group.children_nodes.length > 0) {
      group.children_nodes.forEach((childId) => {
        if (!nodeIds.has(childId)) return;
        edges.push({
          id: `edge-${edgeIndex++}`,
          source: group.id,
          target: childId
        });
      });
    }
  });

  return { nodes, edges };
};

export const TopicHierarchy = () => {
  const theme = useTheme();
  const { applicationId } = useParams();

  const {
    data: semanticGroupsTree,
    isLoading: semanticGroupsTreeLoading,
    isError: semanticGroupsTreeError
  } = useSemanticGroupsTree(applicationId ?? '');

  const graphData = useMemo(() => {
    return transformSemanticGroupsToGraph(semanticGroupsTree ?? []);
  }, [semanticGroupsTree]);

  const getNodeFillColor = () => {
    return (
      theme.palette.vars?.baseBackgroundMedium || theme.palette.background.paper
    );
  };

  const getNodeStrokeColor = () => {
    return (
      theme.palette.vars?.interactivePrimaryDefaultDefault ||
      theme.palette.primary.main
    );
  };

  if (semanticGroupsTreeLoading) {
    return (
      <Stack
        justifyContent={'center'}
        alignItems={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (semanticGroupsTreeError) {
    return <>An error occurred!</>;
  }

  return (
    <Stack direction={'column'} gap={'12px'}>
      <Typography variant={'h6'}>Topic Hierarchy</Typography>
      <Box
        sx={{
          height: 'calc(100vh - 350px)',
          minHeight: 400,
          overflow: 'hidden'
        }}
      >
        <KGGraph
          data={graphData}
          layout={TREE_LAYOUT}
          nodeProps={{
            style: {
              size: getNodeSize,
              labelFontSize: FONT_SIZE,
              labelWordWrap: true,
              labelWordWrapWidth: MAX_NODE_WIDTH - PADDING_X * 2,
              labelMaxLines: 1,
              labelTextOverflow: 'ellipsis',
              fill: getNodeFillColor,
              stroke: getNodeStrokeColor
            }
          }}
          edgeProps={{
            type: 'polyline',
            style: {
              radius: 8
            }
          }}
        />
      </Box>
    </Stack>
  );
};
