/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip } from 'recharts';

export interface SpiderChartDataPoint {
  subject: string;
  variableA: number;
}

export interface SpiderChartProps {
  data: SpiderChartDataPoint[];
  domain?: [number, number];
  fillColor?: string;
  strokeColor?: string;
}

const DEFAULT_DOMAIN: [number, number] = [0, 100];
const DEFAULT_FILL = '#8884d8';
const DEFAULT_STROKE = '#8884d8';

const TOP_OFFSET = -18;

const renderAxisTick =
  (dataMap: Map<string, number>, dataLength: number) =>
  ({ payload, x, y, textAnchor, index }: any) => {
    const label: string = payload?.value ?? '';
    const value = dataMap.get(label);
    const isTop = index === 0;
    const adjustedY = isTop ? y + TOP_OFFSET : y;
    return (
      <text x={x} y={adjustedY} textAnchor={textAnchor} fontSize={11} fill="#fff">
        <tspan x={x} dy={0}>
          {label}
        </tspan>
        {value !== undefined && (
          <tspan x={x} dy={14} fontSize={10} fill="#aaa">
            {value}%
          </tspan>
        )}
      </text>
    );
  };

export const SpiderChart = ({ data, domain = DEFAULT_DOMAIN, fillColor = DEFAULT_FILL, strokeColor = DEFAULT_STROKE }: SpiderChartProps) => {
  const dataMap = new Map(data.map((d) => [d.subject, d.variableA]));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RadarChart cx="40%" cy="50%" outerRadius="65%" data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="subject" tick={renderAxisTick(dataMap, data.length)} />
        <PolarRadiusAxis angle={90} domain={domain} tick={{ fontSize: 9, fill: '#fff' }} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const { subject, variableA } = payload[0].payload as SpiderChartDataPoint;
            return (
              <div
                style={{ backgroundColor: '#1e1e1e', border: '1px solid #444', borderRadius: 4, padding: '6px 10px', color: '#fff', fontSize: 12 }}
              >
                {subject}: {variableA}%
              </div>
            );
          }}
        />
        <Radar
          name="Value"
          dataKey="variableA"
          stroke={strokeColor}
          fill={fillColor}
          fillOpacity={0.35}
          dot={{ r: 2, fill: '#fff', stroke: strokeColor, strokeWidth: 2 }}
          activeDot={{ r: 4, fill: '#fff', stroke: strokeColor, strokeWidth: 2 }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
};
