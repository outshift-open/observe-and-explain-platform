/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export interface OutlierMetricWithRootContributorAgent {
  metricKey: string;
  metricValue: string;
  expectedValue: string;
  rootContributorAgent: string;
}
