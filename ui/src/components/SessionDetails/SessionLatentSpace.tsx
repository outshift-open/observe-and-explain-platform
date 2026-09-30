/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Graph } from '@antv/g6';
import { Box, Stack, Typography, useTheme, Theme, FormControlLabel, Switch } from '@mui/material';
import type { LatentSpaceNode, LatentSpaceEdge, SessionLatentSpaceData } from '@/types/oxp.type';

interface SemanticTypeColors {
  initial: { fill: string; stroke: string };
  intermediate: { fill: string; stroke: string };
  final: { fill: string; stroke: string };
}

function getSemanticTypeColors(theme: Theme): SemanticTypeColors {
  return {
    initial: {
      fill: theme.palette.vars?.excellentBackgroundDefault || theme.palette.success.light,
      stroke: theme.palette.vars?.excellentBorderDefault || theme.palette.success.main
    },
    intermediate: {
      fill: theme.palette.vars?.infoBackgroundDefault || theme.palette.info.light,
      stroke: theme.palette.vars?.infoBorderDefault || theme.palette.info.main
    },
    final: {
      fill: theme.palette.vars?.severeWarningBackgroundDefault || theme.palette.warning.light,
      stroke: theme.palette.vars?.severeWarningBorderDefault || theme.palette.warning.main
    }
  };
}

function getEdgeColor(theme: Theme): string {
  return theme.palette.vars?.interactivePrimaryDefaultDefault || theme.palette.primary.main;
}

function getTimeoutColor(theme: Theme): { fill: string; stroke: string } {
  return {
    fill: theme.palette.vars?.negativeBackgroundDefault || theme.palette.error.light,
    stroke: theme.palette.vars?.negativeBorderDefault || theme.palette.error.main
  };
}

interface TooltipThemeColors {
  background: string;
  text: string;
  textSecondary: string;
  shadow: string;
}

function createNodesFromData(
  nodes: LatentSpaceNode[],
  semanticTypeColors: SemanticTypeColors,
  isTimeout: boolean,
  timeoutColors: { fill: string; stroke: string }
) {
  return nodes.map((node) => {
    const isFinalWithTimeout = isTimeout && node.data.semantic_type === 'final';
    return {
      id: node.id,
      style: {
        x: node.x,
        y: node.y,
        size: 20,
        fill: isFinalWithTimeout ? timeoutColors.fill : semanticTypeColors[node.data.semantic_type]?.fill || '#888',
        stroke: isFinalWithTimeout ? timeoutColors.stroke : semanticTypeColors[node.data.semantic_type]?.stroke || '#666',
        lineWidth: 2,
        cursor: 'pointer' as const
      },
      data: {
        label: node.label,
        content: node.data.content,
        semantic_type: node.data.semantic_type,
        state_id: node.data.state_id
      }
    };
  });
}

function createEdgesFromData(edges: LatentSpaceEdge[], edgeColor: string) {
  // Build a set of edge pairs to detect bidirectional edges
  const edgePairs = new Set<string>();
  edges.forEach((edge) => {
    edgePairs.add(`${edge.source}->${edge.target}`);
  });

  // Track which edges we've already curved (to curve in opposite directions)
  const curvedEdges = new Set<string>();

  return edges.map((edge) => {
    const reverseKey = `${edge.target}->${edge.source}`;
    const forwardKey = `${edge.source}->${edge.target}`;
    const hasBidirectional = edgePairs.has(reverseKey);

    // Determine curve offset for bidirectional edges
    let curveOffset = 0;
    if (hasBidirectional) {
      // Use a canonical key to ensure consistent curve directions
      const canonicalKey = [edge.source, edge.target].sort().join('<->');
      if (!curvedEdges.has(canonicalKey)) {
        curvedEdges.add(canonicalKey);
        curveOffset = 40; // First edge curves one way
      } else {
        curveOffset = -40; // Second edge curves the other way
      }
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      style: {
        stroke: edgeColor,
        lineWidth: 3,
        endArrow: true,
        endArrowSize: 10,
        endArrowFill: edgeColor,
        ...(curveOffset !== 0 && { curveOffset })
      },
      data: {
        label: edge.label,
        duration: edge.data.duration,
        entity_name: edge.data.entity_name
      }
    };
  });
}

