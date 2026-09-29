/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ScatterChart, Scatter, XAxis, YAxis, ResponsiveContainer, ReferenceArea, ReferenceLine, Customized } from 'recharts';
import { Box, Typography } from '@mui/material';
import { SessionWithMetrics, Unit } from '@/types/oxp.type';
import { findMetricCatalogEntry, formatMetricValue } from '@/utils/metrics';
import { metricCatalog } from '@/common';
import { getDisplayedResultsCount } from '@/utils/stringUtils';

interface SessionDistributionChartProps {
  data: SessionWithMetrics[];
  targetMetricName: string;
  outlierSessionIds: string[];
  metricUnit: Unit;
}

interface ScatterPoint {
  x: number;
  y: number;
  index: number;
  isOutlier: boolean;
  session: SessionWithMetrics;
}

const POINT_COLOR = '#5B8DEF';
const OUTLIER_COLOR = '#EF4444';
const POINT_RADIUS = 4;
const HOVER_RADIUS = 6;
const HIT_RADIUS = 12;

const formatTimestamp = (timestamp: string): string => {
  const ms = parseFloat(timestamp) * 1000;
  return new Date(ms).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

const formatValue = (value: unknown) => {
  if (Array.isArray(value)) {
    return value.length === 0 ? '—' : value.join(', ');
  }
  if (typeof value === 'number') {
    return getDisplayedResultsCount(value);
  }
  return String(value ?? '—');
};

const formatTooltipValue = (key: string, value: number, unit?: Unit) => {
  if (key === 'timestamp') {
    return formatTimestamp(String(value));
  }

  if (!unit) {
    return formatValue(value);
  }

  return formatMetricValue(value, unit);
};

const FILTERED_KEYS = ['semanticGroupMetrics', 'session_metrics', 'statefulEval'];

const FIELD_LABELS: Record<string, string> = {
  sessionId: 'Session ID',
  timestamp: 'Timestamp',
  agents: 'Agents',
  llms: 'LLMs',
  tokens: 'Tokens',
  status: 'Status',
  cost: 'Cost',
  duration: 'Duration'
};

const TooltipContent = ({ point, targetMetricName, metricUnit }: { point: ScatterPoint; targetMetricName: string; metricUnit: Unit }) => {
  const { session } = point;
  const metricEntry = session.semanticGroupMetrics.find((m) => m.name === targetMetricName);

  return (
    <Box
      sx={{
        backgroundColor: '#1E1E1E',
        border: '1px solid #444',
        borderRadius: '6px',
        p: 1.5,
        width: 320,
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        pointerEvents: 'none'
      }}
    >
      {Object.entries(session)
        .filter(([key]) => !FILTERED_KEYS.includes(key) && key.toLowerCase() !== targetMetricName.toLowerCase())
        .map(([key, value]) => (
          <Box key={key} sx={{ display: 'flex', gap: '6px', fontSize: '11px', lineHeight: 1.4 }}>
            <Typography variant="caption" sx={{ color: '#888', whiteSpace: 'nowrap', minWidth: 80 }}>
              {FIELD_LABELS[key] ?? key}
            </Typography>
            <Typography variant="caption" sx={{ color: '#E0E0E0', wordBreak: 'break-word' }}>
              {formatTooltipValue(key, value, findMetricCatalogEntry(key)?.unit)}
            </Typography>
          </Box>
        ))}
      {metricEntry && (
        <Box sx={{ display: 'flex', gap: '6px', fontSize: '11px', lineHeight: 1.4 }}>
          <Typography variant="caption" sx={{ color: '#888', whiteSpace: 'nowrap', minWidth: 80 }}>
            {findMetricCatalogEntry(targetMetricName)?.name}
          </Typography>
          <Typography variant="caption" sx={{ color: '#E0E0E0' }}>
            {formatTooltipValue(targetMetricName, metricEntry.value, findMetricCatalogEntry(targetMetricName)?.unit)}
          </Typography>
        </Box>
      )}
    </Box>
  );
};

interface DotProps {
  cx?: number;
  cy?: number;
  payload?: ScatterPoint;
  activeIndex: number | null;
  dotPositions: React.MutableRefObject<Map<number, { cx: number; cy: number }>>;
}

const HoverableDot = ({ cx, cy, payload, activeIndex, dotPositions }: DotProps) => {
  if (cx == null || cy == null || !payload) return null;

  dotPositions.current.set(payload.index, { cx, cy });

  const isActive = activeIndex === payload.index;
  const color = payload.isOutlier ? OUTLIER_COLOR : POINT_COLOR;
  const r = isActive ? HOVER_RADIUS : POINT_RADIUS;

  return (
    <g>
      {isActive && <circle cx={cx} cy={cy} r={HOVER_RADIUS + 4} fill={color} opacity={0.2} />}
      <circle cx={cx} cy={cy} r={r} fill={color} style={{ transition: 'r 0.15s ease' }} />
    </g>
  );
};

export const SessionDistributionChart = ({ data, targetMetricName, outlierSessionIds, metricUnit }: SessionDistributionChartProps) => {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const [bandCenterPx, setBandCenterPx] = useState<number | null>(null);
  const xScaleRef = useRef<((v: number) => number) | null>(null);
  const dotPositions = useRef<Map<number, { cx: number; cy: number }>>(new Map());
  const containerRef = useRef<HTMLDivElement>(null);

  const findNearestDot = useCallback((mouseX: number, mouseY: number): number | null => {
    let nearest: number | null = null;
    let minDist = HIT_RADIUS;

    for (const [index, pos] of dotPositions.current) {
      const dx = mouseX - pos.cx;
      const dy = mouseY - pos.cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < minDist) {
        minDist = dist;
        nearest = index;
      }
    }

    return nearest;
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const nearest = findNearestDot(mouseX, mouseY);
      setActiveIndex(nearest);

      if (nearest != null) {
        const pos = dotPositions.current.get(nearest);
        if (pos) {
          setTooltipPos({ x: rect.left + pos.cx - 336, y: rect.top + pos.cy - 16 });
        }
      } else {
        setTooltipPos(null);
      }
    },
    [findNearestDot]
  );

  const handleMouseLeave = useCallback(() => {
    setActiveIndex(null);
    setTooltipPos(null);
  }, []);

  const { points, bandStart, bandEnd, percentInBand } = useMemo(() => {
    if (data.length === 0) {
      return { points: [], bandStart: 0, bandEnd: 0, percentInBand: 0 };
    }

    const outlierSet = new Set(outlierSessionIds);
    const pts: ScatterPoint[] = data.map((session, i) => ({
      x: session.semanticGroupMetrics.find((metric) => metric.name === targetMetricName)?.value ?? 0,
      y: parseFloat(session.timestamp) * 1000,
      index: i,
      isOutlier: outlierSet.has(session.sessionId),
      session
    }));

    const normalPoints = pts.filter((p) => !p.isOutlier);
    const normalX = normalPoints.map((p) => p.x);
    const bStart = normalX.length > 0 ? Math.min(...normalX) : 0;
    const bEnd = normalX.length > 0 ? Math.max(...normalX) : 0;

    const pct = pts.length > 0 ? Math.round((normalPoints.length / pts.length) * 100) : 0;

    return { points: pts, bandStart: bStart, bandEnd: bEnd, percentInBand: pct };
  }, [data, targetMetricName, outlierSessionIds]);

  if (points.length === 0) {
    return null;
  }

  const xValues = points.map((p) => p.x);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const xPadding = (xMax - xMin) * 0.08 || 1;
  const xStep = (xMax - xMin) / 4;
  const xTicks = xStep > 0 ? [xMin, xMin + xStep, xMin + xStep * 2, xMin + xStep * 3, xMax] : [xMin];

  const yValues = points.map((p) => p.y);
  const yMin = Math.min(...yValues);
  const yMax = Math.max(...yValues);
  const yPadding = (yMax - yMin) * 0.08 || 1;

  const activePoint = activeIndex != null ? points[activeIndex] : null;

  return (
    <Box sx={{ position: 'relative', width: '100%', marginTop: '20px' }}>
      <Box sx={{ position: 'relative' }}>
        {bandCenterPx != null && (
          <Box
            sx={{
              position: 'absolute',
              left: bandCenterPx,
              transform: 'translate(-50%, -110%)',
              backgroundColor: POINT_COLOR,
              borderRadius: '6px',
              whiteSpace: 'nowrap',
              padding: '4px'
            }}
          >
            <Typography variant="caption" sx={{ color: '#fff', fontWeight: 600 }}>
              {percentInBand}% of sessions
            </Typography>
          </Box>
        )}
      </Box>

      <Box
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        sx={{ width: '100%', height: 140, border: '1px solid #444', borderRadius: '6px' }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 0, right: 12, bottom: 0, left: 12 }}>
            <XAxis type="number" dataKey="x" domain={[xMin - xPadding, xMax + xPadding]} tick={false} axisLine={false} tickLine={false} height={0} />
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin - yPadding * 2, yMax + yPadding * 2]}
              tick={false}
              axisLine={false}
              tickLine={false}
              width={0}
            />

            <ReferenceArea x1={bandStart} x2={bandEnd} fill={POINT_COLOR} fillOpacity={0.12} stroke="none" />
            <ReferenceLine x={bandStart} stroke="#666" strokeDasharray="4 4" />
            <ReferenceLine x={bandEnd} stroke="#666" strokeDasharray="4 4" />

            <Customized
              component={(props: Record<string, unknown>) => {
                const { xAxisMap } = props as { xAxisMap: Record<string, { scale: (v: number) => number }> };
                const xAxis = xAxisMap && Object.values(xAxisMap)[0];
                if (!xAxis?.scale) return null;

                xScaleRef.current = xAxis.scale;

                const pxStart = xAxis.scale(bandStart);
                const pxEnd = xAxis.scale(bandEnd);
                const newCenter = (pxStart + pxEnd) / 2;

                if (newCenter !== bandCenterPx) {
                  requestAnimationFrame(() => setBandCenterPx(newCenter));
                }

                return null;
              }}
            />

            <Scatter data={points} isAnimationActive={false} shape={<HoverableDot activeIndex={activeIndex} dotPositions={dotPositions} />} />
          </ScatterChart>
        </ResponsiveContainer>
      </Box>

      {xScaleRef.current && (
        <Box sx={{ position: 'relative', height: 16, mt: '2px', mx: '0px' }}>
          {xTicks.map((tick, i) => {
            const px = xScaleRef.current!(tick);
            return (
              <Typography
                key={i}
                variant="caption"
                sx={{
                  position: 'absolute',
                  left: px,
                  transform: 'translateX(-50%)',
                  color: '#888',
                  fontSize: 10,
                  whiteSpace: 'nowrap'
                }}
              >
                {formatMetricValue(tick, metricUnit)}
              </Typography>
            );
          })}
        </Box>
      )}

      <Box sx={{ padding: '8px 0 0 0', textAlign: 'center' }}>
        <Typography variant="captionMedium">{`${percentInBand}% of sessions fall within the expected range between `}</Typography>
        <Typography variant="body2Semibold">{`${formatMetricValue(bandStart, metricUnit)}`}</Typography>
        <Typography variant="captionMedium"> and </Typography>
        <Typography variant="body2Semibold"> {`${formatMetricValue(bandEnd, metricUnit)}.`}</Typography>
      </Box>

      {activePoint &&
        tooltipPos &&
        createPortal(
          <Box
            sx={{
              position: 'fixed',
              left: tooltipPos.x,
              top: tooltipPos.y,
              zIndex: 99999,
              pointerEvents: 'none'
            }}
          >
            <TooltipContent point={activePoint} targetMetricName={targetMetricName} metricUnit={metricUnit} />
          </Box>,
          document.body
        )}
    </Box>
  );
};
