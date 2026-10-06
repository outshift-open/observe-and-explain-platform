#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, Integer, Text
from sqlalchemy.orm import DeclarativeBase

# ── SQLAlchemy ORM models ────────────────────────────────────────────────────


class OXPBaseModel(DeclarativeBase):
    """Base model for all oxp tables."""


class OtelTrace(OXPBaseModel):
    """Represents a row in the ``otel_traces`` table (oxp.db)."""

    __tablename__ = "otel_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Text, nullable=False)
    trace_id = Column(Text, nullable=False)
    span_id = Column(Text, nullable=False)
    parent_span_id = Column(Text, default="")
    trace_state = Column(Text, default="")
    span_name = Column(Text, default="")
    span_kind = Column(Text, default="")
    service_name = Column(Text, default="")
    resource_attributes = Column(Text, default="")
    scope_name = Column(Text, default="")
    scope_version = Column(Text, default="")
    span_attributes = Column(Text, default="")
    duration = Column(BigInteger, default=0)
    status_code = Column(Text, default="")
    status_message = Column(Text, default="")
    events_timestamp = Column(Text, default="")
    events_name = Column(Text, default="")
    events_attributes = Column(Text, default="")
    links_trace_id = Column(Text, default="")
    links_span_id = Column(Text, default="")
    links_trace_state = Column(Text, default="")
    links_attributes = Column(Text, default="")
    session_id = Column(Text, default="")
    agent_id = Column(Text, default="")
    application_id = Column(Text, default="")


# ── Pydantic request / response models ───────────────────────────────────────


