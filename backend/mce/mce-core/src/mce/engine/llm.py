#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import json
import hashlib
import threading
from datetime import datetime
from typing import Any
from pathlib import Path

# Try to import openai, handle if missing
try:
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None


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
        """
        Execute completion for a prompt.
        """
        # Determine model: explicit arg → instance default → hardcoded default
        if model is None:
            model = self._default_model or "gpt-4o"

        key = self._hash_prompt(prompt, model)

        # REPLAY MODE: Strict cache lookup — a miss is a test configuration error.
        if self.mode == "replay":
            if key in self.cache:
                return self.cache[key]["output"]
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

            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
            except Exception as e:
                raise RuntimeError(f"LLM call failed: {e}") from e
            content = response.choices[0].message.content or ""

            if self.mode == "record":
                self.cache[key] = {
                    "prompt": prompt,
                    "output": content,
                    "model": model,
                    "timestamp": datetime.now().isoformat(),
                    "params": kwargs,
                }
                self._save_cache()

            return content
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

    # No-op stubs — keep interface compatible with code that calls these.
    def _load_cache(self) -> None:  # pragma: no cover
        pass

    def _save_cache(self) -> None:  # pragma: no cover
        pass
