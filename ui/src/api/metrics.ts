/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export type Operation = 'sum' | 'average';

export type MetricDef = {
  name: string;
  description?: string;
  isCard?: boolean;
  operation?: Operation;
  isRounded?: boolean;
  disabled?: boolean;
  componentName?: string;
};

const generalMetrics: Record<string, MetricDef> = {
  totalLLMInvocationDuration: {
    name: 'Total LLM invocations duration',
    description: 'The total duration of all the LLM invocations for an agent.',
    operation: 'average',
    componentName: 'ArthurGeneralMetricChart'
  },

  totalAgentCost: {
    name: 'Total agent cost',
    description: 'Sums of LLM and Tools cost',
    operation: 'sum',
    // isCard: true
    componentName: 'ArthurGeneralMetricChart'
  },
  overallTaskCompletion: {
    name: 'Overall task completion',
    description: "Assesses whether the agents successfully achieved the user's goal.",
    operation: 'average',
    componentName: 'ArthurGeneralMetricChart'
    // isCard: true
  },
  averageAnswerRelevancy: {
    name: 'Average answer relevancy',
    description: 'Measures how closely the answer aligns to the user query.',
    operation: 'average',
    componentName: 'ArthurGeneralMetricChart'
    // isCard: true
  },

  successRate: {
    name: 'Completion rate',
    description: 'The completion rate of the agent.',
    operation: 'average',
    componentName: 'ArthurGeneralMetricChart'
    // isCard: true
  }

  // totalLLMInvocationsDuration: {
  //   name: 'Total LLM invocations duration',
  //   description: 'The total duration of all the LLM invocations for an agent.'
  // },
  // totalToolCallLatency: {
  //   name: 'Total tool call latency',
  //   description: 'The total latency of all the tool calls for an agent.'
  // },
  // averageLLMInvocationDuration: {
  //   name: 'Average LLM invocation duration',
  //   description: 'The average of one LLM invocation within an agent.'
  // },
  // averageToolCallLatency: {
  //   name: 'Average tool call latency',
  //   description: 'The average latency of one tool call for an agent.'
  // },
  // totalRetrievalLatency: {
  //   name: 'Total retrieval latency',
  //   description: 'The total latency of all the retrieval actions taken by the agent (RAG). It could be considered as a tool.'
  // },
  // averageRetrievalLatency: {
  //   name: 'Average retrieval latency',
  //   description: 'The average latency of one retrieval action taken by the agent.'
  // },
  // totalLLMCost: {
  //   name: 'Total LLM cost',
  //   description: 'The total cost of LLM operations.'
  // },
  // totalToolCost: {
  //   name: 'Total tool cost',
  //   description: 'The total cost of tool operations.'
  // },
  // totalCost: {
  //   name: 'Total cost',
  //   description: 'Sums of LLM and Tools cost'
  // },
  // averageLLMCost: {
  //   name: 'Average LLM cost',
  //   description: 'The average cost per LLM operation.'
  // },
  // averageToolCost: {
  //   name: 'Average Tool cost',
  //   description: 'Should be broken down per tool.'
  // },
  // numberOfLLMCalls: {
  //   name: 'Number of LLM calls',
  //   description: 'The total number of LLM calls.'
  // },
  // numberOfToolCalls: {
  //   name: 'Number of tool calls',
  //   description: 'The total number of tool calls.'
  // }
};

const reliabilityMetrics: Record<string, MetricDef> = {
  successRate: {
    name: 'Completion rate',
    description: 'The completion rate of the agent (avg between avg llm and avg tool completion rates).',
    isCard: true
  },
  errorRate: {
    name: 'Error rate',
    description: 'The rate of error for an agent (avg between avg llm and avg tool error rates).',
    isCard: true
  },
  recoveryRate: {
    name: 'Recovery rate',
    description: 'The recovery rate of the agent (avg llm recovery rate).',
    isCard: true
  },
  retryRate: {
    name: 'Retry rate',
    description: 'The retry rate of the agent (avg between avg llm and avg tool retry rates).',
    isCard: true
  },

  // toolErrorRate: {
  //   name: 'Tool error rate',
  //   description: 'The rate of error in tool call for an agent'
  // },
  // toolCallSuccessRate: {
  //   name: 'Tool call success rate',
  //   description: 'The success rate of tool call for an agent'
  // },
  // toolRetryRate: {
  //   name: 'Tool retry rate',
  //   description: 'The rate of retry for a tool call.'
  // },

  agentFailureCount: {
    name: 'Agent failure count',
    description: 'The number of failures for an agent.',
    isCard: true
  },
  agentRecoveryCount: {
    name: 'Agent recovery count',
    description: 'The number of recoveries for an agent.',
    isCard: true
  },
  agentRecoveryRate: {
    name: 'Agent recovery rate',
    description: 'The recovery rate of the agent.',
    isCard: true
  },
  // agentAvailability: {
  //   name: 'Agent availability',
  //   description: 'The availability of the agent.',
  //   isCard: true
  // },
  bias: {
    name: 'Bias',
    description: `A score indicating the level of bias detected in the agent's output.`,
    operation: 'average',
    componentName: 'ArthurReliabilityMetricChart'
  },
  toxicity: {
    name: 'Toxicity',
    description: `A score indicating the level of toxicity detected in the agent's output.`,
    operation: 'average',
    componentName: 'ArthurReliabilityMetricChart'
  }
  // policyViolation: {
  //   name: 'Policy violations',
  //   description: `A score indicating the level of policy violations detected in the agent's output.`
  // }
};

