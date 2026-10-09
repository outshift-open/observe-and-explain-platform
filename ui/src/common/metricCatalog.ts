/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Unit } from '@/types/oxp.type';

export interface SemanticGroupMetric {
  name: string;
  description: string;
  unit: Unit;
}

export const metricCatalog = {
  Duration: {
    name: 'Session Duration',
    description: 'The duration of the session.',
    unit: Unit.Milliseconds
  },
  Cost: {
    name: 'Session Cost',
    description: 'The cost of the session.',
    unit: Unit.Dollar
  },
  Groundedness: {
    name: 'Groundedness',
    description: 'The groundedness of the session.',
    unit: Unit.Percentage
  },
  ToolUtilizationAccuracy: {
    name: 'Tool Utilization Accuracy',
    description: 'The accuracy of the tool utilization.',
    unit: Unit.Percentage
  },
  AnswerRelevancy: {
    name: 'Answer Relevancy',
    description: 'The relevancy of the answer.',
    unit: Unit.Percentage
  },
  trajectory_score: {
    name: 'Trajectory Score',
    description: 'The trajectory score of the session.',
    unit: Unit.Scalar
  },
  CyclesCount: {
    name: 'Cycles Count',
    description: 'The number of cycles in the session.',
    unit: Unit.Scalar
  },
  ResponseCompleteness: {
    name: 'Response Completeness',
    description: 'The completeness of the response.',
    unit: Unit.Percentage
  },
  WorkflowCohesionIndex: {
    name: 'Workflow Cohesion Index',
    description: 'The cohesion index of the workflow.',
    unit: Unit.Percentage
  },
  IntentRecognitionAccuracy: {
    name: 'Intent Recognition Accuracy',
    description: 'The accuracy of intent recognition.',
    unit: Unit.Percentage
  },
  GoalSuccessRate: {
    name: 'Goal Success Rate',
    description: 'The success rate of achieving goals.',
    unit: Unit.Percentage
  },
  TaskCompletion: {
    name: 'Task Completion',
    description: 'The task completion rate.',
    unit: Unit.Percentage
  },
  WorkflowEfficiency: {
    name: 'Workflow Efficiency',
    description: 'The efficiency of the workflow.',
    unit: Unit.Percentage
  },
  GraphDeterminismScore: {
    name: 'Graph Determinism Score',
    description: 'The determinism score of the execution graph.',
    unit: Unit.Scalar
  },
  AgentToAgentInteractions: {
    name: 'Agent-to-Agent Interactions',
    description: 'The number of agent-to-agent interactions.',
    unit: Unit.Scalar
  },
  AgentToToolInteractions: {
    name: 'Agent-to-Tool Interactions',
    description: 'The number of agent-to-tool interactions.',
    unit: Unit.Scalar
  },
  PolicySafety: {
    name: 'Policy Safety',
    description: 'Whether the policies in place allow evidence-based correction.',
    unit: Unit.Percentage
  },
  GoalAlignment: {
    name: 'Goal Alignment',
    description: 'Whether delegated work preserves the root objective.',
    unit: Unit.Percentage
  },
  InstructionFollowing: {
    name: 'Instruction Following',
    description: 'Whether agents followed their instructions and constraints.',
    unit: Unit.Percentage
  },
  HandoffQuality: {
    name: 'Handoff Quality',
    description: 'The quality of handoffs between agents.',
    unit: Unit.Percentage
  },
  ConfidenceCalibration: {
    name: 'Confidence Calibration',
    description: 'Whether expressed confidence matches the evidence.',
    unit: Unit.Percentage
  },
  VerificationQuality: {
    name: 'Verification Quality',
    description: 'Whether outputs were verified before synthesis or action.',
    unit: Unit.Percentage
  },
  CommunicationEfficiency: {
    name: 'Communication Efficiency',
    description: 'Whether inter-agent communication adds enough value.',
    unit: Unit.Percentage
  },
  ConstraintSatisfaction: {
    name: 'Constraint Satisfaction',
    description: 'Whether the final outcome satisfies hard constraints.',
    unit: Unit.Percentage
  },
  SemanticConsistency: {
    name: 'Semantic Consistency',
    description: 'The semantic consistency of the session.',
    unit: Unit.Percentage
  },
  LLMErrorRate: {
    name: 'LLM Error Rate',
    description: 'The error rate of LLM calls.',
    unit: Unit.Percentage
  },
  ToolErrorRate: {
    name: 'Tool Error Rate',
    description: 'The error rate of tool calls.',
    unit: Unit.Percentage
  }
};

export const defaultSelectedMetricKeys: (keyof typeof metricCatalog)[] = [
  'Duration',
  'Cost',
  'Groundedness',
  'ToolUtilizationAccuracy',
  'AnswerRelevancy'
];
