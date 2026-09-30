/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * ExecutionTimeline Component
 *
 * This component visualizes a state machine execution as a hierarchical timeline (Gantt-chart style).
 * It displays 5 hierarchy levels: Session > MAS > Agent > Task > Call
 *
 * The visualization shows:
 * - Segments (colored bars): Represent edges/transitions in the state machine graph
 * - State nodes (white squares): Represent states between transitions
 */

import { Typography, Box, Stack } from '@open-ui-kit/core';
import { useMemo, useCallback, useEffect, useState } from 'react';
import { useStateMachine } from '@/api/kgInspectorApi';
import { useTimelineReasoningPath } from '@/api/oxpApi';
import { useTheme, Tooltip, alpha, Chip, IconButton } from '@mui/material';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import { Spinner } from '@open-ui-kit/core';
import { getHierarchyColor } from '@/utils/graphUtils';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';
import type {
  TimelineReasoningVariable,
  TimelineReasoningDependency
} from '@/types/oxp.type';

type HierarchyLevel = 'session' | 'mas' | 'agent' | 'task' | 'call';

interface TimelineEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  entityType: string;
  entityName: string;
  duration: number;
  hierarchyLevel: HierarchyLevel;
  spanId?: string;
  executionId?: string;
}

interface TimelineSegment {
  id: string;
  entityName: string;
  entityType: string;
  edgeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  startPosition: number;
  width: number;
  duration: number;
  hierarchyLevel: HierarchyLevel;
  spanId?: string;
  executionId?: string;
}

interface TimelineStateNode {
  id: string;
  label: string;
  content?: string;
  semanticType?: string;
  position: number;
}

interface TimelineRow {
  level: HierarchyLevel;
  segments: TimelineSegment[];
  stateNodes: TimelineStateNode[];
}

const HIERARCHY_LEVELS: HierarchyLevel[] = [
  'session',
  'mas',
  'agent',
  'task',
  'call'
];
const MIN_SEGMENT_WIDTH = 80;
const MIN_SEGMENT_SPACING = 60;
const ROW_LABEL_WIDTH = 200;
const TIMELINE_PADDING = 40;
const NODE_SIZE = 16;
const SEGMENT_NODE_GAP = 4;

const LEVEL_LABELS: Record<HierarchyLevel, string> = {
  session: 'Session',
  mas: 'MAS',
  agent: 'Agents',
  task: 'Tasks',
  call: 'Calls'
};

const CALL_TYPE_COLORS: Record<string, string> = {
  llm: '#FFE659',
  tool: '#74FFC7',
  memory: '#FF007F',
  rag: '#464C54',
  processing: '#2E3E57',
  user: '#F44336',
  unknown: '#FF007F'
};

const HIERARCHY_LEGEND_ITEMS: HierarchyLevel[] = [
  'session',
  'mas',
  'agent',
  'task',
  'call'
];

const CALL_LEGEND_ITEMS = [
  { type: 'llm', label: 'llm' },
  { type: 'tool', label: 'tool' },
  { type: 'memory', label: 'memory' },
  { type: 'rag', label: 'rag' },
  { type: 'processing', label: 'processing' }
  // { type: 'user', label: 'user' }
];

const TIER_COLORS: Record<string, string> = {
  entity: '#2196f3',
  process: '#9c27b0',
  alignment: '#4caf50'
};

const getVariableColor = (
  variable: TimelineReasoningVariable | TimelineReasoningDependency
): string => {
  const value =
    typeof variable.value === 'string' ? variable.value.toLowerCase() : '';
  if (value === 'satisfied' || value === 'true') return '#4caf50';
  if (value === 'violated' || value === 'false') return '#f44336';
  if (value === 'pending' || value === 'unresolved') return '#ff9800';
  return TIER_COLORS[variable.tier] || '#9e9e9e';
};

const getEntityTypeFromLabel = (
  label: string,
  hierarchyLevel: HierarchyLevel
): string => {
  const lowerLabel = label.toLowerCase();

  if (hierarchyLevel === 'session') return 'session';
  if (hierarchyLevel === 'mas') return 'mas';
  if (hierarchyLevel === 'agent') return 'agent';
  if (hierarchyLevel === 'task') return 'task';

  if (
    lowerLabel.includes('gpt') ||
    lowerLabel.includes('gemini') ||
    lowerLabel.includes('claude') ||
    lowerLabel.includes('llm') ||
    lowerLabel.includes('vertex')
  ) {
    return 'llm';
  }
  if (
    lowerLabel.includes('tool') ||
    lowerLabel.includes('calculate') ||
    lowerLabel.includes('query') ||
    lowerLabel.includes('read') ||
    lowerLabel.includes('list') ||
    lowerLabel.includes('get_schedule')
  ) {
    return 'tool';
  }
  if (lowerLabel.includes('memory')) return 'memory';
  if (lowerLabel.includes('rag')) return 'rag';
  if (lowerLabel.includes('prompt')) return 'processing';
  if (lowerLabel.includes('user')) return 'user';

  return 'unknown';
};

