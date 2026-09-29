/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  NodeTypes,
  type Node,
  type NodeChange
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Chip, Stack, Typography, useTheme } from '@mui/material';
import { Spinner } from '@open-ui-kit/core';
import { useApplicationReasoningPath } from '@/api/oxpApi';
import type { AppReasoningNode } from '@/types/oxp.type';
import { ApplicationReasoningPathNode } from './ApplicationReasoningPathNode';
import {
  computeLayout,
  computeEdges,
  NODE_WIDTH,
  NODE_HEIGHT
} from './ApplicationReasoningPath.utils';

const nodeTypes: NodeTypes = {
  appReasoningNode: ApplicationReasoningPathNode
};

interface ApplicationReasoningPathGraphProps {
  masName: string;
}

export const ApplicationReasoningPathGraph = ({
  masName
}: ApplicationReasoningPathGraphProps) => {
  const theme = useTheme();
  const { data, isLoading, error } = useApplicationReasoningPath(masName);

  const [layoutedPositions, setLayoutedPositions] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());
  const [layoutReady, setLayoutReady] = useState(false);
  const [dragOffsets, setDragOffsets] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());

  useEffect(() => {
    if (!data) {
      setLayoutedPositions(new Map());
      setLayoutReady(false);
      return;
    }
    let cancelled = false;
    computeLayout(data.nodes, data.edges).then((positions) => {
      if (!cancelled) {
        setLayoutedPositions(positions);
        setLayoutReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [data]);

  const computedNodes: Node[] = useMemo(() => {
    if (!data || !layoutReady) return [];
    return data.nodes.map((apiNode: AppReasoningNode) => {
      const pos = layoutedPositions.get(apiNode.id) ?? { x: 0, y: 0 };
      return {
        id: apiNode.id,
        type: 'appReasoningNode',
        position: pos,
        data: apiNode as unknown as Record<string, unknown>,
        width: NODE_WIDTH,
        height: NODE_HEIGHT
      };
    });
  }, [data, layoutReady, layoutedPositions]);

  const edges = useMemo(() => {
    if (!data) return [];
    return computeEdges(data.edges, data.nodes);
  }, [data]);

  const nodes = useMemo(() => {
    if (dragOffsets.size === 0) return computedNodes;
    return computedNodes.map((node) => {
      const offset = dragOffsets.get(node.id);
      if (!offset) return node;
      return { ...node, position: offset };
    });
  }, [computedNodes, dragOffsets]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    const positionChanges = changes.filter(
      (c) => c.type === 'position' && 'position' in c && c.position
    );
    if (positionChanges.length > 0) {
      setDragOffsets((prev) => {
        const next = new Map(prev);
        for (const change of positionChanges) {
          if (
            change.type === 'position' &&
            'position' in change &&
            change.position
          ) {
            next.set(change.id, change.position);
          }
        }
        return next;
      });
    }
  }, []);

  if (
    isLoading ||
    (computedNodes.length === 0 && !error && data === undefined)
  ) {
    return (
      <Stack
        justifyContent="center"
        alignItems="center"
        sx={{ width: '100%', height: '100%', minHeight: 400 }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (error) {
    return (
      <Stack
        justifyContent="center"
        alignItems="center"
        sx={{ width: '100%', height: '100%', minHeight: 400 }}
      >
        <Typography color="error">
          Failed to load application reasoning path: {(error as Error).message}
        </Typography>
      </Stack>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <Stack
        justifyContent="center"
        alignItems="center"
        sx={{ width: '100%', height: '100%', minHeight: 400 }}
      >
        <Typography color="text.secondary">
          No reasoning path data available for this application.
        </Typography>
      </Stack>
    );
  }

  const passRate =
    data.totalSessions > 0
      ? ((data.passedSessions / data.totalSessions) * 100).toFixed(1)
      : '0';

  return (
    <Stack sx={{ width: '100%', height: '100%', minHeight: 500 }}>
      {/* Header bar */}
      <Stack
        direction="row"
        alignItems="center"
        gap={2}
        sx={{
          px: 2,
          py: 1,
          borderBottom: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Application Reasoning Path
        </Typography>

        {data.model && (
          <Stack direction="row" alignItems="center" gap={1}>
            <Typography variant="caption" color="text.secondary">
              {data.model.modelName}
            </Typography>
            <Chip
              label={`v${data.model.version}`}
              size="small"
              sx={{ height: 20, fontSize: '0.65rem' }}
            />
          </Stack>
        )}

        <Stack direction="row" alignItems="center" gap={1} sx={{ ml: 'auto' }}>
          <Chip
            label={`${data.totalSessions} sessions`}
            size="small"
            sx={{ fontSize: '0.65rem', height: 22 }}
          />
          <Chip
            label={`${data.passedSessions} passed`}
            size="small"
            sx={{
              backgroundColor: '#4caf50',
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.65rem',
              height: 22
            }}
          />
          <Chip
            label={`${data.failedSessions} failed`}
            size="small"
            sx={{
              backgroundColor: '#f44336',
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.65rem',
              height: 22
            }}
          />
          <Chip
            label={`${passRate}% pass rate`}
            size="small"
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: '0.65rem', height: 22 }}
          />
        </Stack>
      </Stack>

      {/* Graph */}
      <Box sx={{ flex: 1, minHeight: 500 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          deleteKeyCode={null}
          proOptions={{ hideAttribution: true }}
          className={theme.palette.mode === 'dark' ? 'dark' : undefined}
        >
          <Background
            variant={BackgroundVariant.Dots}
            bgColor={
              theme.palette.mode === 'dark'
                ? theme.palette.background.default
                : '#fafafa'
            }
          />
          <MiniMap
            nodeStrokeWidth={3}
            pannable
            zoomable
            style={{
              backgroundColor:
                theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5'
            }}
          />
          <Controls
            position="top-right"
            showInteractive={false}
            style={{
              ['--xy-controls-button-background-color' as string]:
                theme.palette.mode === 'dark' ? '#2d2d2d' : '#fff',
              ['--xy-controls-button-background-color-hover' as string]:
                theme.palette.mode === 'dark' ? '#3d3d3d' : '#f0f0f0',
              ['--xy-controls-button-color' as string]:
                theme.palette.mode === 'dark' ? '#fff' : '#333',
              ['--xy-controls-button-border-color' as string]:
                theme.palette.mode === 'dark' ? '#555' : '#ddd',
              ['--xy-controls-box-shadow' as string]: 'none'
            }}
          />
        </ReactFlow>
      </Box>
    </Stack>
  );
};