class Filters(BaseModel):
    """Common query-string filters for time-range queries."""

    start_time: Optional[str] = Field(None, description="Unix epoch timestamp (start)")
    end_time: Optional[str] = Field(None, description="Unix epoch timestamp (end)")
    app_name: Optional[str] = Field(None, description="Filter by application name")
    limit: int = Field(50, ge=1, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Pagination offset")


class TraceItem(BaseModel):
    """A single trace summary returned by ``get_traces``."""

    session_id: str
    application_id: str
    start_time: str
    end_time: str


class TracesResponse(BaseModel):
    """Response body for ``get_traces``."""

    sessions: list[TraceItem]


class ApplicationNameItem(BaseModel):
    """A single application entry returned by ``get_applications``."""

    application_id: str
    start_time: str


class ApplicationNamesResponse(BaseModel):
    """Response body for ``get_applications``."""

    applications: list[ApplicationNameItem]


class ApplicationItem(BaseModel):
    """A single application with its computed metrics."""

    applicationName: str
    version: int = 1
    description: str = ""
    cost: float = 0.0
    costDollars: float = 0.0
    timestamp: str = ""
    llms: list[str] = []
    agents: list[str] = []
    overallPerformance: "SingleValueData" = None  # type: ignore[assignment]


class ApplicationsResponse(BaseModel):
    """Response body for ``get_applications`` (full application details)."""

    applications: list[ApplicationItem]


class UniqueAgentPerSession(BaseModel):
    """A single agent entry returned by ``get_session_agents``."""

    agent_id: str
    session_id: str


class SpanAttribute(BaseModel):
    """A single key/value attribute."""

    key: str
    value: str


class SpanDetailsItem(BaseModel):
    """Detailed information about a single span."""

    spanId: str
    spanName: str
    spanType: str
    exception: str = ""
    attributes: list[SpanAttribute] = []


class SpanDetailsResponse(BaseModel):
    """Response body for ``get_span_details``."""

    spanDetails: SpanDetailsItem


class SingleValueData(BaseModel):
    """A numeric value with its unit."""

    value: float
    unit: str  # e.g. "SCALAR", "DOLLAR", "PERCENTAGE", "MILLISECONDS", "TOKENS"


class AgentDetailsItem(BaseModel):
    """Detailed information about a single agent in a session."""

    id: str
    name: str
    description: str = ""
    llms: list[str] = []
    inputTokens: SingleValueData
    outputTokens: SingleValueData
    inputCost: SingleValueData
    outputCost: SingleValueData
    attributes: list[SpanAttribute] = []


class AgentDetailsResponse(BaseModel):
    """Response body for ``get_agent_details``."""

    agentDetails: AgentDetailsItem


class SLIMMetricsData(BaseModel):
    """SLIM agentic-protocol metrics."""

    processingTime: SingleValueData
    messagesProcessed: SingleValueData
    successRate: SingleValueData
    errorRate: SingleValueData


class AgenticProtocolsMetricsResponse(BaseModel):
    """Response body for ``/agentic-protocols-metrics``."""

    slimMetrics: SLIMMetricsData


# ── Monitor Application Level models ─────────────────────────────────────────


class TimelineData(BaseModel):
    """A data point in a time series (used by totalTokens / totalCost)."""

    timestamp: str
    sessionIDs: list[str] = []
    value: SingleValueData


class MultipleValuesData(BaseModel):
    """A count with an associated list of strings."""

    count: int
    items: list[str] = Field(default=[])


class MostActiveAgent(BaseModel):
    """The most active agent summary."""

    agentName: str
    activity: SingleValueData = SingleValueData(value=0.0, unit="PERCENTAGE")


class MonitorApplicationLevelData(BaseModel):
    """Response body for ``MonitorApplicationLevelData``."""

    traces: SingleValueData
    totalTokens: list[TimelineData] = []
    totalCost: list[TimelineData] = []
    sessionDuration: SingleValueData
    workflowEfficiency: SingleValueData
    answerGroundedness: SingleValueData
    answerRelevancy: SingleValueData
    overallTaskCompletion: SingleValueData
    toolUtilisationAccuracyScore: SingleValueData
    overallPerformanceScore: SingleValueData
    toxicity: SingleValueData
    errorCount: SingleValueData
    mostFrequentErrors: MultipleValuesData
    sessions: SingleValueData
    llmCalls: SingleValueData
    toolCalls: SingleValueData
    totalActionCount: SingleValueData
    totalConversationCount: SingleValueData
    graphDeterminism: SingleValueData
    graphDynamism: SingleValueData
    mostActiveAgent: MostActiveAgent


# ── Monitor By Application models ────────────────────────────────────────────


class MonitorTaskItem(BaseModel):
    """A single task within an agent in the monitor-by-application view."""

    id: str
    name: str
    status: str
    duration: float
    cost: SingleValueData


class MonitorAgentItem(BaseModel):
    """A single agent entry in the monitor-by-application view."""

    id: str
    name: str
    failures: int = 0
    recoveryRate: float = 100.0
    cost: SingleValueData
    costTokens: SingleValueData
    utilisation: SingleValueData
    activity: SingleValueData
    tasks: list[MonitorTaskItem] = []


class MonitorByApplicationResponse(BaseModel):
    """Response body for ``monitor_by_application``."""

    totalCost: float = 0.0
    avgDuration: float = 0.0
    duration: float = 0.0
    overrallTaskCompletion: float = 0.0
    overrallActionAdvancement: float = 0.0
    agents: list[MonitorAgentItem] = []


# ── Agent tools (Overview page) models ────────────────────────────────────────


class AgentToolItem(BaseModel):
    """A single tool used by an agent."""

    name: str
    description: Optional[str] = None


class ApplicationAgentTools(BaseModel):
    """An agent and the tools it uses, for a given application."""

    agent_id: str
    agent_name: str
    agent_description: Optional[str] = None
    tools: list[AgentToolItem] = []


class ApplicationAgentToolsResponse(BaseModel):
    """Response body for ``GET /applications/{application_id}/agent-tools``."""

    application_id: str
    agents: list[ApplicationAgentTools] = []


# ── Collect By Application models ─────────────────────────────────────────────


class CollectSessionItem(BaseModel):
    """A single session in the collect-by-application view."""

    sessionId: str
    timestamp: str
    agents: list[str] = []
    llms: list[str] = []
    tokens: int = 0
    status: str = "done"
    cost: float = 0.0
    duration: float = 0.0
    session_metrics: list[dict[str, Any]] = []
    # Optional stateful evaluation metric (e.g. trajectory_score)
    statefulEval: dict | None = None


class CollectByApplicationResponse(BaseModel):
    """Response body for ``collect_by_application``."""

    avgDuration: float = 0.0
    successRate: float = 100.0
    errorRate: float = 0.0
    sessionList: list[CollectSessionItem] = []


# ── Application General Charts models ─────────────────────────────────────────


class ApplicationGeneralChartsResponse(BaseModel):
    """Response body for ``application_general_charts``."""

    totalLLMInvocationDuration: list[TimelineData] = []
    totalAgentCost: list[TimelineData] = []
    overallTaskCompletion: list[TimelineData] = []
    averageAnswerRelevancy: list[TimelineData] = []
    successRate: list[TimelineData] = []


# ── Application Quality And Reasoning Charts models ───────────────────────────


class ApplicationQualityAndReasoningChartsResponse(BaseModel):
    """Response body for ``application_quality_and_reasoning_charts``."""

    overallTaskCompletion: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    toolUtilizationAccuracy: list[TimelineData] = []
    generalStructureAndStyle: list[TimelineData] = []
    answerCorrectness: list[TimelineData] = []
    answerRelevancy: list[TimelineData] = []
    answerGroundedness: list[TimelineData] = []
    answerCoherence: list[TimelineData] = []
    agentTonality: list[TimelineData] = []


# ── Application Reliability And Safety Charts models ──────────────────────────


class ApplicationReliabilityAndSafetyChartsResponse(BaseModel):
    """Response body for ``application_reliability_and_safety_charts``."""

    successRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    errorRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    recoveryRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    retryRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    agentFailureCount: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    agentRecoveryCount: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    agentRecoveryRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    agentAvailability: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    bias: list[TimelineData] = []
    toxicity: list[TimelineData] = []
    policyViolation: list[TimelineData] = []


# ── Application Cost Charts models ───────────────────────────────────────────


class ApplicationCostChartsResponse(BaseModel):
    """Response body for ``application_cost_charts``."""

    totalLLMCost: list[TimelineData] = []
    totalToolCost: list[TimelineData] = []
    averageLLMCost: list[TimelineData] = []
    averageToolCost: list[TimelineData] = []
    numberOfLLMCalls: list[TimelineData] = []
    numberOfToolCalls: list[TimelineData] = []


# ── Application Performance Charts models ─────────────────────────────────────


class ErrorItem(BaseModel):
    """A single error entry with its name and count."""

    name: str
    count: int


class ApplicationPerformanceChartsResponse(BaseModel):
    """Response body for ``application_performance_charts``."""

    agentErrorCount: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    agentLatencyPercentile90: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    agentLatencyPercentile95: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    agentRetrievalLatency: SingleValueData = SingleValueData(value=0, unit="SCALAR")
    averageLatency: list[TimelineData] = []
    agentThroughput: list[TimelineData] = []
    agentWorkflowEfficiency: list[TimelineData] = []
    averageLLMInvocationDuration: list[TimelineData] = []
    errorRateOverTime: list[TimelineData] = []
    errorsBreakdown: list[ErrorItem] = []


# ── Application Tools Charts models ──────────────────────────────────────────


class ToolDetail(BaseModel):
    """A single tool entry in the tools-charts response."""

    toolName: str
    utilization: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    errorRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    successRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    retryRate: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")
    utilizationAccuracyScore: SingleValueData = SingleValueData(
        value=0, unit="PERCENTAGE"
    )
    toolDuration: list[TimelineData] = []


class ApplicationToolsChartsResponse(BaseModel):
    """Response body for ``application_tools_charts``."""

    toolDetails: list[ToolDetail] = []


# ── Application Conversation Charts models ────────────────────────────────────


class ApplicationConversationChartsResponse(BaseModel):
    """Response body for ``application_conversation_charts``."""

    relevancy: list[TimelineData] = []
    completeness: list[TimelineData] = []
    roleAdherence: list[TimelineData] = []
    topicAdherence: list[TimelineData] = []
    contextPreservation: list[TimelineData] = []
    intentRecognitionAccuracy: list[TimelineData] = []
    workflowCohesionIndex: list[TimelineData] = []
    goalSuccessRate: list[TimelineData] = []


# ── Application LLM Charts models ────────────────────────────────────────────


class ApplicationLLMChartsResponse(BaseModel):
    """Response body for ``application_llm_charts``."""

    totalLLMCost: list[TimelineData] = []
    totalTokens: list[TimelineData] = []
    inputTokens: list[TimelineData] = []
    outputTokens: list[TimelineData] = []
    inferenceDuration: list[TimelineData] = []
    answerCorrectness: list[TimelineData] = []
    answerRelevancy: list[TimelineData] = []
    answerFaithfulness: list[TimelineData] = []
    coherence: list[TimelineData] = []
    tonality: list[TimelineData] = []
    generalStructureStyleMetric: list[TimelineData] = []
    llmErrorRate: list[TimelineData] = []
    llmSuccessRate: list[TimelineData] = []
    llmRecoveryRate: list[TimelineData] = []
    llmRetryRate: list[TimelineData] = []
    toxicity: list[TimelineData] = []
    bias: list[TimelineData] = []
    uncertaintyScore: list[TimelineData] = []
    piiDetection: list[TimelineData] = []
    policyViolation: list[TimelineData] = []


# ── StaticTopology models ───────────────────────────────────────────────


class NodeType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"


class TopologyNode(BaseModel):
    id: str
    type: NodeType
    name: str
    description: str = ""
    has_tools: bool = False


class TopologyEdge(BaseModel):
    source: str
    target: str


class StaticTopology(BaseModel):
    nodes: list[TopologyNode] = []
    edges: list[TopologyEdge] = []


class SemanticGroupNode(BaseModel):
    id: str
    group_name: str
    group_summary: str = ""
    n_sessions: int = 0
    medioid_session_id: str = ""
    children_nodes: list[str] = []
    session_ids: list[str] = []
    split_distance: float = 0.0
    overall_quality: float = 0.0
    overall_reliability: float = 0.0
    overall_performance: float = 0.0


class SemanticgroupsResponse(BaseModel):
    nodes: list[SemanticGroupNode] = []


class SemanticgroupNormalBehaviorItem(BaseModel):
    metadata: str
    centroid: float


class SemanticgroupNormalBehaviorResponse(BaseModel):
    reports: list[SemanticgroupNormalBehaviorItem] = []


class SemanticgroupConsistencyItem(BaseModel):
    metadata: str
    mean: float
    confidence_indicator: str


class SemanticgroupConsistencyResponse(BaseModel):
    reports: list[SemanticgroupConsistencyItem] = []


class SemanticgroupAnomalyItem(BaseModel):
    metadata: str
    outliers_values: list


class SemanticgroupAnomalyResponse(BaseModel):
    reports: list[SemanticgroupAnomalyItem] = []


class SemanticgroupDetailsResponse(BaseModel):
    children_nodes: list[str] = []
    group_name: str = ""
    group_summary: str = ""
    id: str = ""
    n_sessions: int = 0
    session_ids: list[str] = []


class ImpactAssementAgentItem(BaseModel):
    agent_name: str
    value: SingleValueData = SingleValueData(value=0, unit="PERCENTAGE")


class ImpactAssessmentMetric(BaseModel):
    metric_name: str
    agents: list[ImpactAssementAgentItem] = []


class ImpactAssessmentResponse(BaseModel):
    impact_report: list[ImpactAssessmentMetric] = []


# ── Timeline (Waterfall) models ───────────────────────────────────────────────


class WaterfallSpan(BaseModel):
    """A single span node in the waterfall timeline tree."""

    spanId: str
    duration: int = 0
    spanName: str = ""
    timestamp: str = ""
    startTime: str = ""
    endTime: str = ""
    icon: str = ""
    error: bool = False
    childrenSpans: list["WaterfallSpan"] = []


class WaterfallResponse(BaseModel):
    """Response body for ``timeline_by_id``."""

    spanId: str = "root"
    timestamp: str = ""
    startTime: str = ""
    spanName: str = "root"
    icon: str = "application"
    endTime: str = ""
    duration: int = 0
    error: bool = False
    Spans: list[WaterfallSpan] = []


# ── Timeline (Trajectory) models ───────────────────────────────────────────────


class TrajectoryResponse(BaseModel):
    """Response body for ``trajectory``."""

    info: str = ""


# ── Session endpoint models ──────────────────────────────────────────────────


class SessionSummaryItem(BaseModel):
    """A single session returned by ``GET /sessions``."""

    session_id: str
    timestamp: str


class SessionSummaryResponse(BaseModel):
    """Response body for ``GET /sessions``."""

    sessions: list[SessionSummaryItem]


class SpanMetadataItem(BaseModel):
    """Full span metadata returned by ``GET /sessions/spans``."""

    span_id: str
    session_id: str
    span_name: str
    span_type: str
    timestamp: str
    duration: int = 0
    status_code: str = ""
    parent_span_id: str = ""
    service_name: str = ""
    span_attributes: dict = {}
    links_trace_id: list[str] = Field(default_factory=list)
    links_span_id: list[str] = Field(default_factory=list)
    links_trace_state: list[str] = Field(default_factory=list)
    links_attributes: list[dict[str, Any]] = Field(default_factory=list)


class SessionSpansResponse(BaseModel):
    """Response body for ``GET /sessions/spans``."""

    spans: list[SpanMetadataItem]


# ── Execution Graph endpoint models ──────────────────────────────────────────────────


class ToolCallGraphNodeData(BaseModel):
    """Typed payload for tool-call execution graph node `data`."""

    transition_id: str
    level: str
    call_type: str
    tool_name: Optional[str] = None
    duration: float = 0.0
    edge_type: str = ""
    timestamp: float
    execution_id: Optional[str] = None
    span_id: Optional[str] = None
    input_params: Optional[Any] = None
    input: Optional[str] = None
    output: Optional[str] = None
    parent_agent_exec_id: Optional[str] = None
    parent_agent_name: Optional[str] = None


class LlmCallGraphNodeData(BaseModel):
    """Typed payload for LLM-call execution graph node `data`."""

    transition_id: str
    level: str
    call_type: str
    model_name: Optional[str] = None
    provider: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    temperature: Optional[float] = None
    finish_reason: Optional[str] = None
    duration: float = 0.0
    edge_type: str = ""
    timestamp: float
    execution_id: Optional[str] = None
    span_id: Optional[str] = None
    input: Optional[str] = None
    output: Optional[str] = None
    parent_agent_exec_id: Optional[str] = None
    parent_agent_name: Optional[str] = None


class GraphNode(BaseModel):
    """Node in the graph visualization"""

    id: str
    label: str
    type: str  # 'state', 'agent', 'llm', 'tool', etc.
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    """Edge in the graph visualization"""

    id: str
    source: str
    target: str
    label: Optional[str] = None
    type: str  # 'transition', 'contains', 'executes', etc.
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class GraphResponse(BaseModel):
    """Complete graph response"""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    session_id: str
    hierarchy_level: Optional[str] = None
    metadata: Dict[str, Any]


# ── Agent conversation endpoint models ───────────────────────────────────────


class AgentSubCallMessage(BaseModel):
    """A single LLM or tool call nested under the agent-level turn that made
    it, in the chronological order it actually happened."""

    transition_id: str
    execution_id: Optional[str] = None
    call_type: str  # "llm" | "tool"
    name: Optional[str] = None  # model name (llm) or tool name (tool)
    timestamp: float
    duration: float = 0.0
    input: Optional[str] = None
    output: Optional[str] = None


class AgentConversationMessage(BaseModel):
    """A single agent-level turn, used to render the Conversation tab."""

    transition_id: str
    agent_name: Optional[str] = None
    execution_id: Optional[str] = None
    timestamp: float
    duration: float = 0.0
    edge_type: str = ""
    input: Optional[str] = None
    output: Optional[str] = None
    calls: List[AgentSubCallMessage] = []


class AgentConversationResponse(BaseModel):
    """Response body for ``GET /sessions/{session_id}/conversation``."""

    session_id: str
    messages: List[AgentConversationMessage]
    metadata: Dict[str, Any]


# ── Latent space endpoint models ─────────────────────────────────────────────


class LatentSpaceNode(BaseModel):
    """Node in the latent space visualization"""

    id: str
    label: str
    x: float
    y: float
    type: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class LatentSpaceEdge(BaseModel):
    """Edge in the latent space visualization"""

    id: str
    source: str
    target: str
    label: Optional[str] = None
    type: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class LatentSpaceResponse(BaseModel):
    """Response for latent space visualization"""

    nodes: List[LatentSpaceNode]
    edges: List[LatentSpaceEdge]
    session_id: str
    metadata: Dict[str, Any]


# ── Metrics endpoint models ──────────────────────────────────────────────────


class MetricItem(BaseModel):
    """A single metric name/value pair."""

    name: str
    value: Optional[float] = None
    metric_id: Optional[str] = Field(
        None, description="unique identifier for the metric run"
    )
    source: Optional[str] = Field(None, description="Who calculated the metric")
    reasoning: Optional[Any] = Field(None, description="Explanation for the metric")
    error: Optional[str] = Field(
        None, description="Error message when the metric is unavailable or failed"
    )


class WriteMetricItem(BaseModel):
    """A single metric to write."""

    name: str = Field(..., description="Metric name (e.g. 'TokenCount')")
    value: Optional[float] = Field(None, description="Metric value")
    provider: str = Field("API", description="Provider / source of the metric")
    metric_id: Optional[str] = Field(
        None, description="unique identifier for the metric run"
    )
    source: Optional[str] = Field(None, description="Who calculated the metric")
    reasoning: Optional[Any] = Field(None, description="Explanation for the metric")


class SessionMetricsWriteRequest(BaseModel):
    """Request body for ``POST /metrics/sessions/{session_id}``."""

    metrics: list[WriteMetricItem] = Field(
        ..., description="Metrics to write to the session"
    )


class SpanMetricsWriteRequest(BaseModel):
    """Request body for ``POST /metrics/sessions/{session_id}/spans/{span_id}``."""

    metrics: list[WriteMetricItem] = Field(
        ..., description="Metrics to write to the span"
    )


class MetricsWriteResponse(BaseModel):
    """Response body for metric write operations."""

    written: int = Field(0, description="Number of metrics successfully written")
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )


class SessionMetricsResponse(BaseModel):
    """Response body for ``GET /metrics/sessions/{session_id}``."""

    session_id: str
    metrics: list[MetricItem] = []
    subgraph: Optional[dict] = None


class SpanMetricsResponse(BaseModel):
    """Response body for ``GET /metrics/sessions/{session_id}/spans/{span_id}``."""

    session_id: str
    span_id: str
    metrics: list[MetricItem] = []
    subgraph: Optional[dict] = None


# TODO could be merged with category model
class ApplicationMetricsTimeline(BaseModel):
    metric_name: str
    values: List[List[float]] = []


class ApplicationMetricsSummary(BaseModel):
    quality: list[ApplicationMetricsTimeline] = []
    reliability: list[MetricItem] = []
    performance: list[ApplicationMetricsTimeline] = []


# ── Category-level metrics models ────────────────────────────────────────────


class CategoryMetricValue(BaseModel):
    """A single metric value attached to a session."""

    session_id: str
    name: str
    value: Optional[float] = None
    timestamp: Optional[str] = None
    metric_id: Optional[str] = None
    source: Optional[str] = None
    reasoning: Optional[str] = None


class AggregatedMetric(BaseModel):
    """Aggregated result for a single metric name."""

    name: str
    operation: Optional[str] = Field(
        None, description="Aggregation applied: 'sum', 'average', or null (card-only)"
    )
    value: Optional[float] = Field(None, description="Result of the aggregation")
    count: int = 0


