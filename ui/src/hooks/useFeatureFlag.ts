/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { FeatureFlagKey, isFeatureEnabled } from '@/config/featureFlags';

/**
 * Read a single feature flag.
 *
 * Flags are resolved from a static, per-deployment source (window.featureFlags
 * / VITE_FEATURE_FLAGS / defaults), so a plain module-level read is sufficient
 * — no React context/provider is needed. This mirrors how other injected
 * runtime config (e.g. window.restApiUrl) is consumed elsewhere in the app.
 */
export const useFeatureFlag = (key: FeatureFlagKey): boolean =>
  isFeatureEnabled(key);
