/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, useTheme } from '@mui/material';
import { animated, useSpring } from '@react-spring/web';
import Collapse from '@mui/material/Collapse';
import { TransitionProps } from '@mui/material/transitions';
import { styled, alpha, lighten, duration } from '@mui/material/styles';
import { RichTreeView } from '@mui/x-tree-view/RichTreeView';
import {
  useTreeItem,
  UseTreeItemParameters
} from '@mui/x-tree-view/useTreeItem';
import {
  TreeItemCheckbox,
  TreeItemIconContainer,
  TreeItemLabel
} from '@mui/x-tree-view/TreeItem';
import { TreeItemIcon } from '@mui/x-tree-view/TreeItemIcon';
import { TreeItemProvider } from '@mui/x-tree-view/TreeItemProvider';
import { useTreeItemModel } from '@mui/x-tree-view/hooks';
import { TreeViewBaseItem } from '@mui/x-tree-view/models';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@open-ui-kit/core';

import { Typography } from '@mui/material';
import { GeneralSize, Stack, Spinner, Tag } from '@open-ui-kit/core';
import DurationTree from './DurationTree.tsx';
import { ExtendedTreeItemProps, TraceType } from '@/types/trace-types.ts';
import { CustomTooltip, SpanDrawer } from '@/components';
import {
  getColorFromTraceType,
  getIconFromTraceType,
  sortByDateAccessorAsc
} from '@/utils';
import { useParams } from 'react-router';
import { Span, SpanStatefulEvalMetric } from '@/types/oxp.type';
import ErrorIcon from '@mui/icons-material/Error';
import { useSessionTimeline, useSpanListStatefulEval } from '@/api/oxpApi';
import MetricsTree from './MetricsTree';

export interface ExecutionTraceProps {
  sessionId?: string;
}

export interface CustomTreeItemProps
  extends Omit<UseTreeItemParameters, 'rootRef'>,
    Omit<React.HTMLAttributes<HTMLLIElement>, 'onFocus'> {}

export interface CustomLabelProps {
  children: React.ReactNode;
  icon?: React.ElementType;
  duration?: number;
  item: ExtendedTreeItemProps;
}

export const CustomCollapse = styled(Collapse)({
  padding: 0
});

export const AnimatedCollapse = animated(CustomCollapse);

export interface CustomTransitionProps extends TransitionProps {
  isLast?: boolean;
}

export function TransitionComponent(props: CustomTransitionProps) {
  const theme = useTheme();

  const style = useSpring({
    immediate: true,
    to: {
      marginLeft: '8px',
      paddingLeft: '44px',
      borderLeft: props.isLast
        ? 'none'
        : `1px solid ${theme.palette.vars.baseBorderStrong}`
    }
  });

  return (
    <AnimatedCollapse style={style} {...props}>
      {props.children}
    </AnimatedCollapse>
  );
}

export const TreeItemLabelText = styled(Typography)({
  color: 'inherit',
  fontFamily: 'Inter,sans-serif',
  fontWeight: 400
});

export function CustomLabel({
  icon: Icon,
  duration,
  children,
  item,
  ...other
}: CustomLabelProps) {
  const theme = useTheme();
  const baseColor = getColorFromTraceType(item.traceType);
  const blendedBackground = alpha(
    baseColor,
    theme.palette.mode === 'dark' ? 0.18 : 0.12
  );
  const iconColor =
    theme.palette.mode === 'dark' ? lighten(baseColor, 0.8) : baseColor;
  return (
    <TreeItemLabel
      {...other}
      sx={{
        display: 'flex',
        alignItems: 'center'
      }}
    >
      {Icon && (
        <Stack
          alignItems={'center'}
          justifyContent={'center'}
          sx={{
            width: '24px',
            height: '24px',
            marginRight: '8px',
            backgroundColor: blendedBackground,
            borderRadius: '8px'
          }}
        >
          <Icon
            sx={{
              color: iconColor,
              fontSize: '18px'
            }}
          />
        </Stack>
      )}

      {/*{Icon && <Box component={Icon} className="labelIcon" color="inherit" sx={{ marginRight: '8px', fontSize: '18px' }} />}*/}

      <Stack
        direction={'row'}
        gap={'8px'}
        justifyContent={'space-between'}
        alignItems={'center'}
        sx={{ flex: 1 }}
      >
        <CustomTooltip title={children}>
          <TreeItemLabelText
            variant="body2"
            sx={{
              maxWidth: '200px',
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
              color: item.error ? theme.palette.error.main : 'inherit'
            }}
          >
            {item.error ? (
              <ErrorIcon
                sx={{ color: theme.palette.error.main, fontSize: '16px' }}
              />
            ) : null}
            <Box
              component="span"
              sx={{
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis'
              }}
            >
              {children}
            </Box>
          </TreeItemLabelText>
        </CustomTooltip>

        <Typography variant={'caption'} sx={{ marginLeft: '4px' }}>
          {duration}(ms)
        </Typography>
      </Stack>
    </TreeItemLabel>
  );
}