const createTooltipPlugin = (colors: TooltipThemeColors) => ({
  type: 'tooltip',
  key: 'tooltip',
  getContent: (
    _event: unknown,
    items: Array<{
      id: string;
      data?: { content?: string; semantic_type?: string; state_id?: string };
    }>
  ) => {
    const item = items[0];
    if (!item?.data) return null;
    const { content, semantic_type, state_id } = item.data;
    if (!content) return null;

    const truncatedContent = content.length > 300 ? content.substring(0, 300) + '...' : content;

    return `
      <div style="max-width: 400px; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <div style="font-weight: 600; margin-bottom: 4px; color: ${colors.text}; font-size: 12px;">${state_id || 'Node'}</div>
        <div style="color: ${colors.textSecondary}; margin-bottom: 6px; font-size: 11px;">Type: ${semantic_type || 'N/A'}</div>
        <div style="color: ${colors.text}; font-size: 12px; line-height: 1.5; white-space: pre-wrap;">${truncatedContent}</div>
      </div>
    `;
  },
  style: {
    '.tooltip': {
      padding: '12px 16px',
      background: colors.background,
      color: colors.text,
      borderRadius: '8px',
      fontSize: '12px',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
      boxShadow: colors.shadow,
      maxWidth: '420px',
      zIndex: 10
    }
  }
});

export interface SessionLatentSpaceProps {
  data: SessionLatentSpaceData;
  title?: string;
  width?: number;
  height?: number;
  onNodeClick?: (nodeId: string) => void;
}

