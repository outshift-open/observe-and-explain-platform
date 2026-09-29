/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { Box, Chip, Stack, Tooltip, Typography, useTheme } from '@mui/material';
import { format } from 'date-fns';
import type { ReasoningNode, ValueStatus } from './ReasoningPath.types';
import { getStatusColor } from './ReasoningPath.utils';

type ReasoningNodeData = ReasoningNode & {
  status: ValueStatus;
  isFresh: boolean;
};

function getValueLabel(
  status: ValueStatus,
  value: ReasoningNode['value']
): string {
  switch (status) {
    case 'satisfied':
      return 'Satisfied';
    case 'violated':
      return 'Violated';
    case 'not_applicable':
      return 'N/A';
    case 'no_value':
      return value !== null && value !== undefined ? String(value) : '—';
  }
}

function getExecutionTypeLabel(labels: string[] | null): string | null {
  if (!labels || labels.length === 0) return null;
  for (const label of labels) {
    if (label.toLowerCase().includes('tool')) return 'ToolCall';
    if (label.toLowerCase().includes('processing')) return 'ProcessingCall';
    if (label.toLowerCase().includes('llm')) return 'LLMCall';
    if (label.toLowerCase().includes('agent')) return 'AgentCall';
  }
  return labels[0];
}

const EXECUTION_TYPE_DESCRIPTIONS: Record<string, string> = {
  ToolCall:
    'External API/DB call made by the agent (retrieval, web search, etc.)',
  ProcessingCall:
    'Internal computation within the agent (reasoning, formatting, routing)',
  LLMCall: 'Language model inference call (prompt → completion)'
};

function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null || durationMs === undefined) return null;
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

function formatTimestamp(ts: number | null): string | null {
  if (ts === null || ts === undefined) return null;
  try {
    const date = new Date(Number(ts) * 1000);
    return format(date, 'MMM d, yyyy HH:mm:ss');
  } catch {
    return null;
  }
}

const TIER_CONFIG: Record<
  string,
  { label: string; color: string; description: string }
> = {
  entity: {
    label: 'Entity',
    color: '#1976d2',
    description: 'Observed fact extracted directly from the trajectory'
  },
  process: {
    label: 'Process',
    color: '#7b1fa2',
    description:
      "Boolean predicate about the agent's behavior or intermediate result"
  },
  alignment: {
    label: 'Alignment',
    color: '#e65100',
    description:
      'Semantic judgment on whether a requirement or expectation was met'
  }
};

