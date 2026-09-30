#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Golden-data client — returns hardcoded reference responses.

``GoldenClient`` implements the same interface as ``LocalClient`` but
returns static, known-good data instead of querying a database.  This is
useful for:

* **Frontend development** — the API can serve realistic data without a DB.
* **Integration testing** — endpoints return deterministic responses.
* **Demos** — no infrastructure required.

Usage::

    from oxp.client.mock.client import GoldenClient

    client = GoldenClient()
    apps = client.get_applications()
"""

from __future__ import annotations

from oxp.client.base import OXPAPIClient
from oxp.models.otel_traces import (
    AgentDetailsItem,
    AgentDetailsResponse,
    ApplicationConversationChartsResponse,
    ApplicationCostChartsResponse,
    ApplicationGeneralChartsResponse,
    ApplicationItem,
    ApplicationLLMChartsResponse,
    ApplicationNameItem,
    ApplicationNamesResponse,
    ApplicationQualityAndReasoningChartsResponse,
    ApplicationReliabilityAndSafetyChartsResponse,
    ApplicationsResponse,
    ApplicationToolsChartsResponse,
    CollectByApplicationResponse,
    MonitorAgentItem,
    MonitorApplicationLevelData,
    MonitorByApplicationResponse,
    MonitorTaskItem,
    MostActiveAgent,
    MultipleValuesData,
    NodeType,
    SemanticgroupDetailsResponse,
    SemanticGroupNode,
    SemanticgroupNormalBehaviorResponse,
    SemanticgroupsResponse,
    SingleValueData,
    SpanAttribute,
    SpanDetailsItem,
    SpanDetailsResponse,
    StaticTopology,
    TimelineData,
    TopologyEdge,
    TopologyNode,
    WaterfallResponse,
    WaterfallSpan,
)

# ── Shared constants ─────────────────────────────────────────────────────────

_TIMESTAMPS = [
    "2026-01-12T10:09:21+00:00",
    "2026-01-12T12:54:21+00:00",
    "2026-01-12T15:39:21+00:00",
    "2026-01-12T18:24:21+00:00",
    "2026-01-12T21:09:21+00:00",
    "2026-01-12T23:54:21+00:00",
    "2026-01-13T02:39:21+00:00",
    "2026-01-13T05:24:21+00:00",
    "2026-01-13T08:09:21+00:00",
    "2026-01-13T10:54:21+00:00",
    "2026-01-13T13:39:21+00:00",
    "2026-01-13T16:24:21+00:00",
]

_SESSION_IDS_BUCKET_2 = [
    "70accc97-78db-46f8-9089-a8498f5f05c5",
    "25ca931a-965b-4c36-a119-255c7b091dbc",
    "175e4cdd-d996-4404-8543-d2dc77eb484f",
]

_SESSION_IDS_BUCKET_2_ALT = [
    "70accc97-78db-46f8-9089-a8498f5f05c5",
    "175e4cdd-d996-4404-8543-d2dc77eb484f",
    "25ca931a-965b-4c36-a119-255c7b091dbc",
]


def _timeline(unit: str, session_ids: list[str] | None = None) -> list[TimelineData]:
    """Build a 12-bucket timeline.  All sessionIDs are empty because the SQLite
    test dataset stores timestamps in short 'MM:SS.f' format which never matches
    ISO datetime range filters."""
    return [
        TimelineData(
            timestamp=ts,
            sessionIDs=[],
            value=SingleValueData(value=0.0, unit=unit),
        )
        for ts in _TIMESTAMPS
    ]


# ── GoldenClient ─────────────────────────────────────────────────────────────


class GoldenClient(OXPAPIClient):
    """Client that returns hardcoded golden data for every operation."""

    # ── lifecycle / common ────────────────────────────────────────────────

    def info(self, domain: str = "oxp") -> str:
        return f"Hello! This is the {domain.upper()} endpoint."

    # ── get_applications ──────────────────────────────────────────────────

    def get_applications(
        self,
        start_time: str = "",
        end_time: str = "",
    ) -> ApplicationsResponse:
        return ApplicationsResponse(
            applications=[
                ApplicationItem(
                    applicationName="App1",
                    version=1,
                    description="",
                    cost=1378.0,
                    costDollars=0.003445,
                    timestamp="33:02.8",
                    llms=["gpt-4o"],
                    agents=[],
                    overallPerformance=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                ApplicationItem(
                    applicationName="Hercule-Poirot",
                    version=1,
                    description="",
                    cost=2947.0,
                    costDollars=0.007367500000000001,
                    timestamp="30:45.3",
                    llms=["gpt-4o"],
                    agents=[],
                    overallPerformance=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                ApplicationItem(
                    applicationName="NOA",
                    version=1,
                    description=(
                        "Network of Assistants (NoA), a sample multi-agent multi-framework "
                        "application designed to orchestrate specialized AI assistants to "
                        "answer general queries. Think of it as an intelligent network of "
                        "AI minds working collaboratively to get the job done!"
                    ),
                    cost=20461.0,
                    costDollars=0.051152500000000004,
                    timestamp="00:30.8",
                    llms=["gpt-4o"],
                    agents=["noa-moderator", "noa-math-assistant"],
                    overallPerformance=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
            ]
        )

    # ── get_application_names ─────────────────────────────────────────────

    def get_application_names(
        self,
        start_time: str = "",
        end_time: str = "",
    ) -> ApplicationNamesResponse:
        return ApplicationNamesResponse(
            applications=[
                ApplicationNameItem(application_id="App1", start_time="33:02.8"),
                ApplicationNameItem(
                    application_id="Hercule-Poirot", start_time="11:14.6"
                ),
                ApplicationNameItem(application_id="NOA", start_time="00:22.5"),
            ]
        )

    # ── get_spans ─────────────────────────────────────────────────────────

    def get_spans(
        self,
        span_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SpanDetailsResponse:
        return SpanDetailsResponse(
            spanDetails=SpanDetailsItem(
                spanId="15ddf3bd7d0488b2",
                spanName="ChatOpenAI.chat",
                spanType="chat",
                exception="",
                attributes=[
                    SpanAttribute(key="gen_ai.prompt.0.role", value="system"),
                    SpanAttribute(
                        key="gen_ai.prompt.0.content",
                        value=(
                            "\nYou are able to reason based on text containing words and numbers.\n"
                            "You are able to perform simple arithmetic operations on the numbers\n"
                            "appearing in a text, in order to answer a certain question.\n"
                        ),
                    ),
                    SpanAttribute(key="gen_ai.completion.0.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.1.role", value="user"),
                    SpanAttribute(
                        key="gen_ai.prompt.1.content",
                        value=(
                            "\nYou are given the following piece of information: \n"
                            "1. https://www.ineos159challenge.com/news/history-is-made-as-eliud-kipchoge-becomes-first-human-to-break-the-two-hour-marathon-barrier/\n"
                            "2. https://en.wikipedia.org/wiki/Lunar_distance\n"
                            "3. https://www.calculator.net/speed-calculator.html\n"
                            "4. https://en.run-motion.com/eliud-kipchoge-analysis-of-his-marathon-performances/\n"
                            "5. https://spaceplace.nasa.gov/moon-distance/\n"
                            "I encountered a timeout error while trying to extract information from the websites. Please try again later or check the URLs for accessibility.\n"
                            "It seems that the documentation did not return any relevant passages for the queries about Eliud Kipchoge's marathon record pace and the minimum Earth-Moon distance perigee. You might want to refer to external sources such as Wikipedia or official marathon records for this information..\n"
                            "Answer the following question: In a scenario where Eliud Kipchoge runs non-stop at his marathon record pace, how many thousands of hours would it take to cover the minimum Earth-Moon distance? Find the minimum perigee on Wikipedia, round the result to the nearest 1000 hours, and avoid comma usage..\n"
                        ),
                    ),
                    SpanAttribute(key="gen_ai.prompt.2.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.3.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.4.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.5.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.6.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.7.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.8.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.9.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.10.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.11.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.12.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.13.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.14.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.15.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.16.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.17.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.18.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.19.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.20.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.21.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.22.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.23.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.24.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.25.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.26.role", value="tool"),
                    SpanAttribute(key="gen_ai.prompt.27.role", value="assistant"),
                    SpanAttribute(key="gen_ai.prompt.28.role", value="tool"),
                    SpanAttribute(key="Input Tokens", value="1886"),
                    SpanAttribute(key="Input Cost", value="0.004715$"),
                    SpanAttribute(key="Output Tokens", value="85"),
                    SpanAttribute(key="Output Cost", value="0.000213$"),
                    SpanAttribute(key="Total Tokens", value="1971"),
                    SpanAttribute(key="Total Cost", value="0.004928$"),
                ],
            )
        )

    # ── get_session_agent_details ─────────────────────────────────────────

    def get_session_agent_details(
        self,
        session_id: str,
        agent_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> AgentDetailsResponse:
        return AgentDetailsResponse(
            agentDetails=AgentDetailsItem(
                id="4d7b274d-8f3c-4ca5-bbcf-2ca3c319b91d",
                name="noa-web-surfer",
                description="A web surfer agent that can browse the web and answer questions using a multimodal LLM.",
                llms=[],
                inputTokens=SingleValueData(value=0.0, unit="SCALAR"),
                outputTokens=SingleValueData(value=0.0, unit="SCALAR"),
                inputCost=SingleValueData(value=0.0, unit="DOLLAR"),
                outputCost=SingleValueData(value=0.0, unit="DOLLAR"),
                attributes=[],
            )
        )

    # ── get_application_details ───────────────────────────────────────────

    def get_application_details(
        self,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> MonitorApplicationLevelData:
        return MonitorApplicationLevelData(
            traces=SingleValueData(value=0.0, unit="SCALAR"),
            totalTokens=_timeline("SCALAR"),
            totalCost=_timeline("DOLLAR"),
            sessionDuration=SingleValueData(value=0.0, unit="MILLISECONDS"),
            workflowEfficiency=SingleValueData(value=0.0, unit="PERCENTAGE"),
            answerGroundedness=SingleValueData(value=0.0, unit="PERCENTAGE"),
            answerRelevancy=SingleValueData(value=0.0, unit="PERCENTAGE"),
            overallTaskCompletion=SingleValueData(value=0.0, unit="PERCENTAGE"),
            toolUtilisationAccuracyScore=SingleValueData(value=0.0, unit="PERCENTAGE"),
            overallPerformanceScore=SingleValueData(value=0.0, unit="PERCENTAGE"),
            toxicity=SingleValueData(value=0.0, unit="PERCENTAGE"),
            errorCount=SingleValueData(value=0.0, unit="SCALAR"),
            mostFrequentErrors=MultipleValuesData(count=0, items=[]),
            sessions=SingleValueData(value=0.0, unit="SCALAR"),
            llmCalls=SingleValueData(value=0.0, unit="SCALAR"),
            toolCalls=SingleValueData(value=0.0, unit="SCALAR"),
            totalActionCount=SingleValueData(value=0.0, unit="SCALAR"),
            totalConversationCount=SingleValueData(value=0.0, unit="SCALAR"),
            graphDeterminism=SingleValueData(value=0.0, unit="PERCENTAGE"),
            graphDynamism=SingleValueData(value=0.0, unit="PERCENTAGE"),
            mostActiveAgent=MostActiveAgent(agentName=""),
        )

    # ── get_application_agents ────────────────────────────────────────────

    def get_application_agents(
        self,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> MonitorByApplicationResponse:
        return MonitorByApplicationResponse(
            agents=[
                MonitorAgentItem(
                    id="noa-moderator",
                    name="Noa Moderator",
                    failures=0,
                    recoveryRate=100.0,
                    cost=SingleValueData(value=0.0, unit="DOLLAR"),
                    costTokens=SingleValueData(value=0.0, unit="SCALAR"),
                    utilisation=SingleValueData(value=100.0, unit="PERCENTAGE"),
                    activity=SingleValueData(value=0.0, unit="PERCENTAGE"),
                    tasks=[
                        MonitorTaskItem(
                            id="noa-moderator",
                            name="noa-moderator",
                            status="done",
                            duration=0.0,
                            cost=SingleValueData(value=0.0, unit="DOLLAR"),
                        ),
                    ],
                ),
            ],
        )

    # ── get_application_sessions ──────────────────────────────────────────

    def get_application_sessions(
        self,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> CollectByApplicationResponse:
        return CollectByApplicationResponse(
            avgDuration=0.0,
            successRate=100.0,
            errorRate=0.0,
            sessionList=[],
        )

    # ── get_application_charts ────────────────────────────────────────────

    def get_application_charts(
        self,
        application_id: str,
        agent_id: str,
        chart_type: str,
        start_time: str = "",
        end_time: str = "",
    ):
        _DISPATCH = {
            "general": self._charts_general,
            "quality-and-reasoning": self._charts_quality_and_reasoning,
            "reliability-and-safety": self._charts_reliability_and_safety,
            "cost": self._charts_cost,
            "tools": self._charts_tools,
            "conversation": self._charts_conversation,
            "llm": self._charts_llm,
        }
        handler = _DISPATCH.get(chart_type)
        if handler is None:
            raise ValueError(f"Unknown chart_type: {chart_type!r}")
        return handler(
            application_id=application_id,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

    # ── _charts_general ────────────────────────────────────────────

    def _charts_general(self, **kw) -> ApplicationGeneralChartsResponse:
        return ApplicationGeneralChartsResponse(
            totalLLMInvocationDuration=[
                TimelineData(
                    timestamp="2026-01-12T10:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-12T12:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-12T15:39:21+00:00",
                    sessionIDs=_SESSION_IDS_BUCKET_2,
                    value=SingleValueData(value=23615.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-12T18:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-12T21:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-12T23:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T02:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T05:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T08:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T10:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T13:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
                TimelineData(
                    timestamp="2026-01-13T16:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="MILLISECONDS"),
                ),
            ],
            totalAgentCost=[
                TimelineData(
                    timestamp="2026-01-12T10:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-12T12:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-12T15:39:21+00:00",
                    sessionIDs=_SESSION_IDS_BUCKET_2,
                    value=SingleValueData(value=0.00685, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-12T18:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-12T21:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-12T23:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T02:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T05:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T08:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T10:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T13:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
                TimelineData(
                    timestamp="2026-01-13T16:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="DOLLAR"),
                ),
            ],
            overallTaskCompletion=[
                TimelineData(
                    timestamp="2026-01-12T10:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T12:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T15:39:21+00:00",
                    sessionIDs=_SESSION_IDS_BUCKET_2,
                    value=SingleValueData(value=100.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T18:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T21:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T23:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T02:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T05:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T08:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T10:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T13:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T16:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
            ],
            averageAnswerRelevancy=[
                TimelineData(
                    timestamp="2026-01-12T10:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T12:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T15:39:21+00:00",
                    sessionIDs=_SESSION_IDS_BUCKET_2,
                    value=SingleValueData(value=92.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T18:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T21:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T23:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T02:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T05:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T08:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T10:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T13:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T16:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
            ],
            successRate=[
                TimelineData(
                    timestamp="2026-01-12T10:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T12:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T15:39:21+00:00",
                    sessionIDs=_SESSION_IDS_BUCKET_2,
                    value=SingleValueData(value=100.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T18:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T21:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-12T23:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T02:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T05:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T08:09:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T10:54:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T13:39:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
                TimelineData(
                    timestamp="2026-01-13T16:24:21+00:00",
                    sessionIDs=[],
                    value=SingleValueData(value=0.0, unit="PERCENTAGE"),
                ),
            ],
        )

    def _charts_quality_and_reasoning(
        self, **kw
    ) -> ApplicationQualityAndReasoningChartsResponse:
        return ApplicationQualityAndReasoningChartsResponse(
            overallTaskCompletion=SingleValueData(value=0.0, unit="PERCENTAGE"),
            toolUtilizationAccuracy=_timeline("PERCENTAGE"),
            generalStructureAndStyle=_timeline("PERCENTAGE"),
            answerCorrectness=_timeline("PERCENTAGE"),
            answerRelevancy=_timeline("PERCENTAGE"),
            answerGroundedness=_timeline("PERCENTAGE"),
            answerCoherence=_timeline("PERCENTAGE"),
            agentTonality=_timeline("PERCENTAGE"),
        )

    def _charts_reliability_and_safety(
        self, **kw
    ) -> ApplicationReliabilityAndSafetyChartsResponse:
        return ApplicationReliabilityAndSafetyChartsResponse(
            successRate=SingleValueData(value=0.0, unit="PERCENTAGE"),
            errorRate=SingleValueData(value=0.0, unit="PERCENTAGE"),
            recoveryRate=SingleValueData(value=0.0, unit="PERCENTAGE"),
            retryRate=SingleValueData(value=0.0, unit="PERCENTAGE"),
            agentFailureCount=SingleValueData(value=0.0, unit="SCALAR"),
            agentRecoveryCount=SingleValueData(value=0.0, unit="SCALAR"),
            agentRecoveryRate=SingleValueData(value=0.0, unit="PERCENTAGE"),
            agentAvailability=SingleValueData(value=0.0, unit="PERCENTAGE"),
            bias=_timeline("PERCENTAGE"),
            toxicity=_timeline("PERCENTAGE"),
            policyViolation=_timeline("PERCENTAGE"),
        )

    def _charts_cost(self, **kw) -> ApplicationCostChartsResponse:
        return ApplicationCostChartsResponse(
            totalLLMCost=_timeline("DOLLAR"),
            totalToolCost=_timeline("DOLLAR"),
            averageLLMCost=_timeline("DOLLAR"),
            averageToolCost=_timeline("DOLLAR"),
            numberOfLLMCalls=_timeline("SCALAR"),
            numberOfToolCalls=_timeline("SCALAR"),
        )

    def _charts_tools(self, **kw) -> ApplicationToolsChartsResponse:
        return ApplicationToolsChartsResponse(toolDetails=[])

    def _charts_conversation(self, **kw) -> ApplicationConversationChartsResponse:
        return ApplicationConversationChartsResponse(
            relevancy=_timeline("PERCENTAGE"),
            completeness=_timeline("PERCENTAGE"),
            roleAdherence=_timeline("PERCENTAGE"),
            topicAdherence=_timeline("PERCENTAGE"),
            contextPreservation=_timeline("PERCENTAGE"),
            intentRecognitionAccuracy=_timeline("PERCENTAGE"),
            workflowCohesionIndex=_timeline("PERCENTAGE"),
            goalSuccessRate=_timeline("PERCENTAGE"),
        )

    def _charts_llm(self, **kw) -> ApplicationLLMChartsResponse:
        return ApplicationLLMChartsResponse(
            totalLLMCost=_timeline("DOLLAR"),
            totalTokens=_timeline("SCALAR"),
            inputTokens=_timeline("SCALAR"),
            outputTokens=_timeline("SCALAR"),
            inferenceDuration=_timeline("MILLISECONDS"),
            answerCorrectness=_timeline("PERCENTAGE"),
            answerRelevancy=_timeline("PERCENTAGE"),
            answerFaithfulness=_timeline("PERCENTAGE"),
            coherence=_timeline("PERCENTAGE"),
            tonality=_timeline("PERCENTAGE"),
            generalStructureStyleMetric=_timeline("PERCENTAGE"),
            llmErrorRate=_timeline("PERCENTAGE"),
            llmSuccessRate=_timeline("PERCENTAGE"),
            llmRecoveryRate=_timeline("PERCENTAGE"),
            llmRetryRate=_timeline("PERCENTAGE"),
            toxicity=_timeline("PERCENTAGE"),
            bias=_timeline("PERCENTAGE"),
            uncertaintyScore=_timeline("PERCENTAGE"),
            piiDetection=_timeline("PERCENTAGE"),
            policyViolation=_timeline("PERCENTAGE"),
        )

    # ── get_application_topology ──────────────────────────────────────────

    def get_application_topology(
        self,
        application_id: str,
    ) -> StaticTopology:
        if application_id == "NOA":
            return self._noa_topology()
        return StaticTopology(
            nodes=[
                TopologyNode(
                    id="007",
                    type=NodeType.AGENT,
                    name="EmptyTopology",
                    description="This is an empty topology.",
                ),
            ],
        )

    @staticmethod
    def _noa_topology() -> StaticTopology:
        nodes = [
            TopologyNode(
                id="moderator",
                type=NodeType.AGENT,
                name="ModeratorAgent",
                description="Central coordinator that routes questions to specialized agents and synthesizes final answers",
                has_tools=False,
            ),
            TopologyNode(
                id="schedule_agent",
                type=NodeType.AGENT,
                name="ScheduleAgent",
                description="Handles train/airplane timetables and city attraction information",
                has_tools=True,
            ),
            TopologyNode(
                id="itinerary_agent",
                type=NodeType.AGENT,
                name="ItineraryAgent",
                description="Handles route planning and travel time calculations using graph database",
                has_tools=True,
            ),
            TopologyNode(
                id="concierge_agent",
                type=NodeType.AGENT,
                name="ConciergeAgent",
                description="Handles train fares and pricing information",
                has_tools=True,
            ),
            TopologyNode(
                id="tool_schedule_list_documents",
                type=NodeType.TOOL,
                name="list_documents",
                description="Lists available documents in the schedule_agent data directory",
            ),
            TopologyNode(
                id="tool_schedule_read_document",
                type=NodeType.TOOL,
                name="read_document",
                description="Reads content from .txt files for schedule information",
            ),
            TopologyNode(
                id="tool_query_graph_database",
                type=NodeType.TOOL,
                name="query_graph_database",
                description="Loads city graph and returns all paths with travel times between cities",
            ),
            TopologyNode(
                id="tool_itinerary_calculate",
                type=NodeType.TOOL,
                name="calculate",
                description="Evaluates mathematical expressions for travel time calculations",
            ),
            TopologyNode(
                id="tool_concierge_list_documents",
                type=NodeType.TOOL,
                name="list_documents",
                description="Lists available documents in the concierge_agent data directory",
            ),
            TopologyNode(
                id="tool_concierge_read_document",
                type=NodeType.TOOL,
                name="read_document",
                description="Reads content from .txt files for fare information",
            ),
            TopologyNode(
                id="tool_concierge_calculate",
                type=NodeType.TOOL,
                name="calculate",
                description="Evaluates mathematical expressions for fare calculations",
            ),
        ]
        edges = [
            TopologyEdge(source="moderator", target="schedule_agent"),
            TopologyEdge(source="moderator", target="itinerary_agent"),
            TopologyEdge(source="moderator", target="concierge_agent"),
            TopologyEdge(source="schedule_agent", target="moderator"),
            TopologyEdge(source="itinerary_agent", target="moderator"),
            TopologyEdge(source="concierge_agent", target="moderator"),
            TopologyEdge(
                source="schedule_agent", target="tool_schedule_list_documents"
            ),
            TopologyEdge(source="schedule_agent", target="tool_schedule_read_document"),
            TopologyEdge(source="itinerary_agent", target="tool_query_graph_database"),
            TopologyEdge(source="itinerary_agent", target="tool_itinerary_calculate"),
            TopologyEdge(
                source="concierge_agent", target="tool_concierge_list_documents"
            ),
            TopologyEdge(
                source="concierge_agent", target="tool_concierge_read_document"
            ),
            TopologyEdge(source="concierge_agent", target="tool_concierge_calculate"),
        ]
        return StaticTopology(nodes=nodes, edges=edges)

    # ── get_application_semanticgroups_table ──────────────────────────────────────────

    def get_application_semanticgroups_table(
        self,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupsResponse:
        if application_id == "NOA":
            return self._noa_semanticgroups_table()
        return SemanticgroupsResponse(nodes=[])

    @staticmethod
    def _noa_semanticgroups_table() -> SemanticgroupsResponse:
        nodes = [
            SemanticGroupNode(
                id="sg_321",
                name="Leaf node",
                summary="Leaf node summary",
                n_sessions=2,
                medioid_session_id="session_124",
                children_nodes=[],
                session_ids=["session_124", "session_125"],
                split_distance=0.123,
            ),
        ]
        return SemanticgroupsResponse(nodes=nodes)

    # ── get_application_semanticgroups ──────────────────────────────────────────

    def get_application_semanticgroups(
        self,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupsResponse:
        if application_id == "NOA":
            return self._noa_semanticgroups()
        return SemanticgroupsResponse(nodes=[])

    @staticmethod
    def _noa_semanticgroups() -> SemanticgroupsResponse:
        nodes = [
            SemanticGroupNode(
                id="sg_123",
                name="Internal node",
                summary="Internal node summary",
                n_sessions=5,
                medioid_session_id="",
                children_nodes=["sg_124", "sg_125"],
                session_ids=[],
                split_distance=0.321,
            ),
            SemanticGroupNode(
                id="sg_321",
                name="Leaf node",
                summary="Leaf node summary",
                n_sessions=2,
                medioid_session_id="session_124",
                children_nodes=[],
                session_ids=["session_124", "session_125"],
                split_distance=0.123,
            ),
        ]
        return SemanticgroupsResponse(nodes=nodes)

    # ── get_semanticgroup_normal_behavior ──────────────────────────────────────────

    def get_semanticgroup_normal_behavior(
        self,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupNormalBehaviorResponse:
        if semanticgroup_id == "sg_123":
            return self._noa_semanticgroup_normal_behavior()
        return SemanticgroupNormalBehaviorResponse(info="")

    @staticmethod
    def _noa_semanticgroup_normal_behavior() -> SemanticgroupNormalBehaviorResponse:
        return SemanticgroupNormalBehaviorResponse(
            info="Example info for normal behavior"
        )

    # ── get_semanticgroup_details ──────────────────────────────────────────

    def get_semanticgroup_details(
        self,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupDetailsResponse:
        if semanticgroup_id == "sg_123":
            return self._noa_semanticgroup_details()
        return SemanticgroupDetailsResponse(info="")

    @staticmethod
    def _noa_semanticgroup_details() -> SemanticgroupDetailsResponse:
        return SemanticgroupDetailsResponse(info="Example info for details")

    # ── _get_session_timeline ────────────────────────────────────────

    def _get_session_timeline(
        self,
        session_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> WaterfallResponse:
        return WaterfallResponse(
            spanId="root",
            timestamp="2026-01-12T18:09:21.687014",
            startTime="2026-01-12T18:09:21.687014",
            spanName="root",
            icon="application",
            endTime="2026-01-12T18:09:21.691014",
            duration=4,
            error=False,
            Spans=[
                WaterfallSpan(
                    spanId="ec9cbfdf050f8358",
                    duration=4,
                    spanName="noa-flow.graph",
                    timestamp="2026-01-12T18:09:21.687014",
                    startTime="2026-01-12T18:09:21.687014",
                    endTime="2026-01-12T18:09:21.691014",
                    icon="agent",
                    error=False,
                    childrenSpans=[],
                ),
            ],
        )
