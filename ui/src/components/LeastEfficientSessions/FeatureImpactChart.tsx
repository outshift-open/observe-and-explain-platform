/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useWastedResourcesFeatureScores } from '@/api/oxpApi';
import { WastefulSession } from '@/types/oxp.type';
import {
  Box,
  FormControl,
  MenuItem,
  Select,
  Stack,
  Tooltip as MuiTooltip,
  Typography,
  useTheme
} from '@mui/material';
import { GeneralSize, Spinner, Tag } from '@open-ui-kit/core';
import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  Tooltip,
  ReferenceLine
} from 'recharts';
import { featureCatalog } from '@/common/featureCatalog';
import {
  GLOBAL_BACKGROUND_COLOR,
  GLOBAL_BORDER_COLOR,
  GLOBAL_TEXT_COLOR
} from '@/common/styles';
import { colorTokens } from '@/theme/colors';
import { CustomTooltip } from '../CustomTooltip';

const POSITIVE_COLOR = '#F97316';
const NEGATIVE_COLOR = '#34D399';

const formatQualityTarget = (raw: string): string =>
  raw.replace(/^metric_/, '').replace(/([a-z])([A-Z])/g, '$1 $2');

const FeatureTickLabel = ({
  x,
  y,
  payload,
  fill
}: {
  x: number;
  y: number;
  payload: { value: string };
  fill: string;
}) => {
  const description = featureCatalog[payload.value];
  const label = (
    <text
      x={x}
      y={y}
      textAnchor="end"
      dominantBaseline="central"
      fill={fill}
      fontSize={12}
      style={{ cursor: description ? 'help' : 'default' }}
    >
      {payload.value}
    </text>
  );

  if (!description) return label;

  return (
    <foreignObject x={x - 220} y={y - 12} width={230} height={24}>
      <MuiTooltip title={description} placement="top" enterDelay={300}>
        <span
          style={{
            display: 'block',
            textAlign: 'right',
            color: fill,
            fontSize: 12,
            lineHeight: '24px',
            cursor: 'help',
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis'
          }}
        >
          {payload.value}
        </span>
      </MuiTooltip>
    </foreignObject>
  );
};

interface FeatureImpactChartProps {
  session: WastefulSession | null;
  onGroupClick?: (groupId: string) => void;
  onSessionClick?: (session: WastefulSession) => void;
}

