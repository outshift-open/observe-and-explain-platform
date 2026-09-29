/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export type Operation = 'sum' | 'average';

export type ApplicationLevelMetricCategory = 'quality' | 'reliability' | 'performance';

export const ApplicationLevelMetricCategoryLabels: Record<ApplicationLevelMetricCategory, string> = {
  quality: 'Overall Quality',
  reliability: 'Overall Reliability',
  performance: 'Overall Performance'
};

export type ApplicationLevelMetricDef = {
  name: string;
  description?: string;
  isCard?: boolean;
  operation?: Operation;
  isRounded?: boolean;
  disabled?: boolean;
};

const overallQualityMetrics: Record<string, ApplicationLevelMetricDef> = {
  intentRecognitionAccuracy: {
    name: 'Intent recognition accuracy',
    description: 'Measure how well the Assistant understands and correctly identifies user intents.',
    operation: 'average'
  },
  answerGroundedness: {
    name: 'Answer groundedness',
    description: 'Measures how much the answer is inferred from the given context.',
    operation: 'average'
  },
  toolUtilizationAccuracy: {
    name: 'Tool utilization accuracy',
    description: 'Assesses how effective the agent selects the appropriate tool and how the tool addresses the user input.',
    operation: 'average'
  },
  answerRelevancy: {
    name: 'Answer relevancy',
    description: 'Measures how closely the answer aligns to the user query.',
    operation: 'average'
  },
  completeness: {
    name: 'Completeness',
    description: 'Judges whether the conversation fully addresses user needs, covering all requested points or sub-queries across turns.',
    operation: 'average'
  }
};

const overallReliabilityMetrics: Record<string, ApplicationLevelMetricDef> = {
  metricConsistency: {
    name: 'Metric consistency',
    description: 'Measures how consistently the system produces stable metric scores across similar inputs.',
    operation: 'average'
  },
  textConsistency: {
    name: 'Text consistency',
    description: 'Measures how consistently the system generates similar text responses for equivalent queries.',
    operation: 'average'
  },
  graphConsistency: {
    name: 'Graph consistency',
    description: 'Measures how consistently the system follows the same workflow graph paths for similar tasks.',
    operation: 'average'
  },
  completionRate: {
    name: 'Completion rate',
    description: 'The rate at which the agent successfully completes requested tasks without failures.',
    operation: 'average'
  }
};

const overallPerformanceMetrics: Record<string, ApplicationLevelMetricDef> = {
  llmErrorRate: {
    name: 'LLM error rate',
    description: 'The rate of errors produced by the LLM during inference.',
    operation: 'average'
  },
  toolErrorRate: {
    name: 'Tool error rate',
    description: 'The rate of errors produced by tools during execution.',
    operation: 'average'
  },
  cyclesCount: {
    name: 'Cycles count',
    description: 'The number of repeated cycles in the agent workflow, indicating potential loops or retries.',
    operation: 'average'
  },
  workflowEfficiency: {
    name: 'Workflow efficiency',
    description: 'A score representing the efficiency of the sequence of steps taken by an agent to complete a task.',
    operation: 'average'
  }
};

export const applicationLevelMetrics: Record<ApplicationLevelMetricCategory, Record<string, ApplicationLevelMetricDef>> = {
  quality: overallQualityMetrics,
  reliability: overallReliabilityMetrics,
  performance: overallPerformanceMetrics
};

export const ApplicationLevelMetricCategoryDescription: Record<ApplicationLevelMetricCategory, string> = {
  quality:
    "Measures the stability of the system's infrastructure: how consistently requests complete without crashes, tool failures, or availability issues.",
  reliability: "Measures the semantic correctness of responses: how accurate, faithful to context, safe, and goal-aligned the system's outputs are.",
  performance: 'Measures execution efficiency: how quickly and with how few steps the system completes a task relative to its expected baseline.'
};
