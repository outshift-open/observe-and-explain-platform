#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import random
from typing import Dict, List, Optional, Tuple

from openai import AsyncOpenAI, RateLimitError

from ..utils import setup_logger

logger = setup_logger(__name__)

LLM_GENERATION_ERROR = "Failed to generate"


class LLM:
    def __init__(
        self,
        llm_base_url: str = "https://api.openai.com/v1",
        llm_model_name: str = "gpt-4o",
        llm_api_key: Optional[str] = None,
        max_concurrent_requests: int = 10,
        max_retries: int = 5,
    ):
        self.llm_base_url: str = llm_base_url
        self.llm_model_name: str = llm_model_name
        self.llm_api_key: str = llm_api_key
        self.max_retries = max_retries
        self.semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent_requests)

        self.client = AsyncOpenAI(
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
        )

    async def generate_group_name(self, queries: List[str]) -> Tuple[str, str]:
        """
        Generates a common group name and summary from a list of queries
        using an LLM.
        """
        if not queries:
            return "", ""

        prompt_template = """
        From the list of json objects below containing metadata, find out what the
        common query they are sending is and respond ONLY with a JSON object in the
        format `{"display_name": "Short name", "summary": "Extracted query"}`, where
        the display name is composed of max 5 words describing the extracted query.
        Follow the format of the queries (e.g., if they are all questions, you should
        output a question).
        """
        queries_str = "\n".join([f"- {s}" for s in queries])
        full_prompt = f"{prompt_template}\n\n{queries_str}"

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant designed to output JSON.",
            },
            {"role": "user", "content": full_prompt},
        ]

        for attempt in range(self.max_retries):
            try:
                async with self.semaphore:
                    response = await self.client.chat.completions.create(
                        model=self.llm_model_name,
                        messages=messages,
                        response_format={"type": "json_object"},
                    )

                    content = response.choices[0].message.content
                    if not content:
                        logger.warning("LLM returned empty content.")
                        return LLM_GENERATION_ERROR, LLM_GENERATION_ERROR

                    # Clean markdown if present
                    if content.startswith("```json"):
                        content = content.strip("```json").strip("```").strip()

                    parsed_dict = json.loads(content)
                    group_name = parsed_dict.get("display_name", "")
                    group_summary = parsed_dict.get("summary", "")

                    return group_name, group_summary

            except RateLimitError as _:
                wait_time = (2**attempt) * 5 + random.uniform(0, 1)
                logger.warning(
                    f"Rate limit hit (429). Attempt {attempt + 1}/{self.max_retries}. Retrying in {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from LLM response: {content}")
                return LLM_GENERATION_ERROR, LLM_GENERATION_ERROR

            except Exception as e:
                logger.warning(f"An error occurred during LLM invocation: {e}")
                if "429" not in str(e):
                    break
                await asyncio.sleep(5)

        return LLM_GENERATION_ERROR, LLM_GENERATION_ERROR

    async def process_nodes_batch(
        self, tasks: List[Tuple[str, List[str]]]
    ) -> Dict[str, Tuple[str, str]]:
        """
        Takes a list of (node_id, queries) and processes them in parallel.
        Returns a mapping of node_id -> (name, summary).
        """
        node_ids = [t[0] for t in tasks]
        query_lists = [t[1] for t in tasks]

        coros = [self.generate_group_name(ql) for ql in query_lists]
        results = await asyncio.gather(*coros)

        return dict(zip(node_ids, results))
