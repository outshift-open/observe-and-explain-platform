/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export interface SessionMetric {
  name: string;
  value: number;
  metric_id: string;
  source: string | null;
  reasoning: string | null;
  error: string | null;
}

export interface Session {
  sessionId: string;
  timestamp: string;
  agents: (string | null)[] | null;
  llms: (string | null)[] | null;
  tokens: number;
  status: string;
  cost: number;
  duration: number;
  session_metrics?: SessionMetric[];
}

export interface SessionWithStatefulEval extends Session {
  statefulEval?:
    | (SessionStatefulEvalMetric & { value: string | number })
    | null;
}

export interface WastefulSession {
  sessionId: string;
  timestamp: string;
  actualCost?: number;
  constEfficiency?: number;
  estimatedOptimalCost?: number;
  estimatedWaste?: number;
  qualityScore?: number;
  semanticGroup?: string;
  semanticGroupId?: string;
}

export interface SessionWithMetrics extends Session {
  semanticGroupMetrics: {
    name: string;
    value: number;
  }[];
}

export interface Application {
  applicationName: string;
  version: number;
  description: string;
  cost: number;
  costDollars: number;
  timestamp: string;
  llms: string[];
  agents: string[];
  overallPerformance: {
    unit: Unit;
    value: number;
  };
}

export interface ApplicationWithStatefulEval extends Application {
  fatalFailures: number;
  minorFailures: number;
}

export enum Unit {
  Dollar = 'DOLLAR',
  Milliseconds = 'MILLISECONDS',
  Percentage = 'PERCENTAGE',
  Scalar = 'SCALAR'
}

export interface SingleValueData {
  value: number;
  unit: Unit;
}

export interface MultipleValuesData {
  count: number;
  list: string[];
}

export interface TimelineData {
  timestamp: string;
  sessionIDs: string[];
  value: SingleValueData;
}

export interface MostActiveAgent {
  agentName: string;
  activity: SingleValueData;
}

export interface ApplicationMetrics {
  totalTokens: TimelineData[];
  totalCost: TimelineData[];
  sessionDuration: SingleValueData;
  workflowEfficiency: SingleValueData;
  answerGroundedness: SingleValueData;
  answerRelevancy: SingleValueData;
  overallTaskCompletion: SingleValueData;
  toolUtilisationAccuracyScore: SingleValueData;
  overallPerformanceScore: SingleValueData;
  toxicity: SingleValueData;
  errorCount: SingleValueData;
  mostFrequentErrors: MultipleValuesData;
  traces: SingleValueData;
  sessions: SingleValueData;
  llmCalls: SingleValueData;
  toolCalls: SingleValueData;
  totalActionCount: SingleValueData;
  totalConversationCount: SingleValueData;
  graphDeterminism: SingleValueData;
  graphDynamism: SingleValueData;
  mostActiveAgent: MostActiveAgent;
}

export interface AgentTask {
  id: string;
  name: string;
  status: string;
  duration: number;
  cost: SingleValueData;
}

export interface Agent {
  id: string;
  name: string;
  failures: number;
  recoveryRate: number;
  cost: SingleValueData;
  utilisation: SingleValueData;
  costTokens: SingleValueData;
  activity: SingleValueData;
  tasks: AgentTask[];
}

export interface ApplicationAgents {
  totalCost: number;
  avgDuration: number;
  duration: number;
  overallTaskCompletion: number;
  overallActionAdvancement: number;
  agents: Agent[];
}

export interface ApplicationSessions {
  avgDuration: number;
  successRate: number;
  errorRate: number;
  sessionList: SessionWithStatefulEval[];
}

export interface Span {
  spanId: string;
  duration: number;
  spanName: string;
  timestamp: string;
  startTime: number;
  endTime: number;
  icon: string;
  error: boolean;
  childrenSpans?: (Span | null)[] | null;
}

export interface SessionTimeline {
  spanId: string;
  timestamp: string;
  startTime: string;
  spanName: string;
  icon: string;
  endTime: string;
  duration: number;
  error: boolean;
  Spans?: (Span | null)[] | null;
}

