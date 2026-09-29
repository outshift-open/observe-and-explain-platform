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
import { useTheme } from '@mui/material/styles';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import type { LiveSession } from '@/types/oxpApi.type';

type MRT_ColumnDefList = TableProps<LiveSession>['columns'];

interface LiveSessionsTableProps {
  data: LiveSession[];
  isLoading: boolean;
  isError?: boolean;
  onSessionClick?: (session: LiveSession) => void;
  title?: string;
}

function getStatusColor(status: string): TagBackgroundColorVariants {
  switch (status) {
    case 'completed':
      return TagBackgroundColorVariants.AccentGWeak;
    case 'running':
      return TagBackgroundColorVariants.AccentAWeak;
    case 'failed':
      return TagBackgroundColorVariants.AccentFWeak;
    default:
      return TagBackgroundColorVariants.AccentEWeak;
  }
}

export const LiveSessionsTable = ({
  data,
  isLoading,
  isError,
  onSessionClick,
  title
}: LiveSessionsTableProps) => {
  const [columnVisibility, setColumnVisibility] =
    useState<MRT_VisibilityState>({});
  const [sorting, setSorting] = useState<MRT_SortingState>([
    { id: 'start_time', desc: true }
  ]);
  const theme = useTheme();

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'session_id',
        header: 'Session ID',
        size: 250,
        accessorFn: ({ session_id }) => {
          return (
            <Tooltip title={session_id} placement={'top'}>
              <Typography
                variant={'body2'}
                sx={{
                  textOverflow: 'ellipsis',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap'
                }}
              >
                {session_id}
              </Typography>
            </Tooltip>
          );
        }
      },
      {
        accessorKey: 'start_time',
        header: 'Start Time',
        size: 180,
        accessorFn: ({ start_time }) => {
          return (
            <Typography variant={'body2'}>
              {start_time
                ? format(new Date(start_time), 'MMM d, yyyy HH:mm:ss')
                : ''}
            </Typography>
          );
        },
        sortingFn: (rowA, rowB) => {
          const a = new Date(rowA.original.start_time).getTime();
          const b = new Date(rowB.original.start_time).getTime();
          return a - b;
        }
      },
      {
        accessorKey: 'end_time',
        header: 'End Time',
        size: 180,
        accessorFn: ({ end_time }) => {
          return (
            <Typography variant={'body2'}>
              {end_time
                ? format(new Date(end_time), 'MMM d, yyyy HH:mm:ss')
                : ''}
            </Typography>
          );
        },
        sortingFn: (rowA, rowB) => {
          const a = new Date(rowA.original.end_time).getTime();
          const b = new Date(rowB.original.end_time).getTime();
          return a - b;
        }
      },
      {
        accessorKey: 'status',
        header: 'Status',
        size: 120,
        accessorFn: ({ status }) => {
          return (
            <Tag color={getStatusColor(status)} size={GeneralSize.Medium}>
              {status}
            </Tag>
          );
        }
      }
    ],
    []
  );

  const tableRef = CreateTableInstance({
    data,
    columns,
    isLoading,
    rowCount: data?.length,
    title: { label: title ?? 'Live Sessions' },
    topToolbarProps: {
      export: { enableExport: false }
    },
    enableRowActions: false,
    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () => (
      <EmptyState
        title={'No Live Sessions'}
        description={'No active sessions found'}
      />
    ),
    state: { columnVisibility, sorting },
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: setSorting,

    muiTableBodyRowProps: ({ row }) => ({
      onClick: onSessionClick
        ? () => onSessionClick(row.original)
        : undefined,
      sx: {
        cursor: onSessionClick ? 'pointer' : 'default',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        '& > td': {
          backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`
        }
      }
    }),

    muiTablePaperProps: {
      sx: {
        padding: '12px',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: GLOBAL_BACKGROUND_COLOR, color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: {
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        color: '#ffffff',
        height: '40px'
      }
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
