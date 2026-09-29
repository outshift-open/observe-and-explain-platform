/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Tooltip, Typography, useTheme } from '@mui/material';
import { GeneralSize, Tag, TagBackgroundColorVariants, Spinner } from '@open-ui-kit/core';
import { StaticTopology } from '@/components';
import { LLM } from '@/assets/icons';
import {
  useApplications,
  useLiveSessions,
  useSessionsCount,
  useStaticTopology
} from '@/api/oxpApi';
import { useNavigate, useParams } from 'react-router-dom';
import { isToolDataArray } from '@/utils';
import { useTimeRangeStore } from '@/store';
import { PATHS } from '@/routes/routes';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';

interface EntityWithDescription {
  name: string;
  description?: string;
}

const EXCLUDED_AGENT_NAMES = ['__start__', '__end__', 'finalize'];

export const OverviewTab = () => {
  const theme = useTheme();
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const liveTopologyEnabled = useFeatureFlag('live_topology');

  const { data: applicationList, isLoading: applicationListFetching } =
    useApplications();
  const { data: topology, isLoading: topologyLoading } = useStaticTopology(
    applicationId ?? ''
  );

  const { startDate, endDate } = useTimeRangeStore();

  const { data: sessionsCountData } = useSessionsCount(
    applicationId ?? '',
    startDate,
    endDate
  );

  const {
    data: liveSessionsData,
    error: liveSessionsError,
    isLoading: liveSessionsLoading
  } = useLiveSessions(applicationId ?? '', liveTopologyEnabled);

  const { llms = [] } =
    applicationList?.applications.find(
      (application) => application.applicationName === applicationId
    ) ?? {};

  // Extract agents and tools from topology data with their descriptions
  const agents: EntityWithDescription[] = [];
  const tools: EntityWithDescription[] = [];

  if (topology && topology.nodes) {
    Object.values(topology.nodes).forEach((node) => {
      if (isToolDataArray(node.data)) {
        node.data.forEach((tool) => {
          if (!tools.some((t) => t.name === tool.name)) {
            tools.push({ name: tool.name, description: tool.description });
          }
        });
      } else if (!EXCLUDED_AGENT_NAMES.includes(node.id)) {
        agents.push({ name: node.name, description: node.description });
      }
    });
  }

  if (applicationListFetching || topologyLoading || liveSessionsLoading) {
    return (
      <Stack
        alignItems={'center'}
        justifyContent={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  return (
    <Stack direction="row" gap="24px" sx={{ height: '100%', width: '100%' }}>
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          minHeight: 500,
          //backgroundColor: theme.palette.vars.baseBackgroundWeak,
          //  border: `1px solid ${theme.palette.divider}`,
          borderRadius: '8px'
          //padding: '16px'
        }}
      >
        <StaticTopology />
      </Box>

      <Stack
        direction="column"
        gap="16px"
        sx={{
          width: '300px',
          flexShrink: 0
        }}
      >
        <Stack direction="column" gap="4px" sx={{ padding: '0 16px' }}>
          <Box
            sx={{
              borderRadius: '8px',
              cursor: 'pointer'
            }}
            onClick={() => {
              navigate(
                PATHS.applicationCollectCompleted.replace(
                  ':applicationId',
                  applicationId ?? ''
                )
              );
            }}
          >
            <Stack direction="row" gap="12px" alignItems="center">
              <Typography variant="body1" fontWeight={600}>
                Completed Sessions
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                <Tag
                  color={TagBackgroundColorVariants.AccentGWeak}
                  size={GeneralSize.Small}
                >
                  {sessionsCountData?.count ?? 0}
                </Tag>
              </Box>
            </Stack>
          </Box>

          {liveTopologyEnabled && (
            <Box
              sx={{
                borderRadius: '8px',
                cursor: 'pointer'
              }}
              onClick={() => {
                navigate(
                  PATHS.applicationCollectLiveSessions.replace(
                    ':applicationId',
                    applicationId ?? ''
                  )
                );
              }}
            >
              <Stack direction="row" gap="12px" alignItems="center">
                <Typography variant="body1" fontWeight={600}>
                  Live Sessions
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  <Tag
                    color={TagBackgroundColorVariants.AccentAWeak}
                    size={GeneralSize.Small}
                  >
                    {liveSessionsData?.sessions?.length ?? 0}
                  </Tag>
                </Box>
              </Stack>
            </Box>
          )}
        </Stack>

        <Box
          sx={{
            //  backgroundColor: theme.palette.vars.baseBackgroundWeak,
            borderRadius: '8px',
            padding: '16px'
          }}
        >
          <Stack direction="column" gap="12px">
            <Typography variant="body1" fontWeight={600}>
              Agents
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {agents?.map((agent) => (
                <Tooltip
                  key={agent.name}
                  title={agent.description || ''}
                  arrow
                  placement="top"
                >
                  <span>
                    <Tag
                      color={TagBackgroundColorVariants.AccentAWeak}
                      size={GeneralSize.Small}
                      sx={{ cursor: 'pointer' }}
                    >
                      {agent.name}
                    </Tag>
                  </span>
                </Tooltip>
              ))}
            </Box>
          </Stack>
        </Box>

        <Box
          sx={{
            //  backgroundColor: theme.palette.vars.baseBackgroundWeak,
            borderRadius: '8px',
            padding: '16px'
          }}
        >
          <Stack direction="column" gap="12px">
            <Typography variant="body1" fontWeight={600}>
              LLMs
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {llms?.map((llm) => (
                <Tag
                  key={llm}
                  color={TagBackgroundColorVariants.AccentGWeak}
                  size={GeneralSize.Small}
                  icon={
                    <LLM
                      fill={theme.palette.vars.baseTextMedium}
                      sx={{ width: '16px', height: '16px' }}
                    />
                  }
                  sx={{ cursor: 'pointer' }}
                >
                  {llm}
                </Tag>
              ))}
            </Box>
          </Stack>
        </Box>

        <Box
          sx={{
            //  backgroundColor: theme.palette.vars.baseBackgroundWeak,
            borderRadius: '8px',
            padding: '16px'
          }}
        >
          <Stack direction="column" gap="12px">
            <Typography variant="body1" fontWeight={600}>
              Tools
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {tools?.map((tool) => (
                <Tooltip
                  key={tool.name}
                  title={tool.description || ''}
                  arrow
                  placement="top"
                >
                  <span>
                    <Tag
                      color={TagBackgroundColorVariants.AccentDWeak}
                      size={GeneralSize.Small}
                      sx={{ cursor: 'pointer' }}
                    >
                      {tool.name}
                    </Tag>
                  </span>
                </Tooltip>
              ))}
            </Box>
          </Stack>
        </Box>
      </Stack>
    </Stack>
  );
};

export default OverviewTab;