export interface SessionAnomalyDetectionMetric {
  value: SingleValueData;
  isOutlier?: boolean;
}

export interface SessionAnomalyDetection {
  sessionId: string;
  duration: SessionAnomalyDetectionMetric;
  sessionCost: SessionAnomalyDetectionMetric;
  answerRelevancy: SessionAnomalyDetectionMetric;
  answerGroundedness: SessionAnomalyDetectionMetric;
  toolUtilizationAccuracy: SessionAnomalyDetectionMetric;
}

export interface LatentSpaceNodeData {
  state_id: string;
  content: string;
  semantic_type: 'initial' | 'intermediate' | 'final';
  path: string;
}

export interface LatentSpaceNodeResponse {
  id: string;
  label: string;
  x: number;
  y: number;
  type: string;
  data: LatentSpaceNodeData;
  metadata: {
    color: string;
    shape: string;
    size: number;
  };
}

export interface LatentSpaceEdgeData {
  transition_id: string;
  duration: number;
  edge_type: string;
  entity_name: string;
  entity_type: string;
}

export interface LatentSpaceEdgeResponse {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
  data: LatentSpaceEdgeData;
  metadata: {
    color: string;
  };
}

export interface LatentSpaceMetadata {
  graph_type: string;
  projection_method: string;
  node_count: number;
  edge_count: number;
  states_with_embeddings: number;
  states_without_embeddings: number;
  tsne_params: {
    perplexity: number;
    metric: string;
  };
  source: string;
}

export interface SessionLatentSpaceResponse {
  nodes: LatentSpaceNodeResponse[];
  edges: LatentSpaceEdgeResponse[];
  session_id: string;
  metadata: LatentSpaceMetadata;
}

export interface LatentSpaceNode {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  data: {
    state_id: string;
    content: string;
    semantic_type: 'initial' | 'intermediate' | 'final';
    path: string;
  };
  metadata: {
    hierarchy_levels: string[];
  };
}

export interface LatentSpaceEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
  data: {
    transition_id: string;
    duration: number;
    edge_type: string;
    entity_name: string;
    entity_type: string;
  };
  metadata: {
    hierarchy_level: string;
  };
}

export interface SessionLatentSpaceData {
  nodes: LatentSpaceNode[];
  edges: LatentSpaceEdge[];
  session_id: string;
  hierarchy_level: string;
  metadata: {
    graph_type: string;
    node_count: number;
    edge_count: number;
    source: string;
    isTimeout: boolean;
  };
}

export interface ErrorItem {
  name: string;
  count: number;
  source: string;
  sourceName: string;
  description: string;
}

export type AgentMetricType =
  | 'general'
  | 'performance'
  | 'quality_and_reasoning'
  | 'reliability_and_safety'
  | 'cost'
  | 'tools'
  | 'conversation'
  | 'llm';

export type AgentMetrics =
  | AgentGeneralMetrics
  | AgentPerformanceMetrics
  | AgentQualityAndReasoningMetrics
  | AgentReliabilityAndSafetyMetrics
  | AgentCostMetrics
  | AgentToolsMetrics
  | AgentConversationMetrics
  | AgentLLMMetrics;
export interface AgentGeneralMetrics {
  totalLLMInvocationDuration: TimelineData[];
  totalAgentCost: TimelineData[];
  overallTaskCompletion: TimelineData[];
  averageAnswerRelevancy: TimelineData[];
  successRate: TimelineData[];
}

export interface AgentPerformanceMetrics {
  agentErrorCount: SingleValueData;
  agentLatencyPercentile90: SingleValueData;
  agentLatencyPercentile95: SingleValueData;
  agentRetrievalLatency: SingleValueData;
  averageLatency: TimelineData[];
  agentThroughput: TimelineData[];
  agentWorkflowEfficiency: TimelineData[];
  averageLLMInvocationDuration: TimelineData[];
  errorRateOverTime: TimelineData[];
  errorsBreakdown: ErrorItem[];
}

