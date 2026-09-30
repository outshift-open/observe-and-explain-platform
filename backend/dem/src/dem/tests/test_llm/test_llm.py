#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice, CompletionUsage


# Fixture to mock the logger instance directly.
@pytest.fixture(autouse=True, scope="function")
def mock_module_logger():
    # Create a mock logger instance
    mock_logger_instance = MagicMock()

    with patch("dem.llm.llm.logger", new=mock_logger_instance) as mock_logger:
        yield mock_logger  # Yield the mock logger instance for assertions


# Fixture to mock the OpenAI client and its chat completions create method
@pytest.fixture(scope="function")
def mock_openai_client_create_fixture():
    with patch("dem.llm.llm.AsyncOpenAI") as mock_openai_class:
        mock_client_instance = MagicMock()
        mock_openai_class.return_value = mock_client_instance

        # Mock the chat.completions.create method with AsyncMock to handle async calls
        mock_create_method = AsyncMock()
        mock_client_instance.chat.completions.create = mock_create_method

        yield mock_openai_class, mock_create_method


class TestLLM:
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL_NAME = "gpt-4o"
    DEFAULT_API_KEY = "test-api-key"

    # Fixture to import LLM class.
    @pytest.fixture(scope="class")
    def llm_class_fixture(self):
        from dem.llm import LLM

        return LLM

    def test_llm_init(self, llm_class_fixture, mock_openai_client_create_fixture):
        """
        Test that the LLM class initializes correctly and sets up the OpenAI client.
        """
        mock_openai_class, _ = mock_openai_client_create_fixture

        llm = llm_class_fixture(
            llm_base_url=self.DEFAULT_BASE_URL,
            llm_model_name=self.DEFAULT_MODEL_NAME,
            llm_api_key=self.DEFAULT_API_KEY,
        )

        assert llm.llm_base_url == self.DEFAULT_BASE_URL
        assert llm.llm_model_name == self.DEFAULT_MODEL_NAME
        assert llm.llm_api_key == self.DEFAULT_API_KEY

        mock_openai_class.assert_called_once_with(
            base_url=self.DEFAULT_BASE_URL,
            api_key=self.DEFAULT_API_KEY,
        )
        assert llm.client is mock_openai_class.return_value

    def test_generate_group_name_empty_queries(
        self, llm_class_fixture, mock_openai_client_create_fixture
    ):
        """
        Test generate_group_name with an empty list of queries.
        Should return empty strings and not call the OpenAI API.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        display_name, summary = asyncio.run(llm.generate_group_name(queries=[]))

        assert display_name == ""
        assert summary == ""
        mock_create_method.assert_not_called()

    def test_generate_group_name_success(
        self, llm_class_fixture, mock_openai_client_create_fixture
    ):
        """
        Test generate_group_name with valid queries and a successful LLM response.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        mock_response_content = json.dumps(
            {
                "display_name": "Test Group Name",
                "summary": "This is a test summary of queries.",
            }
        )

        mock_chat_completion = ChatCompletion(
            id="chatcmpl-test",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant", content=mock_response_content
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )
        mock_create_method.return_value = mock_chat_completion

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        queries = ["query1", "query2", "query3"]
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))

        assert display_name == "Test Group Name"
        assert summary == "This is a test summary of queries."

        mock_create_method.assert_called_once()
        args, kwargs = mock_create_method.call_args
        assert kwargs["model"] == self.DEFAULT_MODEL_NAME
        assert kwargs["response_format"] == {"type": "json_object"}
        assert "From the list of json objects below" in kwargs["messages"][1]["content"]
        assert "- query1" in kwargs["messages"][1]["content"]

    def test_generate_group_name_invalid_json_response(
        self, llm_class_fixture, mock_openai_client_create_fixture, mock_module_logger
    ):
        """
        Test generate_group_name when the LLM returns content that is not valid JSON.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        mock_response_content = "This is not valid JSON"
        mock_chat_completion = ChatCompletion(
            id="chatcmpl-test",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant", content=mock_response_content
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )
        mock_create_method.return_value = mock_chat_completion

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        queries = ["query1"]
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))

        assert display_name == "Failed to generate"
        assert summary == "Failed to generate"

        mock_module_logger.warning.assert_called_once()
        args, _ = mock_module_logger.warning.call_args
        assert "Failed to parse JSON from LLM response" in args[0]
        assert mock_response_content in args[0]

    def test_generate_group_name_empty_llm_content(
        self, llm_class_fixture, mock_openai_client_create_fixture, mock_module_logger
    ):
        """
        Test generate_group_name when the LLM returns empty content.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        mock_response_content = ""
        mock_chat_completion = ChatCompletion(
            id="chatcmpl-test",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant", content=mock_response_content
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )
        mock_create_method.return_value = mock_chat_completion

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        queries = ["query1"]
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))

        assert display_name == "Failed to generate"
        assert summary == "Failed to generate"
        mock_module_logger.warning.assert_called_once_with(
            "LLM returned empty content."
        )

    def test_generate_group_name_llm_api_exception(
        self, llm_class_fixture, mock_openai_client_create_fixture, mock_module_logger
    ):
        """
        Test generate_group_name when the OpenAI API call raises an exception.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        mock_create_method.side_effect = Exception("OpenAI API error")

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        queries = ["query1"]
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))

        assert display_name == "Failed to generate"
        assert summary == "Failed to generate"
        mock_module_logger.warning.assert_called_once()
        args, _ = mock_module_logger.warning.call_args
        assert "An error occurred during LLM invocation: OpenAI API error" in args[0]

    def test_generate_group_name_json_missing_keys(
        self, llm_class_fixture, mock_openai_client_create_fixture, mock_module_logger
    ):
        """
        Test generate_group_name when the LLM returns valid JSON but missing 'display_name' or 'summary' keys.
        """
        _, mock_create_method = mock_openai_client_create_fixture

        # Test case 1: Missing 'summary'
        mock_response_content_missing_summary = json.dumps(
            {"display_name": "Only Display Name"}
        )
        mock_chat_completion_1 = ChatCompletion(
            id="chatcmpl-test-1",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant", content=mock_response_content_missing_summary
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )

        # Test case 2: Missing 'display_name'
        mock_response_content_missing_display_name = json.dumps(
            {"summary": "Only Summary"}
        )
        mock_chat_completion_2 = ChatCompletion(
            id="chatcmpl-test-2",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=mock_response_content_missing_display_name,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )

        # Test case 3: Missing both
        mock_response_content_missing_both = json.dumps({"other_key": "some_value"})
        mock_chat_completion_3 = ChatCompletion(
            id="chatcmpl-test-3",
            object="chat.completion",
            created=1677652288,
            model=self.DEFAULT_MODEL_NAME,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant", content=mock_response_content_missing_both
                    ),
                    finish_reason="stop",
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )

        # Use side_effect to provide different return values for multiple calls
        mock_create_method.side_effect = [
            mock_chat_completion_1,
            mock_chat_completion_2,
            mock_chat_completion_3,
        ]

        llm = llm_class_fixture(llm_api_key=self.DEFAULT_API_KEY)
        queries = ["query_a", "query_b"]

        # Test 1: Missing 'summary'
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))
        assert display_name == "Only Display Name"
        assert summary == ""
        mock_module_logger.warning.assert_not_called()

        mock_module_logger.reset_mock()  # Reset calls for the logger mock

        # Test 2: Missing 'display_name'
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))
        assert display_name == ""
        assert summary == "Only Summary"

        mock_module_logger.reset_mock()

        # Test 3: Missing both
        display_name, summary = asyncio.run(llm.generate_group_name(queries=queries))
        assert display_name == ""
        assert summary == ""

        assert mock_create_method.call_count == 3
        mock_module_logger.warning.assert_not_called()
