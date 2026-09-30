/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  MaterialReactTable,
  MRT_SortingState,
  MRT_VisibilityState
} from 'material-react-table';
import {
  CreateTableInstance,
  EmptyState,
  GeneralSize,
  TableProps,
  Tag,
  TagBackgroundColorVariants,
  Tooltip
} from '@open-ui-kit/core';
import { useMemo, useState } from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { format } from 'date-fns';
import { SessionWithStatefulEval } from '@/types/oxp.type';
import { CircleBadge, ExecutionTrace, SessionStatus, Tags } from '@/components';
import { Dayjs } from 'dayjs';
import { formatDurationMs } from '@/utils/stringUtils';
import { useTheme } from '@mui/material/styles';
import { getMetricPulseColor } from '@/utils/metrics';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';

type MRT_ColumnDefList = TableProps<SessionWithStatefulEval>['columns'];

// Columns whose data comes from stateful-eval (trajectory scoring). Dropped
// when the stateful_eval feature flag is off.
const STATEFUL_EVAL_COLUMN_KEYS = [
  'status',
  'metricPulse',
  'fatalErrors',
  'minorErrors'
];

interface SessionsTableProps {
  data: SessionWithStatefulEval[];
  isLoading: boolean;
  isError?: boolean;
  onReload?: () => void;
  startDate: Dayjs | null;
  endDate: Dayjs | null;
  onSessionClick?: (session: SessionWithStatefulEval) => void;
  showDateInterval?: boolean;
  defaultHiddenColumns?: string[];
  title?: string;
}

function getMetricTooltipContent(
  metricName: string,
  reasoning?: string
): React.ReactNode {
  if (!reasoning) {
    return metricName;
  }
  return (
    <Box>
      <Box sx={{ fontWeight: 600, marginBottom: '4px' }}>{metricName}</Box>
      <Box>{reasoning}</Box>
    </Box>
  );
}

