/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography } from '@mui/material';
import { CustomTooltip } from '../CustomTooltip';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { GeneralSize, Tag } from '@open-ui-kit/core';
import { colorTokens } from '@/theme/colors';
import { CostEfficiencyGrouppedSessions as CostEfficiencyGrouppedSessionsType } from '@/types/oxp.type';
import { SemanticGroupOption } from '../SemanticGroupSelector';
import { useMemo } from 'react';
import { formatTwoDecimals } from '@/utils/stringUtils';

interface CostEfficiencySummaryProps {
  data: CostEfficiencyGrouppedSessionsType[];
  allGroups: SemanticGroupOption[];
}

export const CostEfficiencySummary = ({
  data,
  allGroups
}: CostEfficiencySummaryProps) => {
  const highestCostTopicData = useMemo(() => {
    if (!data || data.length === 0 || allGroups.length === 0)
      return { label: '', cost: 0 };
    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));
    const costByGroup = new Map<string, number>();
    for (const item of data) {
      const label = groupMap.get(item.groupId);
      if (!label) continue;
      costByGroup.set(
        label,
        (costByGroup.get(label) ?? 0) + (item.actualCost ?? 0)
      );
    }
    let maxLabel = '';
    let maxCost = -Infinity;
    for (const [label, cost] of costByGroup) {
      if (cost > maxCost) {
        maxCost = cost;
        maxLabel = label;
      }
    }
    return { label: maxLabel, cost: maxCost === -Infinity ? 0 : maxCost };
  }, [data, allGroups]);

  const highestCostTopic = highestCostTopicData.label;
  const highestCostTopicCost = formatTwoDecimals(highestCostTopicData.cost);

  const mostWastefulTopicData = useMemo(() => {
    if (!data || data.length === 0 || allGroups.length === 0)
      return { label: '', cost: 0 };
    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));
    const wasteByGroup = new Map<string, number>();
    for (const item of data) {
      const label = groupMap.get(item.groupId);
      if (!label) continue;
      wasteByGroup.set(
        label,
        (wasteByGroup.get(label) ?? 0) + (item.estimatedWaste ?? 0)
      );
    }
    let maxLabel = '';
    let maxWaste = -Infinity;
    for (const [label, waste] of wasteByGroup) {
      if (waste > maxWaste) {
        maxWaste = waste;
        maxLabel = label;
      }
    }
    return { label: maxLabel, cost: maxWaste === -Infinity ? 0 : maxWaste };
  }, [data, allGroups]);

  const mostWastefulTopic = mostWastefulTopicData.label;
  const mostWastefulTopicCost = formatTwoDecimals(mostWastefulTopicData.cost);

  const topicWithMostWastefulSessionsData = useMemo(() => {
    if (!data || data.length === 0 || allGroups.length === 0)
      return { label: '', avgWaste: 0 };
    const groupMap = new Map(allGroups.map((g) => [g.groupId, g.label]));
    const wasteByGroup = new Map<string, { total: number; count: number }>();
    for (const item of data) {
      const label = groupMap.get(item.groupId);
      if (!label) continue;
      const entry = wasteByGroup.get(label) ?? { total: 0, count: 0 };
      entry.total += item.estimatedWaste ?? 0;
      entry.count += 1;
      wasteByGroup.set(label, entry);
    }
    let maxLabel = '';
    let maxAvg = -Infinity;
    for (const [label, { total, count }] of wasteByGroup) {
      const avg = total / count;
      if (avg > maxAvg) {
        maxAvg = avg;
        maxLabel = label;
      }
    }
    return { label: maxLabel, avgWaste: maxAvg === -Infinity ? 0 : maxAvg };
  }, [data, allGroups]);

  const topicWithMostWastefulSessions = topicWithMostWastefulSessionsData.label;
  const topicWithMostWastefulSessionsCost = formatTwoDecimals(
    topicWithMostWastefulSessionsData.avgWaste
  );

  return (
    <Stack direction="row" alignItems="flex-start" gap="24px">
      <Stack direction="column" gap="4px">
        <Stack direction="row" alignItems="flex-start" gap="4px">
          <Typography variant="captionSemibold">Top Wasteful Topic</Typography>

          <CustomTooltip
            title={`The topic with the highest estimated waste across all its sessions: ${mostWastefulTopicCost}$`}
            placement={'top'}
            sx={{ maxWidth: '550px' }}
          >
            <InfoOutlineIcon
              sx={{
                width: '14px',
                height: '14px',
                cursor: 'pointer'
              }}
            />
          </CustomTooltip>
        </Stack>
        <CustomTooltip
          title={mostWastefulTopic}
          placement="top"
          enterDelay={1500}
          enterNextDelay={1500}
        >
          <Box>
            <Tag
              sx={{
                backgroundColor: colorTokens.greyBackground,
                border: `1px solid ${colorTokens.inactiveBorder}`
              }}
              size={GeneralSize.Medium}
            >
              {mostWastefulTopic}
            </Tag>
          </Box>
        </CustomTooltip>
      </Stack>

      <Stack direction="column" gap="4px">
        <Stack direction="row" alignItems="flex-start" gap="4px">
          <Typography variant="captionSemibold">
            Topic with most wasteful sessions
          </Typography>

          <CustomTooltip
            title={`The topic with the highest estimated waste average across all its sessions: ${topicWithMostWastefulSessionsCost}$`}
            placement={'top'}
            sx={{ maxWidth: '550px' }}
          >
            <InfoOutlineIcon
              sx={{
                width: '14px',
                height: '14px',
                cursor: 'pointer'
              }}
            />
          </CustomTooltip>
        </Stack>
        <CustomTooltip
          title={topicWithMostWastefulSessions}
          placement="top"
          enterDelay={1500}
          enterNextDelay={1500}
        >
          <Box>
            <Tag
              sx={{
                backgroundColor: colorTokens.greyBackground,
                border: `1px solid ${colorTokens.inactiveBorder}`
              }}
              size={GeneralSize.Medium}
            >
              {topicWithMostWastefulSessions}
            </Tag>
          </Box>
        </CustomTooltip>
      </Stack>

      <Stack direction="column" gap="4px">
        <Stack direction="row" alignItems="flex-start" gap="4px">
          <Typography variant="captionSemibold">Highest Cost Topic</Typography>

          <CustomTooltip
            title={`The topic with the highest sum cost of all its sessions: ${highestCostTopicCost}$`}
            placement={'top'}
            sx={{ maxWidth: '550px' }}
          >
            <InfoOutlineIcon
              sx={{
                width: '14px',
                height: '14px',
                cursor: 'pointer'
              }}
            />
          </CustomTooltip>
        </Stack>
        <CustomTooltip
          title={highestCostTopic}
          placement="top"
          enterDelay={1500}
          enterNextDelay={1500}
        >
          <Box>
            <Tag
              sx={{
                backgroundColor: colorTokens.greyBackground,
                border: `1px solid ${colorTokens.inactiveBorder}`
              }}
              size={GeneralSize.Medium}
            >
              {highestCostTopic}
            </Tag>
          </Box>
        </CustomTooltip>
      </Stack>
    </Stack>
  );
};