export const FeatureImpactChart = ({
  session,
  onGroupClick,
  onSessionClick
}: FeatureImpactChartProps) => {
  const theme = useTheme();
  const {
    data: wastedResourcesFeatureScores,
    isLoading,
    isError
  } = useWastedResourcesFeatureScores(
    session?.sessionId ?? '',
    session !== null
  );

  const qualityTargets = useMemo(() => {
    if (!wastedResourcesFeatureScores) return [];
    const unique = [
      ...new Set(wastedResourcesFeatureScores.map((d) => d.qualityTarget))
    ];
    return unique;
  }, [wastedResourcesFeatureScores]);

  const [selectedTarget, setSelectedTarget] = useState<string>('');

  useEffect(() => {
    if (qualityTargets.length > 0 && !qualityTargets.includes(selectedTarget)) {
      setSelectedTarget(qualityTargets[0]);
    }
  }, [qualityTargets]);

  const chartData = useMemo(() => {
    if (!wastedResourcesFeatureScores) return [];
    return wastedResourcesFeatureScores
      .filter((item) => item.qualityTarget === selectedTarget)
      .sort((a, b) => b.score - a.score)
      .map((item) => ({
        feature: item.feature,
        score: parseFloat(item.score.toFixed(3))
      }));
  }, [wastedResourcesFeatureScores, selectedTarget]);

  if (!session) return null;

  if (isLoading) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Typography variant="body1">Error loading feature scores</Typography>
    );
  }

  if (chartData.length === 0) {
    return (
      <Typography variant="body1">No feature score data available</Typography>
    );
  }

  // Symmetric x-axis domain so bars extend equally in both directions
  const maxAbsScore = Math.max(...chartData.map((d) => Math.abs(d.score)));
  // 15% padding so the longest bar doesn't touch the chart edge
  const domainPad = maxAbsScore * 0.15;
  const xDomain: [number, number] = [
    -(maxAbsScore + domainPad),
    maxAbsScore + domainPad
  ];

  return (
    <Stack
      direction="column"
      gap="12px"
      sx={{ flex: 1, minWidth: 0, minHeight: 0, paddingLeft: '8px' }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography
          variant="h6"
          sx={{
            color: colorTokens.disabledBlue1Text,
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
            minWidth: 0,
            display: 'block',
            cursor: 'pointer'
          }}
          onClick={() => onSessionClick?.(session)}
        >
          {session.sessionId}
        </Typography>

        <CustomTooltip
          title={session.semanticGroup}
          placement="top"
          sx={{ maxWidth: '400px' }}
        >
          <Box>
            <Tag
              sx={{
                backgroundColor: GLOBAL_BACKGROUND_COLOR,
                border: `1px solid ${colorTokens.inactiveBorder}`,
                maxWidth: '300px'
              }}
              size={GeneralSize.Medium}
              onClick={() => onGroupClick?.(session.semanticGroupId ?? '')}
            >
              {session.semanticGroup}
            </Tag>
          </Box>
        </CustomTooltip>
      </Stack>
      <Typography variant="headingSubSection">
        Features contributing to Inefficiency
      </Typography>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        gap="4px"
      >
        <FormControl size="small" sx={{ maxWidth: 280, width: '100%' }}>
          <Select
            value={selectedTarget}
            onChange={(e) => setSelectedTarget(e.target.value)}
            displayEmpty
            MenuProps={{
              PaperProps: {
                sx: {
                  backgroundColor: GLOBAL_BACKGROUND_COLOR,
                  border: `1px solid ${colorTokens.selectBorder}`,
                  boxShadow: 'none'
                }
              }
            }}
            sx={{
              backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
              color: `${GLOBAL_TEXT_COLOR} !important`,
              '&:focus, &:focus-visible, &.Mui-focusVisible': {
                outline: 'none !important'
              },
              '&:active': {
                outline: 'none !important'
              },
              '&.Mui-disabled': {
                border: `2px solid ${GLOBAL_BORDER_COLOR} !important`,
                backgroundColor: `${theme.palette.vars?.controlBackgroundDisabled} !important`
              },
              '& .MuiSvgIcon-root': {
                color: `${theme.palette.vars?.controlIconDefault} !important`
              },
              height: '36px !important',
              '& .MuiOutlinedInput-notchedOutline': {
                border: 'none'
              },
              '& .MuiSelect-select': {
                backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
                border: `1px solid ${colorTokens.selectBorder} !important`
              }
            }}
          >
            {qualityTargets.map((target) => (
              <MenuItem
                key={target}
                value={target}
                sx={{
                  color: `${GLOBAL_TEXT_COLOR} !important`,
                  backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
                  border: 'none',
                  '&:hover': {
                    backgroundColor: `${theme.palette.vars.baseBackgroundHover} !important`
                  }
                }}
              >
                {formatQualityTarget(target)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Stack direction="row" alignItems="center" gap="24px">
          <Stack direction="row" alignItems="center" gap="8px">
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: POSITIVE_COLOR
              }}
            />
            <Typography variant="body1Semibold">Reduces Efficiency</Typography>
          </Stack>
          <Stack direction="row" alignItems="center" gap="8px">
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: NEGATIVE_COLOR
              }}
            />
            <Typography variant="body1Semibold">
              Increases Efficiency
            </Typography>
          </Stack>
        </Stack>
      </Stack>
      <Box
        sx={{
          width: '100%',
          flex: 1,
          minHeight: 0,
          borderRadius: '8px',
          padding: '16px 8px 16px 8px'
        }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 48, bottom: 0, left: 72 }}
          >
            <XAxis
              type="number"
              domain={xDomain}
              tickFormatter={(v: number) =>
                v >= 0 ? `+${v.toFixed(1)}` : v.toFixed(1)
              }
              tick={{ fill: theme.palette.text.secondary, fontSize: 11 }}
              axisLine={{ stroke: theme.palette.divider }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="feature"
              width={180}
              tick={(props: any) => (
                <FeatureTickLabel
                  {...props}
                  fill={theme.palette.text.primary}
                />
              )}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const item = payload[0]?.payload;
                if (!item) return null;
                return (
                  <Box
                    sx={{
                      p: '6px 10px',
                      bgcolor: theme.palette.vars.baseBackgroundWeak,
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: '6px'
                    }}
                  >
                    <Typography variant="captionSemibold">
                      {item.feature}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        color: item.score >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR
                      }}
                    >
                      {item.score >= 0 ? `+${item.score}` : item.score}
                    </Typography>
                  </Box>
                );
              }}
            />
            <ReferenceLine
              x={0}
              stroke={theme.palette.divider}
              strokeWidth={1}
            />
            <Bar
              dataKey="score"
              radius={[4, 4, 4, 4]}
              barSize={16}
              minPointSize={2}
              label={({ x, y, width, height, value }) => {
                const isPositive = value >= 0;
                return (
                  <text
                    x={isPositive ? x + width + 4 : x + width - 4}
                    y={y + height / 2}
                    textAnchor={isPositive ? 'start' : 'end'}
                    dominantBaseline="central"
                    fill={isPositive ? POSITIVE_COLOR : NEGATIVE_COLOR}
                    fontSize={11}
                  >
                    {isPositive ? `+${value}` : value}
                  </text>
                );
              }}
            >
              {chartData.map((entry) => (
                <Cell
                  key={entry.feature}
                  fill={entry.score >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </Stack>
  );
};
