/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { memo, useEffect, useState, type ElementType } from 'react';
import { Stack } from '@open-ui-kit/core';
import { Box, Typography, useTheme } from '@mui/material';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import PowerOutlinedIcon from '@mui/icons-material/PowerOutlined';
import ReportProblemOutlinedIcon from '@mui/icons-material/ReportProblemOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import CompareArrowsOutlinedIcon from '@mui/icons-material/CompareArrowsOutlined';

import SemanticGrouping from './SemanticGrouping';
import { useParams } from 'react-router-dom';
import { TopicHierarchy } from './TopicHierarchy';
import { SemanticGroupDetails } from '@/components/SemanticGroupDetails/SemanticGroupDetails';
import { ResourcesUsage } from './ResourcesUsage';
import {
  ApplicationReasoningPathGraph,
  SemanticGroupsInsightsTable
} from '@/components';
import CognitiveObservability from '@/components/CognitiveObservability';
import L9ProtocolsComparison from '@/components/L9ProtocolsComparison';
import { FeatureFlagKey, getFeatureFlags } from '@/config/featureFlags';

const ANALYZE_TABS = [
  'What agents are working on',
  'How they are failing',
  'What resources they are using',
  'How they are reasoning',
  'Cognitive observability',
  'L9 protocols'
] as const;

type AnalyzeTabName = (typeof ANALYZE_TABS)[number];

// Each Explain (Analyze) sub-view is gated by its own feature flag.
// Tabs without an entry are always visible.
const ANALYZE_TAB_FLAGS: Partial<Record<AnalyzeTabName, FeatureFlagKey>> = {
  'What agents are working on': 'semantic_groups',
  'How they are failing': 'insights',
  'What resources they are using': 'waste_estimation',
  'How they are reasoning': 'neurosymbolic_eval',
  'Cognitive observability': 'cognitive_observability',
  'L9 protocols': 'l9_protocols'
};

const ANALYZE_TAB_META: Record<
  AnalyzeTabName,
  { label: string; icon: ElementType }
> = {
  'What agents are working on': {
    label: 'Active work',
    icon: TrackChangesIcon
  },
  'How they are reasoning': {
    label: 'Reasoning',
    icon: PsychologyOutlinedIcon
  },
  'What resources they are using': {
    label: 'Resource use',
    icon: PowerOutlinedIcon
  },
  'How they are failing': {
    label: 'Failure modes',
    icon: ReportProblemOutlinedIcon
  },
  'Cognitive observability': {
    label: 'Cognitive observability',
    icon: VisibilityOutlinedIcon
  },
  'L9 protocols': {
    label: 'L9 protocols',
    icon: CompareArrowsOutlinedIcon
  }
};

// Sidebar sections, in display order. Sections with no visible tabs are hidden.
const ANALYZE_TAB_SECTIONS: { title: string; tabs: AnalyzeTabName[] }[] = [
  {
    title: 'Agent behavior',
    tabs: [
      'What agents are working on',
      'How they are reasoning',
      'What resources they are using'
    ]
  },
  {
    title: 'Performance',
    tabs: ['How they are failing', 'Cognitive observability', 'L9 protocols']
  }
];

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
  const visibleTabs = ANALYZE_TABS.filter((tab) => {
    const flag = ANALYZE_TAB_FLAGS[tab];
    return flag ? flags[flag] : true;
  });

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
          gap={'24px'}
          sx={{ flexShrink: 0, minWidth: '260px', paddingTop: '4px' }}
        >
          {ANALYZE_TAB_SECTIONS.map((section) => {
            const sectionTabs = section.tabs.filter((tab) =>
              visibleTabs.includes(tab)
            );
            if (sectionTabs.length === 0) return null;

            return (
              <Stack key={section.title} direction={'column'} gap={'4px'}>
                <Typography
                  variant={'caption'}
                  sx={{
                    padding: '0 16px 8px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: theme.palette.vars.baseTextWeak
                  }}
                >
                  {section.title}
                </Typography>
                {sectionTabs.map((tab) => {
                  const isActive = tab === effectiveActiveTab;
                  const { label, icon: Icon } = ANALYZE_TAB_META[tab];
                  const activeColor =
                    theme.palette.vars.interactivePrimaryDefaultDefault;
                  return (
                    <Stack
                      key={tab}
                      direction={'row'}
                      alignItems={'center'}
                      gap={'12px'}
                      onClick={() => setActiveTab(tab)}
                      sx={{
                        padding: '10px 16px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        color: isActive
                          ? activeColor
                          : theme.palette.vars.baseTextDefault,
                        backgroundColor: isActive
                          ? `color-mix(in srgb, ${activeColor} 16%, transparent)`
                          : 'transparent',
                        '&:hover': {
                          backgroundColor: isActive
                            ? undefined
                            : theme.palette.action.hover
                        }
                      }}
                    >
                      <Icon sx={{ fontSize: 20, color: 'inherit' }} />
                      <Typography
                        variant={'subtitle2'}
                        sx={{ color: 'inherit', fontWeight: 500 }}
                      >
                        {label}
                      </Typography>
                    </Stack>
                  );
                })}
              </Stack>
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
    case 'Cognitive observability':
      return <CognitiveObservability />;
    case 'L9 protocols':
      return <L9ProtocolsComparison />;
  }
});

export default AnalyzeTab;