const performanceMetrics: Record<string, MetricDef> = {
  averageLatency: {
    name: 'Agent duration',
    description: 'The average time an agent takes to process a task.',
    operation: 'average',
    componentName: 'ArthurPerformanceMetricChart'
  },
  agentLatencyPercentile90: {
    name: 'Agent duration percentile 90',
    description: 'The duration value at which 90% of requests are faster, used to measure tail duration.',
    isCard: true
  },
  agentLatencyPercentile95: {
    name: 'Agent duration percentile 95',
    description: 'The duration value at which 95% of requests are faster, used to measure tail duration.',
    isCard: true
  },
  agentRetrievalLatency: {
    name: 'Agent retrieval duration',
    description: 'The average time taken for information retrieval processes (RAG)',
    isCard: true
  },
  agentErrorCount: {
    name: 'Error count',
    description: 'The number of errors for an agent.',
    isCard: true,
    isRounded: true
  },
  agentThroughput: {
    name: 'Agent throughput',
    description: 'The rate of requests or operations processed over time.',
    operation: 'average',
    componentName: 'ArthurPerformanceMetricChart'
    // isCard: true
  },
  // agentWorkflowEfficiency: {
  //   name: 'Agent workflow efficiency',
  //   description: 'A score representing the efficiency of the sequence of steps taken by an agent to complete a task.',
  //   operation: 'average'
  // },
  averageLLMInvocationDuration: {
    name: 'Average LLM invocation duration',
    description: 'The average of one LLM invocation within an agent.',
    operation: 'average',
    componentName: 'ArthurPerformanceMetricChart'
  },
  errorRateOverTime: {
    name: 'Error rate over time',
    description: 'The rate of errors for an agent over time.',
    operation: 'average',
    componentName: 'ArthurPerformanceMetricChart'
  }
};

