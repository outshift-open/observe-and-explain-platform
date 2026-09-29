/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, SideDrawer, Spinner, Stack } from '@open-ui-kit/core';
import { DrawerTitle } from './DrawerTitle';
import { DrawerContent } from './DrawerContent';
import { AnalyzeSemanticGroupingData } from '@/types/agentCharts.type';
import { ApplicationLevelMetricCategory, ApplicationLevelMetricCategoryDescription } from '@/api/applicationLevelMetrics';
import { ApplicationSummaryMetrics } from '@/types/oxp.type';

interface ApplicationLevelMetricDrawerWrapper {
  onClose: () => void;
  metricCategory: ApplicationLevelMetricCategory;
  applicationSummaryMetrics: ApplicationSummaryMetrics;
  aggregatedReliabilityValue?: number;
  aggregatedQualityValue?: number;
  aggregatedPerformanceValue?: number;
}

const ApplicationLevelMetricDrawerWrapper = ({
  metricCategory,
  onClose,
  applicationSummaryMetrics,
  aggregatedReliabilityValue = 0,
  aggregatedQualityValue = 0,
  aggregatedPerformanceValue = 0
}: ApplicationLevelMetricDrawerWrapper) => {
  const description = ApplicationLevelMetricCategoryDescription[metricCategory];

  return (
    <SideDrawer
      open={Boolean(metricCategory)}
      onClose={onClose}
      titleNode={<DrawerTitle metricCategory={metricCategory} description={description} />}
      copyURL={''}
      hideTitleAction={true}
      hidePrev={true}
      hideNext={true}
      hideActionButtons={true}
      hideFooter={true}
      customDividerStyle={{ display: 'none' }}
      paperProps={{
        width: '980px',
        '&.MuiPaper-root > .MuiBox-root': {
          width: '980px'
        }
      }}
    >
      <DrawerContent
        metricCategory={metricCategory}
        applicationSummaryMetrics={applicationSummaryMetrics}
        aggregatedReliabilityValue={aggregatedReliabilityValue}
        aggregatedQualityValue={aggregatedQualityValue}
        aggregatedPerformanceValue={aggregatedPerformanceValue}
      />
    </SideDrawer>
  );
};

export default ApplicationLevelMetricDrawerWrapper;