export interface ExecutionTimelineProps {
  sessionId: string;
  height?: string | number;
  onDataLoaded?: (data: any) => void;
}

export const ExecutionTimeline = ({
  sessionId,
  height = 'calc(100vh - 300px)',
  onDataLoaded
}: ExecutionTimelineProps) => {
  const theme = useTheme();
  const [hoveredRowId, setHoveredRowId] = useState<string | null>(null);
  const [expandedAlignments, setExpandedAlignments] = useState<Set<string>>(
    new Set()
  );

  const selectedLevels = useMemo(() => HIERARCHY_LEVELS, []);
  const { data, isLoading, error } = useStateMachine(sessionId, selectedLevels);
  const { data: reasoningData } = useTimelineReasoningPath(sessionId);

  useEffect(() => {
    if (data && onDataLoaded) {
      onDataLoaded(data);
    }
  }, [data, onDataLoaded]);

  const { timelineRows, title, totalWidth } = useMemo(() => {
    if (!data || typeof data !== 'object') {
      return { timelineRows: [], title: '', totalWidth: 0 };
    }

    const graphData = data as any;

    const rawNodes = (graphData.nodes || []).map((node: any) => ({
      id: node.id,
      label: node.label || node.id,
      content: node.data?.content,
      semanticType: node.data?.semantic_type
    }));

    const edges: TimelineEdge[] = (graphData.edges || []).map((edge: any) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || '',
      entityType: edge.data?.entity_type || 'unknown',
      entityName: edge.data?.entity_name || edge.label || 'unknown',
      duration: edge.data?.duration || 0,
      hierarchyLevel: (edge.metadata?.hierarchy_level ||
        'call') as HierarchyLevel,
      spanId: edge.data?.spanId,
      executionId: edge.data?.executionId
    }));

    const initialNode = rawNodes.find((n: any) => n.semanticType === 'initial');
    const initialNodeId = initialNode?.id;

    const callOnlyEdges = edges.filter((e) => e.hierarchyLevel === 'call');

    const edgeOrder = new Map<string, number>();
    const nodeOrder = new Map<string, number>();

    if (initialNodeId) {
      const visitedNodes = new Set<string>();
      const visitedEdges = new Set<string>();
      const queue = [initialNodeId];
      let nodeIdx = 0;
      let edgeIdx = 0;

      while (queue.length > 0) {
        const currentId = queue.shift()!;
        if (visitedNodes.has(currentId)) continue;
        visitedNodes.add(currentId);
        nodeOrder.set(currentId, nodeIdx++);

        const outgoingEdges = callOnlyEdges.filter(
          (e) => e.source === currentId
        );
        for (const edge of outgoingEdges) {
          if (!visitedEdges.has(edge.id)) {
            visitedEdges.add(edge.id);
            edgeOrder.set(edge.id, edgeIdx++);
          }
          if (!visitedNodes.has(edge.target)) {
            queue.push(edge.target);
          }
        }
      }

      rawNodes.forEach((node: any) => {
        if (!nodeOrder.has(node.id)) {
          nodeOrder.set(node.id, nodeIdx++);
        }
      });

      edges.forEach((edge) => {
        if (!edgeOrder.has(edge.id)) {
          edgeOrder.set(edge.id, edgeIdx++);
        }
      });
    }

    const levelEdges = new Map<HierarchyLevel, TimelineEdge[]>();
    HIERARCHY_LEVELS.forEach((level) => levelEdges.set(level, []));

    edges.forEach((edge) => {
      const level = edge.hierarchyLevel;
      if (levelEdges.has(level)) {
        levelEdges.get(level)!.push(edge);
      }
    });

    HIERARCHY_LEVELS.forEach((level) => {
      const levelEdgeList = levelEdges.get(level);
      if (levelEdgeList) {
        levelEdgeList.sort((a, b) => {
          const aOrder = edgeOrder.get(a.id) ?? Infinity;
          const bOrder = edgeOrder.get(b.id) ?? Infinity;
          return aOrder - bOrder;
        });
      }
    });

    const callEdges = (levelEdges.get('call') || []).filter(
      (edge) => edge.source !== edge.target
    );

    const callSegments: TimelineSegment[] = callEdges.map((edge, index) => {
      const entityType = getEntityTypeFromLabel(edge.entityName, 'call');
      const startPosition =
        index *
        (NODE_SIZE + SEGMENT_NODE_GAP + MIN_SEGMENT_WIDTH + SEGMENT_NODE_GAP);
      return {
        id: `call-${edge.id}`,
        entityName: edge.entityName,
        entityType,
        edgeId: edge.id,
        sourceNodeId: edge.source,
        targetNodeId: edge.target,
        startPosition: startPosition + NODE_SIZE + SEGMENT_NODE_GAP,
        width: MIN_SEGMENT_WIDTH,
        duration: edge.duration,
        hierarchyLevel: 'call',
        spanId: edge.spanId,
        executionId: edge.executionId
      };
    });

    const findNodesOnPath = (
      startNodeId: string,
      endNodeId: string,
      childSegments: TimelineSegment[]
    ): Set<string> => {
      const nodesOnPath = new Set<string>();
      const visited = new Set<string>();
      const queue = [startNodeId];

      while (queue.length > 0) {
        const currentId = queue.shift()!;
        if (visited.has(currentId)) continue;
        visited.add(currentId);
        nodesOnPath.add(currentId);

        if (currentId === endNodeId) continue;

        const outgoing = childSegments.filter(
          (seg) => seg.sourceNodeId === currentId
        );
        for (const seg of outgoing) {
          if (!visited.has(seg.targetNodeId)) {
            queue.push(seg.targetNodeId);
          }
        }
      }

      if (!nodesOnPath.has(endNodeId)) {
        return new Set<string>();
      }

      return nodesOnPath;
    };

    const buildParentSegments = (
      parentLevel: HierarchyLevel,
      childSegments: TimelineSegment[]
    ): TimelineSegment[] => {
      const parentEdges = (levelEdges.get(parentLevel) || []).filter(
        (edge) => edge.source !== edge.target
      );
      if (parentEdges.length === 0) return [];

      const segmentsWithChildren: TimelineSegment[] = [];
      const edgesWithoutChildren: TimelineEdge[] = [];

      parentEdges.forEach((edge) => {
        const entityType = getEntityTypeFromLabel(edge.entityName, parentLevel);

        const nodesOnPath = findNodesOnPath(
          edge.source,
          edge.target,
          childSegments
        );

        const matchingChildren = childSegments.filter(
          (child) =>
            nodesOnPath.has(child.sourceNodeId) &&
            nodesOnPath.has(child.targetNodeId)
        );

        if (matchingChildren.length === 0) {
          edgesWithoutChildren.push(edge);
          return;
        }

        const minStart = Math.min(
          ...matchingChildren.map((c) => c.startPosition)
        );
        const maxEnd = Math.max(
          ...matchingChildren.map((c) => c.startPosition + c.width)
        );

        const startPosition = minStart;
        const width = Math.max(maxEnd - minStart, MIN_SEGMENT_WIDTH);

        segmentsWithChildren.push({
          id: `${parentLevel}-${edge.id}`,
          entityName: edge.entityName,
          entityType,
          edgeId: edge.id,
          sourceNodeId: edge.source,
          targetNodeId: edge.target,
          startPosition,
          width,
          duration: edge.duration,
          hierarchyLevel: parentLevel
        });
      });

      let currentEndPosition = 0;
      if (segmentsWithChildren.length > 0) {
        currentEndPosition = Math.max(
          ...segmentsWithChildren.map((s) => s.startPosition + s.width)
        );
      } else if (childSegments.length > 0) {
        currentEndPosition = Math.max(
          ...childSegments.map((s) => s.startPosition + s.width)
        );
      }

      const childlessSegments: TimelineSegment[] = edgesWithoutChildren.map(
        (edge) => {
          const entityType = getEntityTypeFromLabel(
            edge.entityName,
            parentLevel
          );
          const startPosition = currentEndPosition + MIN_SEGMENT_SPACING;
          currentEndPosition = startPosition + MIN_SEGMENT_WIDTH;

          return {
            id: `${parentLevel}-${edge.id}`,
            entityName: edge.entityName,
            entityType,
            edgeId: edge.id,
            sourceNodeId: edge.source,
            targetNodeId: edge.target,
            startPosition,
            width: MIN_SEGMENT_WIDTH,
            duration: edge.duration,
            hierarchyLevel: parentLevel
          };
        }
      );

      return [...segmentsWithChildren, ...childlessSegments];
    };

    const taskSegments = buildParentSegments('task', callSegments);
    const agentSegments = buildParentSegments('agent', taskSegments);
    const masSegments = buildParentSegments('mas', agentSegments);
    const sessionSegments = buildParentSegments('session', masSegments);

    const nodeMap = new Map<
      string,
      { id: string; label: string; content?: string; semanticType?: string }
    >(rawNodes.map((n: any) => [n.id, n]));

    const callInitialNodePosition =
      callSegments.length > 0
        ? [...callSegments].sort((a, b) => a.startPosition - b.startPosition)[0]
            .startPosition -
          SEGMENT_NODE_GAP -
          NODE_SIZE / 2
        : 0;

    const buildStateNodesForLevel = (
      segments: TimelineSegment[],
      level: HierarchyLevel
    ): TimelineStateNode[] => {
      const nodePositionsForLevel = new Map<string, number>();
      const sortedSegments = [...segments].sort(
        (a, b) => a.startPosition - b.startPosition
      );

      if (initialNodeId) {
        nodePositionsForLevel.set(initialNodeId, callInitialNodePosition);
      }

      sortedSegments.forEach((seg, index) => {
        if (level === 'call') {
          if (!nodePositionsForLevel.has(seg.sourceNodeId)) {
            nodePositionsForLevel.set(
              seg.sourceNodeId,
              seg.startPosition - SEGMENT_NODE_GAP - NODE_SIZE / 2
            );
          }
          const targetPos =
            seg.startPosition + seg.width + SEGMENT_NODE_GAP + NODE_SIZE / 2;
          if (
            !nodePositionsForLevel.has(seg.targetNodeId) ||
            nodePositionsForLevel.get(seg.targetNodeId)! < targetPos
          ) {
            nodePositionsForLevel.set(seg.targetNodeId, targetPos);
          }
        } else {
          if (!nodePositionsForLevel.has(seg.sourceNodeId)) {
            nodePositionsForLevel.set(
              seg.sourceNodeId,
              seg.startPosition - NODE_SIZE / 2
            );
          }

          const segEnd = seg.startPosition + seg.width;
          const nextSeg = sortedSegments[index + 1];
          let targetPos: number;

          if (nextSeg) {
            targetPos = segEnd + (nextSeg.startPosition - segEnd) / 2;
          } else {
            targetPos = segEnd + SEGMENT_NODE_GAP + NODE_SIZE / 2;
          }

          if (
            !nodePositionsForLevel.has(seg.targetNodeId) ||
            nodePositionsForLevel.get(seg.targetNodeId)! < targetPos
          ) {
            nodePositionsForLevel.set(seg.targetNodeId, targetPos);
          }
        }
      });

      return Array.from(nodePositionsForLevel.entries())
        .map(([nodeId, position]) => {
          const nodeData = nodeMap.get(nodeId);
          return {
            id: nodeId,
            label: nodeData?.label || nodeId,
            content: nodeData?.content,
            semanticType: nodeData?.semanticType,
            position
          };
        })
        .sort((a, b) => a.position - b.position);
    };

    const allRows: TimelineRow[] = [
      {
        level: 'session',
        segments: sessionSegments,
        stateNodes: buildStateNodesForLevel(sessionSegments, 'session')
      },
      {
        level: 'mas',
        segments: masSegments,
        stateNodes: buildStateNodesForLevel(masSegments, 'mas')
      },
      {
        level: 'agent',
        segments: agentSegments,
        stateNodes: buildStateNodesForLevel(agentSegments, 'agent')
      },
      {
        level: 'task',
        segments: taskSegments,
        stateNodes: buildStateNodesForLevel(taskSegments, 'task')
      },
      {
        level: 'call',
        segments: callSegments,
        stateNodes: buildStateNodesForLevel(callSegments, 'call')
      }
    ];

    const rows = allRows.filter((row) => row.segments.length > 0);

    const allSegments = [
      ...sessionSegments,
      ...masSegments,
      ...agentSegments,
      ...taskSegments,
      ...callSegments
    ];
    const maxSegmentEnd =
      allSegments.length > 0
        ? Math.max(...allSegments.map((s) => s.startPosition + s.width))
        : 0;

    const allStateNodes = rows.flatMap((r) => r.stateNodes);
    const maxNodeEnd =
      allStateNodes.length > 0
        ? Math.max(...allStateNodes.map((n) => n.position + NODE_SIZE / 2))
        : 0;
    const maxPosition = Math.max(maxSegmentEnd, maxNodeEnd);

    return {
      timelineRows: rows,
      title: 'Execution Timeline',
      totalWidth: maxPosition + TIMELINE_PADDING * 2
    };
  }, [data]);

  const timelineWidth = useMemo(() => {
    return Math.max(totalWidth, 800);
  }, [totalWidth]);

  const segmentReasoningMap = useMemo(() => {
    const map = new Map<string, TimelineReasoningVariable[]>();
    if (!reasoningData || !timelineRows.length) return map;

    const callRow = timelineRows.find((r) => r.level === 'call');
    if (!callRow) return map;

    for (const span of reasoningData.spans) {
      const candidateSegments = callRow.segments.filter(
        (seg) => seg.spanId && seg.spanId === span.spanId
      );

      for (const variable of span.variables) {
        let matched: TimelineSegment | undefined;

        if (variable.executionId && candidateSegments.length > 0) {
          matched = candidateSegments.find(
            (seg) => seg.executionId === variable.executionId
          );
        }

        if (!matched) {
          matched = callRow.segments.find(
            (seg) =>
              seg.entityName === span.entityName &&
              Math.abs(seg.duration - span.executionDuration) < 0.001
          );
        }

        if (matched) {
          const existing = map.get(matched.id);
          if (existing) {
            if (!existing.some((v) => v.variableId === variable.variableId)) {
              existing.push(variable);
            }
          } else {
            map.set(matched.id, [variable]);
          }
        }
      }
    }

    return map;
  }, [reasoningData, timelineRows]);

  type ReasoningDisplayRow = {
    variableId: string;
    name: string;
    tier: string;
    isAlignment: boolean;
    indent: boolean;
  };

  const reasoningDisplayRows = useMemo((): ReasoningDisplayRow[] => {
    if (segmentReasoningMap.size === 0) return [];

    const alignmentSet = new Map<string, { name: string; tier: string }>();
    const depSet = new Map<
      string,
      { name: string; tier: string; parentIds: Set<string> }
    >();

    for (const vars of segmentReasoningMap.values()) {
      for (const v of vars) {
        if (v.tier === 'alignment' && !alignmentSet.has(v.variableId)) {
          alignmentSet.set(v.variableId, { name: v.name, tier: v.tier });
        }
        if (v.dependencies) {
          for (const dep of v.dependencies) {
            const existing = depSet.get(dep.variableId);
            if (existing) {
              existing.parentIds.add(v.variableId);
            } else {
              depSet.set(dep.variableId, {
                name: dep.name,
                tier: dep.tier,
                parentIds: new Set([v.variableId])
              });
            }
          }
        }
      }
    }

    const sortedAlignments = Array.from(alignmentSet.entries()).sort(
      ([, a], [, b]) => a.name.localeCompare(b.name)
    );

    const rows: ReasoningDisplayRow[] = [];
    for (const [alignId, { name, tier }] of sortedAlignments) {
      rows.push({
        variableId: alignId,
        name,
        tier,
        isAlignment: true,
        indent: false
      });

      const deps = Array.from(depSet.entries())
        .filter(([, d]) => d.parentIds.has(alignId))
        .sort(([, a], [, b]) => {
          const tierOrder = { process: 0, entity: 1 };
          const ta = tierOrder[a.tier as keyof typeof tierOrder] ?? 2;
          const tb = tierOrder[b.tier as keyof typeof tierOrder] ?? 2;
          if (ta !== tb) return ta - tb;
          return a.name.localeCompare(b.name);
        });

      for (const [depId, { name: depName, tier: depTier }] of deps) {
        rows.push({
          variableId: depId,
          name: depName,
          tier: depTier,
          isAlignment: false,
          indent: true
        });
      }
    }

    return rows;
  }, [segmentReasoningMap]);

  const getSegmentColor = useCallback(
    (segment: TimelineSegment) => {
      if (
        ['session', 'mas', 'agent', 'task'].includes(segment.hierarchyLevel)
      ) {
        return getHierarchyColor(segment.hierarchyLevel, theme);
      }
      return CALL_TYPE_COLORS[segment.entityType] || CALL_TYPE_COLORS.unknown;
    },
    [theme]
  );

  const getSegmentStyle = useCallback(
    (segment: TimelineSegment) => {
      return {
        left: `${segment.startPosition + TIMELINE_PADDING}px`,
        width: `${segment.width}px`,
        backgroundColor: getSegmentColor(segment)
      };
    },
    [getSegmentColor]
  );

  if (isLoading) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{
          width: '100%',
          height: height,
          minHeight: '100px',
          backgroundColor:
            theme.palette.vars?.baseBackgroundWeak ||
            theme.palette.background.default
        }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (error) {
    return (
      <Box
        sx={{
          p: 2,
          borderRadius: 1,
          backgroundColor: theme.palette.error.dark,
          color: theme.palette.error.contrastText
        }}
      >
        <Typography variant="body1">Error: {error.message}</Typography>
      </Box>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Box
      sx={{
        height: height,
        overflow: 'auto',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        borderRadius: 1,
        p: 2
      }}
    >
      <Stack
        direction="column"
        gap={1}
        sx={{ mb: 3, position: 'sticky', left: 0 }}
      >
        <Typography
          variant="subtitle1"
          sx={{
            color: theme.palette.text.primary,
            fontWeight: 600,
            textAlign: 'center'
          }}
        >
          {title}
        </Typography>

        <Stack
          direction="row"
          gap={2}
          alignItems="center"
          justifyContent="center"
          flexWrap="wrap"
        >
          {/* <Stack direction="row" gap={1} alignItems="center">
            <Typography variant="caption" sx={{ color: theme.palette.text.secondary, mr: 0.5 }}>
              LEVELS:
            </Typography>
            {HIERARCHY_LEGEND_ITEMS.map((level) => (
              <Stack key={level} direction="row" gap={0.5} alignItems="center">
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: '2px',
                    backgroundColor: getHierarchyColor(level, theme)
                  }}
                />
                <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
                  {level}
                </Typography>
              </Stack>
            ))}
          </Stack> */}
          <Stack direction="row" gap={1} alignItems="center">
            <Typography
              variant="caption"
              sx={{ color: theme.palette.text.secondary, mr: 0.5 }}
            >
              CALL TYPES:
            </Typography>
            {CALL_LEGEND_ITEMS.map((item) => (
              <Stack
                key={item.type}
                direction="row"
                gap={0.5}
                alignItems="center"
              >
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: '2px',
                    backgroundColor: CALL_TYPE_COLORS[item.type]
                  }}
                />
                <Typography
                  variant="caption"
                  sx={{ color: theme.palette.text.secondary }}
                >
                  {item.label}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Stack>
      </Stack>

      <Box
        sx={{
          position: 'relative',
          minWidth: timelineWidth + ROW_LABEL_WIDTH
        }}
      >
        {timelineRows.map((row) => (
          <Stack
            key={row.level}
            direction="row"
            alignItems="center"
            sx={{
              height: 48,
              mb: 1,
              position: 'relative'
            }}
          >
            <Box
              sx={{
                width: ROW_LABEL_WIDTH,
                flexShrink: 0,
                pr: 2,
                position: 'sticky',
                left: 0,
                backgroundColor: GLOBAL_BACKGROUND_COLOR,
                zIndex: 100,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                //  justifyContent: 'center',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  right: '100%',
                  width: TIMELINE_PADDING + NODE_SIZE,
                  backgroundColor: GLOBAL_BACKGROUND_COLOR
                }
              }}
            >
              <Typography
                variant="caption"
                sx={{
                  color: theme.palette.text.secondary,
                  fontWeight: 500,
                  textTransform: 'capitalize',
                  textAlign: 'center'
                }}
              >
                {LEVEL_LABELS[row.level]}
              </Typography>
            </Box>

            <Box
              sx={{
                width: timelineWidth,
                flexShrink: 0,
                position: 'relative',
                height: 32,
                backgroundColor: GLOBAL_BACKGROUND_COLOR,
                borderRadius: 1
              }}
            >
              {row.stateNodes.map((node) => (
                <Tooltip
                  key={node.id}
                  title={
                    <Box sx={{ maxWidth: 300 }}>
                      <Typography variant="caption" display="block">
                        <strong>{node.label}</strong>
                      </Typography>
                      {node.semanticType && (
                        <Typography variant="caption" display="block">
                          Type: {node.semanticType}
                        </Typography>
                      )}
                      {node.content && (
                        <Typography
                          variant="caption"
                          display="block"
                          sx={{ wordBreak: 'break-word' }}
                        >
                          {node.content.substring(0, 200)}
                          {node.content.length > 200 ? '...' : ''}
                        </Typography>
                      )}
                    </Box>
                  }
                  arrow
                >
                  <Box
                    sx={{
                      position: 'absolute',
                      left: `${node.position + TIMELINE_PADDING}px`,
                      top: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: 16,
                      height: 16,
                      backgroundColor: '#fff',
                      border: `2px solid ${theme.palette.grey[400]}`,
                      borderRadius: '2px',
                      cursor: 'pointer',
                      zIndex: 15,
                      boxShadow: 1,
                      '&:hover': {
                        borderColor: theme.palette.primary.main
                      }
                    }}
                  />
                </Tooltip>
              ))}

              {row.segments.map((segment) => {
                const style = getSegmentStyle(segment);
                return (
                  <Tooltip
                    key={segment.id}
                    title={
                      <Box>
                        <Typography variant="caption" display="block">
                          <strong>{segment.entityName}</strong>
                        </Typography>
                        <Typography variant="caption" display="block">
                          Type: {segment.entityType}
                        </Typography>
                        <Typography variant="caption" display="block">
                          Duration: {segment.duration.toFixed(2)}ms
                        </Typography>
                      </Box>
                    }
                    arrow
                  >
                    <Box
                      sx={{
                        position: 'absolute',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        height: 24,
                        borderRadius: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        px: 1,
                        overflow: 'hidden',
                        cursor: 'pointer',
                        transition: 'opacity 0.2s',
                        '&:hover': {
                          opacity: 0.8
                        },
                        ...style
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{
                          color:
                            segment.hierarchyLevel === 'task' ||
                            segment.hierarchyLevel === 'call'
                              ? '#333'
                              : '#fff',
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          fontSize: '10px'
                        }}
                      >
                        {segment.entityName}
                      </Typography>
                    </Box>
                  </Tooltip>
                );
              })}
            </Box>
          </Stack>
        ))}

        {reasoningDisplayRows.length > 0 &&
          (() => {
            const callRow = timelineRows.find((r) => r.level === 'call');
            if (!callRow) return null;
            const matchedSegments = callRow.segments.filter((seg) =>
              segmentReasoningMap.has(seg.id)
            );
            if (matchedSegments.length === 0) return null;

            const ROW_HEIGHT = 20;
            const INDENT_PX = 16;

            const findVariableInSegment = (
              segmentId: string,
              variableId: string,
              isAlignment: boolean
            ):
              | (TimelineReasoningVariable | TimelineReasoningDependency)
              | null => {
              const vars = segmentReasoningMap.get(segmentId)!;
              if (isAlignment) {
                return vars.find((v) => v.variableId === variableId) ?? null;
              }
              for (const v of vars) {
                if (v.dependencies) {
                  const dep = v.dependencies.find(
                    (d) => d.variableId === variableId
                  );
                  if (dep) return dep;
                }
              }
              return null;
            };

            return (
              <Box
                sx={{
                  mt: 2,
                  borderTop: `1px solid ${alpha(theme.palette.divider, 0.3)}`,
                  pt: 1
                }}
              >
                {(() => {
                  let currentParentId: string | null = null;
                  return reasoningDisplayRows.map((row, idx) => {
                    if (row.isAlignment) {
                      currentParentId = row.variableId;
                    }

                    // Hide child rows when parent is collapsed
                    if (
                      row.indent &&
                      currentParentId &&
                      !expandedAlignments.has(currentParentId)
                    ) {
                      return null;
                    }

                    const rowKey = row.indent
                      ? `${currentParentId}-${row.variableId}-${idx}`
                      : `${row.variableId}-align`;
                    const isHovered = hoveredRowId === rowKey;
                    const isExpanded =
                      row.isAlignment && expandedAlignments.has(row.variableId);
                    const rowIndex = reasoningDisplayRows.indexOf(row);
                    const hasChildren =
                      row.isAlignment &&
                      rowIndex < reasoningDisplayRows.length - 1 &&
                      reasoningDisplayRows[rowIndex + 1].indent;

                    return (
                      <Stack
                        key={rowKey}
                        direction="row"
                        alignItems="center"
                        onMouseEnter={() => setHoveredRowId(rowKey)}
                        onMouseLeave={() => setHoveredRowId(null)}
                        sx={{
                          height: ROW_HEIGHT,
                          position: 'relative',
                          backgroundColor: isHovered
                            ? alpha(theme.palette.action.hover, 0.08)
                            : 'transparent',
                          borderRadius: '2px',
                          transition: 'background-color 0.15s'
                        }}
                      >
                        <Box
                          sx={{
                            width: ROW_LABEL_WIDTH,
                            flexShrink: 0,
                            pr: 1,
                            pl: row.indent ? `${INDENT_PX + 16}px` : 0,
                            position: 'sticky',
                            left: 0,
                            backgroundColor: isHovered
                              ? alpha(theme.palette.action.hover, 0.08)
                              : GLOBAL_BACKGROUND_COLOR,
                            zIndex: 100,
                            height: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            '&::before': {
                              content: '""',
                              position: 'absolute',
                              top: 0,
                              bottom: 0,
                              right: '100%',
                              width: TIMELINE_PADDING + NODE_SIZE,
                              backgroundColor: GLOBAL_BACKGROUND_COLOR
                            }
                          }}
                        >
                          {row.isAlignment && hasChildren && (
                            <IconButton
                              size="small"
                              onClick={() => {
                                setExpandedAlignments((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(row.variableId)) {
                                    next.delete(row.variableId);
                                  } else {
                                    next.add(row.variableId);
                                  }
                                  return next;
                                });
                              }}
                              sx={{ p: 0, mr: 0.25, width: 14, height: 14 }}
                            >
                              {isExpanded ? (
                                <KeyboardArrowDownIcon
                                  sx={{
                                    fontSize: 14,
                                    color: theme.palette.text.secondary
                                  }}
                                />
                              ) : (
                                <KeyboardArrowRightIcon
                                  sx={{
                                    fontSize: 14,
                                    color: theme.palette.text.secondary
                                  }}
                                />
                              )}
                            </IconButton>
                          )}
                          <Tooltip
                            title={`${row.name} (${row.tier})`}
                            placement="left"
                          >
                            <Typography
                              variant="caption"
                              sx={{
                                fontSize: row.indent ? '9px' : '10px',
                                color:
                                  TIER_COLORS[row.tier] ||
                                  theme.palette.text.secondary,
                                fontWeight: row.indent ? 400 : 600,
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                maxWidth:
                                  ROW_LABEL_WIDTH -
                                  16 -
                                  (row.indent ? INDENT_PX + 16 : 16)
                              }}
                            >
                              {row.name}
                            </Typography>
                          </Tooltip>
                        </Box>

                        <Box
                          sx={{
                            width: timelineWidth,
                            flexShrink: 0,
                            position: 'relative',
                            height: '100%'
                          }}
                        >
                          {matchedSegments.map((segment) => {
                            const variable = findVariableInSegment(
                              segment.id,
                              row.variableId,
                              row.isAlignment
                            );
                            if (!variable) return null;

                            return (
                              <Tooltip
                                key={segment.id}
                                title={
                                  <Box sx={{ maxWidth: 320 }}>
                                    <Typography
                                      variant="caption"
                                      display="block"
                                      sx={{ fontWeight: 600 }}
                                    >
                                      {variable.name}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      display="block"
                                      sx={{ mt: 0.25 }}
                                    >
                                      {String(variable.value)}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      display="block"
                                      sx={{ mt: 0.5, fontStyle: 'italic' }}
                                    >
                                      {variable.reason}
                                    </Typography>
                                  </Box>
                                }
                                arrow
                                placement="top"
                              >
                                <Chip
                                  label={String(variable.value)}
                                  size="small"
                                  sx={{
                                    position: 'absolute',
                                    left: `${segment.startPosition + TIMELINE_PADDING}px`,
                                    top: '50%',
                                    transform: 'translateY(-50%)',
                                    height: row.indent ? 16 : 18,
                                    fontSize: row.indent ? '9px' : '10px',
                                    fontWeight: 500,
                                    backgroundColor: alpha(
                                      getVariableColor(variable),
                                      0.15
                                    ),
                                    cursor: 'pointer',
                                    color: getVariableColor(variable),
                                    border: `1px solid ${alpha(getVariableColor(variable), 0.4)}`,
                                    borderRadius: '4px',
                                    maxWidth: `${segment.width}px`,
                                    '& .MuiChip-label': {
                                      px: 0.5,
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap'
                                    }
                                  }}
                                />
                              </Tooltip>
                            );
                          })}
                        </Box>
                      </Stack>
                    );
                  });
                })()}
              </Box>
            );
          })()}
      </Box>
    </Box>
  );
};
