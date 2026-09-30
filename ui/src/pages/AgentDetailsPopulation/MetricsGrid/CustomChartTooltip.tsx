/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState, useRef, useLayoutEffect } from 'react';
import ReactDOM from 'react-dom';
import { Box, Typography } from '@mui/material';
import { TooltipProps } from 'recharts';
import { format, parseISO } from 'date-fns';
import { formatMetricValueLineChartTooltip } from '@/utils/metrics.tsx';
import { Unit } from '@/types/oxp.type';

const TOOLTIP_MARGIN = 12;

const formatISODate = (isoDate: string, fmt: string): string => {
  try {
    return format(parseISO(isoDate), fmt);
  } catch (error) {
    return isoDate;
  }
};

type ExtraTooltipProps = { suffix?: string; metricName?: string; unit?: Unit };

const CustomChartTooltip: React.FC<TooltipProps<number, string> & ExtraTooltipProps> = ({ active, payload, label, suffix, metricName, unit }) => {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [tooltipWidth, setTooltipWidth] = useState(0);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setPosition({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useLayoutEffect(() => {
    if (tooltipRef.current) {
      const width = tooltipRef.current.offsetWidth;
      if (width !== tooltipWidth) {
        setTooltipWidth(width);
      }
    }
  }, [payload, label, tooltipWidth]);

  if (!active || !payload || payload.length === 0) return null;

  const placeLeft = position.x + tooltipWidth + TOOLTIP_MARGIN > window.innerWidth;

  const leftPos = placeLeft ? position.x - tooltipWidth - TOOLTIP_MARGIN : position.x + TOOLTIP_MARGIN;

  const formattedLabel = typeof label === 'string' ? formatISODate(label, 'yyyy-MM-dd HH:mm:ss') : String(label ?? '');

  return ReactDOM.createPortal(
    <>
      {/* Invisible tooltip for width measurement */}
      <Box
        ref={tooltipRef}
        sx={{
          position: 'fixed',
          top: -9999,
          left: -9999,
          visibility: 'hidden',
          whiteSpace: 'normal',
          maxWidth: '300px',
          padding: '8px',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          fontWeight: 'inherit'
        }}
      >
        <Typography variant="caption" sx={{ mb: 0.5 }}>
          {formattedLabel}
        </Typography>
        {payload.map((entry, index) => {
          if (!entry.value) return null;

          const formattedValue = formatMetricValueLineChartTooltip(entry.value, unit ?? Unit.Scalar);

          return (
            <Typography key={index} variant="body2" noWrap={false}>
              {metricName ?? entry.name}: {formattedValue}
            </Typography>
          );
        })}
      </Box>

      {/* Actual visible tooltip */}
      <Box
        sx={(theme) => ({
          position: 'fixed',
          top: position.y + TOOLTIP_MARGIN,
          left: leftPos,
          backgroundColor: theme.palette.vars.baseBackgroundWeak,
          border: `1px solid ${theme.palette.vars.baseBorderDefault}`,
          borderRadius: '4px',
          padding: '8px',
          zIndex: 2000,
          pointerEvents: 'none',
          boxShadow: theme.shadows[3],
          userSelect: 'none',
          maxWidth: '300px',
          whiteSpace: 'normal',
          color: theme.palette.vars.baseTextStrong
        })}
      >
        <Typography variant="caption" sx={(theme) => ({ mb: 0.5, color: theme.palette.vars.baseTextStrong })}>
          {formattedLabel}
        </Typography>
        {payload.map((entry, index) => {
          if (!entry.value) return null;

          const formattedValue = formatMetricValueLineChartTooltip(entry.value, unit ?? Unit.Scalar);

          return (
            <Typography key={index} variant="body2" noWrap={false}>
              {metricName ?? entry.name}: {formattedValue}
            </Typography>
          );
        })}
      </Box>
    </>,
    document.body
  );
};

export default CustomChartTooltip;
