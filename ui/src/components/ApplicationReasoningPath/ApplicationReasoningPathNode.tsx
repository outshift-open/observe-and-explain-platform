/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { Box, Chip, Stack, Tooltip, Typography, useTheme } from '@mui/material';
import type { AppReasoningNode } from '@/types/oxp.type';
import { getDistributionColor, isHighCardinality } from './ApplicationReasoningPath.utils';

const TIER_CONFIG: Record<string, { label: string; color: string; description: string }> = {
  entity: {
    label: 'Entity',
    color: '#1976d2',
    description: 'Observed fact extracted directly from the trajectory'
  },
  process: {
    label: 'Process',
    color: '#7b1fa2',
    description: "Boolean predicate about the agent's behavior or intermediate result"
  },
  alignment: {
    label: 'Alignment',
    color: '#e65100',
    description: 'Semantic judgment on whether a requirement or expectation was met'
  }
};

interface DistributionBarProps {
  distribution: Record<string, number>;
  total: number;
}

const DistributionBar = ({ distribution, total }: DistributionBarProps) => {
  if (total === 0) return null;

  // Normalize keys to lowercase and merge counts for case-insensitive grouping
  const merged: Record<string, number> = {};
  for (const [key, count] of Object.entries(distribution)) {
    const lower = key.toLowerCase();
    merged[lower] = (merged[lower] ?? 0) + count;
  }
  const sorted = Object.entries(merged).sort(([, a], [, b]) => b - a);

  return (
    <Stack gap={0.25} sx={{ width: '100%' }}>
      <Box
        sx={{
          display: 'flex',
          width: '100%',
          height: 14,
          borderRadius: '4px',
          overflow: 'hidden'
        }}
      >
        {sorted.map(([value, count]) => (
          <Tooltip
            key={value}
            title={`${value}: ${count} (${((count / total) * 100).toFixed(1)}%)`}
            placement="top"
          >
            <Box
              sx={{
                width: `${(count / total) * 100}%`,
                backgroundColor: getDistributionColor(value),
                minWidth: count > 0 ? 2 : 0,
                transition: 'width 0.2s'
              }}
            />
          </Tooltip>
        ))}
      </Box>
      <Stack direction="row" flexWrap="wrap" gap={0.25}>
        {sorted.map(([value, count]) => (
          <Typography
            key={value}
            variant="caption"
            sx={{
              fontSize: '0.55rem',
              lineHeight: 1.2,
              color: getDistributionColor(value),
              fontWeight: 500
            }}
          >
            {value}: {count}
          </Typography>
        ))}
      </Stack>
    </Stack>
  );
};

export const ApplicationReasoningPathNode = memo(({ data }: NodeProps) => {
  const theme = useTheme();
  const nodeData = data as unknown as AppReasoningNode;
  const tierInfo = TIER_CONFIG[nodeData.tier] ?? { label: nodeData.tier, color: '#757575', description: '' };
  const highCardinality = isHighCardinality(nodeData);

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ background: '#555', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: '#555', width: 6, height: 6 }} />

      <Box
        sx={{
          width: 300,
          borderRadius: '8px',
          border: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
          boxShadow: theme.shadows[2],
          overflow: 'hidden'
        }}
      >
        {/* Header */}
        <Box
          sx={{
            px: 1.5,
            py: 1,
            borderBottom: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between" gap={0.5}>
            <Tooltip title={nodeData.description || nodeData.name} placement="top">
              <Typography
                variant="subtitle2"
                noWrap
                sx={{ fontWeight: 600, fontSize: '0.75rem', flex: 1, minWidth: 0 }}
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
        <Stack sx={{ px: 1.5, py: 1, gap: 0.75 }}>
          {highCardinality ? (
            <Stack gap={0.5}>
              <Typography
                variant="caption"
                sx={{ fontSize: '0.7rem', color: theme.palette.text.secondary }}
              >
                {nodeData.distinctValueCount} distinct values across {nodeData.sessionCount} sessions
              </Typography>
              <Tooltip
                title="This variable has too many distinct values to display as a distribution bar."
                placement="top"
              >
                <Chip
                  label="High cardinality"
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: '0.6rem', height: 18, alignSelf: 'flex-start' }}
                />
              </Tooltip>
            </Stack>
          ) : (
            <DistributionBar distribution={nodeData.distribution} total={nodeData.sessionCount} />
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
            backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)'
          }}
        >
          <Typography variant="caption" sx={{ fontSize: '0.6rem', color: theme.palette.text.secondary }}>
            {nodeData.sessionCount} sessions
          </Typography>
          {nodeData.avgLastTrajectoryIndex !== null && (
            <Tooltip title="Average last trajectory index across sessions" placement="top">
              <Typography variant="caption" sx={{ fontSize: '0.6rem', color: theme.palette.text.secondary }}>
                Avg step: {nodeData.avgLastTrajectoryIndex.toFixed(1)}
              </Typography>
            </Tooltip>
          )}
        </Stack>
      </Box>
    </>
  );
});

ApplicationReasoningPathNode.displayName = 'ApplicationReasoningPathNode';
