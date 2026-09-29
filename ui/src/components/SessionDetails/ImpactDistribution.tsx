/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography, useTheme } from '@mui/material';
import { useState, useMemo } from 'react';
import { ResponsiveContainer, ComposedChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Bar, Line } from 'recharts';
import { ImpactAssessment } from '@/types/oxp.type';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';

const FILTERED_AGENTS = new Set(['finalize_on_error', 'user']);

// Rotating palette for dynamic metrics
const METRIC_COLORS = ['#3A95FF', '#F2643D', '#00B98D', '#FFE659', '#C62953', '#9B59B6', '#E67E22', '#1ABC9C'];

// Human-readable labels for known metric keys; unknown metrics fall back to their raw name
const METRIC_LABELS: Record<string, string> = {
  Cost: 'Cost',
  Duration: 'Duration',
  ToolUtilizationAccuracy: 'Tool Utilization Accuracy',
  ResponseCompleteness: 'Response Completeness',
  IntentRecognitionAccuracy: 'Intent Recognition Accuracy',
  AnswerRelevancy: 'Answer Relevancy',
  Groundedness: 'Groundedness'
};

interface ImpactDistributionProps {
  data: ImpactAssessment[];
  title?: string;
}

/**
 * Renders a grouped bar + line chart showing how each metric's impact
 * is distributed across agents in a session.
 *
 * The API delivers data in a metric-centric shape (each metric lists agents).
 * This component pivots it to an agent-centric shape (each row = one agent,
 * columns = metric percentages) so Recharts can plot grouped bars per agent.
 *
 * Chart layout (numeric X-axis):
 *   Each agent occupies a "group" on the X-axis.
 *   Within a group, each metric bar is offset slightly so bars sit side-by-side.
 *   Agent labels are placed at the center (baseIndex) of each group.
 */
