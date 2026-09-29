/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState, useEffect, useCallback } from 'react';
import {
  Typography,
  NestedMenu,
  Box,
  useNestedMenu,
  SelectNodeType
} from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import Tags from '../Tags';
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from '@/common/styles';

export interface SemanticGroupOption {
  groupId: string;
  label: string;
}

// ---------------------------------------------------------------------------
// Shared button styles
// ---------------------------------------------------------------------------
const useButtonSx = () => {
  const theme = useTheme();
  return {
    theme,
    buttonSx: {
      backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
      border: `1px solid ${GLOBAL_BORDER_COLOR} !important`,
      color: theme.palette.vars?.baseTextWeak,
      '&:focus, &:focus-visible, &.Mui-focusVisible': {
        outline: 'none !important'
      },
      '&:active': {
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
    },
    popOverSx: {
      backgroundColor: GLOBAL_BACKGROUND_COLOR,
      border: `1px solid ${GLOBAL_BORDER_COLOR}`
    }
  };
};

// ---------------------------------------------------------------------------
// Multi-select variant
// ---------------------------------------------------------------------------

interface MultiSelectInnerProps {
  groups: SemanticGroupOption[];
  onSelectionChange: (ids: Set<string>) => void;
}

const MultiSelectInner = ({
  groups,
  onSelectionChange
}: MultiSelectInnerProps) => {
  const { buttonSx, popOverSx } = useButtonSx();

  const treeData: SelectNodeType[] = useMemo(
    () =>
      groups.map((g) => ({
        value: g.groupId,
        valueFormatter: () => g.label,
        isSelectable: true,
        isSelected: true
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const {
    flattenedTreeOptions,
    searchTextDebounced,
    selectAllNode,
    selectedValues,
    setSearchText,
    toggleExpand,
    updateCheckbox
  } = useNestedMenu({ treeData, selectAllIcon: null });

  useEffect(() => {
    if (selectedValues && Array.isArray(selectedValues)) {
      onSelectionChange(
        new Set(selectedValues.map((node) => String(node.value)))
      );
    }
  }, [selectedValues, onSelectionChange]);

  const selectedLabels = useMemo(() => {
    if (!selectedValues || !Array.isArray(selectedValues)) return [];
    const selectedIds = new Set(selectedValues.map((n) => String(n.value)));
    return groups
      .filter((g) => selectedIds.has(g.groupId))
      .map((g) => ({ name: g.label }));
  }, [selectedValues, groups]);

  return (
    <Box sx={{ maxWidth: 600 }}>
      <NestedMenu
        buttonContent={
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 0.5,
              alignItems: 'center',
              backgroundColor: GLOBAL_BACKGROUND_COLOR
            }}
          >
            {selectedLabels.length > 0 ? (
              <Tags tags={selectedLabels} minDisplayed={3} />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Select groups...
              </Typography>
            )}
          </Box>
        }
        buttonSize="medium"
        buttonProps={{ sx: buttonSx }}
        flattenedTreeOptions={
          flattenedTreeOptions.flattenedSelectTreeWithSearch
        }
        isSearchFieldEnabled={true}
        searchText={searchTextDebounced}
        selectAllNode={selectAllNode}
        setSearchText={setSearchText}
        toggleExpand={toggleExpand}
        updateCheckbox={updateCheckbox}
        popOverPaperSx={popOverSx}
      />
    </Box>
  );
};

export const useMultiSemanticGroupSelector = (
  groups: SemanticGroupOption[]
) => {
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<string>>(
    new Set()
  );

  useEffect(() => {
    if (groups.length > 0) {
      setSelectedGroupIds(new Set(groups.map((g) => g.groupId)));
    }
  }, [groups]);

  return { selectedGroupIds, setSelectedGroupIds, groups };
};

type MultiSelectorDropdownProps = ReturnType<
  typeof useMultiSemanticGroupSelector
>;

export const MultiSemanticGroupSelectorDropdown = ({
  setSelectedGroupIds,
  groups
}: MultiSelectorDropdownProps) => {
  if (groups.length === 0) return null;
  return (
    <MultiSelectInner groups={groups} onSelectionChange={setSelectedGroupIds} />
  );
};

// ---------------------------------------------------------------------------
// Single-select variant
// ---------------------------------------------------------------------------

interface SingleSelectInnerProps {
  groups: SemanticGroupOption[];
  onSelectionChange: (id: string | null) => void;
}

const SingleSelectInner = ({
  groups,
  onSelectionChange
}: SingleSelectInnerProps) => {
  const { buttonSx, popOverSx } = useButtonSx();

  const treeData: SelectNodeType[] = useMemo(
    () =>
      groups.map((g, i) => ({
        value: g.groupId,
        valueFormatter: () => g.label,
        isSelectable: true,
        isSelected: i === 0
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const {
    flattenedTreeOptions,
    searchTextDebounced,
    selectAllNode,
    selectedValues,
    setSearchText,
    toggleExpand,
    updateCheckbox
  } = useNestedMenu({ treeData, selectAllIcon: null });

  const singleSelectCheckbox = useCallback(
    (node: Parameters<typeof updateCheckbox>[0], isSelected: boolean) => {
      if (!isSelected) return;
      updateCheckbox(treeData, false);
      updateCheckbox(node, true);
    },
    [updateCheckbox, treeData]
  );

  useEffect(() => {
    if (
      selectedValues &&
      Array.isArray(selectedValues) &&
      selectedValues.length > 0
    ) {
      onSelectionChange(
        String(selectedValues[selectedValues.length - 1].value)
      );
    } else {
      onSelectionChange(null);
    }
  }, [selectedValues, onSelectionChange]);

  const selectedLabel = useMemo(() => {
    if (
      !selectedValues ||
      !Array.isArray(selectedValues) ||
      selectedValues.length === 0
    )
      return null;
    const lastId = String(selectedValues[selectedValues.length - 1].value);
    return groups.find((g) => g.groupId === lastId)?.label ?? null;
  }, [selectedValues, groups]);

  return (
    <Box sx={{ maxWidth: 600 }}>
      <NestedMenu
        buttonContent={
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 0.5,
              alignItems: 'center',
              backgroundColor: GLOBAL_BACKGROUND_COLOR
            }}
          >
            {selectedLabel ? (
              <Tags tags={[{ name: selectedLabel }]} minDisplayed={1} />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Select a group...
              </Typography>
            )}
          </Box>
        }
        buttonSize="medium"
        buttonProps={{ sx: buttonSx }}
        flattenedTreeOptions={
          flattenedTreeOptions.flattenedSelectTreeWithSearch
        }
        isSearchFieldEnabled={true}
        searchText={searchTextDebounced}
        selectAllNode={selectAllNode}
        setSearchText={setSearchText}
        toggleExpand={toggleExpand}
        updateCheckbox={singleSelectCheckbox}
        popOverPaperSx={popOverSx}
      />
    </Box>
  );
};

export const useSingleSemanticGroupSelector = (
  groups: SemanticGroupOption[]
) => {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  useEffect(() => {
    if (groups.length > 0 && selectedGroupId === null) {
      setSelectedGroupId(groups[0].groupId);
    }
  }, [groups, selectedGroupId]);

  return { selectedGroupId, setSelectedGroupId, groups };
};

type SingleSelectorDropdownProps = ReturnType<
  typeof useSingleSemanticGroupSelector
>;

export const SingleSemanticGroupSelectorDropdown = ({
  setSelectedGroupId,
  groups
}: SingleSelectorDropdownProps) => {
  if (groups.length === 0) return null;
  return (
    <SingleSelectInner groups={groups} onSelectionChange={setSelectedGroupId} />
  );
};

// Keep backwards-compat aliases
export const useSemanticGroupSelector = useMultiSemanticGroupSelector;
export const SemanticGroupSelectorDropdown = MultiSemanticGroupSelectorDropdown;
