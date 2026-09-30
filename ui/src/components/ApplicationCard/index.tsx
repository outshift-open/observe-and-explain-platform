/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useNavigate } from 'react-router-dom';
import {
  Stack,
  Typography,
  Box,
  useTheme,
  Tooltip,
  IconButton
} from '@mui/material';
import { PATHS } from '@/routes/routes.tsx';
import { format } from 'date-fns';
import {
  OS_LIGHT_COLORS,
  TagBackgroundColorVariants,
  Card,
  CardContent
} from '@open-ui-kit/core';
import { ApplicationWithStatefulEval } from '@/types/oxp.type';
import { CustomTooltip, Tags, WidgetCard } from '..';
import {
  getDisplayedResultsCount,
  getDisplayedResultsCountTooltip
} from '@/utils';
import { ApplicationGrid, LLM } from '@/assets/icons';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';

interface ApplicationCardProps {
  application: ApplicationWithStatefulEval;
  healthScore: number;
}

export const ApplicationCard = ({
  application,
  healthScore
}: ApplicationCardProps) => {
  const theme = useTheme();
  const applicationDetailsPath = PATHS.application.replace(
    ':applicationId',
    encodeURIComponent(application.applicationName ?? '')
  );
  const navigate = useNavigate();

  const getCostTitleContent = () => {
    const costNumberFormat = application.costDollars
      ? getDisplayedResultsCount(application.costDollars)
      : '0';
    const costNumberFormatTooltip = application.costDollars
      ? `${getDisplayedResultsCountTooltip(application.costDollars)}$`
      : '';

    return (
      <Tooltip title={costNumberFormatTooltip}>
        <Typography variant="h5">{costNumberFormat}$</Typography>
      </Tooltip>
    );
  };

  return (
    <Card
      connector
      sx={{
        width: '100%',
        minWidth: '370px',
        height: '320px',
        cursor: 'pointer',
        transition:
          'background-color 0.2s ease, box-shadow 0.2s ease, transform 0.1s ease',
        '&:hover': {
          boxShadow: theme.shadows[4],
          transform: 'translateY(-2px)'
        }
      }}
      onClick={() => {
        navigate(applicationDetailsPath);
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
        <Stack
          direction={'column'}
          gap={'4px'}
          justifyContent={'space-between'}
          sx={{ height: '100%' }}
        >
          <Stack direction={'column'} gap={'8px'}>
            <Stack direction={'column'} gap={'4px'}>
              <Stack direction={'row'} justifyContent={'space-between'}>
                <Stack direction={'row'} gap={'4px'} alignItems={'center'}>
                  <ApplicationGrid
                    fill={theme.palette.vars.baseTextMedium}
                    sx={{ width: '16px', height: '16px' }}
                  />
                  <Typography variant={'captionMedium'}>App</Typography>
                </Stack>
                <IconButton>
                  <BookmarkBorderIcon sx={{ width: '20px', height: '20px' }} />
                </IconButton>
              </Stack>
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
                {application.applicationName}
                {application.description && (
                  <CustomTooltip
                    title={
                      typeof application.description === 'string' ? (
                        <Typography
                          variant={'caption'}
                          sx={{ whiteSpace: 'pre-line' }}
                        >
                          {application.description}
                        </Typography>
                      ) : (
                        application.description
                      )
                    }
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
                )}
              </Typography>

              <Stack direction="row" gap="2px" alignItems="center">
                {application.version && (
                  <Typography variant="caption">
                    Version {application.version}
                  </Typography>
                )}

                <Box display="flex" alignItems="center" gap="2px">
                  <Box
                    width="4px"
                    height="4px"
                    borderRadius="2px"
                    sx={{
                      backgroundColor: (theme) => OS_LIGHT_COLORS.grey[200]
                    }}
                  />
                  <Typography variant={'caption'} fontWeight={500}>
                    {application.timestamp
                      ? format(new Date(application.timestamp), 'MMM d, yyyy')
                      : ''}
                  </Typography>
                </Box>
              </Stack>

              <Stack direction={'column'} gap={'8px'}>
                <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
                  <Typography variant={'captionMedium'} fontWeight={500}>
                    Agents
                  </Typography>
                  <Tags
                    tags={application.agents?.map((agent) => ({
                      name: agent,
                      color: TagBackgroundColorVariants.AccentAWeak
                    }))}
                    minDisplayed={1}
                  />
                </Stack>

                <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
                  <Typography variant={'captionMedium'} fontWeight={500}>
                    LLMs
                  </Typography>
                  <Tags
                    tags={application.llms?.map((llm) => ({
                      name: llm,
                      icon: (
                        <LLM
                          fill={theme.palette.vars.baseTextMedium}
                          sx={{ width: '16px', height: '16px' }}
                        />
                      ),
                      color: TagBackgroundColorVariants.AccentGWeak
                    }))}
                    minDisplayed={1}
                  />
                </Stack>
              </Stack>
            </Stack>
          </Stack>

          <Stack direction={'column'} gap={'8px'}>
            <Stack direction={'row'} gap={'8px'}>
              <WidgetCard
                tooltip={`${application.fatalFailures ?? 0} occurences of fatal failures across Intent Recognition, Relevancy, and Groundedness.`}
                content={
                  <Stack
                    direction={'column'}
                    gap={'4px'}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(
                        `${PATHS.applicationCollect}`.replace(
                          ':applicationId',
                          application.applicationName ?? ''
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
                      {application.fatalFailures ?? 0}
                    </Typography>
                    <Typography variant="caption" sx={{ textAlign: 'center' }}>
                      Fatal
                    </Typography>
                  </Stack>
                }
              />
              <WidgetCard
                tooltip={`${application.minorFailures ?? 0} occurences of minor failures across Intent Recognition, Relevancy, and Groundedness.`}
                content={
                  <Stack
                    direction={'column'}
                    gap={'4px'}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(
                        `${PATHS.applicationCollect}`.replace(
                          ':applicationId',
                          application.applicationName ?? ''
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
                      {application.minorFailures ?? 0}
                    </Typography>
                    <Typography variant="caption" sx={{ textAlign: 'center' }}>
                      Minor
                    </Typography>
                  </Stack>
                }
              />
            </Stack>

            <Stack direction={'row'} gap={'8px'}>
              <WidgetCard
                title={'Total Cost'}
                content={getCostTitleContent()}
                description={'The total cost of LLM operations.'}
              />
              <WidgetCard
                title={'Health Score'}
                content={
                  <Typography variant="h5">
                    {healthScore ? `${healthScore}%` : 'N/A'}
                  </Typography>
                }
                description={
                  'The health score of the application, aggregated from the overall performance score, the overall quality score and the overall reliability score of the application.'
                }
              />
            </Stack>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default ApplicationCard;
