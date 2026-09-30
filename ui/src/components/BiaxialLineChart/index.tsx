/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  CartesianGridProps,
  ResponsiveContainer,
  LineChart as RechartLineChart,
  XAxisProps,
  YAxisProps,
  LineProps
} from 'recharts';
import { ChartCategory, ChartProps } from '@open-ui-kit/core';
import { BiaxialLineChartTooltip, BiaxialLineChartTooltipProps } from './tooltip';
import { formatISODate, formatNumber } from './utils';
import { useTheme } from '@mui/material';

type SafeLineProps = Omit<LineProps, 'ref'>;

export interface BiaxialLineChartProps extends ChartProps, Pick<BiaxialLineChartTooltipProps, 'valueFormatterLeft' | 'valueFormatterRight' | 'leftLabel' | 'rightLabel'> {
  subject?: string;
  data: Array<{ date: string; [key: string]: number | string }>;
  // dataLeft: Array<{ date: string; [key: string]: number | string }>; // left axis series
  //  dataRight: Array<{ date: string; [key: string]: number | string }>; // right axis series
  leftCategory: ChartCategory; // dataKey for left series
  rightCategory: ChartCategory; // dataKey for right series
  xAxisProps?: XAxisProps;
  yAxisRightProps?: YAxisProps;
  yAxisLeftProps?: YAxisProps;
  lineProps?: Partial<SafeLineProps>;
  gridProps?: CartesianGridProps;
}

export const BiaxialLineChart = ({
  data,
  // dataLeft,
  // dataRight,
  leftCategory,
  rightCategory,
  showTooltip = true,
  subject,
  xAxisProps,
  yAxisRightProps,
  yAxisLeftProps,
  customTooltip,
  valueFormatterLeft,
  valueFormatterRight,
  leftLabel,
  rightLabel,
  lineProps,
  gridProps
}: BiaxialLineChartProps) => {
  const theme = useTheme();

  // Merge on date without duplicating keys
  // type DataPoint = { date: string; [key: string]: number | string };
  // const mergedByDate = new Map<string, DataPoint>();

  // for (const p of dataLeft) {
  //   const existing = mergedByDate.get(p.date);
  //   const value = p[leftCategory.name] as number | string | undefined;
  //   mergedByDate.set(p.date, {
  //     date: p.date,
  //     ...(existing ?? {}),
  //     ...(value === undefined ? {} : { [leftCategory.name]: value })
  //   });
  // }

  // for (const p of dataRight) {
  //   const existing = mergedByDate.get(p.date);
  //   const value = p[rightCategory.name] as number | string | undefined;
  //   mergedByDate.set(p.date, {
  //     date: p.date,
  //     ...(existing ?? {}),
  //     ...(value === undefined ? {} : { [rightCategory.name]: value })
  //   });
  // }

  // const merged = Array.from(mergedByDate.values()).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RechartLineChart data={data} margin={{ top: 13, right: 5, bottom: 0, left: 0 }} {...{ overflow: 'visible' }}>
        <XAxis
          dataKey="date"
          type="category"
          axisLine={{
            strokeWidth: 1,
            stroke: theme.palette.vars.inactiveBackgroundDefault
          }}
          tickSize={2}
          tickLine={{
            strokeWidth: 1,
            stroke: theme.palette.vars.inactiveBackgroundDefault,
            style: { transform: 'translateY(3.5px)' }
          }}
          tick={{
            fontFamily: 'Inter',
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: 0.4,
            color: theme.palette.vars.inactiveBackgroundDefault
          }}
          tickMargin={8}
          minTickGap={16}
          tickFormatter={(date) => formatISODate(date, 'd')}
          {...xAxisProps}
        />
        <YAxis
          yAxisId="left"
          width={40}
          type="number"
          domain={['dataMin', 'dataMax']}
          axisLine={false}
          tickLine={false}
          tick={{
            fontFamily: 'Inter',
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: 0.4,
            color: theme.palette.vars.inactiveBackgroundDefault
          }}
          tickMargin={10}
          minTickGap={14}
          tickFormatter={valueFormatterLeft || formatNumber}
          {...yAxisLeftProps}
        />

        <YAxis
          yAxisId="right"
          orientation="right"
          width={40}
          type="number"
          domain={['dataMin', 'dataMax']}
          axisLine={false}
          tickLine={false}
          tick={{
            fontFamily: 'Inter',
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: 0.4,
            color: theme.palette.vars.inactiveBackgroundDefault
          }}
          tickMargin={10}
          minTickGap={14}
          tickFormatter={valueFormatterRight || formatNumber}
          {...yAxisRightProps}
        />
        <CartesianGrid vertical={false} strokeWidth={1} stroke={theme.palette.vars.inactiveBackgroundDefault} {...gridProps} />
        <Line
          yAxisId="left"
          key={leftCategory.name}
          type="monotone"
          dataKey={leftCategory.name}
          legendType="none"
          dot={false}
          activeDot={true}
          strokeWidth={2}
          stroke={leftCategory.color}
          name={leftCategory.name}
          {...lineProps}
        />
        <Line
          yAxisId="right"
          key={rightCategory.name}
          type="monotone"
          dataKey={rightCategory.name}
          legendType="none"
          dot={false}
          activeDot={true}
          strokeWidth={2}
          stroke={rightCategory.color}
          name={rightCategory.name}
          {...lineProps}
        />
        {showTooltip && (
          <Tooltip
            content={
              customTooltip ?? (
                <BiaxialLineChartTooltip
                  subject={subject}
                  valueFormatterLeft={valueFormatterLeft}
                  valueFormatterRight={valueFormatterRight}
                  leftName={leftCategory.name}
                  rightName={rightCategory.name}
                  leftLabel={leftLabel}
                  rightLabel={rightLabel}
                />
              )
            }
            wrapperStyle={{ zIndex: 1 }}
            allowEscapeViewBox={{ x: false, y: true }}
            cursor={{
              strokeWidth: 1,
              strokeDasharray: '5',
              stroke: theme.palette.vars.inactiveBackgroundDefault
            }}
          />
        )}
      </RechartLineChart>
    </ResponsiveContainer>
  );
};
