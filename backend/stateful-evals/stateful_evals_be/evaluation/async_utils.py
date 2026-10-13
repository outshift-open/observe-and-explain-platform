# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""One async HTTP client per evaluation, plus synchronous API compatibility."""

import asyncio
import inspect
from contextlib import asynccontextmanager
from contextvars import ContextVar

import litellm
from metrics_computation_engine.llm_judge.llm import LLMClient
from openai import AsyncOpenAI

_transports = ContextVar("evaluation_transports", default=None)


def supports_async(client):
    return type(client) is LLMClient or callable(getattr(client, "aquery", None))


@asynccontextmanager
async def model_query_scope(client):
    if _transports.get() is not None:
        yield
        return
    transports = {}
    token = _transports.set(transports)
    try:
        yield
    finally:
        await asyncio.gather(*(transport.close() for transport in transports.values()))
        _transports.reset(token)


async def query(client, messages, **kwargs):
    if callable(getattr(client, "aquery", None)):
        response = client.aquery(messages, **kwargs)
        return await response if inspect.isawaitable(response) else response
    if type(client) is not LLMClient:
        return client.query(messages, **kwargs)
    if client.custom_llm_provider != "openai":
        return await litellm.acompletion(
            model=client.model, api_base=client.api_base, api_version=client.api_version,
            api_key=client.api_key, messages=list(messages),
            custom_llm_provider=client.custom_llm_provider, num_retries=client.num_retries,
            **kwargs,
        )
    if _transports.get() is None:
        async with model_query_scope(client):
            return await query(client, messages, **kwargs)
    transports = _transports.get()
    if id(client) not in transports:
        # Construction has no await, so concurrent calls share this client.
        transports[id(client)] = AsyncOpenAI(api_key=client.api_key,
                                            base_url=client.api_base or None,
                                            max_retries=client.num_retries)
    kwargs.pop("allowed_openai_params", None)
    return await transports[id(client)].chat.completions.create(
        model=client.model, messages=list(messages), **kwargs,
    )


def run_sync(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RuntimeError("Await the async evaluation API inside an active event loop.")