class CategoryMetricsResponse(BaseModel):
    """Response body for ``GET /metrics/{application_id}/{category}``."""

    application_id: str
    category: str
    metrics: list[CategoryMetricValue] = []
    aggregations: list[AggregatedMetric] = []


# ── Time-series metrics models ────────────────────────────────────────────────


class MetricTimePoint(BaseModel):
    """A single data point in a metric time-series."""

    bucket: str = Field(..., description="ISO-8601 timestamp of the bucket start")
    avg_value: float = Field(..., description="Average metric value in this bucket")
    min_value: float = Field(..., description="Minimum value in this bucket")
    max_value: float = Field(..., description="Maximum value in this bucket")
    n_sessions: int = Field(..., description="Number of sessions in this bucket")


class MetricTimeSeriesResponse(BaseModel):
    """Response body for ``GET /metrics/timeseries``."""

    metric_id: str
    bucket_size: str = Field(..., description="Bucket granularity: minute, hour, day")
    start: str
    end: Optional[str] = None
    points: list[MetricTimePoint] = []


# ── Concepts endpoint models ─────────────────────────────────────────────────


class ConceptItem(BaseModel):
    """A single concept / symbol for neurosymbolic analysis."""

    name: str
    type: str = ""
    properties: dict = {}


class ConceptsResponse(BaseModel):
    """Response body for ``GET /concepts/{app_id}``."""

    app_id: str
    concepts: list[ConceptItem] = []


