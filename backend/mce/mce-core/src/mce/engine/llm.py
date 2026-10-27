#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import json
import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from pathlib import Path

from mce.engine.usage import record_usage

# Try to import openai, handle if missing
try:
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None


@dataclass
class CompletionResult:
    """One LLM completion with the usage and (optionally) token log-probabilities.

    ``logprobs`` is a list of ``{"token", "logprob", "top": [{"token",
    "logprob"}, ...]}`` entries, one per generated token, when requested and
    supported by the endpoint; otherwise ``None``.
    """

    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    logprobs: list[dict[str, Any]] | None = field(default=None, repr=False)


# Sampling options some OpenAI-compatible endpoints reject. When a call that
# used them fails it is retried once without them, and they are then left out
# of every later call on that service.
_OPTIONAL_PARAMS = ("logprobs", "top_logprobs", "temperature")


def _logprobs_from_response(response: Any) -> list[dict[str, Any]] | None:
    choice_logprobs = getattr(response.choices[0], "logprobs", None)
    content = getattr(choice_logprobs, "content", None) if choice_logprobs else None
    if not content:
        return None
    return [
        {
            "token": item.token,
            "logprob": item.logprob,
            "top": [
                {"token": top.token, "logprob": top.logprob}
                for top in (item.top_logprobs or [])
            ],
        }
        for item in content
    ]