export interface AgentLLMMetrics {
  totalLLMCost: TimelineData[];
  totalTokens: TimelineData[];
  inputTokens: TimelineData[];
  outputTokens: TimelineData[];
  inferenceDuration: TimelineData[];
  answerCorrectness: TimelineData[];
  answerRelevancy: TimelineData[];
  answerFaithfulness: TimelineData[];
  coherence: TimelineData[];
  tonality: TimelineData[];
  llmErrorRate: TimelineData[];
  llmSuccessRate: TimelineData[];
  llmRecoveryRate: TimelineData[];
  llmRetryRate: TimelineData[];
  toxicity: TimelineData[];
  bias: TimelineData[];
  uncertaintyScore: TimelineData[];
  piiDetection: TimelineData[];
  policyViolation: TimelineData[];
}

export interface AgentPerformanceMetrics {
  agentErrorCount: SingleValueData;
  agentLatencyPercentile90: SingleValueData;
  agentLatencyPercentile95: SingleValueData;
  agentRetrievalLatency: SingleValueData;
  averageLatency: TimelineData[];
  agentThroughput: TimelineData[];
  agentWorkflowEfficiency: TimelineData[];
  averageLLMInvocationDuration: TimelineData[];
  errorRateOverTime: TimelineData[];
  errorsBreakdown: ErrorItem[];
}

export interface AgentQualityAndReasoningMetrics {
  overallTaskCompletion: SingleValueData;
  toolUtilizationAccuracy: TimelineData[];
  generalStructureAndStyle: TimelineData[];
  answerCorrectness: TimelineData[];
  answerRelevancy: TimelineData[];
  answerGroundedness: TimelineData[];
  answerCoherence: TimelineData[];
  agentTonality: TimelineData[];
}

export interface AgentReliabilityAndSafetyMetrics {
  successRate: SingleValueData;
  errorRate: SingleValueData;
  recoveryRate: SingleValueData;
  retryRate: SingleValueData;
  agentFailureCount: SingleValueData;
  agentRecoveryCount: SingleValueData;
  agentRecoveryRate: SingleValueData;
  agentAvailability: SingleValueData;
  bias: TimelineData[];
  toxicity: TimelineData[];
  policyViolation: TimelineData[];
}

export interface AgentCostMetrics {
  totalLLMCost: TimelineData[];
  totalToolCost: TimelineData[];
  averageLLMCost: TimelineData[];
  averageToolCost: TimelineData[];
  numberOfLLMCalls: TimelineData[];
  numberOfToolCalls: TimelineData[];
}

export interface AgentToolsMetrics {
  toolDetails: ToolDetail[];
}
export interface ToolDetail {
  toolName: string;
  utilization: SingleValueData;
  errorRate: SingleValueData;
  successRate: SingleValueData;
  retryRate: SingleValueData;
  utilizationAccuracyScore: SingleValueData;
  toolDuration: TimelineData[];
}

export interface AgentConversationMetrics {
  relevancy: TimelineData[];
  completeness: TimelineData[];
  roleAdherence: TimelineData[];
  topicAdherence: TimelineData[];
  contextPreservation: TimelineData[];
  intentRecognitionAccuracy: TimelineData[];
  workflowCohesionIndex: TimelineData[];
  goalSuccessRate: TimelineData[];
}

export type AgentFailingEntityType = 'tool' | 'llm' | 'agent';
export interface AgentFailingEntity {
  name: string;
  type: AgentFailingEntityType;
  failingAction?: string;
  occurrences?: number;
  reasoning?: string;
  explanation?: string;
}

export interface AgentCard {
  id: string;
  name: string;
  version: string;
  llm: string;
  trajectoryCount: number;
  totalSessions: number;
  spanCount: number;
  status: string;
  trajectoryScore: number;
  topFailingEntities?: AgentFailingEntity[];
}

export interface AgentCardWithStatefulEval extends AgentCard {
  fatalErrors: number;
  minorErrors: number;
  topFailingEntities: AgentFailingEntity[];
}

export interface StaticTopologyTool {
  name: string;
  description: string;
  isTool: boolean;
}

export interface StaticTopologyNode {
  id: string;
  name: string;
  data: string | StaticTopologyTool[];
  metadata: Record<string, unknown> | null;
  description?: string;
}