class SpanConceptsResponse(BaseModel):
    """Response body for concepts scoped to a span."""

    app_id: str
    session_id: str
    span_id: str
    concepts: list[ConceptItem] = []


class WriteConceptItem(BaseModel):
    """A single concept to write."""

    name: str = Field(..., description="Concept name")
    type: str = Field("", description="Concept type / category")
    properties: dict = Field(
        default_factory=dict, description="Arbitrary extra properties"
    )


class ConceptsWriteRequest(BaseModel):
    """Request body for ``POST /concepts/{app_id}``."""

    concepts: list[WriteConceptItem] = Field(
        ..., description="Concepts to write to the application"
    )


class SpanConceptsWriteRequest(BaseModel):
    """Request body for ``POST /concepts/{app_id}/sessions/{session_id}/spans/{span_id}``."""

    concepts: list[WriteConceptItem] = Field(
        ..., description="Concepts to write to the span"
    )


class ConceptsWriteResponse(BaseModel):
    """Response body for concept write operations."""

    written: int = Field(0, description="Number of concepts successfully written")
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )


# ── Symbolic endpoint models ────────────────────────────────────────────────


class SymbolicModelSummary(BaseModel):
    """Metadata for an active symbolic model attached to an application."""

    modelId: str = Field(..., description="Stable symbolic model identifier")
    version: Optional[str] = Field(None, description="Human-readable model version")
    createdAt: Optional[str] = Field(None, description="Model creation timestamp")
    updatedAt: Optional[str] = Field(None, description="Model last update timestamp")
    isActive: bool = Field(False, description="Whether this symbolic model is active")
    modelName: Optional[str] = Field(
        None, description="LLM or generator used to produce the model"
    )
    taskDescription: Optional[str] = Field(
        None, description="Optional high-level task or domain description"
    )