export const TreeItemRoot = styled('li')(({ theme }) => ({
  listStyle: 'none',
  margin: 0,
  padding: 0,
  outline: 0,
  color: theme.palette.text.primary,
  ...theme.applyStyles('light', {
    color: theme.palette.text.primary
  })
}));

export const TreeItemContent = styled('div')(({ theme }) => ({
  padding: '2px 0',

  width: '100%',
  boxSizing: 'border-box', // prevent width + padding to overflow
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  gap: theme.spacing(1),
  cursor: 'pointer',
  WebkitTapHighlightColor: 'transparent',
  borderRadius: theme.spacing(0.7),
  marginBottom: '4px',
  marginTop: '4px',
  fontWeight: 400,
  '&.Mui-focused': {
    backgroundColor: 'transparent'
  },
  '&[data-expanded]:not([data-focused], [data-selected]) .labelIcon': {
    ...theme.applyStyles('light', {}),
    '&::before': {
      content: '""',
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

export const CustomTreeItem = React.forwardRef(function CustomTreeItem(
  props: CustomTreeItemProps,
  ref: React.Ref<HTMLLIElement>
) {
  const { id, itemId, label, disabled, children, ...other } = props;

  const {
    getContextProviderProps,
    getRootProps,
    getContentProps,
    getIconContainerProps,
    getCheckboxProps,
    getLabelProps,
    getGroupTransitionProps,
    status
  } = useTreeItem({ id, itemId, children, label, disabled, rootRef: ref });

  const item = useTreeItemModel<ExtendedTreeItemProps>(itemId)!;

  const theme = useTheme();

  const icon = getIconFromTraceType(item.traceType);
  return (
    <TreeItemProvider {...getContextProviderProps()}>
      <TreeItemRoot {...getRootProps(other)}>
        <TreeItemContent
          {...getContentProps()}
          style={{
            cursor: item.traceType === 'application' ? 'default' : 'pointer'
          }}
        >
          {(() => {
            const iconContainerProps = getIconContainerProps({
              sx: {
                borderRadius: '4px',
                padding: '0 10px',
                border: `1px solid ${theme.palette.vars.baseBorderStrong}`,
                color: theme.palette.vars.controlIconMedium,
                display: (children as React.ReactNode[])?.length
                  ? 'flex'
                  : 'none'
              },
              'data-role': 'expand-icon-container'
            });
            const originalOnClick = iconContainerProps.onClick;
            const handleIconClick = (e: React.MouseEvent<HTMLDivElement>) => {
              e.stopPropagation();
              // Invoke the original handler so expansion still works
              originalOnClick?.(e);
            };
            return (
              <TreeItemIconContainer
                {...iconContainerProps}
                onClick={handleIconClick}
              >
                <TreeItemIcon status={status} />
              </TreeItemIconContainer>
            );
          })()}
          <TreeItemCheckbox {...getCheckboxProps()} />
          <CustomLabel
            {...getLabelProps({
              icon,
              duration: item.duration,
              item
            })}
          />
        </TreeItemContent>
        {children && (
          <TransitionComponent
            {...getGroupTransitionProps()}
            isLast={item.isLast}
          />
        )}
      </TreeItemRoot>
    </TreeItemProvider>
  );
});

export type SpanMetricsMap = Map<
  string,
  {
    intentRecognition?: number;
    intentRecognitionReasoning?: string;
    relevance?: number;
    relevanceReasoning?: string;
    groundedness?: number;
    groundednessReasoning?: string;
  }
>;

function getMetricValue(
  metrics: SpanStatefulEvalMetric[] | undefined,
  metricName: string
): number | undefined {
  if (!metrics) return undefined;
  const metric = metrics.find((m) => m.name === metricName);
  return metric?.value;
}

function getMetricReasoning(
  metrics: SpanStatefulEvalMetric[] | undefined,
  metricName: string
): string | undefined {
  if (!metrics) return undefined;
  const metric = metrics.find((m) => m.name === metricName);
  return metric?.reasoning;
}

function collectAllSpanIds(
  spans: (Span | null)[] | null | undefined
): string[] {
  if (!spans) return [];
  const ids: string[] = [];

  for (const span of spans) {
    if (!span) continue;
    if (span.spanId) {
      ids.push(span.spanId);
    }
    if (span.childrenSpans) {
      ids.push(...collectAllSpanIds(span.childrenSpans));
    }
  }

  return ids;
}

export function childrenToTreeViewItems(
  metrics: Span[],
  parentId: string,
  parentDuration: number,
  rootMinUnix: number,
  rootDuration: number,
  rootDurationMultiplier: number,
  spanMetricsMap?: SpanMetricsMap
): TreeViewBaseItem<ExtendedTreeItemProps>[] {
  if (!metrics || metrics.length === 0) {
    return [];
  }
  const children: TreeViewBaseItem<ExtendedTreeItemProps>[] = [];

  const seen = new Set<string>();
  const deduplicated = metrics.filter((m) => {
    if (!m?.spanId || seen.has(m.spanId)) return false;
    seen.add(m.spanId);
    return true;
  });

  // Sort siblings by startTime ascending to ensure consistent order within the same level
  const sortedMetrics = sortByDateAccessorAsc(
    deduplicated,
    (m: Span) => m?.startTime
  );

  sortedMetrics.forEach((metric, metricIndex) => {
    if (!metric) {
      return;
    }
    const minDate = new Date(metric.startTime);
    const minUnix = minDate.getTime();

    let duration = Math.max(metric.duration ?? 0, 3);

    // Offset relative to ROOT so offsets accumulate from the very beginning
    const absoluteOffsetMs = minUnix - rootMinUnix;

    // Get stateful eval metrics for this span
    const spanMetrics = spanMetricsMap?.get(metric.spanId);

    const child: TreeViewBaseItem<ExtendedTreeItemProps> = {
      id: metric.spanId + '-' + parentId,
      label: metric.spanName,
      traceType: (metric.icon as TraceType) ?? undefined,

      duration,
      parentId,
      isLast: metricIndex === sortedMetrics.length - 1,
      rootDuration: rootDuration,
      rootDurationMultiplier,
      absoluteOffsetMs,
      startTime: metric.startTime,
      endTime: metric.endTime,
      error: metric.error ?? false,
      intentRecognition: spanMetrics?.intentRecognition,
      intentRecognitionReasoning: spanMetrics?.intentRecognitionReasoning,
      relevance: spanMetrics?.relevance,
      relevanceReasoning: spanMetrics?.relevanceReasoning,
      groundedness: spanMetrics?.groundedness,
      groundednessReasoning: spanMetrics?.groundednessReasoning
    };

    child.children = childrenToTreeViewItems(
      (metric.childrenSpans ?? []).filter(Boolean) as Span[],
      child.id,
      duration,
      rootMinUnix,
      rootDuration,
      rootDurationMultiplier,
      spanMetricsMap
    );
    children.push(child);
  });

  return children;
}

export function countDescendantsOfItem(
  item: TreeViewBaseItem<ExtendedTreeItemProps>
): number {
  const children = (item.children ??
    []) as TreeViewBaseItem<ExtendedTreeItemProps>[];
  return children.reduce(
    (sum, child) => sum + 1 + countDescendantsOfItem(child),
    0
  );
}

export function countAllDescendants(
  items: TreeViewBaseItem<ExtendedTreeItemProps>[]
): number {
  if (!items || items.length === 0) {
    return 0;
  }
  return items.reduce((acc, item) => acc + countDescendantsOfItem(item), 0);
}

export const ExecutionTrace = ({
  sessionId: propSessionId
}: ExecutionTraceProps) => {
  const { sessionId: paramSessionId } = useParams();
  const sessionId = propSessionId ?? paramSessionId;

  const [expandedItems, setExpandedItems] = React.useState<string[]>([]);
  const [selectedSpanId, setSelectedSpanId] = React.useState<string>('');
  const [spanDuration, setSpanDuration] = React.useState<number>(0);
  const [treeViewItems, setTreeViewItems] = useState<
    TreeViewBaseItem<ExtendedTreeItemProps>[]
  >([]);
  const [spanCount, setSpanCount] = useState(0);
  const [traceCount, setTraceCount] = useState(0);
  const [startTime, setStartTime] = React.useState(0);
  const [endTime, setEndTime] = React.useState(0);
  const [activeView, setActiveView] = React.useState<'spans' | 'metrics'>(
    'spans'
  );
  const { data, error, isLoading } = useSessionTimeline(sessionId ?? '');
  const allSpanIds = useMemo(
    () => collectAllSpanIds(data?.Spans),
    [data?.Spans]
  );
  const spanStatefulEvalQueries = useSpanListStatefulEval(
    sessionId ?? '',
    allSpanIds
  );
  const spanStatefulEvalLoading = spanStatefulEvalQueries.some(
    (q) => q.isLoading
  );
  const spanStatefulEvalError = spanStatefulEvalQueries.some((q) => q.error);

  const spanMetricsMap = useMemo<SpanMetricsMap>(() => {
    const map: SpanMetricsMap = new Map();
    if (spanStatefulEvalLoading) return map;

    spanStatefulEvalQueries.forEach((query) => {
      if (query.data?.span_id && query.data?.metrics) {
        const metrics = query.data.metrics;
        map.set(query.data.span_id, {
          intentRecognition: getMetricValue(metrics, 'IntentRecognition'),
          intentRecognitionReasoning: getMetricReasoning(
            metrics,
            'IntentRecognition'
          ),
          relevance: getMetricValue(metrics, 'Relevancy'),
          relevanceReasoning: getMetricReasoning(metrics, 'Relevancy'),
          groundedness: getMetricValue(metrics, 'Groundedness'),
          groundednessReasoning: getMetricReasoning(metrics, 'Groundedness')
        });
      }
    });

    return map;
  }, [spanStatefulEvalQueries, spanStatefulEvalLoading]);

  const lastSignatureRef = useRef<string>('');

  const findItemById = (
    items: TreeViewBaseItem<ExtendedTreeItemProps>[],
    id: string
  ): TreeViewBaseItem<ExtendedTreeItemProps> | undefined => {
    for (const item of items ?? []) {
      if (item.id === id) {
        return item;
      }
      const childItems = (item.children ??
        []) as TreeViewBaseItem<ExtendedTreeItemProps>[];
      const foundInChildren = findItemById(childItems, id);
      if (foundInChildren) {
        return foundInChildren;
      }
    }
    return undefined;
  };

  useEffect(() => {
    if (!data || spanStatefulEvalLoading) {
      return;
    }

    const rootItem = data;

    const spans = (rootItem?.Spans ?? []).filter(Boolean) as Span[];
    const spansSig = spans
      .map(
        (s) =>
          `${s?.spanId}:${s?.spanName}:${s?.startTime}:${s?.endTime}:${s?.duration}:${s?.error}`
      )
      .sort()
      .join('|');
    const metricsSig = Array.from(spanMetricsMap.entries())
      .map(
        ([id, m]) =>
          `${id}:${m.intentRecognition}:${m.relevance}:${m.groundedness}`
      )
      .sort()
      .join('|');
    const signature = `${rootItem?.timestamp}:${rootItem?.spanId}:${rootItem?.spanName}:${rootItem?.startTime}:${rootItem?.endTime}:${rootItem?.duration}:S(${spans.length})[${spansSig}]:M[${metricsSig}]`;

    if (signature === lastSignatureRef.current) {
      return;
    }
    lastSignatureRef.current = signature;

    const rootItemId = rootItem?.spanName;
    const itemTreeViewItem: TreeViewBaseItem<ExtendedTreeItemProps> = {
      id: rootItemId,
      label: rootItem?.spanName,
      duration: data?.duration ?? 0,
      traceType: rootItem?.icon as TraceType,
      children: [],
      isLast: true
    };

    const rootDuration = rootItem?.duration ?? 0;
    const rootDurationMultiplier = 400;
    const rootMinUnix = new Date(rootItem?.startTime).getTime();

    // Enrich root with absolute timeline context so children can inherit
    itemTreeViewItem.rootDuration = rootDuration;
    itemTreeViewItem.rootDurationMultiplier = rootDurationMultiplier;
    itemTreeViewItem.absoluteOffsetMs = 0;

    itemTreeViewItem.children = childrenToTreeViewItems(
      (rootItem?.Spans ?? []).filter(Boolean) as Span[],
      rootItemId,
      rootDuration,
      rootMinUnix,
      rootDuration,
      rootDurationMultiplier,
      spanMetricsMap
    );

    setSpanCount(countAllDescendants([itemTreeViewItem]));
    setTraceCount(itemTreeViewItem.children.length);

    setTreeViewItems([itemTreeViewItem]);

    // Expand the root level by default
    setExpandedItems((prev) => (prev.length === 0 ? [rootItemId] : prev));
  }, [
    data?.timestamp,
    data?.spanId,
    data?.spanName,
    data?.startTime,
    data?.endTime,
    data?.duration,
    data?.Spans,
    spanMetricsMap,
    spanStatefulEvalLoading
  ]);

  if (!sessionId) {
    return null;
  }

  if (isLoading || spanStatefulEvalLoading) {
    return (
      <Stack
        alignItems={'center'}
        justifyContent={'center'}
        sx={{ width: '100%', height: '100%', minHeight: '100px' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (error || spanStatefulEvalError) {
    return <>An error occurred!</>;
  }

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        maxWidth: '900px',
        padding: '24px 0',
        overflow: 'auto'
      }}
    >
      <Stack direction={'row'} gap={'8px'} sx={{ marginBottom: '16px' }}>
        <Tag
          size={GeneralSize.Medium}
          sx={{ minWidth: '100px' }}
        >{`${traceCount} Trace${traceCount > 1 ? 's' : ''}`}</Tag>
        <Tag
          size={GeneralSize.Medium}
          sx={{ minWidth: '100px' }}
        >{`${spanCount} Span${spanCount > 1 ? 's' : ''}`}</Tag>
      </Stack>

      <Stack
        direction={'row'}
        gap={'8px'}
        sx={{ marginBottom: '16px' }}
        alignItems={'center'}
      >
        <Button
          variant={activeView === 'spans' ? 'gradient' : 'outlined'}
          onClick={(e) => {
            e.stopPropagation();
            setActiveView('spans');
          }}
          disableRipple
          size={activeView === 'spans' ? 'medium' : 'small'}
          sx={{
            '&:focus, &:focus-visible, &.Mui-focusVisible': {
              outline: 'none !important',
              boxShadow: 'none !important'
            }
          }}
        >
          Spans
        </Button>
        <Button
          variant={activeView === 'metrics' ? 'gradient' : 'outlined'}
          onClick={(e) => {
            e.stopPropagation();
            setActiveView('metrics');
          }}
          disableRipple
          size={activeView === 'metrics' ? 'medium' : 'small'}
          sx={{
            '&:focus, &:focus-visible, &.Mui-focusVisible': {
              outline: 'none !important',
              boxShadow: 'none !important'
            }
          }}
        >
          Assessment Scores
        </Button>
      </Stack>

      <Stack direction={'row'} gap={'44px'} sx={{ minWidth: '564px' }}>
        <Box sx={{ /* minHeight: 352, */ minWidth: 400 }}>
          <RichTreeView
            slots={{ item: CustomTreeItem }}
            expansionTrigger="iconContainer"
            expandedItems={expandedItems}
            onItemClick={(event, itemId) => {
              const target = event.target as HTMLElement;
              if (!target.closest('[data-role="expand-icon-container"]')) {
                const clickedItem = findItemById(treeViewItems, String(itemId));
                if (clickedItem?.traceType !== 'application') {
                  setSelectedSpanId(String(itemId).split('-')[0]);
                  setSpanDuration(clickedItem?.duration ?? 0);
                  setStartTime(clickedItem?.startTime ?? 0);
                  setEndTime(clickedItem?.endTime ?? 0);
                }
              }
            }}
            items={treeViewItems}
            onExpandedItemsChange={(event, ids) => {
              setExpandedItems(ids);
            }}
          />
        </Box>

        <Box sx={{ /* minHeight: 352, */ minWidth: 420 }}>
          {activeView === 'spans' ? (
            <DurationTree expandedItems={expandedItems} items={treeViewItems} />
          ) : (
            <MetricsTree expandedItems={expandedItems} items={treeViewItems} />
          )}
        </Box>
      </Stack>
      {selectedSpanId && (
        <SpanDrawer
          spanId={selectedSpanId}
          onClose={() => setSelectedSpanId('')}
          spanDuration={spanDuration}
          startTime={startTime}
          endTime={endTime}
        />
      )}
    </Box>
  );
};
