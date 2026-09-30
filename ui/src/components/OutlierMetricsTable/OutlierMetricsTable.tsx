/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { MaterialReactTable } from 'material-react-table';
import { CreateTableInstance, EmptyState, GeneralSize, TableProps, Tag, TagBackgroundColorVariants } from '@open-ui-kit/core';
import { useMemo } from 'react';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { OutlierMetricWithRootContributorAgent } from './types';

type MRT_ColumnDefList = TableProps<OutlierMetricWithRootContributorAgent>['columns'];

interface OutlierMetricsTableProps {
  data: OutlierMetricWithRootContributorAgent[];
  isLoading: boolean;
  isError?: boolean;
}

export const OutlierMetricsTable = ({ data, isLoading, isError }: OutlierMetricsTableProps) => {
  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'metricName',
        header: 'Metric'
      },
      {
        accessorKey: 'metricValue',
        header: 'Outlier Value'
      },
      {
        accessorKey: 'expectedValue',
        header: 'Expected Value'
      },
      {
        accessorKey: 'rootContributorAgent',
        header: 'Root Contributor Agent',
        accessorFn: ({ rootContributorAgent }) => {
          return (
            <Tag color={TagBackgroundColorVariants.AccentFWeak} size={GeneralSize.Medium}>
              {rootContributorAgent}
            </Tag>
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
    enableTopToolbar: false,
    muiTableBodyRowProps: ({ row }) => {
      return {
        sx: {
          cursor: 'pointer',
          backgroundColor: '#00001f',
          '& > td': {
            backgroundColor: '#00001f !important'
          }
        }
      };
    },

    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: '#00001f',
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: '#00001f', color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: { backgroundColor: '#00001f', color: '#ffffff', height: '40px' }
    },
    renderEmptyRowsFallback: () => <EmptyState title={'No outlier metrics found'} description={''} />
  });

  return <MaterialReactTable table={tableRef} />;
};
