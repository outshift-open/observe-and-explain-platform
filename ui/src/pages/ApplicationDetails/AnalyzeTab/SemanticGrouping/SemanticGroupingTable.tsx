/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { Typography, useTheme } from '@mui/material';
import { MaterialReactTable, MRT_VisibilityState } from 'material-react-table';
import {
  CreateTableInstance,
  EmptyState,
  GeneralSize,
  TableProps,
  Tag,
  TagBackgroundColorVariants
} from '@open-ui-kit/core';
import { SemanticGroup } from '@/types/oxp.type';
import { getScoreColor } from '@/utils/metrics';

type MRT_ColumnDefList = TableProps<SemanticGroup>['columns'];

export interface SemanticGroupingTableProps {
  data: SemanticGroup[];
  isLoading?: boolean;
  isError?: boolean;
  onReload?: () => void;
  onRowClick?: (row: SemanticGroup) => void;
}

export const SemanticGroupingTable = ({
  data,
  isLoading = false,
  isError = false,
  onReload,
  onRowClick
}: SemanticGroupingTableProps) => {
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    {
      id: false,
      group_summary: false
    }
  );
  const theme = useTheme();

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'group_name',
        header: 'Group Name',
        size: 280
      },
      {
        accessorKey: 'group_summary',
        header: 'Group Summary',
        size: 280
      },
      {
        accessorKey: 'overall_reliability',
        header: 'Reliability',
        size: 120,
        accessorFn: ({ overall_reliability = 0 }) =>
          Math.round(overall_reliability * 100),
        Cell: ({ cell }) => {
          const reliabilityScore = cell.getValue<number>();
          return (
            <Typography
              variant={'body2'}
              sx={{ color: getScoreColor(reliabilityScore, theme) }}
            >
              {reliabilityScore}%
            </Typography>
          );
        }
      },
      {
        accessorKey: 'overall_quality',
        header: 'Quality',
        size: 120,
        accessorFn: ({ overall_quality = 0 }) =>
          Math.round(overall_quality * 100),
        Cell: ({ cell }) => {
          const qualityScore = cell.getValue<number>();
          return (
            <Typography
              variant={'body2'}
              sx={{ color: getScoreColor(qualityScore, theme) }}
            >
              {qualityScore}%
            </Typography>
          );
        }
      },
      {
        accessorKey: 'overall_performance',
        header: 'Performance',
        size: 120,
        accessorFn: ({ overall_performance = 0 }) =>
          Math.round(overall_performance * 100),
        Cell: ({ cell }) => {
          const performanceScore = cell.getValue<number>();
          return (
            <Typography
              variant={'body2'}
              sx={{ color: getScoreColor(performanceScore, theme) }}
            >
              {performanceScore}%
            </Typography>
          );
        }
      },
      {
        accessorKey: 'id',
        header: 'ID',
        size: 280,
        accessorFn: ({ id }) => (
          <Tag
            color={TagBackgroundColorVariants.AccentAWeak}
            size={GeneralSize.Medium}
          >
            {id}
          </Tag>
        )
      },
      {
        accessorKey: 'n_sessions',
        header: 'Count',
        size: 100
      }
    ],
    [theme]
  );

  const tableRef = CreateTableInstance({
    titleExtension: <Typography variant={'h6'}>Semantic Groups</Typography>,
    data: data,
    columns,
    isLoading: isLoading,
    rowCount: data?.length,
    topToolbarProps: {
      export: { enableExport: false },
      onReload: onReload
    },
    enableRowActions: true,
    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () => (
      <EmptyState title={'No Groups Found'} description={''} />
    ),
    state: { columnVisibility },
    onColumnVisibilityChange: setColumnVisibility,
    muiTableBodyRowProps: ({ row }) => {
      return {
        onClick: (e) => {
          e.stopPropagation();
          onRowClick?.(row.original);
        },
        sx: {
          cursor: 'pointer',
          backgroundColor: 'transparent',
          '& > td': {
            backgroundColor: `transparent !important`
          }
        }
      };
    },
    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: `transparent`,
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: '#0a0e17', color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: {
        backgroundColor: 'transparent',
        color: '#ffffff',
        height: '40px'
      }
    }
  });

  if (isError) {
    return <>An error occurred!</>;
  }

  return <MaterialReactTable table={tableRef} />;
};
