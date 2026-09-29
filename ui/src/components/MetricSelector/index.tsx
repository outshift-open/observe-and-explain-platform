/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo } from 'react';
import { Typography, NestedMenu, Box, useNestedMenu, SelectNodeType } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import Tags from '../Tags';
import { metricCatalog, defaultSelectedMetricKeys } from '@/common';
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from '@/common/styles';

const METRIC_TREE_DATA: SelectNodeType[] = Object.entries(metricCatalog).map(([key, value]) => ({
  value: key,
  valueFormatter: () => value.name,
  isSelectable: true,
  isSelected: defaultSelectedMetricKeys.includes(key as keyof typeof metricCatalog)
}));

export const useMetricSelector = () => {
  const { flattenedTreeOptions, searchTextDebounced, selectAllNode, selectedValues, setSearchText, toggleExpand, updateCheckbox } =
    useNestedMenu({
      treeData: METRIC_TREE_DATA,
      selectAllIcon: null
    });

  const selectedMetricKeys = useMemo(() => {
    if (!selectedValues || !Array.isArray(selectedValues)) {
      return defaultSelectedMetricKeys as string[];
    }
    return selectedValues.map((node) => String(node.value));
  }, [selectedValues]);

  return {
    selectedMetricKeys,
    dropdownProps: {
      flattenedTreeOptions,
      searchTextDebounced,
      selectAllNode,
      setSearchText,
      toggleExpand,
      updateCheckbox
    }
  };
};

type MetricSelectorDropdownProps = ReturnType<typeof useMetricSelector>;

export const MetricSelectorDropdown = ({ selectedMetricKeys, dropdownProps }: MetricSelectorDropdownProps) => {
  const theme = useTheme();
  const { flattenedTreeOptions, searchTextDebounced, selectAllNode, setSearchText, toggleExpand, updateCheckbox } = dropdownProps;

  return (
    <Box sx={{ maxWidth: 600 }}>
      <NestedMenu
        buttonContent={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center', backgroundColor: GLOBAL_BACKGROUND_COLOR }}>
            {selectedMetricKeys.length > 0 ? (
              <Tags
                tags={selectedMetricKeys.map((key) => ({
                  name: metricCatalog[key as keyof typeof metricCatalog]?.name ?? key
                }))}
                minDisplayed={3}
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Select metrics...
              </Typography>
            )}
          </Box>
        }
        buttonSize="medium"
        buttonProps={{
          sx: {
            backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
            border: `1px solid ${GLOBAL_BORDER_COLOR} !important`,
            color: theme.palette.vars?.baseTextWeak,
            '&:hover': {
              border: `2px solid ${GLOBAL_BORDER_COLOR} !important`
            },
            '&:focus, &:focus-visible, &.Mui-focusVisible': {
              border: `2px solid ${GLOBAL_BORDER_COLOR} !important`,
              outline: 'none !important'
            },
            '&:active': {
              border: `2px solid ${GLOBAL_BORDER_COLOR} !important`,
              outline: 'none !important'
            },
            '&.Mui-disabled': {
              border: `2px solid ${GLOBAL_BORDER_COLOR} !important`,
              backgroundColor: `${theme.palette.vars?.controlBackgroundDisabled} !important`
            },
            '&.MuiButton-outlinedSizeMedium': {
              padding: '6px 8px 6px 16px !important'
            },
            '& .MuiSvgIcon-root': {
              color: `${theme.palette.vars?.controlIconDefault} !important`
            },
            height: '36px !important'
          }
        }}
        flattenedTreeOptions={flattenedTreeOptions.flattenedSelectTreeWithSearch}
        isSearchFieldEnabled={true}
        searchText={searchTextDebounced}
        selectAllNode={selectAllNode}
        setSearchText={setSearchText}
        toggleExpand={toggleExpand}
        updateCheckbox={updateCheckbox}
        popOverPaperSx={{
          backgroundColor: GLOBAL_BACKGROUND_COLOR,
          border: `1px solid ${GLOBAL_BORDER_COLOR}`
        }}
      />
    </Box>
  );
};
