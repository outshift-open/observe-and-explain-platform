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
import { SemanticGroupsInsight } from '@/types/oxp.type';
import { Tags } from '@/components';
import { Dayjs } from 'dayjs';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { SessionsInsightsTableWrapper } from '@/components/SessionsInsightsTable';

type MRT_ColumnDefList = TableProps<SemanticGroupsInsight>['columns'];

interface SemanticGroupsInsightsTableProps {
  data: SemanticGroupsInsight[];
  isLoading: boolean;
  isError?: boolean;
  startDate: Dayjs | null;
  endDate: Dayjs | null;
  startDateUnix: number;
  endDateUnix: number;
}

export const SemanticGroupsInsightsTable = ({
  data,
  isLoading,
  isError,
  startDate,
  endDate,
  startDateUnix,
  endDateUnix
}: SemanticGroupsInsightsTableProps) => {
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    {
      // priority: false,
      labels: false,
      sessionIds: false
    }
  );
  const [sorting, setSorting] = useState<MRT_SortingState>([
    { id: 'priority', desc: true }
  ]);

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'name',
        header: 'Insight',
        size: 250,
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
        accessorKey: 'groupName',
        header: 'Semantic Group'
      },
      {
        accessorKey: 'description',
        header: 'Description',
        size: 350,
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
        size: 200,
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
        accessorKey: 'sessionIds',
        header: 'Sessions',
        size: 100,
        accessorFn: ({ sessionIds }) => (
          <Typography variant={'body2'}>{sessionIds?.length ?? 0}</Typography>
        ),
        sortingFn: (rowA, rowB) => {
          return (
            (rowA.original.sessionIds?.length ?? 0) -
            (rowB.original.sessionIds?.length ?? 0)
          );
        }
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
    rowCount: data?.length,
    title: { label: 'Top Failures and Analysis' },
    topToolbarProps: {
      export: { enableExport: false }
    },
    enableSorting: true,
    enableColumnResizing: true,
    enableRowActions: true,
    renderEmptyRowsFallback: () => (
      <EmptyState
        title={'No Insights'}
        description={'Try adjusting your date range'}
      />
    ),

    state: { columnVisibility, sorting },
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: setSorting,

    titleExtension:
      startDate && endDate ? (
        <Stack direction="row" gap={'8px'} alignItems={'center'}>
          <Typography variant={'body2Semibold'}>
            {format(startDate.toDate(), 'MMM d, yyyy HH:mm:ss')}
          </Typography>
          <Typography variant={'body2Semibold'}>-</Typography>
          <Typography variant={'body2Semibold'}>
            {format(endDate.toDate(), 'MMM d, yyyy HH:mm:ss')}
          </Typography>
        </Stack>
      ) : undefined,

    muiTableBodyRowProps: {
      sx: {
        cursor: 'pointer',
        backgroundColor: 'transparent',
        '& > td': {
          backgroundColor: 'transparent !important'
        }
      }
    },
    muiTablePaperProps: {
      sx: {
        padding: '12px',
        backgroundColor: 'transparent',
        elevation: 0
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
    renderDetailPanel: ({ row }) => {
      return (
        <Box
          sx={{
            width: 'calc(100vw - 664px)',
            paddingLeft: '32px'
          }}
        >
          <SessionsInsightsTableWrapper
            startDate={startDateUnix}
            endDate={endDateUnix}
            semanticGroupId={row.original.groupId}
          />
        </Box>
      );
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