export interface StaticTopologyEdge {
  source: string;
  target: string;
  data: string | null;
  conditional: boolean;
}

export interface StaticTopology {
  nodes: Record<string, StaticTopologyNode>;
  edges: StaticTopologyEdge[];
}

export interface SessionStatefulEval {
  session_id: string;
  metrics: SessionStatefulEvalMetric[];
}

export interface SessionStatefulEvalMetricFailure {
  classification: string;
  metric: string;
  span_index: number;
  span_id: string;
  span_type: string;
  entity_name: string;
  metric_score: number;
  fatality_score: number;
  reasoning: string;
  explanation: string;
  observed_impact: string;
  confidence: number;
  hard_rule_violation: boolean;
  self_corrected: boolean;
}

export interface SessionStatefulEvalMetric {
  metric_id?: string;
  name: string;
  reasoning?: string;
  reasoningJson?: {
    fatal_failures: SessionStatefulEvalMetricFailure[];
    minor_failures: SessionStatefulEvalMetricFailure[];
    total_fatal: number;
    total_minor: number;
    trajectory_score: number;
  };
  source?: string;
  value?: number;
}

export interface SpanStatefulEval {
  span_id: string;
  session_id: string;
  metrics: SpanStatefulEvalMetric[];
}

export interface SpanStatefulEvalMetric {
  metric_id?: string;
  name: string;
  reasoning?: string;
  source?: string;
  value?: number;
}

export interface SemanticGroup {
  id: string;
  group_name: string;
  group_summary: string;
  n_sessions: number;
  medioid_session_id: string;
  children_nodes: string[];
  session_ids: string[];
  split_distance: number;
  overall_quality?: number;
  overall_reliability?: number;
  overall_performance?: number;
}

export interface NormalBehaviourReport {
  reports: NormalBehaviourReportItem[];
}

export interface NormalBehaviourReportItem {
  metadata: string;
  centroid: string;
}

export interface ConsistencyReport {
  reports: ConsistencyReportItem[];
}

export interface ConsistencyReportItem {
  metadata: string;
  mean: string;
  confidence_indicator: ConfidenceLevel;
}

export enum ConfidenceLevel {
  High = 'High',
  Low = 'Low',
  Medium = 'Medium'
}

export interface AnomalyReport {
  reports: AnomalyReportItem[];
}
export interface AnomalyReportItem {
  metadata: string;
  outliers_values: string[];
}

export interface SemanticGroupDetails {
  children_nodes: string[];
  group_name: string;
  group_summary: string;
  id: string;
  n_sessions: number;
  session_ids: string[];
}

export interface SessionMetricsItem {
  metricName: string;
  metricResult: string;
}

export interface SessionMetrics {
  metrics: SessionMetricsItem[];
}

export interface OutlierSession {
  sessionId: string;
  metrics: OutlierMetric[];
}

export interface OutlierMetric {
  metricName: string;
  metricKey: string;
  value: SingleValueData;
}

export interface ApplicationSummaryMetrics {
  applicationName: string;
  quality: ApplicationSummaryQualityMetric[];
  reliability: ApplicationSummaryReliabilityMetric[];
  performance: ApplicationSummaryQualityMetric[];
}

export interface ApplicationSummaryQualityMetric {
  metric_name: string;
  values: ApplicationSummaryMetricsValue[];
}

export interface ApplicationSummaryReliabilityMetric {
  name: string;
  value: number;
  metric_id: string | null;
  source: string | null;
  reasoning: string | null;
}

export type ApplicationSummaryMetricsValue = [number, number];

export interface ImpactAssessment {
  session_id: string;
  metric_name: string;
  agents: ImpactAssessmentAgent[];
}

export interface ImpactAssessmentAgent {
  agent_name: string;
  value: SingleValueData;
}

export interface WasteEstimationSemanticGroup {
  groupId: string;
  groupName: string;
  totalCost: number;
}

export interface CostEfficiencyGrouppedSessions {
  groupId: string;
  groupName: string;
  sessionId: string;
  costEfficiency: number;
  startTime: number;
  actualCost?: number;
  estimatedWaste?: number;
}

