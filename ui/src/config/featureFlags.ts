/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * OXP UI feature flags.
 *
 * Seven flags gate optional pages/sub-views on top of the always-on core
 * features (Applications, Sessions, Metrics, Execution Graph, Latent Space).
 * Defaults below match the OSS defaults from the spec:
 *   - Enabled in OSS:  semantic_groups, insights
 *   - Disabled in OSS: everything else (they require optional workers/services)
 *
 * Each flag has its own source (mirroring the existing window.restApiUrl
 * pattern), resolved with precedence (low -> high):
 *   DEFAULT_FLAGS  <  VITE_FF_* (build/dev)  <  window.ff* (per-deployment)
 *
 */

export const FEATURE_FLAG_KEYS = [
  'semantic_groups',
  'insights',
  'live_topology',
  'stateful_eval',
  'impact_assessment',
  'waste_estimation',
  'neurosymbolic_eval'
] as const;

export type FeatureFlagKey = (typeof FEATURE_FLAG_KEYS)[number];

export type FeatureFlags = Record<FeatureFlagKey, boolean>;

export const DEFAULT_FLAGS: FeatureFlags = {
  semantic_groups: true,
  insights: true,
  live_topology: true,
  stateful_eval: true,
  impact_assessment: false,
  waste_estimation: false,
  neurosymbolic_eval: false
};

/**
 * Coerce an untrusted flag value (string from env/window, or a real boolean)
 * to a boolean. Returns `undefined` when unset/blank/unrecognized so callers
 * can fall back to a lower-precedence source.
 */
const toBool = (value: unknown): boolean | undefined => {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true' || normalized === '1') {
      return true;
    }
    if (normalized === 'false' || normalized === '0') {
      return false;
    }
  }
  return undefined;
};

/** window (per-deployment) overrides env (build) overrides the OSS default. */
const resolve = (
  fromWindow: unknown,
  fromEnv: unknown,
  fallback: boolean
): boolean => toBool(fromWindow) ?? toBool(fromEnv) ?? fallback;

/**
 * Per-flag sources: the build/dev env var value and the window property name.
 *
 * NOTE: each `import.meta.env.VITE_FF_*` is written with a literal key on
 * purpose — Vite statically replaces those at build time, whereas dynamic
 * `import.meta.env[key]` access would not be replaced in production builds.
 * These env values are build-time constants, so reading them once here is fine.
 */
const FLAG_SOURCES: Record<
  FeatureFlagKey,
  { env: string | undefined; windowProp: keyof Window }
> = {
  semantic_groups: {
    env: import.meta.env.VITE_FF_SEMANTIC_GROUPS,
    windowProp: 'ffSemanticGroups'
  },
  insights: {
    env: import.meta.env.VITE_FF_INSIGHTS,
    windowProp: 'ffInsights'
  },
  live_topology: {
    env: import.meta.env.VITE_FF_LIVE_TOPOLOGY,
    windowProp: 'ffLiveTopology'
  },
  stateful_eval: {
    env: import.meta.env.VITE_FF_STATEFUL_EVAL,
    windowProp: 'ffStatefulEval'
  },
  impact_assessment: {
    env: import.meta.env.VITE_FF_IMPACT_ASSESSMENT,
    windowProp: 'ffImpactAssessment'
  },
  waste_estimation: {
    env: import.meta.env.VITE_FF_WASTE_ESTIMATION,
    windowProp: 'ffWasteEstimation'
  },
  neurosymbolic_eval: {
    env: import.meta.env.VITE_FF_NEUROSYMBOLIC_EVAL,
    windowProp: 'ffNeurosymbolicEval'
  }
};

/**
 * Resolve the effective set of feature flags. `window` is read at call time so
 * runtime injection is picked up.
 */
export const getFeatureFlags = (): FeatureFlags => {
  const w = typeof window !== 'undefined' ? window : undefined;
  return FEATURE_FLAG_KEYS.reduce((flags, key) => {
    const { env, windowProp } = FLAG_SOURCES[key];
    flags[key] = resolve(w?.[windowProp], env, DEFAULT_FLAGS[key]);
    return flags;
  }, {} as FeatureFlags);
};

export const isFeatureEnabled = (key: FeatureFlagKey): boolean =>
  getFeatureFlags()[key];