class LLMService:
    """
    Centralized Service for LLM interactions.
    Handles:
    1. Provider abstraction (via LiteLLM)
    2. Caching/Recording for deterministic testing
    3. Configuration (Model selection, API keys)
    4. Error handling & Retries
    """

    _instance = None
    _lock = threading.Lock()  # Guards singleton creation

    def __init__(
        self,
        mode: str = "live",
        cache_path: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """
        Args:
            mode: 'live' (call API), 'replay' (use cache only), 'record' (call API + save)
            cache_path: Path to JSON cache file
            api_key: Explicit OpenAI API key
            model: Explicit default LLM model identifier
            base_url: Explicit OpenAI-compatible base URL
        """
        self.mode = mode
        self.cache_path = Path(cache_path) if cache_path else Path("llm_cache.json")
        self.cache: dict[str, Any] = {}
        self._api_key = api_key
        self._default_model = model
        self._base_url = base_url

        # Load cache if needed
        if self.mode in ["replay", "record"]:
            self._load_cache()

        # Client created lazily in _get_client() on first live/record call
        # to avoid requiring OPENAI_API_KEY at configure() time.
        self._client: Any | None = None
        self._client_lock = threading.Lock()  # Guards lazy client creation
        self._dropped_params: set[str] = set()  # optional params the endpoint rejects

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = LLMService(mode="live", cache_path="llm_cache.json")
        return cls._instance

    @classmethod
    def configure(
        cls,
        mode: str,
        cache_path: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        with cls._lock:
            cls._instance = LLMService(
                mode=mode,
                cache_path=cache_path,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

    def _get_client(self) -> Any:
        """Return the cached OpenAI client, creating it lazily on first call."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:  # double-checked locking
                    if _OpenAI is None:
                        raise RuntimeError(
                            "openai package is not installed. Run: pip install openai"
                        )
                    self._client = _OpenAI(
                        api_key=self._api_key,
                        base_url=self._base_url,
                    )
        return self._client

    def _load_cache(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r") as f:
                    self.cache = json.load(f)
            except json.JSONDecodeError:
                self.cache = {}

    def _save_cache(self):
        # Ensure dir exists
        if self.cache_path.parent:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self.cache, f, indent=2)

    def _hash_prompt(self, prompt: str, model: str) -> str:
        # Create a deterministic key based on prompt and model
        content = f"{model}:{prompt}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_completion(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        """Execute a completion and return its text (see :meth:`complete`)."""
        return self.complete(prompt, model, system_prompt, **kwargs).text

    def complete(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        *,
        sample: int = 0,
        **kwargs,
    ) -> CompletionResult:
        """Execute a completion; adds its token usage to the current usage scope.

        ``sample`` distinguishes repeated calls with the same prompt (for
        example when averaging several judge samples) in the record/replay
        cache. Extra keyword arguments (``temperature``, ``logprobs``, ...)
        are passed to the chat completions API.
        """
        # Determine model: explicit arg → instance default → hardcoded default
        if model is None:
            model = self._default_model or "gpt-4o"

        key = self._hash_prompt(prompt, model)
        if sample:
            key = f"{key}:{sample}"

        # REPLAY MODE: Strict cache lookup — a miss is a test configuration error.
        if self.mode == "replay":
            if key in self.cache:
                entry = self.cache[key]
                usage = entry.get("usage") or {}
                result = CompletionResult(
                    text=entry["output"],
                    model=entry.get("model", model),
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    logprobs=entry.get("logprobs"),
                )
                record_usage(
                    result.model, result.prompt_tokens, result.completion_tokens
                )
                return result
            raise KeyError(
                f"Replay cache miss for model='{model}'. "
                "Record the interaction first (mode='record') or add the entry manually."
            )

        # LIVE/RECORD MODE — _get_client() lazy-creates and caches the connection.
        client = self._get_client()

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs = {k: v for k, v in kwargs.items() if k not in self._dropped_params}
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
            except Exception as e:
                optional = [p for p in _OPTIONAL_PARAMS if p in kwargs]
                if not optional:
                    raise RuntimeError(f"LLM call failed: {e}") from e
                self._dropped_params.update(optional)
                kwargs = {k: v for k, v in kwargs.items() if k not in optional}
                try:
                    response = client.chat.completions.create(
                        model=model, messages=messages, **kwargs
                    )
                except Exception as retry_error:
                    raise RuntimeError(f"LLM call failed: {retry_error}") from e
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            result = CompletionResult(
                text=content,
                model=model,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                logprobs=_logprobs_from_response(response),
            )
            record_usage(model, result.prompt_tokens, result.completion_tokens)

            if self.mode == "record":
                self.cache[key] = {
                    "prompt": prompt,
                    "output": content,
                    "model": model,
                    "timestamp": datetime.now().isoformat(),
                    "params": kwargs,
                    "usage": {
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                    },
                    "logprobs": result.logprobs,
                }
                self._save_cache()

            return result
        except Exception as e:
            raise RuntimeError(f"LLM call failed (model={model!r}): {e}") from e


class ErrorLLMService:
    """
    LLMService drop-in that raises immediately on any call to ``get_completion``.

    Install as the default singleton in tests to detect unexpected live LLM
    calls.  Any code path that reaches the LLM without an explicit replay /
    record configuration will fail with a clear ``RuntimeError`` rather than
    silently returning a mock string or spending API credits.

    Usage in tests::

        from mce.engine.llm import LLMService, ErrorLLMService
        LLMService._instance = ErrorLLMService()

    Tests that need LLM evaluation must opt in explicitly by configuring the
    LLMService in replay mode (e.g. via ``--llm-mode replay`` passed to the
    CLI), which replaces the singleton for the duration of that invocation.
    The autouse fixture in ``tests/conftest.py`` restores ``ErrorLLMService``
    after every test, so the guard is always active by default.
    """

    # Minimal stub attributes so duck-typed code that reads ``mode`` or
    # ``cache_path`` on the service instance does not raise AttributeError.
    mode: str = "error"
    cache_path: str | None = None

    def __init__(self) -> None:
        self.cache: dict = {}  # instance-level — never shared across instances

    def get_completion(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        raise RuntimeError(
            "Unexpected live LLM call intercepted by ErrorLLMService. "
            "Tests must not reach the LLM without explicit replay configuration. "
            "If this test needs LLM evaluation, pass --llm-mode replay with a "
            "pre-populated cache file."
        )

    def complete(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> CompletionResult:
        self.get_completion(prompt, model, system_prompt, **kwargs)
        raise AssertionError("unreachable")  # pragma: no cover

    # No-op stubs — keep interface compatible with code that calls these.
    def _load_cache(self) -> None:  # pragma: no cover
        pass

    def _save_cache(self) -> None:  # pragma: no cover
        pass
