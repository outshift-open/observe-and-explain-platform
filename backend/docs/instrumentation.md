# Instrument your multi-agent application

OXP analyzes OpenTelemetry traces from a multi-agent system (MAS). Instrument the **application that runs your agents** with the [AGNTCY Observe SDK](https://github.com/agntcy/observe); OXP does not need to be installed in the agent application. The SDK sends telemetry to an OTLP/HTTP collector, which stores the spans for OXP to process.

## Get started

1. Make an OpenTelemetry collector with an OTLP/HTTP receiver available to your application. Configure it to export traces to the ClickHouse instance used by your OXP deployment. The [Observe deployment example](https://github.com/agntcy/observe/tree/main/deploy) provides a local collector and ClickHouse setup. `localhost` in the example below means the host **running your application**; use a reachable collector address when running in a container or on another machine.
2. Install the SDK in your application's Python environment:

    ```bash
    pip install ioa_observe_sdk
    export OTLP_HTTP_ENDPOINT=http://localhost:4318
    ```

3. Initialize Observe once at startup, decorate the agent and tool functions you want to see, and start a session at the entry point for each MAS execution:

    ```python
    import os

    from ioa_observe.sdk import Observe
    from ioa_observe.sdk.decorators import agent, tool, workflow
    from ioa_observe.sdk.tracing import session_start

    Observe.init("my_mas", api_endpoint=os.environ["OTLP_HTTP_ENDPOINT"])

    @tool(name="lookup")
    def lookup(query: str) -> str:
        return search_documents(query)

    @agent(name="assistant")
    def assistant(question: str) -> str:
        context = lookup(question)
        return answer_question(question, context)

    @workflow(name="answer_question")
    def run(question: str) -> str:
        return assistant(question)

    def handle_request(question: str) -> str:
        with session_start():
            return run(question)
    ```

    Replace `search_documents` and `answer_question` with your application's functions. The PyPI package is named `ioa_observe_sdk`, while its Python imports use `ioa_observe`. Keep `session_start()` at the execution entry point, not inside each agent, so related work belongs to one session.

4. Run a request through your application and confirm that spans arrive in the collector and in ClickHouse's `otel_traces` table. Then arrange for your OXP deployment to trigger ingestion **after the session completes**. Exporting spans alone does not enqueue `new_session_in`; the [ingestion pipeline](architecture/pipelines.md) starts when that queue receives a session notification. Check your deployment's session-completion/queue integration if traces are stored but no OXP session appears.

## Choosing what to instrument

Use `@workflow` for the top-level execution, `@agent` for agent work, and `@tool` for tool calls. For graph topology, use `@graph` as described in the [Observe Getting Started guide](https://github.com/agntcy/observe/blob/main/GETTING-STARTED.md), which also covers LangGraph, LlamaIndex, and distributed agent communication. The SDK supports automatic instrumentation for several LLM frameworks; for unsupported providers or additional operations, see [custom spans](https://github.com/agntcy/observe/blob/main/CUSTOM_SPANS.md).

Avoid attaching secrets or sensitive prompt/response data to span attributes unless your telemetry retention and access policies permit it. For the OXP side of the flow, see the [architecture overview](architecture/overview.md) and [norm](components/norm.md), which maps stored OpenTelemetry spans into the knowledge graph.