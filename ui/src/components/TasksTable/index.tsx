/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { MaterialReactTable } from 'material-react-table';
import { CreateTableInstance, EmptyState, TableProps, Typography } from '@open-ui-kit/core';
import { useMemo } from 'react';

import { CustomTooltip as Tooltip } from '@/components';
import { getDisplayedResultsCount, getDisplayedResultsCountDollar } from '@/utils';
import { Task } from '@/types/oxp.type';
import { formatDurationMs } from '@/utils';
import { DotLabel } from '../DotLabel';
import { Stack, useTheme } from '@mui/material';

type MRT_ColumnDefList = TableProps<Task>['columns'];

export interface TasksTableProps {
  data: Task[];
}

export const TasksTable = ({ data }: TasksTableProps) => {
  const theme = useTheme();

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'name',
        header: 'Task'
      },
      {
        accessorKey: 'status',
        header: 'Status',
        size: 150,
        accessorFn: ({ status }) => {
          return <DotLabel dotColor={theme.palette.vars.successIconDefault} label={status} />;
        }
      },
      {
        accessorKey: 'duration',
        header: 'Duration',
        size: 150,
        accessorFn: ({ duration = 0 }) => {
          return <Typography variant={'inherit'}>{`${formatDurationMs(duration)}`}</Typography>;
        }
      },

      {
        accessorKey: 'cost',
        header: 'Cost ($/tokens)',
        enableSorting: false,
        accessorFn: ({ cost }) => {
          const costTokensNumberFormat = cost?.value ? getDisplayedResultsCount(Math.round(cost.value * 400000)) : '0';
          const costDollarNumberFormat = cost?.value ? getDisplayedResultsCountDollar(cost.value) : '0';

          const costDollar = `${costDollarNumberFormat}${cost?.value > 0 ? '$' : ''}`;

          const costTooltip = costDollar + `${cost?.value > 0 ? '/' + costTokensNumberFormat : ''}`;

          return (
            <Tooltip title={costTooltip}>
              <Stack direction="row" gap="4px">
                <Typography variant="inherit">{costDollar}</Typography>
                {cost?.value > 0 && (
                  <>
                    <Typography variant="inherit">/</Typography>
                    <Typography variant="inherit">{costTokensNumberFormat}</Typography>
                  </>
                )}
              </Stack>
            </Tooltip>
          );
        }
      }
      // {
      //   accessorKey: 'latency',
      //   header: 'Latency',
      //   accessorFn: ({ latency }) => {
      //     return <Typography variant={'inherit'}>{`${latency}ms`}</Typography>;
      //   }
      // }
    ],
    []
  );

  const tableRef = CreateTableInstance({
    data: data,
    columns,
    isLoading: false,
    rowCount: data?.length,
    enableTopToolbar: false,
    enableRowActions: true,

    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () => <EmptyState title={'No tasks'} description={'Try adjusting your filters'} />,

    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: 'transparent',
        elevation: 0
      }
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
