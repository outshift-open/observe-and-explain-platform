/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { SemanticGroupingTable } from './SemanticGroupingTable.tsx';
import { Box, Spinner, Stack } from '@open-ui-kit/core';
import { useNavigate, useParams } from 'react-router-dom';
import { useSemanticGroups } from '@/api/oxpApi.ts';
import { SemanticGroup } from '@/types/oxp.type.ts';

const SemanticGrouping = () => {
  const navigate = useNavigate();
  const { applicationId } = useParams();

  const {
    data: semanticGroups,
    isLoading: semanticGroupsLoading,
    isError: semanticGroupsError
  } = useSemanticGroups(applicationId ?? '');

  const handleRowClick = (row: SemanticGroup) => {
    navigate(
      `/applications/${applicationId}/analyze/overview/${encodeURIComponent(row.id)}`
    );
  };

  if (semanticGroupsLoading) {
    return (
      <Stack
        justifyContent={'center'}
        alignItems={'center'}
        sx={{ width: '100%', height: '100%' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (semanticGroupsError) {
    return <>An error occurred!</>;
  }

  return (
    <Box>
      <SemanticGroupingTable
        data={semanticGroups ?? []}
        onRowClick={handleRowClick}
      />
    </Box>
  );
};

export default SemanticGrouping;
