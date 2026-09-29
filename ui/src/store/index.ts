/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { create } from 'zustand';
import { DEFAULT_END_DATE, DEFAULT_START_DATE } from '@/common/constants';

export type ThemeMode = 'light' | 'dark';

interface ThemeStore {
  themeMode: ThemeMode;
  setThemeMode: (themeMode: ThemeMode) => void;
}

interface TimeRangeStore {
  startDate: number;
  endDate: number;
  setStartDate: (startDate: number) => void;
  setEndDate: (endDate: number) => void;
}

export const useTimeRangeStore = create<TimeRangeStore>((set) => ({
  startDate: DEFAULT_START_DATE,
  endDate: DEFAULT_END_DATE,
  setStartDate: (startDate: number) => set({ startDate }),
  setEndDate: (endDate: number) => set({ endDate })
}));

export const useThemeStore = create<ThemeStore>((set) => ({
  themeMode: 'dark',
  setThemeMode: (themeMode: ThemeMode) => set({ themeMode })
}));