export interface WastedResourcesFeatureScore {
  qualityTarget: string;
  rank: number;
  feature: string;
  score: number;
}

export interface SemanticGroupsInsight {
  groupName: string;
  groupSummary: string;
  groupId: string;
  sessionIds: string[];
  createdAt: string;
  description: string;
  insightId: string;
  name: string;
  labels: string[];
  priority: string;
  targetNodeId: string;
}

export interface SessionInsight {
  duration: number;
  endTime: string;
  sessionId: string;
  startTime: string;
  createdAt: string;
  description: string;
  insightId: string;
  name: string;
  labels: string[];
  priority: string;
  targetNodeId: string;
}

export interface ReasoningPathResponse {
  sessionId: string;
  model: { modelId: string; version: string; modelName: string } | null;
  trajectoryScore: number | null;
  evaluationRounds: number[];
  nodes: ReasoningNode[];
  edges: ReasoningEdge[];
}

export interface ReasoningHistoryValueEntry {
  valueId: string;
  value: string | boolean | number | null;
  reason: string | null;
  trajectoryIndex: number | null;
  assignmentStrategy: string | null;
  spanId: string | null;
  executionId: string | null;
  entityName: string | null;
  executionLabels: string[] | null;
  executionTimestamp: number | null;
  executionDuration: number | null;
  toolName: string | null;
  processingName: string | null;
  llmName: string | null;
  modelName: string | null;
  inputParams: string | null;
  outputContent: string | null;
  toolOutput: string | null;
}

export interface ReasoningNode {
  id: string;
  name: string;
  tier: 'entity' | 'process' | 'alignment';
  type: string;
  description: string | null;
  isEnabledForEvaluation: boolean;
  discriminativeScore: number | null;
  value: string | boolean | number | null;
  reason: string | null;
  trajectoryIndex: number | null;
  assignmentStrategy: string | null;
  valueId: string | null;
  spanId: string | null;
  executionId: string | null;
  entityName: string | null;
  executionLabels: string[] | null;
  toolName: string | null;
  processingName: string | null;
  llmName: string | null;
  modelName: string | null;
  executionTimestamp: number | null;
  executionDuration: number | null;
  inputParams: string | null;
  outputContent: string | null;
  toolOutput: string | null;
  history: ReasoningHistoryValueEntry[];
}

export interface ReasoningEdge {
  source: string;
  target: string;
  relationship: string;
}

// --- Application-level aggregated reasoning path ---

export interface AppReasoningSessionEntry {
  sessionId: string;
  value: string | boolean | number | null;
  lastTrajectoryIndex: number | null;
  trajectoryScore: number | null;
  passed: boolean | null;
}

export interface AppReasoningNode {
  id: string;
  name: string;
  tier: 'entity' | 'process' | 'alignment';
  type: string;
  description: string | null;
  isEnabledForEvaluation: boolean;
  discriminativeScore: number | null;
  sessionCount: number;
  avgLastTrajectoryIndex: number | null;
  distribution: Record<string, number>;
  distinctValueCount: number;
  sessions: AppReasoningSessionEntry[];
}

export interface AppReasoningPathResponse {
  masName: string;
  model: {
    modelId: string;
    version: string;
    modelName: string;
  } | null;
  totalSessions: number;
  passedSessions: number;
  failedSessions: number;
  nodes: AppReasoningNode[];
  edges: ReasoningEdge[];
}

export interface TimelineReasoningDependency {
  variableId: string;
  name: string;
  tier: 'entity' | 'process';
  value: string | boolean | number | string[] | Record<string, unknown> | null;
  reason: string;
  trajectoryIndex: number;
  assignmentStrategy: string;
}

export interface TimelineReasoningVariable {
  variableId: string;
  name: string;
  tier: 'entity' | 'process' | 'alignment';
  value: string | boolean | number | string[] | Record<string, unknown> | null;
  reason: string;
  trajectoryIndex: number;
  assignmentStrategy: string;
  executionId?: string;
  entityName?: string;
  executionLabels?: string[];
  dependencies?: TimelineReasoningDependency[];
}

