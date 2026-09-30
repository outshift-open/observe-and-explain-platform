/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Box, Stack, FormControl } from '@mui/material';
import { Select, MenuItem, Button } from '@open-ui-kit/core';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import {
  SessionHierarchyGraph,
  HierarchyLayoutType
} from '@/components/SessionHierarchyGraph';
import { useHierarchy } from '@/api/kgInspectorApi';
import { useParams } from 'react-router';

export const ExecutionTreeTab = () => {
  const { sessionId } = useParams();
  const [selectedLayout, setSelectedLayout] =
    useState<HierarchyLayoutType>('tree');
  const { data } = useHierarchy(sessionId ?? '');

  const handleCopyJson = () => {
    if (data) {
      navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    }
  };

  if (!sessionId) {
    return null;
  }

  return (
    <Box sx={{ flex: 1, minHeight: 0, pt: 2 }}>
      <Stack direction="row" gap={2} alignItems="flex-start" sx={{ mb: 2 }}>
        <FormControl sx={{ minWidth: 150 }} size="small">
          <Select
            labelId="hierarchy-layout-select-label"
            id="hierarchy-layout-select"
            value={selectedLayout}
            label="Layout"
            onChange={(e) =>
              setSelectedLayout(e.target.value as HierarchyLayoutType)
            }
            size="small"
            variant="standard"
            sx={{ marginTop: 0 }}
            renderValue={(value) => {
              const labels: Record<HierarchyLayoutType, string> = {
                'dagre-tb': 'Top-Bottom',
                'dagre-lr': 'Left-Right',
                tree: 'Tree'
              };
              return `Layout: ${labels[value as HierarchyLayoutType] || value}`;
            }}
          >
            <MenuItem value="dagre-tb">Top-Bottom</MenuItem>
            <MenuItem value="dagre-lr">Left-Right</MenuItem>
            <MenuItem value="tree">Tree</MenuItem>
          </Select>
        </FormControl>

        <Button
          variant="gradient"
          onClick={handleCopyJson}
          disabled={!data}
          startIcon={<ContentCopyIcon />}
        >
          Copy payload
        </Button>
      </Stack>
      <SessionHierarchyGraph
        sessionId={sessionId}
        layout={selectedLayout}
        height="calc(100% - 50px)"
      />
    </Box>
  );
};
