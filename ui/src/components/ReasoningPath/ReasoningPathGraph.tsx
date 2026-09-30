/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  NodeTypes,
  applyNodeChanges,
  type Node,
  type NodeChange
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Box,
  Chip,
  Slider,
  Stack,
  Tooltip,
  Typography,
  useTheme
} from '@mui/material';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { Spinner } from '@open-ui-kit/core';
import { ReasoningPathNode } from './ReasoningPathNode';
import { useReasoningPathGraph } from './useReasoningPath';
import { getStatusColor } from './ReasoningPath.utils';

const nodeTypes: NodeTypes = {
  reasoningNode: ReasoningPathNode
};

interface ReasoningPathGraphProps {
  sessionId: string;
}

export const ReasoningPathGraph = ({ sessionId }: ReasoningPathGraphProps) => {
  const theme = useTheme();
  const {
    nodes: computedNodes,
    edges,
    model,
    trajectoryScore,
    evaluationRounds,
    sliderPosition,
    setSliderPosition,
    isLoading,
    error
  } = useReasoningPathGraph(sessionId);

  const [dragOffsets, setDragOffsets] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());

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

  const scoreColor = useMemo(() => {
    if (trajectoryScore === null) return '#9e9e9e';
    return trajectoryScore >= 1
      ? getStatusColor('satisfied')
      : getStatusColor('violated');
  }, [trajectoryScore]);

  const sliderMarks = useMemo(() => {
    return evaluationRounds.map((round) => ({
      value: round,
      label: String(round)
    }));
  }, [evaluationRounds]);

  const maxRound =
    evaluationRounds.length > 0
      ? evaluationRounds[evaluationRounds.length - 1]
      : 0;

  const handleSliderChange = useCallback(
    (_: unknown, value: number | number[]) => {
      const v = Array.isArray(value) ? value[0] : value;
      setSliderPosition(v);
    },
    [setSliderPosition]
  );

  if (isLoading) {
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
          Failed to load reasoning path: {error.message}
        </Typography>
      </Stack>
    );
  }

  if (computedNodes.length === 0) {
    return (
      <Stack
        justifyContent="center"
        alignItems="center"
        sx={{ width: '100%', height: '100%', minHeight: 400 }}
      >
        <Typography color="text.secondary">
          No reasoning path data available for this session.
        </Typography>
      </Stack>
    );
  }

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
          Reasoning Path
        </Typography>

        {model && (
          <Stack direction="row" alignItems="center" gap={1}>
            <Typography variant="caption" color="text.secondary">
              {model.modelName}
            </Typography>
            <Chip
              label={`v${model.version}`}
              size="small"
              sx={{ height: 20, fontSize: '0.65rem' }}
            />
          </Stack>
        )}

        {trajectoryScore !== null && (
          <Chip
            label={`Outcome: ${trajectoryScore >= 1 ? 'Passed' : 'Failed'}`}
            size="small"
            sx={{
              ml: 'auto',
              backgroundColor: scoreColor,
              color: '#fff',
              fontWeight: 600,
              fontSize: '0.7rem',
              height: 22
            }}
          />
        )}
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

      {/* Timeline slider */}
      {evaluationRounds.length > 1 && (
        <Stack
          direction="row"
          alignItems="flex-start"
          gap={2}
          sx={{
            px: 3,
            py: 1.5,
            borderTop: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper
          }}
        >
          <Stack direction="row" alignItems="center" gap={'2px'}>
            <Typography
              variant="caption"
              sx={{
                fontWeight: 600,
                whiteSpace: 'nowrap',
                minWidth: 60,
                marginTop: '6px'
              }}
            >
              Evaluation Round
            </Typography>
            <Tooltip
              title="Move the slider to step through evaluation rounds. At each round, the symbolic extraction pipeline walks through the session's execution trace and may update some variables' assessments. Not all variables change at every round — an alignment variable may still reflect a previous assessment while its dependencies have already been updated, or vice versa. Nodes with a solid blue border were updated at this round."
              placement="top"
            >
              <InfoOutlineIcon
                sx={{
                  width: '12px',
                  height: '12px',
                  cursor: 'pointer'
                }}
              />
            </Tooltip>
          </Stack>
          <Slider
            value={sliderPosition ?? maxRound}
            min={evaluationRounds[0]}
            max={maxRound}
            step={null}
            marks={sliderMarks}
            onChange={handleSliderChange}
            valueLabelDisplay="auto"
            size="small"
            sx={{ flex: 1 }}
          />
        </Stack>
      )}
    </Stack>
  );
};
