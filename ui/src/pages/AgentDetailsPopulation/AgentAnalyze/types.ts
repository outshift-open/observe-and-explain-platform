/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export interface AgentAnalyzeImpactAssessment {
  sessionId: string;
  cost: number;
  toolUtilizationAccuracy: number;
  responseCompleteness: number;
  intentRecognitionAccuracy: number;
  answerRelevancy: number;
  groundedness: number;
  outlierMetrics: string[];
}