class SymbolicModelWriteRequest(BaseModel):
    """Request body for ``POST /symbolic/applications/{application_id}/models``."""

    modelId: str = Field(..., description="Stable symbolic model identifier")
    version: Optional[str] = Field(None, description="Human-readable model version")
    createdAt: Optional[str] = Field(None, description="Model creation timestamp")
    updatedAt: Optional[str] = Field(None, description="Model update timestamp")
    isActive: bool = Field(
        True,
        description="Whether this model should be marked as active for the application",
    )
    modelName: Optional[str] = Field(
        None, description="LLM or generator used to produce the model"
    )
    taskDescription: Optional[str] = Field(
        None, description="Optional high-level task or domain description"
    )


class SymbolicModelResponse(BaseModel):
    """Response body for single symbolic model reads."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Resolved symbolic model"
    )


class SymbolicModelWriteResponse(BaseModel):
    """Response body for symbolic model upserts."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Persisted symbolic model after the write"
    )
    written: int = Field(
        0, description="Number of symbolic models successfully written"
    )
    errors: list[str] = Field(
        default_factory=list, description="Any write errors encountered"
    )


class SymbolicModelsResponse(BaseModel):
    """Response body for ``GET /symbolic/applications/{application_id}/models``."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    count: int = Field(0, description="Number of symbolic models returned")
    models: list[SymbolicModelSummary] = Field(
        default_factory=list, description="Symbolic models for the application"
    )


class SymbolicModelDeleteResponse(BaseModel):
    """Response body for ``DELETE /symbolic/applications/{application_id}/models/{model_id}``."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    model_id: str = Field(..., description="Deleted symbolic model identifier")
    deleted: bool = Field(False, description="Whether the symbolic model was deleted")


class SymbolicVariableItem(BaseModel):
    """A symbolic variable definition returned by the symbolic API."""

    variableId: Optional[str] = Field(
        None, description="Stable symbolic variable identifier"
    )
    name: str = Field(..., description="Variable name from the symbolic ontology")
    tier: Literal["process", "entity", "alignment"] = Field(
        ..., description="Variable tier within the symbolic ontology"
    )
    type: str = Field(..., description="Variable type such as boolean or categorical")
    description: str = Field("", description="Human-readable variable description")
    extractionQuestion: Optional[str] = Field(
        None, description="Question or instruction used to extract the variable"
    )
    discriminativeScore: Optional[float] = Field(
        None, description="Current discriminative power of the variable"
    )
    isEnabledForEvaluation: Optional[bool] = Field(
        None, description="Whether evaluation logic should consider this variable"
    )
    foundationMetric: Optional[
        Literal["IntentRecognition", "Groundedness", "Relevancy"]
    ] = Field(
        None,
        description="Stateful-eval foundational metric category for this variable",
    )
    status: Optional[str] = Field(None, description="Current variable status")
    createdAt: Optional[str] = Field(None, description="Variable creation timestamp")
    updatedAt: Optional[str] = Field(None, description="Variable last update timestamp")
    dependsOn: list[str] = Field(
        default_factory=list,
        description="Identifiers of variables this variable depends on",
    )


