/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  TimelineData,
  SingleValueData,
  ErrorItem
} from './oxp.type';

export interface ApplicationGeneralCharts {
  averageAnswerRelevancy: TimelineData[];
  overallTaskCompletion: TimelineData[];
  successRate: TimelineData[];
  totalAgentCost: TimelineData[];
  totalLLMInvocationDuration: TimelineData[];
}

export interface ApplicationPerformanceCharts {
  agentErrorCount: SingleValueData;
  agentLatencyPercentile90: SingleValueData;
  agentLatencyPercentile95: SingleValueData;
  agentRetrievalLatency: SingleValueData;
  agentThroughput: TimelineData[];
  agentWorkflowEfficiency: TimelineData[];
  averageLLMInvocationDuration: TimelineData[];
  averageLatency: TimelineData[];
  errorRateOverTime: TimelineData[];
  errorsBreakdown: ErrorItem[];
}

export interface ApplicationCostCharts {
  averageLLMCost: TimelineData[];
  averageToolCost: TimelineData[];
  numberOfLLMCalls: TimelineData[];
  numberOfToolCalls: TimelineData[];
  totalLLMCost: TimelineData[];
  totalToolCost: TimelineData[];
}

export interface ApplicationLlmCharts {
  answerCorrectness: TimelineData[];
  answerFaithfulness: TimelineData[];
  answerRelevancy: TimelineData[];
  bias: TimelineData[];
  coherence: TimelineData[];
  generalStructureStyleMetric: TimelineData[];
  inferenceDuration: TimelineData[];
  inputTokens: TimelineData[];
  llmErrorRate: TimelineData[];
  llmRecoveryRate: TimelineData[];
  llmRetryRate: TimelineData[];
  llmSuccessRate: TimelineData[];
  outputTokens: TimelineData[];
  piiDetection: TimelineData[];
  policyViolation: TimelineData[];
  tonality: TimelineData[];
  totalLLMCost: TimelineData[];
  totalTokens: TimelineData[];
  toxicity: TimelineData[];
  uncertaintyScore: TimelineData[];
}

export interface ApplicationQualityAndReasoningCharts {
  agentTonality: TimelineData[];
  answerCoherence: TimelineData[];
  answerCorrectness: TimelineData[];
  answerGroundedness: TimelineData[];
  answerRelevancy: TimelineData[];
  generalStructureAndStyle: TimelineData[];
  overallTaskCompletion: SingleValueData;
  toolUtilizationAccuracy: TimelineData[];
}

export interface ApplicationReliabilityAndSafetyCharts {
  agentAvailability: SingleValueData;
  agentFailureCount: SingleValueData;
  agentRecoveryCount: SingleValueData;
  agentRecoveryRate: SingleValueData;
  bias: TimelineData[];
  errorRate: SingleValueData;
  policyViolation: TimelineData[];
  recoveryRate: SingleValueData;
  retryRate: SingleValueData;
  successRate: SingleValueData;
  toxicity: TimelineData[];
}

export interface ApplicationConversationCharts {
  completeness: TimelineData[];
  contextPreservation: TimelineData[];
  goalSuccessRate: TimelineData[];
  intentRecognitionAccuracy: TimelineData[];
  relevancy: TimelineData[];
  roleAdherence: TimelineData[];
  topicAdherence: TimelineData[];
  workflowCohesionIndex: TimelineData[];
}

export interface AnalyzeSemanticGroupingData {
  anomalies: number;
  consistencyScore: SingleValueData;
  count: number;
  groupName: string;
  groupSummary: string;
  lastOccurrence: string;
  queryGroup: string;
  successRate: SingleValueData;
}
