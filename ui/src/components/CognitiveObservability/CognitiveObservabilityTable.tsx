/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/routes/routes';
import { MaterialReactTable, MRT_SortingState } from 'material-react-table';
import {
  CreateTableInstance,
  EmptyState,
  TableProps,
  Tooltip
} from '@open-ui-kit/core';
import { Typography, useTheme } from '@mui/material';
import CircleIcon from '@mui/icons-material/Circle';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { format } from 'date-fns';
import {
  SessionsWithCognitiveObservability,
  SessionWithCognitiveObservability
} from '@/types/oxp.type';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { CustomTooltip, Tags } from '@/components';
import { getScoreColor } from '@/utils/metrics';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import {
  getFailuresAboveThreshold,
  getRemediationsAboveThreshold,
  getSortedFailures
} from './utils';

type MRT_ColumnDefList =
  TableProps<SessionWithCognitiveObservability>['columns'];

interface CognitiveObservabilityTableProps {
  sessionsWithCognitiveObservability?: SessionsWithCognitiveObservability;
  // Failures count only when their confidence is above this fraction (0-1).
  threshold: number;
  selectedFailure?: string | null;
  isLoading?: boolean;
  onReload?: () => void;
  onClearFilter?: () => void;
}

const maxConfidence = (
  session: SessionWithCognitiveObservability,
  threshold: number
) => getFailuresAboveThreshold(session, threshold)[0]?.confidence ?? 0;

export const CognitiveObservabilityTable = ({
  sessionsWithCognitiveObservability,
  threshold,
  selectedFailure = null,
  isLoading = false,
  onReload,
  onClearFilter
}: CognitiveObservabilityTableProps) => {
  const theme = useTheme();
  const [sorting, setSorting] = useState<MRT_SortingState>([]);
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const thresholdPercent = Math.round(threshold * 100);
  const sessionCount =
    sessionsWithCognitiveObservability?.sessions?.length ?? 0;

  const onSessionClick = (session: SessionWithCognitiveObservability) => {
    navigate(
      PATHS.applicationCollectSessionTab
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
        .replace(':sessionTab', 'cognitive-observability')
    );
  };

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'sessionId',
        header: 'Session ID',
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
        accessorKey: 'timestamp',
        header: 'Timestamp',
        size: 115,
        accessorFn: ({ timestamp }) => (
          <Typography variant={'body2'}>
            {timestamp
              ? format(
                  new Date(Number(timestamp) * 1000),
                  'MMM d, yyyy HH:mm:ss'
                )
              : ''}
          </Typography>
        ),
        sortingFn: (rowA, rowB) =>
          (Number(rowA.original.timestamp) || 0) -
          (Number(rowB.original.timestamp) || 0)
      },
      {
        id: 'cognitiveFailures',
        header: 'Cognitive Failures',
        enableSorting: false,
        // Highest confidence first, so the visible tag is the one that
        // qualifies the session; the dot is colored by confidence.
        accessorFn: (session) => (
          <Tags
            tags={getSortedFailures(session).map((failure) => ({
              name: `${failure.name}: ${Math.round(failure.confidence * 100)}%`
            }))}
            minDisplayed={1}
          />
        )
      },
      {
        id: 'open',
        header: '',
        size: 30,
        enableSorting: false,
        enableResizing: false,
        accessorFn: () => (
          <ChevronRightIcon
            sx={{ color: theme.palette.vars.baseTextWeak, display: 'block' }}
          />
        )
      }
    ],
    [threshold, theme]
  );

  const tableRef = CreateTableInstance({
    data: sessionsWithCognitiveObservability?.sessions ?? [],
    columns,
    isLoading,
    rowCount: sessionCount,
    title: { label: 'Session Cognitive Insights' },
    titleExtension: (
      <CustomTooltip
        title={
          <Typography variant={'caption'}>
            {`Sessions with at least one failure above ${thresholdPercent}% confidence.`}
          </Typography>
        }
        placement={'top'}
        sx={{ maxWidth: '550px' }}
      >
        <InfoOutlineIcon
          sx={{ width: '14px', height: '14px', cursor: 'pointer' }}
        />
      </CustomTooltip>
    ),
    topToolbarProps: {
      export: { enableExport: false },
      onReload
    },
    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () =>
      selectedFailure ? (
        <EmptyState
          title={'No sessions match this filter'}
          description={`No session has "${selectedFailure}" above ${thresholdPercent}% confidence.`}
          actionTitle={'Clear filter'}
          actionCallback={onClearFilter}
        />
      ) : (
        <EmptyState
          title={'No sessions with failures'}
          description={`No session has a cognitive failure above ${thresholdPercent}% confidence. Try lowering the threshold.`}
        />
      ),
    state: { sorting },
    onSortingChange: setSorting,
    muiTableBodyRowProps: ({ row }) => ({
      onClick: () => onSessionClick(row.original),
      sx: {
        cursor: 'pointer',
        backgroundColor: 'transparent',
        '& > td': {
          backgroundColor: 'transparent !important'
        },
        '&:hover > td': {
          backgroundColor: `${theme.palette.action.hover} !important`
        }
      }
    }),
    muiTablePaperProps: {
      sx: {
        padding: '12px',
        backgroundColor: 'transparent',
        elevation: 0
      }
    },
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
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