export const SessionLatentSpace = ({
  data,
  title = 'Session Trajectory in Latent Space',
  width = 800,
  height = 600,
  onNodeClick
}: SessionLatentSpaceProps) => {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);

  const toolbarBgColor = theme.palette.vars?.baseBackgroundMedium || theme.palette.background.paper;
  const toolbarBorderColor = theme.palette.vars?.baseBorderDefault || theme.palette.divider;
  const toolbarIconColor = theme.palette.vars?.baseTextDefault || theme.palette.text.primary;
  const toolbarHoverBgColor = theme.palette.vars?.baseBackgroundStrong || theme.palette.action.hover;

  const tooltipColors: TooltipThemeColors = useMemo(
    () => ({
      background: theme.palette.background.paper,
      text: theme.palette.text.primary,
      textSecondary: theme.palette.text.secondary,
      shadow: `0 2px 8px ${theme.palette.mode === 'dark' ? 'rgba(0, 0, 0, 0.45)' : 'rgba(0, 0, 0, 0.15)'}`
    }),
    [theme.palette.background.paper, theme.palette.text.primary, theme.palette.text.secondary, theme.palette.mode]
  );

  const semanticTypeColors = useMemo(() => getSemanticTypeColors(theme), [theme]);

  const edgeColor = useMemo(() => getEdgeColor(theme), [theme]);

  const timeoutColors = useMemo(() => getTimeoutColor(theme), [theme]);

  const isTimeout = data.metadata.isTimeout;

  const uniqueAgentLabels = useMemo(() => {
    return [...new Set(data.edges.map((edge) => edge.label))];
  }, [data.edges]);

  const initialStateContent = useMemo(() => {
    const initialNode = data.nodes.find((node) => node.data.semantic_type === 'initial');
    return initialNode?.data.content || '';
  }, [data.nodes]);

  useEffect(() => {
    if (!containerRef.current) return;

    const nodes = createNodesFromData(data.nodes, semanticTypeColors, isTimeout, timeoutColors);
    const effectiveEdgeColor = isTimeout ? timeoutColors.stroke : edgeColor;
    const edges = createEdgesFromData(data.edges, effectiveEdgeColor);

    const graph = new Graph({
      container: containerRef.current,
      width,
      height,
      autoFit: 'view',
      padding: 40,
      node: {
        type: 'circle',
        style: {
          labelText: ''
        }
      },
      edge: {
        type: 'quadratic',
        style: {
          endArrow: true,
          labelText: (d: { data?: { label?: string } }) => (showEdgeLabels ? d.data?.label || '' : ''),
          labelFontSize: 18,
          labelFill: theme.palette.text.secondary,
          labelBackground: false,
          labelOffsetY: -18
        }
      },
      plugins: [
        createTooltipPlugin(tooltipColors),
        {
          type: 'toolbar',
          position: 'top-right',
          className: 'session-latent-space-toolbar',
          style: {
            backgroundColor: toolbarBgColor,
            border: `1px solid ${toolbarBorderColor}`,
            borderRadius: '8px',
            padding: '4px',
            opacity: '1'
          },
          onClick: (item: string) => {
            if (item === 'zoom-in') {
              graph.zoomBy(1.2, { duration: 200 });
            } else if (item === 'zoom-out') {
              graph.zoomBy(0.8, { duration: 200 });
            } else if (item === 'auto-fit') {
              graph.fitView({}, { duration: 200 });
            }
          },
          getItems: () => [
            { id: 'zoom-in', value: 'zoom-in', title: 'Zoom In' },
            { id: 'zoom-out', value: 'zoom-out', title: 'Zoom Out' },
            { id: 'auto-fit', value: 'auto-fit', title: 'Fit to View' }
          ]
        }
      ],
      behaviors: ['drag-canvas', 'zoom-canvas']
    });

    graph.setData({
      nodes,
      edges
    });

    graph.render();

    graph.on('node:click', (event: any) => {
      const nodeId = event.target?.id;
      if (nodeId && onNodeClick) {
        onNodeClick(nodeId);
      }
    });

    graphRef.current = graph;

    return () => {
      try {
        if (graphRef.current) {
          graphRef.current.destroy();
          graphRef.current = null;
        }
      } catch {
        // G6 may throw during cleanup - safe to ignore
      }
    };
  }, [
    data,
    tooltipColors,
    width,
    height,
    onNodeClick,
    theme.palette,
    toolbarBgColor,
    toolbarBorderColor,
    semanticTypeColors,
    edgeColor,
    showEdgeLabels,
    isTimeout,
    timeoutColors
  ]);

  return (
    <>
      <style>
        {`
          .session-latent-space-toolbar .g6-toolbar-item svg {
            fill: ${toolbarIconColor};
          }
          .session-latent-space-toolbar .g6-toolbar-item:hover {
            background-color: ${toolbarHoverBgColor};
            border-radius: 4px;
          }
          .g6-tooltip {
            z-index: 10 !important;
          }
        `}
      </style>

      <Stack direction={'column'} gap={'8px'}>
        <Typography variant="h6">{title}</Typography>
        {initialStateContent && (
          <Typography variant="subtitle2" color="text.secondary">
            {initialStateContent}
          </Typography>
        )}

        <Stack direction={'row'} gap={'16px'} flexWrap={'wrap'}>
          <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              State Types:
            </Typography>
            {Object.entries(semanticTypeColors).map(([type, colors]) => (
              <Stack key={type} direction={'row'} gap={'4px'} alignItems={'center'}>
                <Box
                  sx={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    backgroundColor: colors.fill,
                    border: `2px solid ${colors.stroke}`
                  }}
                />
                <Typography variant="caption">{type}</Typography>
              </Stack>
            ))}
          </Stack>

          <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              Agents:
            </Typography>
            {uniqueAgentLabels.map((label) => (
              <Stack key={label} direction={'row'} gap={'4px'} alignItems={'center'}>
                <Box
                  sx={{
                    width: 16,
                    height: 3,
                    backgroundColor: edgeColor,
                    borderRadius: 1
                  }}
                />
                <Typography variant="caption">{label}</Typography>
              </Stack>
            ))}
            <FormControlLabel
              control={<Switch checked={showEdgeLabels} onChange={(e) => setShowEdgeLabels(e.target.checked)} size="small" />}
              label={
                <Typography variant="caption" sx={{ marginLeft: '4px' }}>
                  Show Agents
                </Typography>
              }
              sx={{
                padding: '4px',
                marginLeft: '0px',
                borderRadius: 1
              }}
            />
          </Stack>
        </Stack>

        <Box
          ref={containerRef}
          sx={{
            width,
            height,
            //  border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1
            //  backgroundColor: theme.palette.vars?.baseBackgroundWeak || theme.palette.background.default
          }}
        />
      </Stack>
    </>
  );
};