const qualityReasoningMetrics: Record<string, MetricDef> = {
  // totalSelectionAccuracy: {
  //   name: 'Tool selection accuracy',
  //   description: 'Assesses how effectively the agent selects the appropriate external tools to accomplish tasks, considering order of calls.',
  //   isCard: true
  // },
  // totalCallParametersAccuracy: {
  //   name: 'Tool call parameters accuracy',
  //   description:
  //     'Assesses the accuracy of arguments or parameters passed to tools by the agent, typically by reference to tool specifications or user requirements. Includes the importance in requred and optional parameters.',
  //   isCard: true
  // },
  // generalStructureAndStyle: {
  //   name: 'General structure and style',
  //   description: 'Assesses how readable and user-friendly is the produced output.',
  //   operation: 'average',
  //   componentName: 'ArthurQualityReasoningMetricChart'
  // },
  // answerCorrectness: {
  //   name: 'Answer correctness',
  //   description: 'Measures if the answer if factually correct.',
  //   operation: 'average',
  //   componentName: 'ArthurQualityReasoningMetricChart'
  // },
  toolUtilizationAccuracy: {
    name: 'Tool utilization accuracy',
    description: 'Assesses how effective the agent selects the appropriate tool and how the tool addresses the user input.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  },

  answerRelevancy: {
    name: 'Answer relevancy',
    description: 'Measures how closely the answer aligns to the user query.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  },
  groundedness: {
    name: 'Answer groundedness',
    description: 'Measures how much the answer is inferred from the given context.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  },
  intentRecognitionAccuracy: {
    name: 'Intent recognition accuracy',
    description: 'Measure how well the Assistant understands and correctly identifies user intents.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  },
  neuroSymbolicEvaluation: {
    name: 'Neuro-symbolic evaluation',
    description: "Evaluates the agent's ability to reason about the world and make decisions based on the information provided.",
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart',
    isCard: true
  },
  responseCompleteness: {
    name: 'Response completeness',
    description: 'Measures the completeness of the response.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  },
  trajectoryQuality: {
    name: 'Trajectory quality',
    description: 'Measures the quality of the trajectory.',
    operation: 'average',
    componentName: 'ArthurQualityReasoningMetricChart'
  }

  // answerCoherence: {
  //   name: 'Answer coherence',
  //   description: 'Measures if the answer is logically structured, internally consistent, and easy to follow.',
  //   operation: 'average',
  //   componentName: 'ArthurQualityReasoningMetricChart'
  // },
  // agentTonality: {
  //   name: 'Agent tonality',
  //   description: 'Evaluates whether the output matches the intended communication style.',
  //   operation: 'average',
  //   componentName: 'ArthurQualityReasoningMetricChart'
  // },
  // overallTaskCompletion: {
  //   name: 'Overall task completion',
  //   description: "Assesses whether the agents successfully achieved the user's goal.",
  //   isCard: true,
  //   componentName: 'ArthurQualityReasoningMetricChart'
  // }
  // overallActionAdvancement: {
  //   name: 'Overall action advancement',
  //   description: 'Measures if the agent enables the user to make progress toward a long-term goal (even if the task is not yet completed).',
  //   isCard: true
  // },
  // graphTrajectoryMatch: {
  //   name: 'Graph trajectory match',
  //   description: 'Measures the executed trajectory overlap with the ground-truth, focusing on the graph structure instead of the messages.',
  //   isCard: true
  // },
  // messageTrajectoryMatch: {
  //   name: 'Message trajectory match',
  //   description: 'Measures the executed trajectory overlap with the ground-truth trajectory.',
  //   isCard: true
  // }
  // summarizationScore: {
  //   name: 'Summarization score',
  //   description: 'Measures the quality, completeness, and factual accuracy of summaries generated by the LLM.',
  //   isCard: true
  // },
  // reflectionScore: {
  //   name: 'Reflection score',
  //   description: 'Measures the quality, bias and reasoning correctness of the scores and outputs generated by LLM-as-judge.',
  //   isCard: true
  // },
  // confidenceScore: {
  //   name: 'Confidence score',
  //   description: "Quantifies the model's confidence in its own outputs, often by analysing the log-probabilities assigned to generated tokens.",
  //   isCard: true
  // },
  // multiStepPlanningAndExecutionScore: {
  //   name: 'Multi-step panning and execution score',
  //   description:
  //     "Evaluates the agent's ability to decompose and successfully execute complex, multi-step tasks, including correct sequencing, error recovery, and plan completion.",
  //   isCard: true
  // }
};

const costMetrics: Record<string, MetricDef> = {
  // totalCost: {
  //   name: 'Total cost',
  //   description: 'Sums of LLM and Tools cost'
  // },
  totalLLMCost: {
    name: 'Total LLM cost',
    description: 'The total cost of LLM operations.',
    operation: 'sum',
    componentName: 'ArthurCostMetricChart'
  },
  totalToolCost: {
    name: 'Total tool cost',
    description: 'The total cost of tool operations.',
    operation: 'sum',
    componentName: 'ArthurCostMetricChart'
  },

  averageLLMCost: {
    name: 'Average LLM cost',
    description: 'The average cost per LLM operation.',
    operation: 'average',
    componentName: 'ArthurCostMetricChart'
  },
  averageToolCost: {
    name: 'Average Tool cost',
    description: 'Should be broken down per tool.',
    operation: 'average',
    componentName: 'ArthurCostMetricChart'
  },

  numberOfLLMCalls: {
    name: 'Number of LLM calls',
    description: 'The total number of LLM calls.',
    operation: 'sum',
    componentName: 'ArthurCostMetricChart'
  },
  numberOfToolCalls: {
    name: 'Number of tool calls',
    description: 'The total number of tool calls.',
    operation: 'sum',
    componentName: 'ArthurCostMetricChart'
  }
};

const toolsMetrics: Record<string, MetricDef> = {
  listOfTools: {
    name: 'List of tools',
    description: 'The list of tools used by the agent.',
    operation: 'sum',
    componentName: 'ArthurToolsMetricChart'
  }
};

const conversationMetrics: Record<string, MetricDef> = {
  relevancy: {
    name: 'Relevancy',
    description:
      'Judges if each turn is pertinent and contributes constructively to the overall dialogue flow, avoiding irrelevant digressions or topic loss.',
    operation: 'average',
    componentName: 'ArthurConversationMetricChart'
  },
  completeness: {
    name: 'Completeness',
    description: 'Judges whether the conversation fully addresses user needs, covering all requested points or sub-queries across turns.',
    operation: 'average',
    componentName: 'ArthurConversationMetricChart'
  },
  roleAdherence: {
    name: 'Role adherence',
    description:
      'Assesses whether the Agent consistently maintains a defined persona, style, or role throughout a conversation, supporting scenario-based and branded assistants.',
    operation: 'average',
    componentName: 'ArthurConversationMetricChart'
  },
  // topicAdherence: {
  //   name: 'Topic adherence',
  //   description:
  //     'Measures whether the Agents responses remain within the expected or allowed topic domains, based on a predefined set of topics or categories. Used for domain-specialized assistants.',
  //   operation: 'average'
  // },
  // contextPreservation: {
  //   name: 'Context preservation',
  //   description: 'Evaluate the given response based on its ability to understand and address the provided input.',
  //   operation: 'average'
  // },
  intentRecognitionAccuracy: {
    name: 'Intent recognition accuracy',
    description: 'Measure how well the Assistant understands and correctly identifies user intents.',
    operation: 'average',
    componentName: 'ArthurConversationMetricChart'
  },

  goalSuccessRate: {
    name: 'Goal success rate',
    description: 'Measure how well the Assistant achieves the goals provided by the user.',
    operation: 'average',
    componentName: 'ArthurConversationMetricChart'
  }

  // workflowCohesionIndex: {
  //   name: 'Workflow cohesion index',
  //   description: 'Assess the seamless integration and coherence among different components in the workflow.',
  //   operation: 'average'
  // },
};

const llmMetrics: Record<string, MetricDef> = {
  //cost
  totalLLMCost: {
    name: 'Total LLM cost',
    description: 'The total cost of LLM operations.',
    operation: 'sum',
    componentName: 'ArthurLLMMetricChart'
  },
  totalTokens: {
    name: 'Total tokens',
    description: 'Number of total tokens.',
    operation: 'sum',
    componentName: 'ArthurLLMMetricChart'
  },
  inputTokens: {
    name: 'Input tokens',
    description: 'Number of input tokens.',
    operation: 'sum',
    componentName: 'ArthurLLMMetricChart'
  },
  outputTokens: {
    name: 'Output tokens',
    description: 'Number of output tokens.',
    operation: 'sum',
    componentName: 'ArthurLLMMetricChart'
  },

  // performance
  inferenceDuration: {
    name: 'Inference duration',
    description: 'Duration of the LLM call.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  answerCorrectness: {
    name: 'Answer correctness',
    description: 'Measures if the answer if factually correct. (ground truth needed)',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  answerRelevancy: {
    name: 'Answer relevancy',
    description: 'Measures how closely the answer aligns to the user query.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  answerFaithfulness: {
    name: 'Answer groundedness',
    description: 'Measures how much the answer is inferred from the given context.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  coherence: {
    name: 'Coherence',
    description: 'Evaluates whether the response is logically structured, internally consistent, and easy to follow.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  tonality: {
    name: 'Tonality',
    description: 'Evaluates whether the output matches the intended communication style.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },

  // reliability
  llmErrorRate: {
    name: 'LLM error rate',
    description: 'The rate of error in LLM calls for an agent',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  llmSuccessRate: {
    name: 'LLM completion rate',
    description: 'The completion rate of LLM calls for an agent',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  llmRecoveryRate: {
    name: 'LLM recovery rate',
    description: 'The recovery rate of the LLM calls for an agent.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  llmRetryRate: {
    name: 'LLM retry rate',
    description: 'The rate of retry for a LLM call for an agent.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },

  // safety
  toxicity: {
    name: 'Toxicity',
    description:
      'Detects the presence of offensive, harmful, or inappropriate language in model outputs, including hate speech, profanity, or abuse.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  },
  bias: {
    name: 'Bias',
    description: 'Identifies presence of unwanted bias (gender, racial, political, etc.) in LLM outputs.',
    operation: 'average',
    componentName: 'ArthurLLMMetricChart'
  }
  // uncertaintyScore: {
  //   name: 'Uncertainty score',
  //   description: `Quantifies the model's confidence in its own outputs, often by analysing the log-probabilities assigned to generated tokens.`
  // },
  // piiDetection: {
  //   name: 'PII detection',
  //   description: 'Detects of PII data in the answer'
  // },
  // policyViolation: {
  //   name: 'Policy violations',
  //   description: 'Detects the violation of a given policy.'
  // }
};

export const metrics: Record<string, Record<string, MetricDef>> = {
  General: generalMetrics,
  Performance: performanceMetrics,
  'Quality & Reasoning': qualityReasoningMetrics,
  'Reliability & Safety': reliabilityMetrics,
  Tools: toolsMetrics,
  Cost: costMetrics,
  LLM: llmMetrics,
  Conversation: conversationMetrics
};
