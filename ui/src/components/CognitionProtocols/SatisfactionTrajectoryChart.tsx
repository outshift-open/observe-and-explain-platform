/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, useTheme } from '@mui/material';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import { formatScore } from './primitives';

interface SatisfactionTrajectoryChartProps {
  // Worst-off agent score per round, round 0 being the seed.
  trajectory: { round: number; worstAgentScore: number | null }[];
  // Satisfaction floor threshold, drawn as a reference line when known.
  tau?: number | null;
}

export const SatisfactionTrajectoryChart = ({
  trajectory,
  tau
}: SatisfactionTrajectoryChartProps) => {
  const theme = useTheme();
  const axisTick = { fontSize: 11, fill: theme.palette.vars.baseTextWeak };
  const data = [...trajectory].sort((a, b) => a.round - b.round);

  return (
    <Box sx={{ width: '100%', height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 16, right: 24, bottom: 16 }}>
          <CartesianGrid
            strokeDasharray="4 4"
            stroke={theme.palette.vars.baseBorderWeak}
          />
          <XAxis
            dataKey="round"
            type="number"
            domain={['dataMin', 'dataMax']}
            allowDecimals={false}
            tick={axisTick}
            label={{
              value: 'Round (0 = seed)',
              position: 'insideBottom',
              offset: -8,
              style: { fontSize: 11 }
            }}
          />
          <YAxis
            domain={[0, 'auto']}
            tick={axisTick}
            tickFormatter={(value: number) => formatScore(value)}
            width={44}
          />
          <Tooltip
            formatter={(value) => [
              typeof value === 'number' ? formatScore(value) : 'N/A',
              'Worst-off agent'
            ]}
            labelFormatter={(round) =>
              Number(round) === 0 ? 'Round 0 (seed)' : `Round ${round}`
            }
          />
          {typeof tau === 'number' && (
            <ReferenceLine
              y={tau}
              ifOverflow="extendDomain"
              stroke={theme.palette.vars.negativeIconDefault}
              strokeDasharray="6 4"
              label={{
                value: `τ = ${formatScore(tau)}`,
                position: 'insideTopRight',
                fill: theme.palette.vars.negativeIconDefault,
                fontSize: 11
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="worstAgentScore"
            name="Worst-off agent"
            stroke={theme.palette.vars.interactivePrimaryDefaultDefault}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
};