export interface TimelineReasoningSpan {
  spanId: string;
  executionId: string;
  entityName: string;
  executionLabels: string[];
  executionTimestamp: number;
  executionDuration: number;
  variables: TimelineReasoningVariable[];
}

export interface TimelineReasoningPathResponse {
  sessionId: string;
  spans: TimelineReasoningSpan[];
}

export enum AttributeType {
  Bool = 'BOOL',
  Dollar = 'DOLLAR',
  Float = 'FLOAT',
  Int = 'INT',
  Json = 'JSON',
  String = 'STRING'
}

export interface Attribute {
  attributeType?: AttributeType;
  key: string;
  value: string;
}

export interface SpanDetails {
  spanId: string;
  spanName: string;
  spanType: string;
  exception?: string | null;
  attributes: Attribute[];
}

export interface SlimMetrics {
  processingTime: SingleValueData;
  messagesProcessed: SingleValueData;
  successRate: SingleValueData;
  errorRate: SingleValueData;
}

export interface AgenticProtocolsMetrics {
  slimMetrics: SlimMetrics;
}

export interface Task {
  id: string;
  name: string;
  status: string;
  duration: number;
  cost: SingleValueData;
}

export interface AnalyzeSummaryData {
  agentName: string;
  description: string;
  value: SingleValueData;
}

export interface DotData {
  id: string;
  x: number;
  y: number;
  label: string;
  group: string;
  isOutlier?: boolean;
  sessionId?: string;
}

export interface ImpactDistribution {
  agentName: string;
  answerGroundedness?: SingleValueData | null;
  answerRelevancy?: SingleValueData | null;
  sessionCost?: SingleValueData | null;
  sessionDuration?: SingleValueData | null;
  toolUtilizationAccuracy?: SingleValueData | null;
  groundedness?: SingleValueData | null;
}

export interface SessionsWithCognitiveObservability {
  sessions: SessionWithCognitiveObservability[];
}

export interface SessionWithCognitiveObservability extends Session {
  cognitiveObservabilityMetrics: CognitiveObservabilityMetric[];
  cognitiveFailures: CognitiveFailure[];
}

export interface CognitiveObservabilityMetric {
  name: string;
  value: SingleValueData;
}

export interface CognitiveFailure {
  name: string;
  confidence: number;
  remediations?: string[] | null;
}

// ---------------------------------------------------------------------------
// L9 protocols (per-session)
//
// The API returns the list of L9 protocols that are relevant for a session.
// Each protocol is `enabled` (applies to the session) and/or `activated`
// (actually started). Every metric may be missing: `null` / absent always means
// "no data" and must never be rendered as a zero.
// ---------------------------------------------------------------------------

// Verdict labels are an extensible enum (not confirmed yet), so they are plain
// strings.
export interface L9Verdict {
  label: string;
  reason?: string | null;
  // Optional list backing the verdict, e.g. issues missing a definition.
  items?: string[] | null;
}

export interface L9ExpectedActivation {
  expected: boolean | null;
  reason?: string | null;
}

// Pass/fail check with the failed items (steps, fields...) when it failed.
export interface L9Check {
  passed: boolean | null;
  failures?: string[] | null;
}

export interface L9UsageSummary {
  inputTokens?: number | null;
  outputTokens?: number | null;
  cacheReadTokens?: number | null;
  cacheCreationTokens?: number | null;
  totalTokens?: number | null;
  // Cost in dollars of each token bucket, and the total.
  inputCost?: number | null;
  outputCost?: number | null;
  cacheReadCost?: number | null;
  cacheCreationCost?: number | null;
  totalCost?: number | null;
}

export interface L9PhaseUsage {
  phase: string;
  llmCalls?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  cacheReadTokens?: number | null;
  cacheCreationTokens?: number | null;
  cost?: number | null;
}

// "achieved / bound": the protocol reports its bounds when the run opens.
export interface L9Bound {
  name: string;
  achieved?: number | null;
  bound?: number | null;
}

