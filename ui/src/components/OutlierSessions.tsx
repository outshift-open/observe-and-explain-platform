/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { MaterialReactTable, MRT_VisibilityState } from 'material-react-table';
import { CreateTableInstance, EmptyState, TableProps, TagBackgroundColorVariants, Tooltip } from '@open-ui-kit/core';
import { useMemo, useState } from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { format } from 'date-fns';
import { OutlierSession, Unit } from '@/types/oxp.type';
import { Dayjs } from 'dayjs';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { OutlierMetricsTable, Tags } from '@/components';

type MRT_ColumnDefList = TableProps<OutlierSession>['columns'];

interface OutlierSessionsProps {
  data: OutlierSession[];
  isLoading: boolean;
  isError?: boolean;
  onReload?: () => void;
  startDate: Dayjs | null;
  endDate: Dayjs | null;
  onSessionClick?: (session: OutlierSession) => void;
  showDateInterval?: boolean;
  defaultHiddenColumns?: string[];
  title?: string;
}

export const OutlierSessions = ({
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
}: OutlierSessionsProps) => {
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>({
    id: false,
    ...defaultHiddenColumns.reduce((acc: Record<string, boolean>, column) => {
      acc[column] = false;
      return acc;
    }, {})
  });

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'sessionId',
        header: 'Session ID',
        size: 250,
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
        accessorKey: 'metrics',
        header: 'Outlier Metrics',
        accessorFn: ({ metrics }) => {
          return (
            <Tags tags={metrics.map((metric) => ({ name: metric.metricName, color: TagBackgroundColorVariants.AccentAWeak }))} minDisplayed={2} />
          );
        }
      }
    ],
    []
  );

  const tableRef = CreateTableInstance({
    data: data,
    columns,
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
    renderEmptyRowsFallback: () => <EmptyState title={'No Sessions'} description={'Try adjusting your filters'} />,

    state: { columnVisibility },
    onColumnVisibilityChange: setColumnVisibility,

    titleExtension: showDateInterval ? (
      <Stack direction="row" gap={'8px'} alignItems={'center'}>
        <Typography variant={'body2Semibold'}>{startDate ? format(startDate.toDate(), 'MMM d, yyyy HH:mm:ss') : ''}</Typography>
        <Typography variant={'body2Semibold'}>-</Typography>
        <Typography variant={'body2Semibold'}>{endDate ? format(endDate.toDate(), 'MMM d, yyyy HH:mm:ss') : ''}</Typography>
      </Stack>
    ) : undefined,

    muiTableBodyRowProps: ({ row }) => {
      return {
        onClick: onSessionClick ? () => onSessionClick(row.original as OutlierSession) : undefined,
        sx: {
          cursor: 'pointer',
          backgroundColor: GLOBAL_BACKGROUND_COLOR,
          '& > td': {
            backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`
          },
          '& > td:first-of-type:not(.Mui-TableBodyCell-DetailPanel)': {
            width: '56px !important',
            minWidth: '56px !important',
            maxWidth: '56px !important'
          }
        }
      };
    },

    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: {
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        color: '#ffffff',
        '&:first-of-type': {
          width: '56px !important',
          minWidth: '56px !important',
          maxWidth: '56px !important'
        }
      }
    },
    muiTableBodyCellProps: {
      sx: { backgroundColor: GLOBAL_BACKGROUND_COLOR, color: '#ffffff', height: '40px' }
    },
    renderDetailPanel: ({ row }) => (
      <Box sx={{ paddingLeft: '48px' }}>
        <OutlierMetricsTable sessionId={row.original.sessionId} outlierMetrics={row.original.metrics} />
      </Box>
    )
  });

  return <MaterialReactTable table={tableRef} />;
};
