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
import { SessionInsight } from '@/types/oxp.type';
import { Tags } from '@/components';
import { formatDurationMs } from '@/utils/stringUtils';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { ExecutionTrace } from '@/components/ExecutionTrace';
import { colorTokens } from '@/theme/colors';
import { PATHS } from '@/routes/routes';
import { useNavigate, useParams } from 'react-router-dom';

type MRT_ColumnDefList = TableProps<SessionInsight>['columns'];

interface SessionsInsightsTableProps {
  data: SessionInsight[];
  isLoading: boolean;
  onSessionClick?: (session: SessionInsight) => void;
}

export const SessionsInsightsTable = ({
  data,
  isLoading,
  onSessionClick
}: SessionsInsightsTableProps) => {
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    { labels: false, duration: false }
  );
  const [sorting, setSorting] = useState<MRT_SortingState>([
    { id: 'priority', desc: true }
  ]);

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'sessionId',
        header: 'Session ID',
        size: 250,
        accessorFn: ({ sessionId }) => (
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
        )
      },
      {
        accessorKey: 'name',
        header: 'Insight',
        size: 200,
        accessorFn: ({ name }) => (
          <Tooltip title={name} placement={'top'}>
            <Typography
              variant={'body2'}
              sx={{
                textOverflow: 'ellipsis',
                overflow: 'hidden',
                whiteSpace: 'nowrap'
              }}
            >
              {name}
            </Typography>
          </Tooltip>
        )
      },
      {
        accessorKey: 'description',
        header: 'Description',
        size: 300,
        accessorFn: ({ description }) => (
          <Tooltip title={description} placement={'top'}>
            <Typography
              variant={'body2'}
              sx={{
                textOverflow: 'ellipsis',
                overflow: 'hidden',
                whiteSpace: 'nowrap'
              }}
            >
              {description}
            </Typography>
          </Tooltip>
        )
      },
      {
        accessorKey: 'priority',
        header: 'Priority',
        size: 120,
        accessorFn: ({ priority }) => {
          const colorMap: Record<string, TagBackgroundColorVariants> = {
            high: TagBackgroundColorVariants.AccentFWeak,
            medium: TagBackgroundColorVariants.AccentEWeak,
            low: TagBackgroundColorVariants.AccentGWeak
          };
          return (
            <Tag
              color={
                colorMap[priority?.toLowerCase()] ??
                TagBackgroundColorVariants.AccentAWeak
              }
              size={GeneralSize.Medium}
            >
              {priority}
            </Tag>
          );
        },
        sortingFn: (rowA, rowB) => {
          const priorityOrder: Record<string, number> = {
            high: 3,
            medium: 2,
            low: 1
          };
          const a = priorityOrder[rowA.original.priority?.toLowerCase()] ?? 0;
          const b = priorityOrder[rowB.original.priority?.toLowerCase()] ?? 0;
          return a - b;
        }
      },
      {
        accessorKey: 'labels',
        header: 'Labels',
        size: 180,
        accessorFn: ({ labels }) => (
          <Tags
            tags={(labels ?? []).map((label) => ({
              name: label,
              color: TagBackgroundColorVariants.AccentAWeak
            }))}
            minDisplayed={2}
          />
        )
      },
      {
        accessorKey: 'duration',
        header: 'Duration',
        size: 120,
        accessorFn: ({ duration }) => (
          <Typography variant={'body2'}>
            {formatDurationMs(duration)}
          </Typography>
        )
      },
      {
        accessorKey: 'createdAt',
        header: 'Created',
        size: 180,
        accessorFn: ({ createdAt }) => (
          <Typography variant={'body2'}>
            {createdAt ? format(new Date(createdAt), 'MMM d, yyyy HH:mm') : ''}
          </Typography>
        ),
        sortingFn: (rowA, rowB) => {
          const a = new Date(rowA.original.createdAt).getTime() || 0;
          const b = new Date(rowB.original.createdAt).getTime() || 0;
          return a - b;
        }
      }
    ],
    []
  );

  const tableRef = CreateTableInstance({
    data,
    columns,
    isLoading,
    rowCount: data?.length ?? 0,
    title: { label: 'Sessions Insights' },
    topToolbarProps: {
      export: { enableExport: false }
    },
    enableSorting: true,
    enableColumnResizing: true,
    enableRowActions: true,
    renderEmptyRowsFallback: () => (
      <EmptyState
        title={'No Sessions Insights'}
        description={'No insights found for this group'}
      />
    ),

    state: { columnVisibility, sorting },
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: setSorting,

    muiTableBodyRowProps: ({ row }) => {
      return {
        sx: {
          cursor: 'pointer',
          backgroundColor: colorTokens.greyBackgroundDark,
          '& > td': {
            backgroundColor: `${colorTokens.greyBackgroundDark} !important`
          }
        },
        onClick: () => {
          onSessionClick?.(row.original);
        }
      };
    },
    muiTablePaperProps: {
      sx: {
        padding: '12px',
        backgroundColor: colorTokens.greyBackgroundDark,
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: colorTokens.greyBackgroundDark, color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: {
        backgroundColor: colorTokens.greyBackgroundDark,
        color: '#ffffff',
        height: '40px'
      }
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
