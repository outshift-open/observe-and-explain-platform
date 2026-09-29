/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useNavigate, useParams } from 'react-router-dom';
import { CardContent, Stack, Typography, Box, useTheme } from '@mui/material';
import { PATHS } from '@/routes/routes.tsx';
import { AgentCardWithStatefulEval } from '@/types/oxp.type';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { WidgetCard } from '..';
import { getScoreVariant } from '@/utils/metrics';
import {
  GaugeChart,
  GeneralSize,
  Tag,
  TagBackgroundColorVariants,
  Tooltip,
  Card
} from '@open-ui-kit/core';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from '@/common/styles';

interface AgentCardProps {
  agent: AgentCardWithStatefulEval;
}

export const AgentCard = ({ agent }: AgentCardProps) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { applicationId } = useParams();
  const statefulEvalEnabled = useFeatureFlag('stateful_eval');
  const agentDetailsPath = PATHS.agent
    .replace(':applicationId', encodeURIComponent(applicationId ?? ''))
    .replace(':agentId', encodeURIComponent(agent.id ?? ''));

  const reliabilityScore = Number.isNaN(
    Math.round((agent.trajectoryScore / agent.totalSessions) * 100)
  )
    ? 100
    : Math.round((agent.trajectoryScore / agent.totalSessions) * 100);

  return (
    <Card
      sx={{
        width: '100%',
        minWidth: '370px',
        height: '432px',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        border: `1px solid ${GLOBAL_BORDER_COLOR}`,
        cursor: 'pointer',
        transition:
          'background-color 0.2s ease, box-shadow 0.2s ease, transform 0.1s ease',
        '&:hover': {
          backgroundColor: theme.palette.vars.baseBackgroundMedium,
          boxShadow: theme.shadows[4],
          transform: 'translateY(-2px)'
        }
      }}
      onClick={() => {
        //navigate(agentDetailsPath);
      }}
    >
      <CardContent
        sx={{
          display: 'flex',
          gap: '12px',
          flexDirection: 'column',
          height: '100%',
          width: '100%'
        }}
      >
        <Stack gap={'12px'} direction={'column'} sx={{ height: '100%' }}>
          <Stack direction={'column'} gap={'4px'}>
            <Typography
              variant={'body1'}
              sx={{
                fontWeight: 600,
                maxWidth: '300px',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis'
              }}
            >
              {agent.name}
            </Typography>

            <Stack direction="row" gap="8px" alignItems="center">
              {/* <Typography variant="caption">Version {agent.version}</Typography>
                <Box component="span" sx={{ width: 4, height: 4, borderRadius: '50%', backgroundColor: 'text.secondary' }} />
                <Typography variant="caption">LLM {agent.llm}</Typography>
                <Box component="span" sx={{ width: 4, height: 4, borderRadius: '50%', backgroundColor: 'text.secondary' }} /> */}
              {statefulEvalEnabled && (
                <Typography variant="caption">
                  {agent.totalSessions} Sessions
                </Typography>
              )}
            </Stack>
          </Stack>

          {statefulEvalEnabled && (
            <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
              <Box>
                <GaugeChart
                  data={[
                    {
                      name: 'Overall Reliability',
                      value: reliabilityScore
                    }
                  ]}
                  variant={getScoreVariant(reliabilityScore)}
                  customLabelComponent={
                    <Box sx={{ marginTop: '8px !important' }}>
                      <Typography variant="caption">Pass</Typography>
                    </Box>
                  }
                />
              </Box>

              <Card glow>
                <Tooltip
                  title={
                    agent.topFailingEntities?.[0]?.explanation ??
                    'Agent is working properly.'
                  }
                  placement="top"
                  slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      textAlign: 'center'
                    }}
                  >
                    {agent.topFailingEntities?.[0]?.explanation ??
                      'Agent is working properly.'}
                  </Typography>
                </Tooltip>
              </Card>
            </Stack>
          )}

          {statefulEvalEnabled && (
            <Stack direction={'row'} gap={'8px'}>
              <WidgetCard
                tooltip={`${agent.fatalErrors} occurences of fatal failures across Intent Recognition, Relevancy, and Groundedness.`}
                content={
                  <Stack
                    direction={'column'}
                    gap={'4px'}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(
                        `${PATHS.applicationCollect}`.replace(
                          ':applicationId',
                          applicationId ?? ''
                        )
                      );
                    }}
                  >
                    <Typography
                      variant="h5"
                      sx={{
                        textAlign: 'center',
                        color: theme.palette.vars.negativeIconDefault
                      }}
                    >
                      {agent.fatalErrors}
                    </Typography>
                    <Typography variant="caption" sx={{ textAlign: 'center' }}>
                      Fatal
                    </Typography>
                  </Stack>
                }
                cardSx={{
                  backgroundColor: theme.palette.vars.baseBackgroundStrong,
                  paddingBottom: '0px'
                }}
              />
              <WidgetCard
                tooltip={`${agent.minorErrors} occurences of minor failures across Intent Recognition, Relevancy, and Groundedness.`}
                content={
                  <Stack
                    direction={'column'}
                    gap={'4px'}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(
                        `${PATHS.applicationCollect}`.replace(
                          ':applicationId',
                          applicationId ?? ''
                        )
                      );
                    }}
                  >
                    <Typography
                      variant="h5"
                      sx={{
                        textAlign: 'center',
                        color: theme.palette.vars.warningIconDefault
                      }}
                    >
                      {agent.minorErrors}
                    </Typography>
                    <Typography variant="caption" sx={{ textAlign: 'center' }}>
                      Minor
                    </Typography>
                  </Stack>
                }
                cardSx={{
                  backgroundColor: theme.palette.vars.baseBackgroundStrong,
                  paddingBottom: '0px'
                }}
              />
              {/* <WidgetCard
                content={
                  <Stack direction={'column'} gap={'4px'}>
                    <Typography variant="h5" sx={{ textAlign: 'center', color: getScoreColor(agent.intents, theme) }}>
                      {agent.intents}%
                    </Typography>
                    <Typography variant="caption" sx={{ textAlign: 'center' }}>
                      Intents
                    </Typography>
                  </Stack>
                }
                cardSx={{ backgroundColor: theme.palette.vars.baseBackgroundStrong, paddingBottom: '0px' }}
              /> */}
            </Stack>
          )}

          {statefulEvalEnabled &&
          agent.topFailingEntities?.length &&
          agent.topFailingEntities?.length > 0 ? (
            <Stack direction={'column'} gap={'8px'} sx={{ marginTop: 'auto' }}>
              <Typography variant="body2Semibold">
                Top Failing Entities
              </Typography>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto auto auto',
                  columnGap: '12px',
                  alignItems: 'center'
                }}
              >
                {agent.topFailingEntities?.map((entity, index) => {
                  const isLastRow =
                    index === (agent.topFailingEntities?.length ?? 0) - 1;
                  const rowSx = {
                    display: 'grid',
                    gridColumn: '1 / -1',
                    gridTemplateColumns: 'subgrid',
                    alignItems: 'center',
                    paddingY: '4px',
                    borderBottom: isLastRow
                      ? 'none'
                      : `1px solid ${theme.palette.vars.baseBorderDefault}`
                  };
                  return (
                    <Box key={index} sx={rowSx}>
                      <Stack
                        direction="row"
                        alignItems="center"
                        gap="4px"
                        sx={{ minWidth: 0, flex: '0 1 auto' }}
                      >
                        <Tooltip
                          title={entity.name}
                          placement="top"
                          slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
                        >
                          <Typography
                            variant="caption"
                            sx={{
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            {entity.name}
                          </Typography>
                        </Tooltip>
                        {entity.reasoning && (
                          <Tooltip
                            title={entity.reasoning}
                            placement="top"
                            slotProps={{ tooltip: { sx: { maxWidth: 300 } } }}
                          >
                            <HelpOutlineIcon
                              sx={{
                                width: '14px',
                                height: '14px',
                                color: theme.palette.vars.baseTextMedium,
                                cursor: 'help'
                              }}
                            />
                          </Tooltip>
                        )}
                      </Stack>
                      <Tag
                        color={TagBackgroundColorVariants.AccentAWeak}
                        size={GeneralSize.Small}
                      >
                        {entity.type === 'tool'
                          ? 'Tool'
                          : entity.type === 'llm'
                            ? 'LLM'
                            : 'Agent'}
                      </Tag>
                      <Typography variant="caption">
                        {entity.failingAction}
                      </Typography>
                      <Typography variant="captionSemibold">{`${entity.occurrences} Occurrence${entity.occurrences && entity.occurrences > 1 ? 's' : ''}`}</Typography>
                    </Box>
                  );
                })}
              </Box>
            </Stack>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default AgentCard;
