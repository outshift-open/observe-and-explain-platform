/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { memo, useEffect, useState } from 'react';
import { Stack } from '@open-ui-kit/core';
import { Box, Typography, useTheme } from '@mui/material';

import SemanticGrouping from './SemanticGrouping';
import { useParams } from 'react-router-dom';
import { TopicHierarchy } from './TopicHierarchy';
import { SemanticGroupDetails } from '@/components/SemanticGroupDetails/SemanticGroupDetails';
import { ResourcesUsage } from './ResourcesUsage';
import {
  ApplicationReasoningPathGraph,
  SemanticGroupsInsightsTable
} from '@/components';
import { FeatureFlagKey, getFeatureFlags } from '@/config/featureFlags';

const ANALYZE_TABS = [
  'What agents are working on',
  'How they are failing',
  'What resources they are using',
  'How they are reasoning'
] as const;

type AnalyzeTabName = (typeof ANALYZE_TABS)[number];

// Each Explain (Analyze) sub-view is gated by its own feature flag.
const ANALYZE_TAB_FLAGS: Record<AnalyzeTabName, FeatureFlagKey> = {
  'What agents are working on': 'semantic_groups',
  'How they are failing': 'insights',
  'What resources they are using': 'waste_estimation',
  'How they are reasoning': 'neurosymbolic_eval'
};

const AnalyzeTab = () => {
  const { applicationId, semanticGroup } = useParams();
  const flags = getFeatureFlags();
  const [activeTab, setActiveTab] = useState<AnalyzeTabName>(ANALYZE_TABS[0]);
  const theme = useTheme();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  // Only show sub-views whose flag is enabled. Filtering here also means the
  // disabled sub-view components are never mounted, so their data hooks (e.g.
  // waste estimation / neurosymbolic) never fire requests against optional
  // workers that may not exist in an OSS deployment.
  const visibleTabs = ANALYZE_TABS.filter(
    (tab) => flags[ANALYZE_TAB_FLAGS[tab]]
  );

  // Clamp the selection: if the currently selected tab is disabled (or the
  // stored selection is otherwise invalid), fall back to the first visible one.
  const effectiveActiveTab = visibleTabs.includes(activeTab)
    ? activeTab
    : visibleTabs[0];

  // The semantic-group drill-down is reached via URL and bypasses the tab
  // switch, so guard it explicitly behind semantic_groups. When disabled, fall
  // through to the (filtered) tab view rather than rendering the detail page.
  if (semanticGroup && flags.semantic_groups) {
    return (
      <Stack
        direction={'column'}
        sx={{ width: '100%', height: '100%' }}
        gap={'24px'}
      >
        <SemanticGroupDetails
          semanticGroupId={semanticGroup ?? ''}
          applicationId={applicationId ?? ''}
        />
      </Stack>
    );
  }

  return (
    <Stack
      direction={'column'}
      sx={{ width: '100%', height: '100%' }}
      gap={'24px'}
    >
      <Stack
        direction={'row'}
        gap={'24px'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Stack
          direction={'column'}
          gap={'4px'}
          sx={{ flexShrink: 0, minWidth: '260px', paddingTop: '4px' }}
        >
          {visibleTabs.map((tab) => {
            const isActive = tab === effectiveActiveTab;
            return (
              <Box
                key={tab}
                onClick={() => setActiveTab(tab)}
                sx={{
                  padding: '10px 16px',
                  cursor: 'pointer',
                  borderRight: isActive
                    ? `2px solid ${theme.palette.vars.interactivePrimaryDefaultDefault}`
                    : '2px solid transparent',
                  '&:hover': {
                    backgroundColor: theme.palette.action.hover
                  }
                }}
              >
                <Typography
                  variant={'body2'}
                  sx={{
                    color: isActive
                      ? theme.palette.vars.interactivePrimaryDefaultDefault
                      : theme.palette.vars.baseTextWeak
                  }}
                >
                  {tab}
                </Typography>
              </Box>
            );
          })}
        </Stack>

        <Box sx={{ flex: 1, minWidth: 0, height: '100%' }}>
          {effectiveActiveTab && <AnalyzeTabContent tab={effectiveActiveTab} />}
        </Box>
      </Stack>
    </Stack>
  );
};

const AnalyzeTabContent = memo(({ tab }: { tab: AnalyzeTabName }) => {
  const { applicationId } = useParams();

  switch (tab) {
    case 'What agents are working on':
      return (
        <Stack direction={'column'} gap={'24px'}>
          <SemanticGrouping />
          <TopicHierarchy />
        </Stack>
      );
    case 'How they are failing':
      return <SemanticGroupsInsightsTable />;
    case 'What resources they are using':
      return <ResourcesUsage />;
    case 'How they are reasoning':
      return <ApplicationReasoningPathGraph masName={applicationId ?? ''} />;
  }
});

export default AnalyzeTab;
