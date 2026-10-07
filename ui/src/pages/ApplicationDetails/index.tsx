/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { GeneralSize, Spinner, Stack, Tag } from '@open-ui-kit/core';
import {
  HealthScore,
  PageWithTitle,
  SessionDetails,
  SessionStatus,
  CustomTooltip
} from '@/components';
import { pageGradientBottomSx, pageGradientContentSx } from '@/common/styles';
import { Box, Typography, useTheme } from '@mui/material';
import { useMatch, useNavigate, useParams } from 'react-router';
import { ApplicationTabs } from './ApplicationTabs';
import { useMemo } from 'react';
import { PATHS } from '@/routes/routes.tsx';
import {
  useApplications,
  useApplicationSessionsWithStatefulEval,
  useApplicationSummaryMetrics,
  useSemanticGroupDetails,
  useSemanticGroups
} from '@/api/oxpApi';
import { useDebouncedValue } from '@/utils';
import { useTimeRangeStore } from '@/store';
import {
  formatTwoDecimals,
  getDisplayedResultsCount,
  formatDurationMs,
  computeOverallQuality,
  computeOverallReliability,
  computeOverallPerformance
} from '@/utils';
import { colorTokens } from '@/theme/colors';
import { SessionWithStatefulEval } from '@/types/oxp.type';

const COLLECT_TAB_SEGMENTS = ['completed', 'live-sessions'];

