/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

interface Window {
  restApiUrl: string;
  // Per-deployment feature flags, injected onto window at container start as
  // "true"/"false" scalars (mirroring window.restApiUrl). Normalized in
  // src/config/featureFlags.ts.
  ffSemanticGroups?: string;
  ffInsights?: string;
  ffLiveTopology?: string;
  ffStatefulEval?: string;
  ffImpactAssessment?: string;
  ffWasteEstimation?: string;
  ffNeurosymbolicEval?: string;
  ffCognitiveObservability?: string;
  ffL9Protocols?: string;
}

interface ImportMetaEnv {
  VITE_REST_API_URL: string;
  // Optional per-flag build/dev overrides ("true"/"false"). Unset => OSS
  // default. See src/config/featureFlags.ts.
  VITE_FF_SEMANTIC_GROUPS?: string;
  VITE_FF_INSIGHTS?: string;
  VITE_FF_LIVE_TOPOLOGY?: string;
  VITE_FF_STATEFUL_EVAL?: string;
  VITE_FF_IMPACT_ASSESSMENT?: string;
  VITE_FF_WASTE_ESTIMATION?: string;
  VITE_FF_NEUROSYMBOLIC_EVAL?: string;
  VITE_FF_COGNITIVE_OBSERVABILITY?: string;
  VITE_FF_L9_PROTOCOLS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