export const SessionsTable = ({
  data,
  isLoading,
  isError,
  onReload,
  startDate,
  endDate,
  onSessionClick,
  showDateInterval = true,
  defaultHiddenColumns = [],
  title
}: SessionsTableProps) => {
  const statefulEvalEnabled = useFeatureFlag('stateful_eval');
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    {
      id: false,
      ...defaultHiddenColumns.reduce((acc: Record<string, boolean>, column) => {
        acc[column] = false;
        return acc;
      }, {})
    }
  );
  const [sorting, setSorting] = useState<MRT_SortingState>(
    statefulEvalEnabled ? [{ id: 'fatalErrors', desc: true }] : []
  );
  const theme = useTheme();

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'sessionId',
        header: 'Session ID',
        size: 124,
        accessorFn: ({ sessionId }) => {
          return (
            <Tooltip title={sessionId} placement={'top'}>
              <Typography
                variant={'body2'}
                sx={{
                  textOverflow: 'ellipsis',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap'
                }}
              >
                {sessionId}
              </Typography>
            </Tooltip>
          );
        }
      },
      {
        accessorKey: 'timestamp',
        header: 'Timestamp',
        size: 115,
        accessorFn: ({ timestamp }) => {
          return (
            <Typography variant={'body2'}>
              {timestamp
                ? format(
                    new Date(Number(timestamp) * 1000),
                    'MMM d, yyyy HH:mm:ss'
                  )
                : ''}
            </Typography>
          );
        },
        sortingFn: (rowA, rowB) => {
          const timestampA = Number(rowA.original.timestamp) ?? 0;
          const timestampB = Number(rowB.original.timestamp) ?? 0;
          return timestampA - timestampB;
        }
      },
      {
        accessorKey: 'agents',
        header: 'Agents',
        accessorFn: ({ agents }) => {
          const overflowAgents = structuredClone(agents ?? []);
          overflowAgents.shift();

          const OverflowTooltip = (
            <Stack direction="column" gap={'4px'}>
              {overflowAgents.map((agent) => (
                <Typography variant="caption" key={agent}>
                  {agent}
                </Typography>
              ))}
            </Stack>
          );

          return (
            <Stack
              gap="10px"
              flexDirection="row"
              alignItems={'center'}
              sx={{ cursor: 'pointer' }}
            >
              {
                <Tags
                  tags={(agents ?? [])
                    .filter((agent) => agent !== null)
                    .map((agent) => ({
                      name: agent,
                      color: TagBackgroundColorVariants.AccentAWeak
                    }))}
                  minDisplayed={1}
                />
              }
            </Stack>
          );
        }
      },
      {
        accessorKey: 'llms',
        header: 'LLMs',
        accessorFn: ({ llms }) => {
          const overflowLLMs = structuredClone(llms ?? []);
          overflowLLMs.shift();

          const OverflowTooltip = (
            <Stack direction="column" gap={'4px'}>
              {overflowLLMs.map((llm) => (
                <Typography variant="caption" key={llm}>
                  {llm}
                </Typography>
              ))}
            </Stack>
          );

          return (
            <Stack
              gap="10px"
              flexDirection="row"
              alignItems={'center'}
              sx={{ cursor: 'pointer' }}
            >
              {llms?.[0] && (
                <Tag
                  color={TagBackgroundColorVariants.AccentGWeak}
                  size={GeneralSize.Medium}
                >
                  {llms[0]}
                </Tag>
              )}
              {overflowLLMs.length > 0 && (
                <Tooltip title={OverflowTooltip} placement={'top'}>
                  <Box>
                    <Tag
                      color={TagBackgroundColorVariants.AccentGWeak}
                      size={GeneralSize.Medium}
                    >
                      +{overflowLLMs.length}
                    </Tag>
                  </Box>
                </Tooltip>
              )}
            </Stack>
          );
        }
      },
      {
        accessorKey: 'tokens',
        header: 'Tokens',
        accessorFn: ({ tokens }) => {
          return (
            <Typography variant={'body2'}>
              {tokens.toLocaleString('en-US')}
            </Typography>
          );
        }
      },
      {
        accessorKey: 'status',
        header: 'Status',
        size: 70,
        accessorFn: ({ statefulEval }) => {
          const status = statefulEval?.reasoningJson
            ?.trajectory_score as number;
          return <SessionStatus status={status} />;
        }
      },
      {
        accessorKey: 'metricPulse',
        header: 'Metric Pulse',
        size: 100,
        accessorFn: ({ statefulEval }) => {
          const intentRecognitionFatal =
            statefulEval?.reasoningJson?.fatal_failures?.find(
              (f: { metric: string }) => f.metric === 'IntentRecognition'
            );
          const relevanceFatal =
            statefulEval?.reasoningJson?.fatal_failures?.find(
              (f: { metric: string }) => f.metric === 'Relevancy'
            );
          const groundednessFatal =
            statefulEval?.reasoningJson?.fatal_failures?.find(
              (f: { metric: string }) => f.metric === 'Groundedness'
            );

          const intentRecognitionMinor =
            statefulEval?.reasoningJson?.minor_failures?.find(
              (f: { metric: string }) => f.metric === 'IntentRecognition'
            );
          const relevanceMinor =
            statefulEval?.reasoningJson?.minor_failures?.find(
              (f: { metric: string }) => f.metric === 'Relevancy'
            );
          const groundednessMinor =
            statefulEval?.reasoningJson?.minor_failures?.find(
              (f: { metric: string }) => f.metric === 'Groundedness'
            );

          const intentRecognitionScore = intentRecognitionFatal
            ? 'fatal'
            : intentRecognitionMinor
              ? 'warning'
              : 'success';
          const relevanceScore = relevanceFatal
            ? 'fatal'
            : relevanceMinor
              ? 'warning'
              : 'success';
          const groundednessScore = groundednessFatal
            ? 'fatal'
            : groundednessMinor
              ? 'warning'
              : 'success';
          return (
            <Stack direction="row" gap={'4px'}>
              <Tooltip
                title={getMetricTooltipContent(
                  'Intent recognition',
                  intentRecognitionFatal?.reasoning ??
                    intentRecognitionMinor?.reasoning
                )}
                placement={'top'}
                slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
              >
                <Box>
                  <CircleBadge
                    letter={'I'}
                    color={getMetricPulseColor(intentRecognitionScore, theme)}
                  />
                </Box>
              </Tooltip>
              <Tooltip
                title={getMetricTooltipContent(
                  'Relevancy',
                  relevanceFatal?.reasoning ?? relevanceMinor?.reasoning
                )}
                placement={'top'}
                slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
              >
                <Box>
                  <CircleBadge
                    letter={'R'}
                    color={getMetricPulseColor(relevanceScore, theme)}
                  />
                </Box>
              </Tooltip>
              <Tooltip
                title={getMetricTooltipContent(
                  'Groundedness',
                  groundednessFatal?.reasoning ?? groundednessMinor?.reasoning
                )}
                placement={'top'}
                slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
              >
                <Box>
                  <CircleBadge
                    letter={'G'}
                    color={getMetricPulseColor(groundednessScore, theme)}
                  />
                </Box>
              </Tooltip>
            </Stack>
          );
        }
      },
      {
        accessorKey: 'fatalErrors',
        header: 'Fatal',
        size: 60,
        accessorFn: ({ statefulEval }) => {
          const fatalErrors =
            (statefulEval?.reasoningJson?.total_fatal as number) ?? 0;
          return (
            <Typography
              variant={'body2'}
              sx={{ color: theme.palette.vars.negativeIconDefault }}
            >
              {fatalErrors}
            </Typography>
          );
        },
        sortingFn: (rowA, rowB) => {
          const fatalErrorsA =
            (rowA.original.statefulEval?.reasoningJson
              ?.total_fatal as number) ?? 0;
          const fatalErrorsB =
            (rowB.original.statefulEval?.reasoningJson
              ?.total_fatal as number) ?? 0;
          return fatalErrorsA - fatalErrorsB;
        }
      },
      {
        accessorKey: 'minorErrors',
        header: 'Minors',
        size: 80,
        accessorFn: ({ statefulEval }) => {
          const minorErrors =
            (statefulEval?.reasoningJson?.total_minor as number) ?? 0;
          return (
            <Typography
              variant={'body2'}
              sx={{ color: theme.palette.vars.warningIconDefault }}
            >
              {minorErrors}
            </Typography>
          );
        },
        sortingFn: (rowA, rowB) => {
          const minorErrorsA =
            (rowA.original.statefulEval?.reasoningJson
              ?.total_minor as number) ?? 0;
          const minorErrorsB =
            (rowB.original.statefulEval?.reasoningJson
              ?.total_minor as number) ?? 0;
          return minorErrorsA - minorErrorsB;
        }
      },
      {
        accessorKey: 'cost',
        header: 'Cost',
        size: 70,
        accessorFn: ({ cost }) => {
          const numeric = Number(cost);
          const formatted = Number.isFinite(numeric) ? numeric.toFixed(3) : '0';
          return <Typography variant={'body2'}>${formatted}</Typography>;
        }
      },
      {
        accessorKey: 'duration',
        header: 'Duration',
        size: 90,
        accessorFn: ({ duration }) => {
          return (
            <Typography variant={'body2'}>
              {formatDurationMs(duration)}
            </Typography>
          );
        }
      }
      // {
      //   accessorKey: 'name',
      //   header: 'Name',
      //   size: 140
      // },
      // {
      //   accessorKey: 'externalId',
      //   header: 'External Id',
      //   size: 150
      // }
      // {
      //   accessorKey: 'totalLatency',
      //   header: 'Total latency',
      //   accessorFn: ({ totalLatency }) => {
      //     return <Typography variant={'inherit'}>{`${totalLatency}ms`}</Typography>;
      //   }
      // }
    ],
    []
  );

  const visibleColumns = useMemo<MRT_ColumnDefList>(
    () =>
      statefulEvalEnabled
        ? columns
        : columns?.filter(
            (col) =>
              !STATEFUL_EVAL_COLUMN_KEYS.includes(
                (col as { accessorKey?: string }).accessorKey ?? ''
              )
          ),
    [columns, statefulEvalEnabled]
  );

  const tableRef = CreateTableInstance({
    data: data,
    columns: visibleColumns,
    isLoading: isLoading,
    rowCount: data?.length,
    title: { label: title ?? '' },
    topToolbarProps: {
      export: { enableExport: false },
      // enableArrangeColumns: false,
      onReload: onReload
    },
    // enableTopToolbar: false,
    enableRowActions: true,

    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () => (
      <EmptyState
        title={'No Sessions'}
        description={'Try adjusting your filters'}
      />
    ),

    state: { columnVisibility, sorting },
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: setSorting,

    titleExtension:
      showDateInterval && startDate && endDate ? (
        <Stack direction="row" gap={'8px'} alignItems={'center'}>
          <Typography variant={'body2Semibold'}>
            {startDate
              ? format(startDate.toDate(), 'MMM d, yyyy HH:mm:ss')
              : ''}
          </Typography>
          <Typography variant={'body2Semibold'}>-</Typography>
          <Typography variant={'body2Semibold'}>
            {endDate ? format(endDate.toDate(), 'MMM d, yyyy HH:mm:ss') : ''}
          </Typography>
        </Stack>
      ) : undefined,

    muiTableBodyRowProps: ({ row }) => {
      return {
        onClick: onSessionClick
          ? () => onSessionClick(row.original)
          : undefined,
        sx: {
          cursor: 'pointer',
          backgroundColor: 'transparent',
          '& > td': {
            backgroundColor: 'transparent !important'
          }
        }
      };
    },

    muiTablePaperProps: {
      sx: {
        padding: '12px',
        backgroundColor: 'transparent',
        elevation: 0
      }
    },
    // Shrink the footer "Rows per page" Select. open-ui-kit hard-codes
    // width: 285px on the Select (getSelectStyles, a single-class rule), so we
    // override it scoped to the bottom toolbar — this only affects that select
    // and out-specifies the library rule without editing open-ui-kit.
    muiBottomToolbarProps: {
      sx: {
        '& .MuiInputBase-root': {
          width: '80px'
        }
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: GLOBAL_BACKGROUND_COLOR, color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: {
        backgroundColor: 'transparent',
        color: '#ffffff',
        height: '40px'
      }
    },
    renderDetailPanel: ({ row }) => (
      <Box
        sx={{
          maxHeight: 400,
          overflowY: 'auto',
          paddingLeft: '16px',
          backgroundColor: GLOBAL_BACKGROUND_COLOR
        }}
      >
        <ExecutionTrace sessionId={row.original.sessionId} />
      </Box>
    )
  });

  return <MaterialReactTable table={tableRef} />;
};