const ApplicationDetails = () => {
  const {
    applicationId,
    tab,
    sessionId: rawSessionId,
    liveSessionId,
    analyzeTab,
    semanticGroup
  } = useParams();
  const sessionId = COLLECT_TAB_SEGMENTS.includes(rawSessionId ?? '')
    ? undefined
    : rawSessionId;
  const { startDate, endDate } = useTimeRangeStore();
  const matchOverview = useMatch(PATHS.applicationOverview);
  const matchCollectWithSession = useMatch(PATHS.applicationCollectSession);
  const matchCollectWithSessionTab = useMatch(
    PATHS.applicationCollectSessionTab
  );
  const matchCollect = useMatch(PATHS.applicationCollect);
  const matchCollectCompleted = useMatch(PATHS.applicationCollectCompleted);
  const matchCollectLiveSessions = useMatch(
    PATHS.applicationCollectLiveSessions
  );
  const matchCollectLiveSession = useMatch(PATHS.applicationCollectLiveSession);
  const matchAnalyze = useMatch(PATHS.applicationAnalyze);
  const matchAnalyzeSubTab = useMatch(
    '/applications/:applicationId/analyze/:analyzeTab'
  );
  const matchAnalyzeSemanticGroup = useMatch(
    '/applications/:applicationId/analyze/:analyzeTab/:semanticGroup'
  );
  const matchMonitor = useMatch(PATHS.applicationMonitor);

  const isSessionDetailView = Boolean(
    (matchCollectWithSession || matchCollectWithSessionTab) &&
      !matchCollectLiveSession &&
      !matchCollectCompleted &&
      !matchCollectLiveSessions
  );

  const {
    data: applicationList,
    error: applicationListError,
    isLoading: applicationListFetching
  } = useApplications();
  const applicationDescription =
    applicationList?.applications.find(
      (application) => application.applicationName === applicationId
    )?.description ?? '';

  const debouncedStartDate = useDebouncedValue(startDate, 500);
  const debouncedEndDate = useDebouncedValue(endDate, 500);
  const { data: sessionsData, isLoading: sessionsLoading } =
    useApplicationSessionsWithStatefulEval(
      applicationId ?? '',
      debouncedStartDate,
      debouncedEndDate
    );

  const {
    data: semanticGroupDetailsData,
    isLoading: semanticGroupDetailsLoading,
    isError: semanticGroupDetailsError
  } = useSemanticGroupDetails(semanticGroup ?? '');

  const {
    data: applicationSummaryMetricsData,
    isLoading: isLoadingApplicationSummaryMetrics
  } = useApplicationSummaryMetrics(
    applicationId ?? '',
    debouncedStartDate,
    debouncedEndDate
  );

  const {
    data: semanticGroupsData,
    isLoading: semanticGroupsLoading,
    isError: semanticGroupsError
  } = useSemanticGroups(applicationId ?? '');

  const parentSemanticGroupSessionDetails = useMemo(() => {
    if (!semanticGroupsData || !sessionId) return null;
    return semanticGroupsData.find((group) =>
      group.session_ids.includes(sessionId)
    );
  }, [semanticGroupsData, sessionId]);

  const sessionStatus = useMemo(() => {
    if (!sessionsData?.sessionList || !sessionId) return null;

    const targetSession = sessionsData.sessionList.find(
      (session) => session.sessionId === sessionId
    );

    if (!targetSession) return null;

    const statefulEval = (targetSession as any).statefulEval;
    if (!statefulEval) return targetSession as SessionWithStatefulEval;

    let parsedValue: any = null;
    try {
      parsedValue =
        typeof statefulEval.value === 'string'
          ? JSON.parse(statefulEval.value)
          : statefulEval;
    } catch {
      parsedValue = null;
    }

    let reasoningJson = null;
    try {
      reasoningJson =
        typeof parsedValue?.reasoning === 'string'
          ? JSON.parse(parsedValue.reasoning)
          : (parsedValue?.reasoning ?? null);
    } catch {
      reasoningJson = null;
    }

    return reasoningJson?.trajectory_score;
  }, [sessionsData, sessionId]);

  const healthScore = useMemo(() => {
    if (!applicationSummaryMetricsData) return 0;

    const qualityScore = computeOverallQuality(
      applicationSummaryMetricsData.quality
    );
    const reliabilityScore = computeOverallReliability(
      applicationSummaryMetricsData.reliability
    );
    const performanceScore = computeOverallPerformance(
      applicationSummaryMetricsData.performance
    );
    const overallScore =
      (qualityScore + reliabilityScore + performanceScore) / 3;

    return Math.round(overallScore);
  }, [applicationSummaryMetricsData]);

  const theme = useTheme();
  const navigate = useNavigate();

  const handleLearnMore = () => {
    navigate(
      PATHS.applicationMonitor.replace(':applicationId', applicationId ?? '')
    );
  };

  const breadcrumbItems = useMemo(() => {
    const TAB_LABELS: Record<string, string> = {
      overview: 'Overview',
      monitor: 'Metrics',
      collect: 'Session Inspection',
      analyze: 'Explain'
    };
    const buildPath = (template: string, params: Record<string, string>) =>
      template.replace(/:([A-Za-z]+)/g, (_, key) =>
        encodeURIComponent(params[key] ?? '')
      );

    const effectiveTab =
      tab ??
      (matchOverview
        ? 'overview'
        : matchCollectWithSession ||
            matchCollectWithSessionTab ||
            matchCollect ||
            matchCollectLiveSession
          ? 'collect'
          : matchAnalyze || matchAnalyzeSubTab || matchAnalyzeSemanticGroup
            ? 'analyze'
            : matchMonitor
              ? 'monitor'
              : undefined);

    const items = [
      { text: 'Applications', link: PATHS.applications },
      {
        text: applicationId ?? '',
        link: buildPath(PATHS.application, {
          applicationId: applicationId ?? ''
        })
      }
    ];

    if (effectiveTab) {
      const pretty = TAB_LABELS[effectiveTab] ?? effectiveTab;
      const tabPathMap: Record<string, string> = {
        overview: PATHS.applicationOverview,
        monitor: PATHS.applicationMonitor,
        collect: PATHS.applicationCollect,
        analyze: PATHS.applicationAnalyzeOverview
      };
      const tabPathTemplate = tabPathMap[effectiveTab];
      if (tabPathTemplate) {
        items.push({
          text: pretty,
          link: buildPath(tabPathTemplate, {
            applicationId: applicationId ?? ''
          })
        });
      }

      if (effectiveTab === 'collect' && sessionId) {
        items.push({
          text: sessionId,
          link: buildPath(PATHS.applicationCollectSession, {
            applicationId: applicationId ?? '',
            sessionId
          })
        });
      }

      if (effectiveTab === 'collect' && liveSessionId) {
        items.push({
          text: liveSessionId,
          link: buildPath(PATHS.applicationCollectLiveSession, {
            applicationId: applicationId ?? '',
            liveSessionId
          })
        });
      }

      if (effectiveTab === 'analyze') {
        if (semanticGroup && semanticGroupDetailsData?.group_name) {
          items.push({
            text: semanticGroupDetailsData?.group_name,
            link: `/applications/${applicationId}/analyze/${analyzeTab}/${semanticGroup}`
          });
        }
      }
    }

    return items;
  }, [
    applicationId,
    matchOverview,
    matchAnalyze,
    matchAnalyzeSubTab,
    matchAnalyzeSemanticGroup,
    matchCollect,
    matchCollectWithSession,
    matchCollectWithSessionTab,
    matchCollectLiveSession,
    matchMonitor,
    sessionId,
    liveSessionId,
    tab,
    analyzeTab,
    semanticGroup,
    semanticGroupDetailsData?.group_name
  ]);

  if (
    applicationListFetching ||
    semanticGroupDetailsLoading ||
    isLoadingApplicationSummaryMetrics
  ) {
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

  if (
    applicationListError ||
    semanticGroupDetailsError ||
    isLoadingApplicationSummaryMetrics
  ) {
    return <>An error occurred!</>;
  }

  return (
    <Box sx={pageGradientBottomSx}>
      <PageWithTitle
        title={
          <Stack
            direction={'row'}
            alignItems={'flex-start'}
            justifyContent={'space-between'}
            gap={'32px'}
            sx={{ width: '100%' }}
          >
            <Stack direction={'column'} alignItems={'flex-start'} gap={'4px'}>
              <Stack direction={'row'} alignItems={'center'} gap={'4px'}>
                <Typography
                  variant={'h5'}
                  sx={{
                    color: theme.palette.vars.interactivePrimaryDefaultDefault
                  }}
                >
                  {applicationId ?? ''}
                  {sessionId ? ` / ${sessionId}` : ''}
                  {liveSessionId ? ` / ${liveSessionId}` : ''}
                  {semanticGroupDetailsData?.group_name
                    ? ` / ${semanticGroupDetailsData?.group_name}`
                    : ''}
                </Typography>

                {sessionId && <SessionStatus status={sessionStatus} />}
              </Stack>
              {parentSemanticGroupSessionDetails && (
                <Stack direction={'row'} alignItems={'center'} gap={'4px'}>
                  <Typography
                    variant={'captionSemibold'}
                    sx={{
                      color:
                        theme.palette.vars.interactivePrimaryDefaultDefault,
                      fontStyle: 'italic'
                    }}
                  >
                    Part of semantic group:
                  </Typography>
                  <CustomTooltip
                    title={parentSemanticGroupSessionDetails?.group_name}
                    placement="top"
                    sx={{ maxWidth: '400px' }}
                  >
                    <Box>
                      <Tag
                        sx={{
                          backgroundColor: colorTokens.greyBackground,
                          border: `1px solid ${colorTokens.inactiveBorder}`
                        }}
                        size={GeneralSize.Medium}
                        onClick={() =>
                          navigate(
                            `/applications/${applicationId}/analyze/overview/${encodeURIComponent(parentSemanticGroupSessionDetails?.id ?? '')}`
                          )
                        }
                      >
                        {parentSemanticGroupSessionDetails?.group_name}
                      </Tag>
                    </Box>
                  </CustomTooltip>
                </Stack>
              )}

              {applicationDescription && !semanticGroup && (
                <Typography variant={'body2'}>
                  {applicationDescription}
                </Typography>
              )}

              {semanticGroupDetailsData?.group_summary && (
                <Typography variant={'body2'}>
                  {semanticGroupDetailsData?.group_summary}
                </Typography>
              )}
              {/* <Tooltip title={applicationDescription} placement={'top'} sx={{ maxWidth: '400px' }}>
              <InfoOutlineIcon
                sx={{ width: '16px', height: '16px', cursor: 'pointer', color: theme.palette.vars.interactivePrimaryDefaultDefault }}
                fill={theme.palette.vars.interactivePrimaryDefaultDefault}
              />
            </Tooltip> */}
            </Stack>

            <HealthScore score={healthScore} onLearnMore={handleLearnMore} />
            {/* 
          <Stack direction={'row'} justifyContent={'flex-end'} gap={'24px'} sx={{ minWidth: '360px' }}>
            <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
              <Typography variant={'body2Semibold'} sx={{ fontWeight: 600 }}>
                Status
              </Typography>
              <DotLabel dotColor={theme.palette.vars.brandIconTertiaryMedium} label={'In dev'} />
            </Stack>

            <Stack direction={'row'} gap={'8px'} alignItems={'center'}>
              <Typography variant={'body2Semibold'} sx={{ fontWeight: 600 }}>
                Last update
              </Typography>
              <Typography variant={'body2'}>{format(new Date(Date.now()), 'MMM d, yyyy HH:mm')}</Typography>
            </Stack>
          </Stack> */}
          </Stack>
        }
        breadcrumbItems={breadcrumbItems}
        sx={pageGradientContentSx}
        // breadcrumbItems={[
        //   { text: 'Applications', link: `${PATHS.monitoring}/${PATHS.applications}` },
        //   { text: data?.monitorByApplication?.name ?? '', link: `${PATHS.monitoring}/${PATHS.applications}/${data?.monitorByApplication?.name ?? ''}` }
        // ]}
        // actions={[
        //   <SessionsDropdown
        //     sessionIds={sessionIds?.sessionIds ?? []}
        //     key={'session-ids-dropdown'}
        //     setSelectedSession={(id) => setSelectedSession(id)}
        //     selectedSession={selectedSession}
        //   />
        // ]}
      >
        <Stack
          direction={'column'}
          gap={'24px'}
          sx={{ height: '100%', paddingTop: '0px' }}
        >
          {isSessionDetailView ? (
            sessionsLoading ? (
              <Stack
                alignItems={'center'}
                justifyContent={'center'}
                sx={{ width: '100%', height: '100%', minHeight: '100px' }}
              >
                <Spinner />
              </Stack>
            ) : (
              <SessionDetails
                costDollars={formatTwoDecimals(
                  sessionsData?.sessionList.find(
                    (session) => session.sessionId === sessionId
                  )?.cost
                )}
                totalTokens={getDisplayedResultsCount(
                  sessionsData?.sessionList.find(
                    (session) => session.sessionId === sessionId
                  )?.tokens ?? 0
                )}
                duration={formatDurationMs(
                  sessionsData?.sessionList.find(
                    (session) => session.sessionId === sessionId
                  )?.duration
                )}
              />
            )
          ) : (
            <ApplicationTabs />
          )}
        </Stack>
      </PageWithTitle>
    </Box>
  );
};

export default ApplicationDetails;
