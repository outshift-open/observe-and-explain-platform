/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { MaterialReactTable } from 'material-react-table';
import { CreateTableInstance, TableProps } from '@open-ui-kit/core';
import { useMemo } from 'react';
import { Typography, useTheme } from '@mui/material';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import { AgentAnalyzeImpactAssessment } from './types';
import { formatMetricValue } from '@/utils/metrics';
import { Unit } from '@/types/oxp.type';
import { PATHS } from '@/routes/routes';
import { useNavigate, useParams } from 'react-router-dom';

type MRT_ColumnDefList = TableProps<AgentAnalyzeImpactAssessment>['columns'];

interface AgentImpactAssessmentTableProps {
  data: AgentAnalyzeImpactAssessment[];
  isLoading: boolean;
  isError?: boolean;
}

export const AgentImpactAssessmentTable = ({ data, isLoading, isError }: AgentImpactAssessmentTableProps) => {
  const navigate = useNavigate();
  const { applicationId } = useParams();
  const theme = useTheme();

  const outlierColor = theme.palette.vars.negativeIconDefault;

  const renderMetricCell = (value: number, outlierMetricName: string, outlierMetrics: string[]) => {
    const isOutlier = outlierMetrics.includes(outlierMetricName);
    const formatted = formatMetricValue(value, Unit.Percentage);
    return isOutlier ? (
      <Typography variant="body2" sx={{ color: outlierColor }}>
        {formatted}
      </Typography>
    ) : (
      formatted
    );
  };

  const columns = useMemo<MRT_ColumnDefList>(
    () => [
      {
        accessorKey: 'sessionId',
        header: 'Session ID',
        size: 300
      },
      {
        accessorKey: 'cost',
        header: 'Cost',
        accessorFn: ({ cost, outlierMetrics }) => renderMetricCell(cost, 'Cost', outlierMetrics)
      },
      {
        accessorKey: 'toolUtilizationAccuracy',
        header: 'Tool Utilization Accuracy',
        accessorFn: ({ toolUtilizationAccuracy, outlierMetrics }) =>
          renderMetricCell(toolUtilizationAccuracy, 'ToolUtilizationAccuracy', outlierMetrics)
      },
      {
        accessorKey: 'responseCompleteness',
        header: 'Response Completeness',
        accessorFn: ({ responseCompleteness, outlierMetrics }) =>
          renderMetricCell(responseCompleteness, 'ResponseCompleteness', outlierMetrics)
      },
      {
        accessorKey: 'intentRecognitionAccuracy',
        header: 'Intent Recognition Accuracy',
        accessorFn: ({ intentRecognitionAccuracy, outlierMetrics }) =>
          renderMetricCell(intentRecognitionAccuracy, 'IntentRecognitionAccuracy', outlierMetrics)
      },
      {
        accessorKey: 'answerRelevancy',
        header: 'Answer Relevancy',
        accessorFn: ({ answerRelevancy, outlierMetrics }) =>
          renderMetricCell(answerRelevancy, 'AnswerRelevancy', outlierMetrics)
      },
      {
        accessorKey: 'groundedness',
        header: 'Groundedness',
        accessorFn: ({ groundedness, outlierMetrics }) => renderMetricCell(groundedness, 'Groundedness', outlierMetrics)
      }
    ],
    [outlierColor]
  );

  const tableRef = CreateTableInstance({
    data: data,
    columns,
    isLoading: isLoading,
    rowCount: data?.length,
    initialState: {
      sorting: [{ id: 'cost', desc: true }]
    },
    title: { label: 'Impact Assessment for metrics' },
    topToolbarProps: {
      export: { enableExport: false }
    },
    muiTableBodyRowProps: ({ row }) => {
      return {
        sx: {
          cursor: 'pointer',
          backgroundColor: GLOBAL_BACKGROUND_COLOR,
          '& > td': {
            backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`
          }
        },
        onClick: () => {
          navigate(`${PATHS.applicationCollectSession.replace(':applicationId', applicationId ?? '').replace(':sessionId', row.original.sessionId)}`);
        }
      };
    },

    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: `${GLOBAL_BACKGROUND_COLOR}`,
        elevation: 0
      }
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: `${GLOBAL_BACKGROUND_COLOR}`, color: '#ffffff' }
    },
    muiTableBodyCellProps: {
      sx: { backgroundColor: `${GLOBAL_BACKGROUND_COLOR}`, color: '#ffffff', height: '40px' }
    }
  });

  return <MaterialReactTable table={tableRef} />;
};
