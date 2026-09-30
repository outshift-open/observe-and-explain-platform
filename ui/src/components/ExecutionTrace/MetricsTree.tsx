/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import Box from '@mui/material/Box';
import { animated, useSpring } from '@react-spring/web';
import Collapse from '@mui/material/Collapse';
import { TransitionProps } from '@mui/material/transitions';
import { styled } from '@mui/material/styles';
import { RichTreeView } from '@mui/x-tree-view/RichTreeView';
import { useTreeItem, UseTreeItemParameters } from '@mui/x-tree-view/useTreeItem';
import { TreeItemLabel } from '@mui/x-tree-view/TreeItem';
import { TreeItemProvider } from '@mui/x-tree-view/TreeItemProvider';
import { useTreeItemModel } from '@mui/x-tree-view/hooks';
import React from 'react';

import { Stack, Tooltip } from '@open-ui-kit/core';
import { ExtendedTreeItemProps } from '@/types/trace-types.ts';
import { getColorFromTraceType, getMetricPulseColor, MetricPulseScore } from '@/utils';
import CircleBadge from '../CircleBadge';
import { useTheme } from '@mui/material';

function getMetricPulseScoreFromValue(value: number | undefined): MetricPulseScore {
  if (value === undefined) return 'warning';
  if (value === 1) return 'success';
  if (value === 0) return 'fatal';
  return 'warning';
}

interface CustomTreeItemProps extends Omit<UseTreeItemParameters, 'rootRef'>, Omit<React.HTMLAttributes<HTMLLIElement>, 'onFocus'> {}

interface CustomLabelProps {
  children: React.ReactNode;
  icon?: React.ElementType;
  item: ExtendedTreeItemProps;
}

const CustomCollapse = styled(Collapse)({
  padding: 0
});

const AnimatedCollapse = animated(CustomCollapse);

interface CustomTransitionProps extends TransitionProps {
  isLast?: boolean;
}

function TransitionComponent(props: CustomTransitionProps) {
  const style = useSpring({
    immediate: true,
    to: {}
  });

  return (
    <AnimatedCollapse style={style} {...props}>
      {props.children}
    </AnimatedCollapse>
  );
}

function getTooltipContent(metricName: string, reasoning?: string): React.ReactNode {
  if (!reasoning) {
    return metricName;
  }
  return (
    <Box>
      <Box sx={{ fontWeight: 600, marginBottom: '4px' }}>{metricName}</Box>
      <Box>{reasoning}</Box>
    </Box>
  );
}

function CustomLabel(props: CustomLabelProps) {
  const theme = useTheme();
  const { item } = props;
  const {
    label,
    duration = 0,
    rootDuration,
    rootDurationMultiplier,
    absoluteOffsetMs,
    intentRecognition,
    intentRecognitionReasoning,
    relevance,
    relevanceReasoning,
    groundedness,
    groundednessReasoning
  } = item as ExtendedTreeItemProps;

  const effectiveRootDuration = (rootDuration ?? duration) || 1;
  const effectiveRootMultiplier = rootDurationMultiplier ?? 400;
  const effectiveOffsetMs = absoluteOffsetMs ?? 0;

  return (
    <TreeItemLabel
      {...props}
      sx={{
        display: 'flex',
        alignItems: 'center'
      }}
    >
      <Stack
        sx={{
          height: '20px'
        }}
        justifyContent={'center'}
        alignItems={'flex-end'}
      >
        <Stack direction="row" gap={'4px'}>
          {intentRecognition !== undefined && (
            <Tooltip title={getTooltipContent('Intent Recognition', intentRecognitionReasoning)} placement={'top'}>
              <Box>
                <CircleBadge letter={'I'} color={getMetricPulseColor(getMetricPulseScoreFromValue(intentRecognition), theme)} size="small" />
              </Box>
            </Tooltip>
          )}
          {relevance !== undefined && (
            <Tooltip title={getTooltipContent('Relevancy', relevanceReasoning)} placement={'top'}>
              <Box>
                <CircleBadge letter={'R'} color={getMetricPulseColor(getMetricPulseScoreFromValue(relevance), theme)} size="small" />
              </Box>
            </Tooltip>
          )}
          {groundedness !== undefined && (
            <Tooltip title={getTooltipContent('Groundedness', groundednessReasoning)} placement={'top'}>
              <Box>
                <CircleBadge letter={'G'} color={getMetricPulseColor(getMetricPulseScoreFromValue(groundedness), theme)} size="small" />
              </Box>
            </Tooltip>
          )}
        </Stack>
      </Stack>
    </TreeItemLabel>
  );
}

const TreeItemRoot = styled('li')(({ theme }) => ({
  listStyle: 'none',
  margin: 0,
  padding: 0,
  outline: 0,
  color: theme.palette.text.primary,
  ...theme.applyStyles('light', {
    color: theme.palette.text.primary
  })
}));

const TreeItemContent = styled('div')(({ theme }) => ({
  padding: '4px 0',
  paddingRight: '8px',
  width: '100%',
  boxSizing: 'border-box', // prevent width + padding to overflow
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  cursor: 'pointer',
  WebkitTapHighlightColor: 'transparent',
  marginBottom: '4px',
  marginTop: '4px',
  fontWeight: 500,
  '&.Mui-focused': {
    backgroundColor: 'transparent'
  },
  '&[data-expanded]:not([data-focused], [data-selected]) .labelIcon': {
    ...theme.applyStyles('light', {}),
    '&::before': {
      content: '""',
      fontSize: '20px',
      display: 'block',
      position: 'absolute',
      left: '16px',
      top: '44px',
      height: 'calc(100% - 48px)',
      width: '1.5px',
      backgroundColor: 'transparent',
      ...theme.applyStyles('light', {
        backgroundColor: 'transparent'
      })
    }
  },
  [`&[data-focused], &[data-selected]`]: {
    backgroundColor: 'transparent',
    ...theme.applyStyles('light', {
      backgroundColor: 'transparent'
    })
  },
  '&:not([data-focused], [data-selected]):hover': {
    backgroundColor: 'transparent',
    ...theme.applyStyles('light', {})
  }
}));

const CustomTreeItem = React.forwardRef(function CustomTreeItem(props: CustomTreeItemProps, ref: React.Ref<HTMLLIElement>) {
  const { id, itemId, label, disabled, children, ...other } = props;

  const { getContextProviderProps, getRootProps, getContentProps, getLabelProps, getGroupTransitionProps, status } = useTreeItem({
    id,
    itemId,
    children,
    label,
    disabled,
    rootRef: ref
  });

  const item = useTreeItemModel<ExtendedTreeItemProps>(itemId)!;

  return (
    <TreeItemProvider {...getContextProviderProps()}>
      <TreeItemRoot {...getRootProps(other)}>
        <TreeItemContent {...getContentProps()}>
          <CustomLabel {...getLabelProps()} item={item} />
        </TreeItemContent>
        {children && <TransitionComponent {...getGroupTransitionProps()} />}
      </TreeItemRoot>
    </TreeItemProvider>
  );
});

interface DurationTreeProps {
  expandedItems: string[];
  items: any[];
}

const DurationTree = ({ expandedItems, items }: DurationTreeProps) => {
  return (
    <Stack direction={'row'} gap={'0px'}>
      <Box sx={{ /* minHeight: 352, */ minWidth: 250, cursor: 'pointer' }}>
        <RichTreeView slots={{ item: CustomTreeItem }} items={items} expandedItems={expandedItems} />
      </Box>
    </Stack>
  );
};

export default DurationTree;