class SymbolicVariablesResponse(BaseModel):
    """Response body for ``GET /symbolic/applications/{application_id}/variables``."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Active symbolic model for the application"
    )
    count: int = Field(0, description="Number of returned symbolic variables")
    variables: list[SymbolicVariableItem] = Field(
        default_factory=list, description="Variable definitions in the active model"
    )


class SymbolicVariableWriteItem(BaseModel):
    """Variable definition payload for symbolic model upserts."""

    variableId: Optional[str] = Field(
        None, description="Stable symbolic variable identifier if already known"
    )
    name: str = Field(..., description="Variable name from the symbolic ontology")
    tier: Literal["process", "entity", "alignment"] = Field(
        ..., description="Variable tier within the symbolic ontology"
    )
    type: str = Field(..., description="Variable type such as boolean or categorical")
    description: str = Field("", description="Human-readable variable description")
    extractionQuestion: Optional[str] = Field(
        None, description="Question or instruction used to extract the variable"
    )
    discriminativeScore: Optional[float] = Field(
        None, description="Current discriminative power of the variable"
    )
    isEnabledForEvaluation: Optional[bool] = Field(
        None, description="Optional explicit evaluation enablement override"
    )
    foundationMetric: Optional[
        Literal["IntentRecognition", "Groundedness", "Relevancy"]
    ] = Field(
        None,
        description="Stateful-eval foundational metric category for this variable",
    )
    status: Optional[str] = Field(
        None, description="Optional variable lifecycle status"
    )


class SymbolicVariableDependencyItem(BaseModel):
    """A dependency edge between two symbolic variables."""

    variableId: str = Field(..., description="Dependent symbolic variable identifier")
    dependsOnVariableId: str = Field(
        ..., description="Identifier of the prerequisite symbolic variable"
    )


class SymbolicVariablesWriteRequest(BaseModel):
    """Request body for ``POST /symbolic/applications/{application_id}/variables``."""

    modelId: str = Field(..., description="Target symbolic model identifier")
    minDiscriminativeScore: Optional[float] = Field(
        None,
        description="Optional threshold used by the caller when selecting variables",
    )
    variables: list[SymbolicVariableWriteItem] = Field(
        ..., description="Variable definitions to add or update on the model"
    )
    dependencies: list[SymbolicVariableDependencyItem] = Field(
        default_factory=list,
        description="Dependency edges to persist among the submitted variables",
    )


class SymbolicVariablesWriteResponse(BaseModel):
    """Response body for symbolic variable upserts."""

    application_id: str = Field(
        ..., description="Application identifier from the route"
    )
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Resolved symbolic model after the write"
    )
    written: int = Field(0, description="Number of variables successfully written")
    count: int = Field(0, description="Number of persisted variables returned")
    variables: list[SymbolicVariableItem] = Field(
        default_factory=list,
        description="Persisted variables as the post-write source of truth",
    )
    errors: list[str] = Field(
        default_factory=list, description="Any write errors encountered"
    )


class SymbolicValueExecutionReference(BaseModel):
    """Execution provenance attached to a symbolic value event."""

    executionId: Optional[str] = Field(None, description="Execution element identifier")
    spanId: str = Field(..., description="Span identifier for the source execution")
    entityType: Optional[str] = Field(
        None, description="Concrete execution type such as ToolCall or LLMCall"
    )
    entityName: Optional[str] = Field(None, description="Execution display name")


class SymbolicStateExecutionReference(BaseModel):
    """Execution provenance attached to a final symbolic state entry."""

    executionId: Optional[str] = Field(None, description="Execution element identifier")
    spanId: str = Field(..., description="Span identifier for the source execution")
    entityName: Optional[str] = Field(None, description="Execution display name")
    executionLabels: list[str] = Field(
        default_factory=list,
        description="Neo4j labels or ontology labels attached to the execution node",
    )


class SymbolicValueItem(BaseModel):
    """A symbolic value event returned by read endpoints."""

    valueId: str = Field(..., description="Stable symbolic value event identifier")
    variableId: str = Field(..., description="Referenced symbolic variable identifier")
    variableName: Optional[str] = Field(
        None, description="Human-readable symbolic variable name"
    )
    tier: Literal["process", "entity", "alignment"] = Field(
        ..., description="Tier of the symbolic variable"
    )
    type: str = Field(..., description="Value type such as boolean or categorical")
    value: Any = Field(None, description="Assigned symbolic value")
    reason: Optional[str] = Field(None, description="Why the value was assigned")
    trajectoryIndex: int = Field(
        ..., ge=0, description="Position of the assignment in the session trajectory"
    )
    assignmentStrategy: Optional[str] = Field(
        None,
        description="Strategy used to assign the value, for example single_span or aggregate",
    )
    createdAt: Optional[str] = Field(None, description="Value write timestamp")
    execution: Optional[SymbolicValueExecutionReference] = Field(
        None, description="Execution provenance for this symbolic value"
    )


class SymbolicValueWriteItem(BaseModel):
    """A symbolic value change submitted for a session."""

    valueId: str = Field(..., description="Stable symbolic value event identifier")
    variableId: str = Field(..., description="Referenced symbolic variable identifier")
    tier: Literal["process", "entity", "alignment"] = Field(
        ..., description="Tier of the symbolic variable"
    )
    type: str = Field(..., description="Value type such as boolean or categorical")
    value: Any = Field(None, description="Assigned symbolic value")
    reason: Optional[str] = Field(None, description="Why the value was assigned")
    trajectoryIndex: int = Field(
        ..., ge=0, description="Position of the assignment in the session trajectory"
    )
    assignmentStrategy: Optional[str] = Field(
        None,
        description="Strategy used to assign the value, for example single_span or aggregate",
    )
    spanId: str = Field(..., description="Source execution span identifier")


class SymbolicSessionValuesWriteRequest(BaseModel):
    """Request body for ``POST /symbolic/sessions/{session_id}/values``."""

    modelId: str = Field(..., description="Target symbolic model identifier")
    values: list[SymbolicValueWriteItem] = Field(
        ..., description="Symbolic value changes to append to the session"
    )


class SymbolicSessionValuesWriteResponse(BaseModel):
    """Response body for symbolic value append operations."""

    session_id: str = Field(..., description="Session identifier from the route")
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Resolved symbolic model for the session"
    )
    written: int = Field(
        0, description="Number of symbolic values successfully written"
    )
    errors: list[str] = Field(
        default_factory=list, description="Any write errors encountered"
    )
    values: list[SymbolicValueItem] = Field(
        default_factory=list,
        description="Persisted symbolic values returned by the write operation",
    )


class SymbolicSessionValuesResponse(BaseModel):
    """Response body for ``GET /symbolic/sessions/{session_id}/values``."""

    session_id: str = Field(..., description="Session identifier from the route")
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Resolved symbolic model for the session"
    )
    count: int = Field(0, description="Number of symbolic values returned")
    values: list[SymbolicValueItem] = Field(
        default_factory=list,
        description="Symbolic values currently stored for the session",
    )


class SymbolicStateItem(BaseModel):
    """A single final-state entry returned for a session."""

    valueId: str = Field(..., description="Stable symbolic value event identifier")
    variableId: str = Field(..., description="Referenced symbolic variable identifier")
    tier: Literal["process", "entity", "alignment"] = Field(
        ..., description="Tier of the symbolic variable"
    )
    type: str = Field(..., description="Value type such as boolean or categorical")
    value: Any = Field(None, description="Final symbolic value for the variable")
    reason: Optional[str] = Field(None, description="Why the value was assigned")
    trajectoryIndex: int = Field(
        ..., ge=0, description="Position of the final assignment in the trajectory"
    )
    assignmentStrategy: Optional[str] = Field(
        None, description="Strategy used to derive the final value"
    )
    createdAt: Optional[str] = Field(None, description="Timestamp for the final value")
    execution: Optional[SymbolicStateExecutionReference] = Field(
        None, description="Execution provenance for the final value"
    )


class SymbolicSessionStateResponse(BaseModel):
    """Response body for ``GET /symbolic/sessions/{session_id}/state``."""

    session_id: str = Field(..., description="Session identifier from the route")
    symbolic_model: SymbolicModelSummary = Field(
        ..., description="Resolved symbolic model for the session"
    )
    count: int = Field(0, description="Number of variables present in the final state")
    state: list[SymbolicStateItem] = Field(
        default_factory=list,
        description="Final symbolic value for each variable assigned in the session",
    )


# ── Label models ─────────────────────────────────────────────────────────────


class LabelItem(BaseModel):
    """A single trace label."""

    session_id: str
    label: bool
    labeler: str
    reason: Optional[str] = None
    updated_at: Optional[str] = None


class LabelResponse(BaseModel):
    """Response body for ``GET /labels/{session_id}``."""

    session_id: str
    label: Optional[LabelItem] = None


class LabelPutRequest(BaseModel):
    """Request body for ``PUT /labels/{session_id}``."""

    label: bool
    labeler: str
    reason: Optional[str] = None


class LabelDeleteResponse(BaseModel):
    """Response body for ``DELETE /labels/{session_id}``."""

    session_id: str
    deleted: bool


# ── Metrics catalog models ────────────────────────────────────────────────────


class MetricCatalogItem(BaseModel):
    """Metadata for a single discoverable metric."""

    metric_id: str = Field(
        ..., description="Canonical metric identifier, e.g. 'Groundedness'"
    )
    id: str = Field("", description="Alias for metric_id (API compatibility)")
    name: str = Field("", description="Human-readable display name")
    provider: str = Field(..., description="Provider name, e.g. 'mce.providers.native'")
    scope: str = Field(
        ..., description="Attachment scope: 'session', 'span', or 'execution_element'"
    )
    target_types: list[str] = Field(
        default_factory=list, description="Node types this metric can be computed for"
    )
    description: Optional[str] = Field(
        None, description="Human-readable metric description"
    )
    unit: Optional[str] = Field(
        None, description="Measurement unit, e.g. 'tokens', 'percent'"
    )
    type: Optional[str] = Field(
        None, description="Metric type: 'gauge', 'counter', etc."
    )


class MetricCatalogResponse(BaseModel):
    """Response body for ``GET /metrics/catalog``."""

    total: int
    metrics: list[MetricCatalogItem]


class MetricInfoItemResponse(BaseModel):
    """Response body for ``GET /metrics/info?metric_id=<id>`` (single-metric detail)."""

    id: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[str] = None
    dimensions: list[str] = Field(
        default_factory=list, description="Applicable target types / dimensions"
    )


# ── Metrics compute models ────────────────────────────────────────────────────


class MetricsComputeRequest(BaseModel):
    """Request body for ``POST /metrics/compute``."""

    session_ids: list[str] = Field(
        ..., description="Session IDs to compute metrics for"
    )
    metric_id: Optional[str] = Field(
        None,
        description="Single metric ID to compute (convenience alias for metric_ids)",
    )
    metric_ids: Optional[list[str]] = Field(
        None, description="Subset of metrics to run. Omit for all."
    )
    recursive: bool = Field(
        False, description="If True, compute metrics for child spans too"
    )


class MetricsComputeResponse(BaseModel):
    """Response body for ``POST /metrics/compute``."""

    job_id: Optional[str] = Field(None, description="Job identifier")
    status: str = Field(
        "completed", description="Job status: 'completed', 'partial', or 'failed'"
    )
    message: str = Field("", description="Human-readable status message")
    total_sessions: int
    computed: int = Field(0, description="Number of sessions successfully processed")
    failed: int = Field(0, description="Number of sessions that failed")
    errors: list[str] = Field(default_factory=list)
    results: list[dict] = Field(
        default_factory=list, description="Computed metric results"
    )


# ── KG query_nodes ─────────────────────────────────────────────────────────────


class KGQueryRequest(BaseModel):
    """Request body for ``POST /kg/query``."""

    entity_type: str = Field(..., description="Node label, e.g. 'Session', 'LLMCall'")
    filters: Optional[dict] = Field(None, description="Exact-match property filters")
    where_clause: Optional[str] = Field(
        None, description="Raw Cypher WHERE clause (without 'WHERE')"
    )
    columns: Optional[list[str]] = Field(
        None, description="Properties to return (default: all)"
    )
    order_by: Optional[list[str]] = Field(
        None, description="Sort fields, prefix '-' for DESC"
    )
    limit: Optional[int] = Field(100, ge=1, le=10000)


class KGQueryResponse(BaseModel):
    """Response body for ``POST /kg/query``."""

    results: list[dict]
    total: int
