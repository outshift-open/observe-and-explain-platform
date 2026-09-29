/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Typography, Stack, Box, SxProps } from '@mui/material';
import { Breadcrumbs, BreadcrumbsProps } from '@open-ui-kit/core';
import React from 'react';
import { useLocation } from 'react-router-dom';

interface PageWithTitleProps {
  children: React.ReactNode;
  actions?: React.ReactNode[];
  breadcrumbItems?: BreadcrumbsProps['items'];
  title: React.ReactNode;
  subTitle?: string;
  moduloMaxWidth?: number;
  sx?: SxProps;
}

const PageWithTitle = ({
  breadcrumbItems,
  children,
  title,
  subTitle,
  actions,
  sx = {}
}: PageWithTitleProps) => {
  const location = useLocation();

  const autoBreadcrumbItems: BreadcrumbsProps['items'] = React.useMemo(() => {
    const pathSegments = location.pathname.split('/').filter(Boolean);
    if (pathSegments.length === 0) return [];

    const prettyNameMap: Record<string, string> = {
      dashboard: 'Dashboard',
      applications: 'Applications',
      optimisation: 'Optimisation',
      monitoring: 'Monitoring',
      agents: 'Agents',
      sessions: 'Sessions',
      evaluation: 'Evaluation',
      settings: 'Settings'
    };

    const toTitleCase = (text: string) =>
      text
        .replace(/[-_]+/g, ' ')
        .split(' ')
        .map((s) => (s ? s[0].toUpperCase() + s.slice(1) : s))
        .join(' ');

    const isUuid = (text: string) =>
      /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
        text
      );

    return pathSegments.map((segment, index) => {
      const link = '/' + pathSegments.slice(0, index + 1).join('/');
      const decoded = decodeURIComponent(segment);
      const text =
        prettyNameMap[decoded] ??
        (isUuid(decoded) ? decoded : toTitleCase(decoded));
      return { text, link } as NonNullable<BreadcrumbsProps['items']>[number];
    });
  }, [location.pathname]);

  const breadcrumbsToRender =
    breadcrumbItems && breadcrumbItems.length > 0
      ? breadcrumbItems
      : autoBreadcrumbItems;

  return (
    <Stack
      direction="column"
      gap="24px"
      sx={{
        height: '100%',
        width: '100%',
        padding: '16px 32px',
        overflow: 'auto',
        ...sx
      }}
    >
      <Stack direction="row" justifyContent="space-between">
        <Stack direction="column" sx={{ width: '100%' }}>
          {breadcrumbsToRender.length > 1 && (
            <Breadcrumbs
              items={breadcrumbsToRender}
              maximumNumberOfVisibleBreadcrumbs={breadcrumbsToRender.length}
            />
          )}
          {title}
          {subTitle && <Typography variant="subtitle2">{subTitle}</Typography>}
        </Stack>
        {actions}
      </Stack>

      <Box
        sx={{
          flex: 1,
          width: '100%',
          position: 'relative'
        }}
      >
        {children}
      </Box>
    </Stack>
  );
};

export default PageWithTitle;