export interface L9ProtocolBase {
  // Protocol identifier, e.g. 'L9-CONCORD'.
  protocol: string;
  displayName?: string | null;
  description?: string | null;
  // The protocol applies to this session.
  enabled: boolean;
  // The protocol was actually started in this session.
  activated: boolean;
  // Round/step or timestamp, shown as is.
  activatedAt?: string | null;
  // Absent: not tracked for this protocol. null: tracked but no data.
  expected?: L9ExpectedActivation | null;
}

// Extensible: the reference doc names the success state both `COMMIT` and
// `SUCCESS`, next to `BEST_EFFORT`.
export type L9ConcordTerminalState = string;

export interface L9ConcordProtocol extends L9ProtocolBase {
  protocol: 'L9-CONCORD';
  compliance?: {
    candidateCompleteness?: L9Check | null;
    completion?: {
      passed: boolean | null;
      terminalState: L9ConcordTerminalState | null;
    } | null;
    protocolCompliance?: L9Check | null;
  } | null;
  correctness?: {
    outcomeSatisfaction?: L9Verdict | null;
    scoreFairness?: L9Verdict | null;
  } | null;
  cost?: {
    usage?: L9UsageSummary | null;
    phases?: L9PhaseUsage[] | null;
    bounds?: L9Bound[] | null;
  } | null;
  outcome?: {
    // Satisfaction floor threshold.
    tau?: number | null;
    // Worst-off agent score per round, round 0 being the seed.
    trajectory?: { round: number; worstAgentScore: number | null }[] | null;
    agentScores?: { agent: string; score: number | null }[] | null;
    // BEST_EFFORT only.
    shortfall?: { agent: string; shortBy: number } | null;
  } | null;
}

export interface L9AccordProtocol extends L9ProtocolBase {
  protocol: 'L9-ACCORD';
  convergence?: {
    lockedFrame?: {
      wellFormed: boolean | null;
      missingFields?: string[] | null;
    } | null;
    roundsPerPhase?: { phase: string; rounds: number | null }[] | null;
  } | null;
  correctness?: {
    // null when there is no ground truth.
    issueCoverage?: {
      covered: number;
      total: number;
      missedIssues?: string[] | null;
    } | null;
    // Does each issue carry a definition from every agent? `complete` is null
    // when this could not be determined.
    definitionsFromAllAgents?: {
      complete: boolean | null;
      reason?: string | null;
      issuesMissingDefinition?: string[] | null;
    } | null;
  } | null;
  cost?: {
    usage?: L9UsageSummary | null;
  } | null;
  benefits?: {
    goalSuccess?: { achieved: boolean | null; reason?: string | null } | null;
    mutualUnderstanding?: L9Verdict | null;
    intentContractConsumedByConcord?: boolean | null;
  } | null;
}

// Protocol without a dedicated renderer: only its activation is shown.
export interface L9GenericProtocol extends L9ProtocolBase {
  protocol: string;
}

export type L9Protocol =
  | L9ConcordProtocol
  | L9AccordProtocol
  | L9GenericProtocol;

export interface SessionL9Protocols {
  sessionId: string;
  protocols: L9Protocol[];
}

// ---------------------------------------------------------------------------
// L9 protocols comparison (sessions of a time interval)
//
// Each session carries its L9 protocol status, so that sessions can be grouped
// by which protocols were activated and compared with each other. Every field
// besides the session itself may be missing, and a missing value is never
// counted as a zero.
// ---------------------------------------------------------------------------

export interface SessionL9ProtocolStatus {
  protocol: string;
  enabled: boolean;
  activated: boolean;
}

export interface SessionWithL9Protocols extends Session {
  // Absent or empty: no L9 protocol was enabled in the session.
  l9Protocols?: SessionL9ProtocolStatus[] | null;
  cognitiveObservabilityMetrics?: CognitiveObservabilityMetric[] | null;
  cognitiveFailures?: CognitiveFailure[] | null;
  // Only for sessions where CONCORD was activated.
  concord?: {
    terminalState?: L9ConcordTerminalState | null;
    // Final satisfaction of the worst-off agent.
    worstOffSatisfaction?: number | null;
  } | null;
}

export interface SessionsWithL9Protocols {
  sessions: SessionWithL9Protocols[];
}
