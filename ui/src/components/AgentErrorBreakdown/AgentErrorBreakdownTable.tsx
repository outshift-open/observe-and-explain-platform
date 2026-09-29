/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { MaterialReactTable } from 'material-react-table';
import { CreateTableInstance, EmptyState, GeneralSize, TableProps, Tag, TagBackgroundColorVariants } from '@open-ui-kit/core';
import { useMemo } from 'react';
import { Typography } from '@mui/material';
import type { ErrorItem } from '@/types/oxp.type';
import { CustomTooltip } from '@/components';
import { capitalizeFirstLetter } from '@/utils';

type MRT_ColumnDefList = TableProps<ErrorItem>['columns'];

interface AgentErrorBreakdownTableProps {
  data: ErrorItem[];
  isLoading: boolean;
  isError: boolean;
  onReload?: () => void;
}

export const AgentErrorBreakdownTable = ({ data, isLoading, isError, onReload }: AgentErrorBreakdownTableProps) => {
  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'name',
        header: 'Name',
        size: 250,
        accessorFn: ({ name }) => {
          return (
            <CustomTooltip title={name} placement={'top'} sx={{ maxWidth: '500px' }}>
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
            </CustomTooltip>
          );
        }
      },
      {
        accessorKey: 'description',
        header: 'Description',
        size: 250,
        accessorFn: ({ description }) => {
          return (
            <CustomTooltip
              title={description}
              placement={'top'}
              slotProps={{
                tooltip: {
                  sx: {
                    whiteSpace: 'pre-wrap',
                    maxWidth: 700
                  }
                }
              }}
            >
              <Typography
                variant={'body2'}
                sx={{
                  textOverflow: 'ellipsis',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap !important'
                }}
              >
                {description}
              </Typography>
            </CustomTooltip>
          );
        }
      },
      {
        accessorKey: 'count',
        header: 'Count',
        size: 100
      },
      {
        accessorKey: 'source',
        header: 'Source',
        size: 100,
        accessorFn: ({ source }) => {
          return (
            <Tag
              color={
                source === 'LLM'
                  ? TagBackgroundColorVariants.AccentGWeak
                  : source === 'Tool'
                    ? TagBackgroundColorVariants.AccentAWeak
                    : TagBackgroundColorVariants.AccentJWeak
              }
              size={GeneralSize.Medium}
            >
              {capitalizeFirstLetter(source)}
            </Tag>
          );
        }
      },
      {
        accessorKey: 'sourceName',
        header: 'Source Name',
        accessorFn: ({ sourceName }) => {
          return <Typography variant={'body2'}>{sourceName}</Typography>;
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
    title: { label: 'Error Breakdown' },
    topToolbarProps: {
      export: { enableExport: false },
      onReload: onReload
    },
    enableRowActions: true,

    enableSorting: true,
    enableColumnResizing: true,
    initialState: {
      sorting: [{ id: 'count', desc: true }]
    },
    renderEmptyRowsFallback: () => <EmptyState title={'Agent is healthy'} description={'No errors found'} />
  });

  if (isError) {
    return <>An error occurred!</>;
  }

  return <MaterialReactTable table={tableRef} />;
};
