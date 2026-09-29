/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material';
import { Spinner } from '@open-ui-kit/core';
import { useHierarchy } from '@/api/kgInspectorApi';
import type { LayoutOptions } from '@antv/g6';
import { KGGraph } from '@/components/KGInspectorGraph';
import { getHierarchyColor } from '@/utils/graphUtils';

export type HierarchyLayoutType = 'dagre-tb' | 'dagre-lr' | 'tree';

const NODE_FONT_SIZE = 18;
const NODE_FONT = `600 ${NODE_FONT_SIZE}px sans-serif`;
const NODE_HEIGHT = 60;
const NODE_H_PADDING = 40;
const NODE_MIN_WIDTH = 120;

let measureCanvas: HTMLCanvasElement | null = null;

const measureLabelWidth = (text: string): number => {
  if (!measureCanvas) {
    measureCanvas = document.createElement('canvas');
  }
  const ctx = measureCanvas.getContext('2d');
  if (!ctx) return NODE_MIN_WIDTH;
  ctx.font = NODE_FONT;
  return ctx.measureText(text).width;
};

const getNodeWidth = (label: string): number => {
  const textWidth = measureLabelWidth(label);
  return Math.max(NODE_MIN_WIDTH, Math.ceil(textWidth) + NODE_H_PADDING * 2);
};

const getNodeSizeFromData = (d: any): [number, number] => {
  const label = d.data?.label || 'Unknown';
  return [getNodeWidth(label), NODE_HEIGHT];
};

export const HIERARCHY_LAYOUT_OPTIONS: Record<
  HierarchyLayoutType,
  LayoutOptions
> = {
  'dagre-tb': {
    type: 'antv-dagre',
    rankdir: 'TB',
    nodesep: 30,
    ranksep: 60,
    align: 'UL',
    nodeSize: (d: any) => getNodeSizeFromData(d)
  },
  'dagre-lr': {
    type: 'antv-dagre',
    rankdir: 'LR',
    nodesep: 40,
    ranksep: 120,
    align: 'UL',
    nodeSize: (d: any) => getNodeSizeFromData(d)
  },
  tree: {
    type: 'compact-box',
    direction: 'TB',
    getHeight: () => NODE_HEIGHT,
    getWidth: (d: any) => getNodeWidth(d.data?.label || 'Unknown'),
    getVGap: () => 40,
    getHGap: () => 60
  }
};

export interface SessionHierarchyGraphProps {
  sessionId: string;
  layout?: HierarchyLayoutType;
  height?: string | number;
}

export const SessionHierarchyGraph = ({
  sessionId,
  layout = 'dagre-tb',
  height = 'calc(100vh - 300px)'
}: SessionHierarchyGraphProps) => {
  const theme = useTheme();
  const { data, isLoading, error } = useHierarchy(sessionId);

  const getNodeFillColor = (d: any) => {
    const nodeType = d.data?.type;
    const level = d.data?.data?.level;

    console.log('level', level);
    console.log('node type', nodeType);

    if (level) {
      return getHierarchyColor(level, theme);
    }

    switch (nodeType) {
      case 'session':
        return '#139BEB';
      case 'mas':
        return '#12275C';
      case 'agent':
        return '#9747FF';
      case 'call':
        return '#74FFC7';
      default:
        return '#FF007F';
    }
  };

  const getNodeTextColor = (d: any) => {
    const level = d.data?.data?.level;

    if (level === 'call') {
      return '#000';
    }

    return '#fff';
  };

  const getEdgeStrokeColor = (d: any) => {
    const edgeType = d.data?.type;
    if (edgeType === 'sequence') {
      return (
        theme.palette.vars?.neutralBorderDefault || theme.palette.grey[500]
      );
    }
    return (
      theme.palette.vars?.interactivePrimaryDefaultDefault ||
      theme.palette.primary.main
    );
  };

  const getEdgeLineDash = (d: any) => {
    const edgeType = d.data?.type;
    if (edgeType === 'sequence') {
      return [4, 4];
    }
    return undefined;
  };

  if (isLoading) {
    return (
      <Stack
        alignItems={'center'}
        justifyContent={'center'}
        sx={{
          width: '100%',
          height: height,
          minHeight: '100px',
          backgroundColor:
            theme.palette.vars?.baseBackgroundWeak ||
            theme.palette.background.default
        }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (error) {
    return (
      <Box
        sx={{
          p: 2,
          borderRadius: 1,
          backgroundColor: theme.palette.error.dark,
          color: theme.palette.error.contrastText
        }}
      >
        <Typography variant="body1">Error: {error.message}</Typography>
      </Box>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Box
      sx={{
        height: height,
        overflow: 'hidden'
      }}
    >
      <KGGraph
        data={data}
        layout={HIERARCHY_LAYOUT_OPTIONS[layout]}
        nodeProps={{
          style: {
            size: getNodeSizeFromData,
            labelWordWrap: false,
            fill: getNodeFillColor,
            labelFill: getNodeTextColor
          }
        }}
        edgeProps={{
          type: 'polyline',
          style: {
            stroke: getEdgeStrokeColor,
            endArrowFill: getEdgeStrokeColor,
            lineDash: getEdgeLineDash,
            radius: 8
          }
        }}
      />
    </Box>
  );
};
