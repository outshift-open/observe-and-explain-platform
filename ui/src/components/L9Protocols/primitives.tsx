/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { ReactNode } from 'react';
import {
  Box,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useTheme
} from '@mui/material';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { GeneralSize, Tag, Tooltip } from '@open-ui-kit/core';
import { L9Tone, getVerdictTone, humanizeLabel } from '@/common/l9Protocols';
import { L9Check, L9Verdict } from '@/types/oxp.type';

export const NO_DATA = 'N/A';

// ---------------------------------------------------------------------------
// Formatters: a missing value is always "N/A", never a blank or a zero.
// ---------------------------------------------------------------------------

const isMissing = (value: unknown): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

export const formatCount = (value?: number | null): string =>
  isMissing(value) ? NO_DATA : value.toLocaleString();

export const formatScore = (value?: number | null): string =>
  isMissing(value) ? NO_DATA : value.toFixed(2);

export const formatCost = (value?: number | null): string =>
  isMissing(value) ? NO_DATA : `$${value.toFixed(4)}`;

// Dollar amount without the currency sign, for columns headed "$".
export const formatDollars = (value?: number | null): string =>
  isMissing(value) ? NO_DATA : value.toFixed(4);

export const formatBound = (
  achieved?: number | null,
  bound?: number | null
): string =>
  isMissing(achieved) && isMissing(bound)
    ? NO_DATA
    : `${formatCount(achieved)} / ${formatCount(bound)}`;

// ---------------------------------------------------------------------------
// Basic building blocks
// ---------------------------------------------------------------------------

export const NotAvailable = ({ text = NO_DATA }: { text?: string }) => {
  const theme = useTheme();
  return (
    <Typography
      variant={'body2'}
      sx={{ color: theme.palette.vars.baseTextWeak }}
    >
      {text}
    </Typography>
  );
};

const useToneColor = () => {
  const theme = useTheme();
  return (tone: L9Tone): string => {
    switch (tone) {
      case 'positive':
        return theme.palette.vars.successIconDefault;
      case 'warning':
        return theme.palette.vars.warningIconDefault;
      case 'negative':
        return theme.palette.vars.negativeIconDefault;
      case 'info':
        return theme.palette.vars.infoIconDefault;
      default:
        return theme.palette.vars.controlIconDefault;
    }
  };
};

export const StatusTag = ({
  label,
  tone = 'neutral'
}: {
  label: string;
  tone?: L9Tone;
}) => {
  const theme = useTheme();
  const getColor = useToneColor();
  return (
    <Tag
      size={GeneralSize.Medium}
      icon={
        <Box
          component="span"
          sx={{
            display: 'inline-block',
            width: '8px !important',
            height: '8px !important',
            borderRadius: '50%',
            backgroundColor: getColor(tone)
          }}
        />
      }
      sx={{ backgroundColor: theme.palette.vars.controlBackgroundMedium }}
    >
      {label}
    </Tag>
  );
};

export const YesNoTag = ({
  value,
  yesTone = 'positive',
  noTone = 'neutral'
}: {
  value?: boolean | null;
  yesTone?: L9Tone;
  noTone?: L9Tone;
}) =>
  isMissing(value) ? (
    <NotAvailable />
  ) : (
    <StatusTag label={value ? 'Yes' : 'No'} tone={value ? yesTone : noTone} />
  );

export const PassFailTag = ({ passed }: { passed?: boolean | null }) =>
  isMissing(passed) ? (
    <NotAvailable />
  ) : (
    <StatusTag
      label={passed ? 'Pass' : 'Fail'}
      tone={passed ? 'positive' : 'negative'}
    />
  );

export const BulletList = ({ items }: { items: string[] }) => (
  <Box component="ul" sx={{ margin: 0, paddingLeft: '18px' }}>
    {items.map((item) => (
      <li key={item}>
        <Typography variant={'body2'}>{item}</Typography>
      </li>
    ))}
  </Box>
);

export const Reason = ({ text }: { text?: string | null }) => {
  const theme = useTheme();
  if (!text) return null;
  return (
    <Typography
      variant={'body2'}
      sx={{ color: theme.palette.vars.baseTextMedium }}
    >
      {text}
    </Typography>
  );
};

// Pass/fail with the failed items (steps, fields...) listed below.
export const CheckResult = ({
  check,
  failuresLabel = 'Failed'
}: {
  check?: L9Check | null;
  failuresLabel?: string;
}) => {
  if (!check) return <NotAvailable />;
  const failures = check.failures ?? [];
  return (
    <Stack direction="column" gap="6px" alignItems="flex-start">
      <PassFailTag passed={check.passed} />
      {failures.length > 0 && (
        <Stack direction="column" gap="2px">
          <Typography variant={'caption'}>{failuresLabel}:</Typography>
          <BulletList items={failures} />
        </Stack>
      )}
    </Stack>
  );
};