export const ReasoningPathNode = memo(({ data }: NodeProps) => {
  const theme = useTheme();
  const nodeData = data as unknown as ReasoningNodeData;
  const statusColor = getStatusColor(nodeData.status);
  const valueLabel = getValueLabel(nodeData.status, nodeData.value);
  const executionType = getExecutionTypeLabel(nodeData.executionLabels);
  const callName =
    nodeData.toolName ||
    nodeData.processingName ||
    nodeData.llmName ||
    nodeData.modelName ||
    nodeData.entityName;
  const duration = formatDuration(nodeData.executionDuration);
  const timestamp = formatTimestamp(nodeData.executionTimestamp);
  const hasIoData = !!(
    nodeData.inputParams ||
    nodeData.outputContent ||
    nodeData.toolOutput
  );
  const tierInfo = TIER_CONFIG[nodeData.tier] ?? {
    label: nodeData.tier,
    color: '#757575'
  };

  const ioTooltipContent = [
    nodeData.inputParams && `Input: ${nodeData.inputParams}`,
    nodeData.outputContent &&
      `Output: ${nodeData.outputContent.length > 300 ? nodeData.outputContent.slice(0, 300) + '…' : nodeData.outputContent}`,
    nodeData.toolOutput &&
      `Tool Output: ${nodeData.toolOutput.length > 300 ? nodeData.toolOutput.slice(0, 300) + '…' : nodeData.toolOutput}`
  ]
    .filter(Boolean)
    .join('\n\n');

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#555', width: 6, height: 6 }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#555', width: 6, height: 6 }}
      />

      <Box
        sx={{
          width: 260,
          borderRadius: '8px',
          border: nodeData.isFresh
            ? `2px solid ${theme.palette.primary.main}`
            : `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
          boxShadow: nodeData.isFresh ? theme.shadows[6] : theme.shadows[2],
          overflow: 'hidden',
          opacity:
            nodeData.value === null && nodeData.status === 'no_value' ? 0.4 : 1,
          transition: 'opacity 0.2s, border-color 0.2s, box-shadow 0.2s'
        }}
      >
        {/* Header */}
        <Box
          sx={{
            px: 1.5,
            py: 1,
            borderBottom: `1px solid ${theme.palette.divider}`,
            backgroundColor:
              theme.palette.mode === 'dark'
                ? 'rgba(255,255,255,0.03)'
                : 'rgba(0,0,0,0.02)'
          }}
        >
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            gap={0.5}
          >
            <Tooltip
              title={nodeData.description || nodeData.name}
              placement="top"
            >
              <Typography
                variant="subtitle2"
                noWrap
                sx={{
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  flex: 1,
                  minWidth: 0
                }}
              >
                {nodeData.name}
              </Typography>
            </Tooltip>
            <Tooltip title={tierInfo.description} placement="top">
              <Chip
                label={tierInfo.label}
                size="small"
                sx={{
                  backgroundColor: tierInfo.color,
                  color: '#fff',
                  fontSize: '0.55rem',
                  fontWeight: 600,
                  height: 16,
                  flexShrink: 0,
                  '& .MuiChip-label': { px: 0.5 }
                }}
              />
            </Tooltip>
          </Stack>
        </Box>

        {/* Body */}
        <Stack sx={{ px: 1.5, py: 1, gap: 0.5 }}>
          <Tooltip title={String(nodeData.value ?? '')} placement="top">
            <Chip
              label={valueLabel}
              size="small"
              sx={{
                alignSelf: 'flex-start',
                backgroundColor: statusColor,
                color: '#fff',
                fontWeight: 600,
                fontSize: '0.65rem',
                height: 20
              }}
            />
          </Tooltip>

          {nodeData.reason && (
            <Tooltip title={nodeData.reason} placement="bottom">
              <Typography
                variant="caption"
                sx={{
                  color: theme.palette.text.secondary,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  fontSize: '0.65rem',
                  lineHeight: 1.3
                }}
              >
                {nodeData.reason}
              </Typography>
            </Tooltip>
          )}

          {/* Execution metadata */}
          {callName && (
            <Tooltip title={callName} placement="bottom">
              <Typography
                variant="caption"
                noWrap
                sx={{
                  color: theme.palette.text.primary,
                  fontSize: '0.65rem',
                  fontWeight: 500,
                  mt: 0.25
                }}
              >
                {callName}
              </Typography>
            </Tooltip>
          )}

          {hasIoData && (
            <Tooltip
              title={
                <pre
                  style={{
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                    fontSize: '0.7rem',
                    maxWidth: 400
                  }}
                >
                  {ioTooltipContent}
                </pre>
              }
              placement="bottom"
            >
              <Typography
                variant="caption"
                sx={{
                  color: theme.palette.info.main,
                  fontSize: '0.6rem',
                  cursor: 'pointer',
                  textDecoration: 'underline dotted'
                }}
              >
                View I/O
              </Typography>
            </Tooltip>
          )}
        </Stack>

        {/* Footer */}
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{
            px: 1.5,
            py: 0.5,
            borderTop: `1px solid ${theme.palette.divider}`,
            backgroundColor:
              theme.palette.mode === 'dark'
                ? 'rgba(255,255,255,0.02)'
                : 'rgba(0,0,0,0.01)',
            flexWrap: 'wrap',
            gap: 0.5
          }}
        >
          <Stack direction="row" alignItems="center" gap={0.5}>
            {nodeData.trajectoryIndex !== null && (
              <Typography
                variant="caption"
                sx={{ fontSize: '0.6rem', color: theme.palette.text.secondary }}
              >
                Step {nodeData.trajectoryIndex}
              </Typography>
            )}
            {timestamp && (
              <Typography
                variant="caption"
                sx={{ fontSize: '0.6rem', color: theme.palette.text.secondary }}
              >
                {timestamp}
              </Typography>
            )}
          </Stack>

          <Stack direction="row" alignItems="center" gap={0.5}>
            {duration && (
              <Chip
                label={duration}
                size="small"
                sx={{
                  fontSize: '0.6rem',
                  height: 16,
                  backgroundColor: theme.palette.action.hover,
                  '& .MuiChip-label': { px: 0.5 }
                }}
              />
            )}
            {executionType && (
              <Tooltip
                title={
                  EXECUTION_TYPE_DESCRIPTIONS[executionType] ?? executionType
                }
                placement="top"
              >
                <Chip
                  label={executionType}
                  size="small"
                  variant="outlined"
                  sx={{
                    fontSize: '0.6rem',
                    height: 18,
                    '& .MuiChip-label': { px: 0.75 }
                  }}
                />
              </Tooltip>
            )}
          </Stack>
        </Stack>
      </Box>
    </>
  );
});

ReasoningPathNode.displayName = 'ReasoningPathNode';
