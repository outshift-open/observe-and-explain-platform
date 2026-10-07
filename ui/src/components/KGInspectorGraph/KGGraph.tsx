/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Graph, NodeData, EdgeData } from '@antv/g6';
import { Box, useTheme, Stack } from '@mui/material';
import { KGDrawer } from './KGDrawer';
import { KGGraphProps } from './types';
import { transformDataToG6Graph, getStatusColor } from '@/utils';
import { EmptyState, Spinner } from '@open-ui-kit/core';
import { GLOBAL_BORDER_COLOR } from '@/common/styles';

// Default layout config
const DEFAULT_LAYOUT = {
  type: 'antv-dagre',
  nodeSize: [220, 40] as [number, number],
  nodesep: 60,
  ranksep: 60,
  controlPoints: true
};

export const KGGraph = ({
  data,
  layout,
  nodeProps,
  edgeProps,
  waitForLayout = false
}: KGGraphProps) => {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const [isLayoutReady, setIsLayoutReady] = useState(!waitForLayout);
  const [selectedElement, setSelectedElement] = useState<{
    type: 'node' | 'edge';
    data: any;
    title: string;
  } | null>(null);

  const isDark = theme.palette.mode === 'dark';

  const graphData = useMemo(() => transformDataToG6Graph(data), [data]);
  const isEmpty = (graphData.nodes?.length ?? 0) === 0;

  // Toolbar theme colors
  const toolbarBgColor =
    theme.palette.vars?.baseBackgroundMedium || theme.palette.background.paper;
  const toolbarBorderColor =
    theme.palette.vars?.baseBorderDefault || theme.palette.divider;
  const toolbarIconColor =
    theme.palette.vars?.baseTextDefault || theme.palette.text.primary;
  const toolbarHoverBgColor =
    theme.palette.vars?.baseBackgroundStrong || theme.palette.action.hover;

  // Create graph instance
  const initGraph = useCallback(() => {
    if (!containerRef.current || isEmpty) return;

    // Reset layout ready state when reinitializing
    if (waitForLayout) {
      setIsLayoutReady(false);
    }

    // Destroy existing graph
    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Create G6 graph instance - G6 v5 has built-in layouts and behaviors
    const graph = new Graph({
      container,
      width,
      height,
      autoFit: 'view',
      padding: [10, 10, 10, 10],
      data: {
        nodes: (graphData.nodes || []).map((node: NodeData) => ({
          id: node.id,
          data: {
            ...node.data,
            // Store original data for click handler
            _originalData: node.data
          }
        })),
        edges: (graphData.edges || []).map((edge: EdgeData) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          data: {
            ...edge.data,
            // Store original data for click handler
            _originalData: edge.data
          }
        }))
      },
      layout: layout || DEFAULT_LAYOUT,
      // Use ProcessParallelEdges transform to handle parallel edges and self-loops
      transforms: [
        {
          type: 'process-parallel-edges',
          mode: 'bundle',
          distance: 40
        }
      ],
      node: {
        type: nodeProps?.type || 'rect',
        style: {
          size: [220, 60] as [number, number],
          radius: 8,
          fill: (d: any) => {
            // Use disabled background for inactive nodes
            if (d.data?.data?.active === false) {
              return (
                theme.palette.vars?.controlBackgroundDisabled ||
                theme.palette.action.disabledBackground
              );
            }
            return (
              theme.palette.vars?.baseBackgroundMedium ||
              theme.palette.background.paper
            );
          },
          stroke: (d: any) => {
            // Use disabled border for inactive nodes
            if (d.data?.data?.active === false) {
              return (
                theme.palette.vars?.controlBorderDisabled ||
                theme.palette.action.disabled
              );
            }
            return getStatusColor(d.data?.status, isDark);
          },
          lineWidth: 2,
          fillOpacity: (d: any) => (d.data?.data?.active === false ? 0.6 : 1),
          shadowColor: isDark ? 'rgba(0, 0, 0, 0.3)' : 'rgba(0, 0, 0, 0.15)',
          shadowBlur: (d: any) => (d.data?.data?.active === false ? 0 : 8),
          shadowOffsetX: 0,
          shadowOffsetY: (d: any) => (d.data?.data?.active === false ? 0 : 2),
          cursor: 'pointer',
          labelText: (d: any) => d.data?.label || d.data?.id || 'Unknown',
          labelFill: (d: any) => {
            // Use disabled text color for inactive nodes
            if (d.data?.data?.active === false) {
              return (
                theme.palette.vars?.baseTextDisabled ||
                theme.palette.text.disabled
              );
            }
            return (
              theme.palette.vars?.baseTextDefault || theme.palette.text.primary
            );
          },
          labelFontSize: 18,
          labelFontWeight: 600,
          labelWordWrap: false,
          labelPlacement: 'center',
          labelPadding: [0, 16],
          ...nodeProps?.style
        },
        state: {
          active: {
            shadowColor:
              theme.palette.vars?.interactivePrimaryWeakActive ||
              theme.palette.primary.light,
            shadowBlur: 16,
            lineWidth: 3
          },
          ...nodeProps?.state
        }
      },
      edge: {
        type: edgeProps?.type || 'quadratic',
        style: {
          stroke:
            theme.palette.vars?.interactivePrimaryDefaultDefault ||
            theme.palette.primary.main,
          lineWidth: 2,
          endArrow: true,
          endArrowFill:
            theme.palette.vars?.interactivePrimaryDefaultDefault ||
            theme.palette.primary.main,
          endArrowSize: 8,
          cursor: 'pointer',
          labelText: (d: any) => d.data?.label || '',
          labelFill:
            theme.palette.vars?.baseTextWeak || theme.palette.text.secondary,
          labelFontSize: 11,
          labelFontWeight: 500,
          labelBackground: true,
          labelBackgroundFill:
            theme.palette.vars?.baseBackgroundMedium ||
            theme.palette.background.paper,
          labelBackgroundFillOpacity: 1,
          labelBackgroundRadius: 4,
          labelBackgroundStroke:
            theme.palette.vars?.baseBorderDefault || theme.palette.divider,
          labelBackgroundLineWidth: 1,
          labelPadding: [4, 12],
          labelOffsetY: -12,
          labelAutoRotate: false,
          ...edgeProps?.style
        },
        state: {
          active: {
            lineWidth: 3,
            stroke:
              theme.palette.vars?.excellentBorderActive ||
              theme.palette.secondary.main,
            endArrowFill:
              theme.palette.vars?.excellentBorderActive ||
              theme.palette.secondary.main
          },
          ...edgeProps?.state
        }
      },
      behaviors: [
        'zoom-canvas',
        'drag-canvas',
        'drag-element',
        'click-select',
        'hover-activate'
      ],
      plugins: [
        {
          type: 'toolbar',
          position: 'top-right',
          className: 'kg-graph-toolbar',
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
      ]
    });

    // Handle node click
    graph.on('node:click', (evt: any) => {
      const nodeId = evt.target?.id;
      if (nodeId) {
        const nodeData = graph.getNodeData(nodeId);
        if (nodeData) {
          setSelectedElement({
            type: 'node',
            data: nodeData.data?._originalData || nodeData.data,
            title: `Node: ${nodeData.data?.label || nodeId}`
          });
        }
      }
    });

    // Handle edge click
    graph.on('edge:click', (evt: any) => {
      const edgeId = evt.target?.id;
      if (edgeId) {
        const edgeData = graph.getEdgeData(edgeId);
        if (edgeData) {
          setSelectedElement({
            type: 'edge',
            data: edgeData.data?._originalData || edgeData.data,
            title: `Edge: ${edgeData.source} → ${edgeData.target}`
          });
        }
      }
    });

    // Handle canvas click to deselect
    graph.on('canvas:click', () => {
      setSelectedElement(null);
    });

    graphRef.current = graph;

    // Listen for layout completion if waitForLayout is enabled
    if (waitForLayout) {
      graph.once('afterlayout', () => {
        setIsLayoutReady(true);
      });
    }

    // Render the graph and fit to view - required in G6 v5
    graph.render().then(() => {
      requestAnimationFrame(() => {
        graph.fitView({}, { duration: 300 });
      });
    });
  }, [
    graphData,
    isEmpty,
    isDark,
    theme,
    layout,
    nodeProps,
    edgeProps,
    waitForLayout,
    toolbarBgColor,
    toolbarBorderColor,
    toolbarHoverBgColor
  ]);

  // Initialize graph when data changes
  useEffect(() => {
    initGraph();

    return () => {
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [initGraph]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (graphRef.current && containerRef.current) {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        graphRef.current.setSize(width, height);
        // Re-fit view after resize
        graphRef.current.fitView({}, { duration: 200 });
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleDrawerClose = useCallback(() => {
    setSelectedElement(null);
    if (graphRef.current) {
      const selectedNodes = graphRef.current.getElementDataByState(
        'node',
        'selected'
      );
      const selectedEdges = graphRef.current.getElementDataByState(
        'edge',
        'selected'
      );

      selectedNodes.forEach((node: any) => {
        graphRef.current?.setElementState(node.id, []);
      });
      selectedEdges.forEach((edge: any) => {
        graphRef.current?.setElementState(edge.id, []);
      });
    }
  }, []);

  if (isEmpty) {
    return <EmptyState title="No data found" description="" />;
  }

  return (
    <>
      {/* Custom styles for G6 toolbar to match Spark theme */}
      <style>
        {`
          .kg-graph-toolbar .g6-toolbar-item svg {
            fill: ${toolbarIconColor};
          }
          .kg-graph-toolbar .g6-toolbar-item:hover {
            background-color: ${toolbarHoverBgColor};
            border-radius: 4px;
          }
        `}
      </style>

      <Box
        sx={{
          position: 'relative',
          width: '100%',
          height: '100%',
          minHeight: 400
        }}
      >
        {/* Loading overlay - shown while layout is computing */}
        {!isLayoutReady && (
          <Stack
            alignItems={'center'}
            justifyContent={'center'}
            sx={{
              width: '100%',
              height: '100%',
              minHeight: '100px',
              // backgroundColor: theme.palette.vars?.baseBackgroundWeak || theme.palette.background.default,
              borderRadius: '8px'
            }}
          >
            <Spinner />
          </Stack>
        )}

        <Box
          ref={containerRef}
          sx={{
            width: '100%',
            height: '100%',
            overflow: 'hidden',
            borderRadius: '8px',
            border: `1px solid ${GLOBAL_BORDER_COLOR}`,
            // backgroundColor: theme.palette.vars?.baseBackgroundWeak || theme.palette.background.default,
            // Hide graph content until layout is ready (but keep container for G6 to render into)
            visibility: isLayoutReady ? 'visible' : 'hidden'
          }}
        />
      </Box>

      {selectedElement && (
        <KGDrawer
          open={true}
          onClose={handleDrawerClose}
          title={selectedElement.title}
          data={selectedElement.data}
        />
      )}
    </>
  );
};