export const ImpactDistribution = ({ data, title }: ImpactDistributionProps) => {
  const theme = useTheme();
  const [hoveredMetric, setHoveredMetric] = useState<string | null>(null);

  // ── Data transformation: metric-centric API → agent-centric chart rows ──
  const { chartData, metrics } = useMemo(() => {
    if (!data || data.length === 0) return { chartData: [], metrics: [] };

    // Build metric descriptors (key, display label, color) from whatever the API returned
    const metrics = data.map((m, idx) => ({
      key: m.metric_name,
      color: METRIC_COLORS[idx % METRIC_COLORS.length],
      label: METRIC_LABELS[m.metric_name] ?? m.metric_name
    }));

    // Collect unique agent names, excluding filtered agents
    const agentSet = new Set<string>();
    for (const metric of data) {
      for (const agent of metric.agents) {
        if (!FILTERED_AGENTS.has(agent.agent_name)) {
          agentSet.add(agent.agent_name);
        }
      }
    }

    // Compute horizontal offsets so each metric's bar is placed side-by-side
    // within a group. Offsets are symmetric around 0 (the group center).
    // E.g. with 3 metrics and OFFSET_STEP=0.25: offsets are [-0.25, 0, 0.25]
    const barsCount = metrics.length;
    const OFFSET_STEP = 0.25;
    const offsets = Object.fromEntries(metrics.map((m, i) => [m.key, (i - (barsCount - 1) / 2) * OFFSET_STEP]));

    // Gap between agent groups on the X-axis
    const GROUP_GAP_STEP = 1;
    const getBaseIndex = (i: number) => i * (1 + GROUP_GAP_STEP);

    // Pivot: one row per agent, with percentage values and X positions for each metric
    const agents = Array.from(agentSet);
    const chartData = agents.map((agentName, idx) => {
      const base = getBaseIndex(idx); // center X position for this agent's group
      const row: Record<string, string | number> = { agentName, baseIndex: base };

      for (const metric of data) {
        const agentEntry = metric.agents.find((a) => a.agent_name === agentName);
        // API returns fractions (0–1), convert to percentage (0–100) with 2 decimal places
        const fraction = agentEntry?.value.value ?? 0;
        row[metric.metric_name] = parseFloat((fraction * 100).toFixed(2));
        // Each metric bar gets its own X position: group center + metric offset
        row[`index_${metric.metric_name}`] = base + (offsets[metric.metric_name] ?? 0);
      }

      return row;
    });

    return { chartData, metrics };
  }, [data]);

  if (!data || data.length === 0) {
    return null;
  }

  const barsCount = metrics.length;
  const OFFSET_STEP = 0.25;
  const offsets = Object.fromEntries(metrics.map((m, i) => [m.key, (i - (barsCount - 1) / 2) * OFFSET_STEP]));
  const GROUP_GAP_STEP = 1;
  const getBaseIndex = (i: number) => i * (1 + GROUP_GAP_STEP);

  const maxIndex = getBaseIndex(chartData.length - 1);
  const minOffset = Math.min(...Object.values(offsets));
  const maxOffset = Math.max(...Object.values(offsets));
  const DOMAIN_PAD = 0.15; // extra breathing room so edge bars don't clip
  const xDomain: [number, number] = [-0.5 + minOffset - DOMAIN_PAD, maxIndex + 0.5 + maxOffset + DOMAIN_PAD];

  // Tick positions at the center of each agent group (for the label axis)
  const tickValues = chartData.map((d) => Number(d.baseIndex));

  return (
    <Stack direction="column" gap="12px" sx={{ width: '100%' }} alignItems="flex-start">
      <Typography variant="h6">{title ?? ''}</Typography>
      <Box
        sx={{
          width: '100%',
          height: '300px',
          backgroundColor: GLOBAL_BACKGROUND_COLOR,
          borderRadius: '8px'
        }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 16, right: 24, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="4 4" stroke={theme.palette.vars.baseBorderMedium} />

            {/* Visible label axis: ticks at group centers, formatted as agent names */}
            <XAxis
              xAxisId="ticks"
              type="number"
              dataKey="baseIndex"
              domain={xDomain}
              tick={{ fill: theme.palette.text.primary }}
              ticks={tickValues}
              tickFormatter={(value: number) => {
                const idx = tickValues.indexOf(value);
                return idx >= 0 ? String(chartData[idx]?.agentName ?? '') : '';
              }}
            />

            {/* Hidden numeric axes — one per metric — used to position each bar/line at its offset */}
            {metrics.map((m, idx) => (
              <XAxis key={`xaxis-${m.key}`} xAxisId={`m${idx}`} type="number" dataKey={`index_${m.key}`} domain={xDomain} hide />
            ))}

            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fill: theme.palette.text.primary }} />

            {/* Custom tooltip: shows all metric values for the hovered agent */}
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null;
                const row = (payload[0] as any)?.payload;
                if (!row) return null;
                const agent = row.agentName as string;
                const rows = metrics.map((m) => ({
                  key: m.key,
                  label: m.label,
                  color: m.color,
                  value: Number(row[m.key] ?? 0)
                }));

                return (
                  <Box
                    sx={{
                      p: '8px 10px',
                      bgcolor: theme.palette.vars.baseBackgroundWeak,
                      border: `1px solid ${theme.palette.vars.baseBorderMedium}`,
                      borderRadius: '6px',
                      minWidth: '220px'
                    }}
                  >
                    <Typography variant="captionSemibold" sx={{ mb: '6px' }}>
                      {agent}
                    </Typography>
                    <Stack direction="column" gap="4px">
                      {rows.map((r) => (
                        <Stack key={`${agent}-${r.key}`} direction="row" alignItems="center" justifyContent="space-between" gap="12px">
                          <Stack direction="row" alignItems="center" gap="6px">
                            <Box sx={{ width: '8px', height: '8px', bgcolor: r.color, borderRadius: '50%' }} />
                            <Typography variant="caption" sx={{ fontWeight: hoveredMetric === r.key ? 600 : 400 }}>
                              {r.label}
                            </Typography>
                          </Stack>
                          <Typography variant="caption" sx={{ fontWeight: hoveredMetric === r.key ? 600 : 400 }}>
                            {Math.round(r.value ?? 0)}%
                          </Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </Box>
                );
              }}
            />

            <Legend verticalAlign="bottom" align="center" />

            {/* One Bar per metric, each bound to its own offset axis for precise positioning */}
            {metrics.map((m, idx) => (
              <Bar key={`bar-${m.key}`} xAxisId={`m${idx}`} dataKey={m.key} name={m.label} fill={m.color} barSize={22} legendType="none" />
            ))}

            {/* One Line per metric connecting values across agents for trend visibility */}
            {metrics.map((m, idx) => (
              <Line
                key={`line-${m.key}`}
                xAxisId={`m${idx}`}
                type="linear"
                dataKey={m.key}
                name={m.label}
                stroke={m.color}
                strokeWidth={1}
                dot={{ r: 3 }}
                activeDot={{ r: 4, onMouseEnter: () => setHoveredMetric(m.key), onMouseLeave: () => setHoveredMetric(null) }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </Box>
    </Stack>
  );
};