// Verdict label (extensible enum) with its reason and backing items.
export const VerdictResult = ({
  verdict,
  itemsLabel
}: {
  verdict?: L9Verdict | null;
  itemsLabel?: string;
}) => {
  if (!verdict?.label) return <NotAvailable />;
  const items = verdict.items ?? [];
  return (
    <Stack direction="column" gap="6px" alignItems="flex-start">
      <StatusTag
        label={humanizeLabel(verdict.label)}
        tone={getVerdictTone(verdict.label)}
      />
      <Reason text={verdict.reason} />
      {items.length > 0 && (
        <Stack direction="column" gap="2px">
          {itemsLabel && (
            <Typography variant={'caption'}>{itemsLabel}:</Typography>
          )}
          <BulletList items={items} />
        </Stack>
      )}
    </Stack>
  );
};

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export const TOOLTIP_MAX_WIDTH = 400;

// Info icon showing a help tooltip, at most 400px wide.
export const InfoTooltip = ({
  description,
  size = 14
}: {
  description: ReactNode;
  size?: number;
}) => (
  <Tooltip
    title={
      typeof description === 'string' ? (
        <Typography variant={'caption'}>{description}</Typography>
      ) : (
        description
      )
    }
    placement={'top'}
    slotProps={{ tooltip: { sx: { maxWidth: TOOLTIP_MAX_WIDTH } } }}
  >
    <Stack sx={{ alignSelf: 'flex-start' }}>
      <InfoOutlineIcon sx={{ width: size, height: size }} />
    </Stack>
  </Tooltip>
);

// Bold block heading with an optional help tooltip.
export const BlockTitle = ({
  title,
  description
}: {
  title: string;
  description?: string;
}) => (
  <Stack direction="row" alignItems="center" gap="4px">
    <Typography variant={'body2Semibold'}>{title}</Typography>
    {description && <InfoTooltip description={description} />}
  </Stack>
);

export const SubSection = ({
  title,
  description,
  children
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) => {
  const theme = useTheme();
  return (
    <Stack
      direction="column"
      gap="12px"
      sx={{
        padding: '16px',
        borderRadius: '8px',
        border: `1px solid ${theme.palette.vars.baseBorderWeak}`
      }}
    >
      <Stack direction="row" alignItems="center" gap="6px">
        <Typography
          variant={'captionSemibold'}
          sx={{
            color: theme.palette.vars.baseTextWeak,
            textTransform: 'uppercase',
            letterSpacing: '0.08em'
          }}
        >
          {title}
        </Typography>
        {description && <InfoTooltip description={description} />}
      </Stack>
      {children}
    </Stack>
  );
};

export const MetricRow = ({
  label,
  description,
  children
}: {
  label: string;
  description?: string;
  children: ReactNode;
}) => {
  const theme = useTheme();
  return (
    <Stack
      direction="row"
      gap="16px"
      alignItems="flex-start"
      sx={{
        paddingBottom: '8px',
        borderBottom: `1px solid ${theme.palette.vars.baseBorderWeak}`,
        '&:last-child': { borderBottom: 'none', paddingBottom: 0 }
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        gap="4px"
        sx={{ width: '280px', flexShrink: 0 }}
      >
        <Typography variant={'body2'}>{label}</Typography>
        {description && <InfoTooltip description={description} />}
      </Stack>
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
    </Stack>
  );
};

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

export interface SimpleTableProps {
  headers: string[];
  rows: ReactNode[][];
  // Optional totals row, rendered in bold.
  footer?: ReactNode[];
  // Columns after this index are right aligned.
  alignRightFrom?: number;
  // Sized to its content instead of the full width, so that the value columns
  // sit next to the first column, which keeps the width of a metric label.
  compact?: boolean;
}

export const SimpleTable = ({
  headers,
  rows,
  footer,
  alignRightFrom = 1,
  compact = false
}: SimpleTableProps) => {
  const theme = useTheme();
  const align = (index: number) => (index >= alignRightFrom ? 'right' : 'left');
  const cellSx = (index: number) =>
    compact && index === 0 ? { minWidth: '280px' } : undefined;

  return (
    // `alignSelf` keeps a column flex parent from stretching the table.
    <Table
      size="small"
      sx={compact ? { width: 'auto', alignSelf: 'flex-start' } : undefined}
    >
      <TableHead>
        <TableRow>
          {headers.map((header, index) => (
            <TableCell key={header} align={align(index)} sx={cellSx(index)}>
              <Typography
                variant={'captionSemibold'}
                sx={{ color: theme.palette.vars.baseTextWeak }}
              >
                {header}
              </Typography>
            </TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row, rowIndex) => (
          <TableRow key={rowIndex}>
            {row.map((cell, index) => (
              <TableCell key={index} align={align(index)} sx={cellSx(index)}>
                {typeof cell === 'string' ? (
                  <Typography variant={'body2'}>{cell}</Typography>
                ) : (
                  cell
                )}
              </TableCell>
            ))}
          </TableRow>
        ))}
        {footer && (
          <TableRow>
            {footer.map((cell, index) => (
              <TableCell key={index} align={align(index)} sx={cellSx(index)}>
                {typeof cell === 'string' ? (
                  <Typography variant={'body2Semibold'}>{cell}</Typography>
                ) : (
                  cell
                )}
              </TableCell>
            ))}
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
};
