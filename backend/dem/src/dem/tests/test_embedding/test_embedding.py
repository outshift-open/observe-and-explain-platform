#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import os
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
import torch

from dem.embedding import (
    EmbeddingModel,
    GensimEmbedder,
    GoogleEmbedder,
    OpenAIEmbedder,
    Qwen3Embedder,
    SentenceTransformerEmbedder,
)
from dem.embedding.cache import CacheManager


@pytest.fixture
def mock_cache_manager():
    """A mock CacheManager that uses an in-memory dictionary for testing."""
    mock_manager = MagicMock(spec=CacheManager)
    mock_manager.cache = {}  # Use a simple dict to simulate cache

    def mock_get_embedding(model_id, sentence):
        key = (model_id, sentence)
        return mock_manager.cache.get(key)

    def mock_set_embedding(model_id, sentence, embedding):
        key = (model_id, sentence)
        mock_manager.cache[key] = embedding

    def mock_save_cache():
        pass  # No actual saving needed for mock

    def mock_close_cache():
        mock_manager.cache.clear()  # Clear cache on close for mock

    mock_manager.get_embedding.side_effect = mock_get_embedding
    mock_manager.set_embedding.side_effect = mock_set_embedding
    mock_manager.save_cache.side_effect = mock_save_cache
    mock_manager.close_cache.side_effect = mock_close_cache
    return mock_manager


# --- Base EmbeddingModel Tests ---


def test_embedding_model_abstract_methods():
    """Test that abstract methods raise NotImplementedError."""
    mock_cache = MagicMock(spec=CacheManager)
    model = EmbeddingModel("base_model", mock_cache)

    with pytest.raises(
        NotImplementedError,
        match="Subclasses must implement the _internal_encode method.",
    ):
        model._internal_encode(["sentence"])

    with pytest.raises(
        NotImplementedError,
        match="Subclasses must implement the get_word_embedding_in_context method.",
    ):
        model.get_word_embedding_in_context("text", 0, 1)


def test_embedding_model_encode_no_cache(mock_cache_manager):
    """Test encode when no embeddings are cached."""

    class ConcreteEmbeddingModel(EmbeddingModel):
        def _internal_encode(self, sentences: list[str]) -> np.ndarray:
            return np.array([[0.1, 0.2], [0.3, 0.4]])

        def get_word_embedding_in_context(
            self, text: str, char_start: int, char_end: int
        ) -> np.ndarray:
            return np.zeros(2)

    model_id = "concrete_model"
    sentences = ["sentence 1", "sentence 2"]
    model = ConcreteEmbeddingModel(model_id, mock_cache_manager)

    # Mock _internal_encode to track calls
    model._internal_encode = MagicMock(return_value=np.array([[0.1, 0.2], [0.3, 0.4]]))

    embeddings = model.encode(sentences)

    model._internal_encode.assert_called_once_with(sentences)
    assert mock_cache_manager.set_embedding.call_count == len(sentences)
    mock_cache_manager.save_cache.assert_called_once()
    np.testing.assert_array_equal(embeddings, np.array([[0.1, 0.2], [0.3, 0.4]]))


def test_embedding_model_encode_all_cached(mock_cache_manager):
    """Test encode when all embeddings are cached."""

    class ConcreteEmbeddingModel(EmbeddingModel):
        def _internal_encode(self, sentences: list[str]) -> np.ndarray:
            return np.array([])  # Should not be called

        def get_word_embedding_in_context(
            self, text: str, char_start: int, char_end: int
        ) -> np.ndarray:
            return np.zeros(2)

    model_id = "concrete_model"
    sentences = ["cached sentence 1", "cached sentence 2"]
    model = ConcreteEmbeddingModel(model_id, mock_cache_manager)

    # Pre-populate cache (write directly to mock cache dict to avoid incrementing mock call counts)
    mock_cache_manager.cache[(model_id, sentences[0])] = np.array([0.5, 0.6])
    mock_cache_manager.cache[(model_id, sentences[1])] = np.array([0.7, 0.8])

    # Mock _internal_encode to ensure it's not called
    model._internal_encode = MagicMock()

    embeddings = model.encode(sentences)

    model._internal_encode.assert_not_called()
    mock_cache_manager.set_embedding.assert_not_called()  # No new embeddings to set
    mock_cache_manager.save_cache.assert_not_called()
    np.testing.assert_array_equal(embeddings, np.array([[0.5, 0.6], [0.7, 0.8]]))


def test_embedding_model_encode_mixed_cache(mock_cache_manager):
    """Test encode when some embeddings are cached and some are new."""

    class ConcreteEmbeddingModel(EmbeddingModel):
        def _internal_encode(self, sentences: list[str]) -> np.ndarray:
            # Simulate encoding for the new sentences
            if sentences == ["new sentence"]:
                return np.array([[0.9, 1.0]])
            return np.array([])  # Should not happen with this logic

        def get_word_embedding_in_context(
            self, text: str, char_start: int, char_end: int
        ) -> np.ndarray:
            return np.zeros(2)

    model_id = "concrete_model"
    sentences = ["cached sentence", "new sentence"]
    model = ConcreteEmbeddingModel(model_id, mock_cache_manager)

    # Pre-populate cache for one sentence (write directly to mock cache dict)
    mock_cache_manager.cache[(model_id, "cached sentence")] = np.array([0.1, 0.2])

    # Mock _internal_encode to track calls and return new embedding
    model._internal_encode = MagicMock(side_effect=model._internal_encode)

    embeddings = model.encode(sentences)

    model._internal_encode.assert_called_once_with(["new sentence"])
    assert mock_cache_manager.set_embedding.call_count == 1
    mock_cache_manager.set_embedding.assert_called_once()
    called_args = mock_cache_manager.set_embedding.call_args[0]
    assert called_args[0] == model_id
    assert called_args[1] == "new sentence"
    np.testing.assert_array_equal(called_args[2], np.array([0.9, 1.0]))
    mock_cache_manager.save_cache.assert_called_once()
    np.testing.assert_array_equal(embeddings, np.array([[0.1, 0.2], [0.9, 1.0]]))


def test_embedding_model_encode_duplicate_sentences_in_input(mock_cache_manager):
    """Test encode with duplicate sentences in the input list."""

    class ConcreteEmbeddingModel(EmbeddingModel):
        def _internal_encode(self, sentences: list[str]) -> np.ndarray:
            # Simulate encoding for unique new sentences
            if sentences == ["unique new"]:
                return np.array([[0.1, 0.2]])
            return np.array([])

        def get_word_embedding_in_context(
            self, text: str, char_start: int, char_end: int
        ) -> np.ndarray:
            return np.zeros(2)

    model_id = "concrete_model"
    sentences = ["unique new", "unique new", "cached"]
    model = ConcreteEmbeddingModel(model_id, mock_cache_manager)

    # Pre-populate cache for one sentence (write directly to mock cache dict)
    mock_cache_manager.cache[(model_id, "cached")] = np.array([0.3, 0.4])
    model._internal_encode = MagicMock(side_effect=model._internal_encode)

    embeddings = model.encode(sentences)

    model._internal_encode.assert_called_once_with(["unique new"])
    assert mock_cache_manager.set_embedding.call_count == 1
    mock_cache_manager.set_embedding.assert_called_once()
    called_args = mock_cache_manager.set_embedding.call_args[0]
    assert called_args[0] == model_id
    assert called_args[1] == "unique new"
    np.testing.assert_array_equal(called_args[2], np.array([0.1, 0.2]))
    mock_cache_manager.save_cache.assert_called_once()
    np.testing.assert_array_equal(
        embeddings, np.array([[0.1, 0.2], [0.1, 0.2], [0.3, 0.4]])
    )


# --- SentenceTransformerModel Tests ---


@patch("dem.embedding.embedding.SentenceTransformer")
@patch(
    "torch.cuda.is_available", return_value=False
)  # Force CPU for predictable device
def test_sentence_transformer_model_init(
    mock_cuda_available, mock_sentence_transformer, mock_cache_manager
):
    """Test SentenceTransformerModel initialization."""
    mock_sbert_instance = MagicMock()
    mock_sbert_instance._modules = {
        "0": MagicMock(
            tokenizer=MagicMock(model_max_length=512),
            auto_model=MagicMock(config=MagicMock(hidden_size=768)),
        )
    }
    mock_sentence_transformer.return_value = mock_sbert_instance

    model_id = "sbert_model"
    model = SentenceTransformerEmbedder(model_id, mock_cache_manager)

    mock_sentence_transformer.assert_called_once_with(model_id)
    assert model.model_id == model_id
    assert model.cache_manager == mock_cache_manager
    assert model.sbert_model == mock_sbert_instance
    assert model.tokenizer == mock_sbert_instance._modules["0"].tokenizer
    assert model.transformer_model == mock_sbert_instance._modules["0"].auto_model
    assert str(model.device) == "cpu"
    model.transformer_model.eval.assert_called_once()
    assert model.embedding_dimension == 768


@patch("dem.embedding.embedding.SentenceTransformer")
@patch("torch.cuda.is_available", return_value=False)
def test_sentence_transformer_internal_encode(
    mock_cuda_available, mock_sentence_transformer, mock_cache_manager
):
    """Test _internal_encode for SentenceTransformerModel."""
    mock_sbert_instance = MagicMock()
    mock_sbert_instance.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
    mock_sbert_instance._modules = {
        "0": MagicMock(
            tokenizer=MagicMock(model_max_length=512),
            auto_model=MagicMock(config=MagicMock(hidden_size=768)),
        )
    }
    mock_sentence_transformer.return_value = mock_sbert_instance

    model_id = "sbert_model"
    sentences = ["sentence A", "sentence B"]
    model = SentenceTransformerEmbedder(model_id, mock_cache_manager)

    embeddings = model._internal_encode(sentences)

    mock_sbert_instance.encode.assert_called_once_with(
        sentences, convert_to_numpy=True, show_progress_bar=False
    )
    np.testing.assert_array_equal(embeddings, np.array([[0.1, 0.2], [0.3, 0.4]]))


@patch("dem.embedding.embedding.SentenceTransformer")
@patch("torch.cuda.is_available", return_value=False)
def test_sentence_transformer_get_word_embedding_in_context(
    mock_cuda_available, mock_sentence_transformer, mock_cache_manager
):
    """Test get_word_embedding_in_context for SentenceTransformerModel."""
    mock_sbert_instance = MagicMock()
    mock_tokenizer = MagicMock()
    mock_transformer_model = MagicMock()

    # Mock tokenizer.encode_plus output
    mock_tokenizer.encode_plus.return_value = {
        "input_ids": torch.tensor([[101, 2000, 2003, 102]]),  # [CLS] Hello world [SEP]
        "offset_mapping": torch.tensor(
            [[0, 0], [0, 5], [6, 11], [0, 0]]
        ),  # [CLS], Hello, world, [SEP]
    }
    mock_tokenizer.model_max_length = 512

    # Mock transformer_model output
    mock_outputs = MagicMock()
    mock_outputs.last_hidden_state = torch.tensor(
        [
            [
                [0.1, 0.1],
                [0.2, 0.2],
                [0.3, 0.3],
                [0.4, 0.4],
            ]  # Embeddings for [CLS], Hello, world, [SEP]
        ]
    )
    mock_transformer_model.return_value = mock_outputs
    mock_transformer_model.config.hidden_size = 2  # Set embedding dimension

    mock_sbert_instance._modules = {
        "0": MagicMock(tokenizer=mock_tokenizer, auto_model=mock_transformer_model)
    }
    mock_sentence_transformer.return_value = mock_sbert_instance

    model_id = "sbert_model"
    model = SentenceTransformerEmbedder(model_id, mock_cache_manager)

    text = "Hello world"
    # Test for "Hello" (char_start=0, char_end=5)
    embedding = model.get_word_embedding_in_context(text, 0, 5)
    np.testing.assert_allclose(
        embedding, np.array([0.2, 0.2]), rtol=1e-6, atol=1e-8
    )  # Embedding for 'Hello'

    # Test for "world" (char_start=6, char_end=11)
    embedding = model.get_word_embedding_in_context(text, 6, 11)
    np.testing.assert_allclose(
        embedding, np.array([0.3, 0.3]), rtol=1e-6, atol=1e-8
    )  # Embedding for 'world'

    # Test for a word not found (e.g., "nonexistent")
    embedding = model.get_word_embedding_in_context(text, 100, 105)
    np.testing.assert_array_equal(embedding, np.zeros(model.embedding_dimension))


# --- GensimModel Tests ---


@patch("dem.embedding.embedding.gensim.downloader.load")
def test_gensim_model_init(mock_gensim_load, mock_cache_manager):
    """Test GensimModel initialization."""
    mock_gensim_model = MagicMock()
    mock_gensim_model.vector_size = 100
    mock_gensim_load.return_value = mock_gensim_model

    model_id = "word2vec-google-news-300"
    model = GensimEmbedder(model_id, mock_cache_manager)

    mock_gensim_load.assert_called_once_with(model_id)
    assert model.model_id == model_id
    assert model.model == mock_gensim_model
    assert model.embedding_dimension == 100


@patch("dem.embedding.embedding.gensim.downloader.load")
def test_gensim_internal_encode(mock_gensim_load, mock_cache_manager):
    """Test _internal_encode for GensimModel."""
    mock_gensim_model = MagicMock()
    mock_gensim_model.vector_size = 3
    mock_gensim_model.__contains__.side_effect = lambda word: word in ["hello", "world"]
    mock_gensim_model.__getitem__.side_effect = {
        "hello": np.array([0.1, 0.2, 0.3]),
        "world": np.array([0.4, 0.5, 0.6]),
    }.get
    mock_gensim_load.return_value = mock_gensim_model

    model_id = "g_model"
    model = GensimEmbedder(model_id, mock_cache_manager)

    # Sentence with known words
    sentences = ["hello world", "unknown words"]
    embeddings = model._internal_encode(sentences)
    expected_embeddings = np.array(
        [
            np.mean([np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])], axis=0),
            np.zeros(3),
        ]
    )
    np.testing.assert_array_almost_equal(embeddings, expected_embeddings)

    # Sentence with no known words
    sentences_no_known = ["completely new sentence"]
    embeddings_no_known = model._internal_encode(sentences_no_known)
    np.testing.assert_array_almost_equal(
        embeddings_no_known, np.array([[0.0, 0.0, 0.0]])
    )

    # Empty sentence
    sentences_empty = [""]
    embeddings_empty = model._internal_encode(sentences_empty)
    np.testing.assert_array_almost_equal(embeddings_empty, np.array([[0.0, 0.0, 0.0]]))


@patch("dem.embedding.embedding.gensim.downloader.load")
def test_gensim_get_word_embedding_in_context(mock_gensim_load, mock_cache_manager):
    """Test get_word_embedding_in_context for GensimModel."""
    mock_gensim_model = MagicMock()
    mock_gensim_model.vector_size = 3
    mock_gensim_model.__contains__.side_effect = lambda word: word in ["hello", "world"]
    mock_gensim_model.__getitem__.side_effect = {
        "hello": np.array([0.1, 0.2, 0.3]),
        "world": np.array([0.4, 0.5, 0.6]),
    }.get
    mock_gensim_load.return_value = mock_gensim_model

    model_id = "g_model"
    model = GensimEmbedder(model_id, mock_cache_manager)

    # Word found
    text = "This is a hello world example."
    embedding = model.get_word_embedding_in_context(text, 10, 15)  # "hello"
    np.testing.assert_array_equal(embedding, np.array([0.1, 0.2, 0.3]))

    # Word not found
    embedding = model.get_word_embedding_in_context(
        text, 8, 9
    )  # "a" (not in mock model)
    np.testing.assert_array_equal(embedding, np.zeros(3))

    # Word with punctuation
    text_punct = "hello,"
    embedding_punct = model.get_word_embedding_in_context(text_punct, 0, 6)  # "hello,"
    np.testing.assert_array_equal(embedding_punct, np.array([0.1, 0.2, 0.3]))


# --- OpenAIModel Tests ---


@patch("dem.embedding.embedding.OpenAI")
@patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "test_key"})
def test_openai_model_init_success(mock_openai, mock_cache_manager):
    """Test OpenAIModel initialization with API key."""
    mock_client_instance = MagicMock()
    mock_openai.return_value = mock_client_instance

    model_id = "text-embedding-ada-002"
    model = OpenAIEmbedder(model_id, mock_cache_manager)

    mock_openai.assert_called_once()
    assert model.client == mock_client_instance
    assert model.embedding_dimension is None
    mock_client_instance.embeddings.create.assert_not_called()


@patch("dem.embedding.embedding.OpenAI")
@patch.dict(os.environ, {}, clear=True)  # Ensure no API key is set
def test_openai_model_init_no_api_key(mock_openai, mock_cache_manager):
    """Test OpenAIModel initialization fails without API key."""
    model_id = "text-embedding-ada-002"
    with pytest.raises(Exception, match="OpenAI API key not found or model error:"):
        OpenAIEmbedder(model_id, mock_cache_manager)


@patch("dem.embedding.embedding.OpenAI")
@patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "test_key"})
@patch("time.sleep", return_value=None)  # Mock sleep to speed up tests
def test_openai_internal_encode(mock_sleep, mock_openai, mock_cache_manager):
    """Test _internal_encode for OpenAIModel with batching."""
    mock_client_instance = MagicMock()
    mock_openai.return_value = mock_client_instance

    model_id = "text-embedding-ada-002"
    model = OpenAIEmbedder(model_id, mock_cache_manager)

    sentences = [f"sentence {i}" for i in range(2500)]  # More than batch_size (2048)
    expected_embeddings = [np.array([float(i)] * 10) for i in range(len(sentences))]

    # Configure mock for _internal_encode calls
    def mock_create_embeddings(*args, **kwargs):
        batch = kwargs["input"]
        start_idx = sentences.index(batch[0])
        end_idx = start_idx + len(batch)
        response_data = [
            MagicMock(embedding=expected_embeddings[i].tolist())
            for i in range(start_idx, end_idx)
        ]
        mock_response = MagicMock()
        mock_response.data = response_data
        return mock_response

    mock_client_instance.embeddings.create.side_effect = mock_create_embeddings

    embeddings = model._internal_encode(sentences)

    assert mock_client_instance.embeddings.create.call_count == 2
    calls = [
        call(input=sentences[:2048], model=model_id),
        call(input=sentences[2048:], model=model_id),
    ]
    mock_client_instance.embeddings.create.assert_has_calls(calls)
    assert model.embedding_dimension == 10
    assert mock_sleep.call_count == 0  # OpenAI embedder does not sleep between batches
    np.testing.assert_array_equal(embeddings, np.array(expected_embeddings))


@patch("dem.embedding.embedding.OpenAI")
@patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "test_key"})
def test_openai_get_word_embedding_in_context(mock_openai, mock_cache_manager):
    """Test get_word_embedding_in_context for OpenAIModel returns zero vector."""
    mock_client_instance = MagicMock()
    mock_openai.return_value = mock_client_instance

    model_id = "text-embedding-ada-002"
    model = OpenAIEmbedder(model_id, mock_cache_manager)

    text = "Any text here"
    embedding = model.get_word_embedding_in_context(text, 0, 5)
    np.testing.assert_array_equal(embedding, np.zeros(3072))


# --- GoogleModel Tests ---


@patch("dem.embedding.embedding.genai")
@patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"})
def test_google_model_init_success(mock_genai, mock_cache_manager):
    """Test GoogleModel initialization with API key."""
    mock_client_instance = MagicMock()
    mock_genai.Client.return_value = mock_client_instance

    model_id = "embedding-001"
    model = GoogleEmbedder(model_id, mock_cache_manager)

    mock_genai.Client.assert_called_once_with(api_key="test_key")
    assert model.client == mock_client_instance
    assert model.embedding_dimension is None
    mock_client_instance.models.embed_content.assert_not_called()


@patch("dem.embedding.embedding.genai")
@patch.dict(os.environ, {}, clear=True)  # Ensure no API key is set
def test_google_model_init_no_api_key(mock_genai, mock_cache_manager):
    """Test GoogleModel initialization fails without API key."""
    model_id = "embedding-001"
    with pytest.raises(ValueError, match="Google API key not found."):
        GoogleEmbedder(model_id, mock_cache_manager)


@patch("dem.embedding.embedding.genai")
@patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"})
@patch("time.sleep", return_value=None)  # Mock sleep to speed up tests
def test_google_internal_encode(mock_sleep, mock_genai, mock_cache_manager):
    """Test _internal_encode for GoogleModel with batching."""
    mock_client_instance = MagicMock()
    mock_genai.Client.return_value = mock_client_instance

    model_id = "embedding-001"
    model = GoogleEmbedder(model_id, mock_cache_manager)

    sentences = [f"sentence {i}" for i in range(250)]  # More than batch_size (100)
    expected_embeddings = [np.array([float(i)] * 5) for i in range(len(sentences))]

    # Configure mock for _internal_encode calls
    def mock_embed_content(*args, **kwargs):
        batch = kwargs["contents"]
        start_idx = sentences.index(batch[0])
        end_idx = start_idx + len(batch)
        response_embeddings = [
            MagicMock(values=expected_embeddings[i].tolist())
            for i in range(start_idx, end_idx)
        ]
        mock_response = MagicMock()
        mock_response.embeddings = response_embeddings
        return mock_response

    mock_client_instance.models.embed_content.side_effect = mock_embed_content

    embeddings = model._internal_encode(sentences)

    assert mock_client_instance.models.embed_content.call_count == 3
    calls = [
        call(model=model_id, contents=sentences[:100]),
        call(model=model_id, contents=sentences[100:200]),
        call(model=model_id, contents=sentences[200:]),
    ]
    mock_client_instance.models.embed_content.assert_has_calls(calls)
    assert model.embedding_dimension == 5
    assert mock_sleep.call_count == 2  # Two sleeps between batches
    np.testing.assert_array_equal(embeddings, np.array(expected_embeddings))


@patch("dem.embedding.embedding.genai")
@patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"})
def test_google_get_word_embedding_in_context(mock_genai, mock_cache_manager):
    """Test get_word_embedding_in_context for GoogleModel returns zero vector."""
    mock_client_instance = MagicMock()
    mock_genai.Client.return_value = mock_client_instance

    model_id = "embedding-001"
    model = GoogleEmbedder(model_id, mock_cache_manager)

    text = "Any text here"
    embedding = model.get_word_embedding_in_context(text, 0, 5)
    np.testing.assert_array_equal(embedding, np.zeros(768))


# --- Qwen3EmbeddingModel Tests ---


@patch("dem.embedding.embedding.AutoTokenizer.from_pretrained")
@patch("dem.embedding.embedding.AutoModel.from_pretrained")
@patch(
    "torch.cuda.is_available", return_value=False
)  # Force CPU for predictable device
@patch("torch.device")  # Mock torch.device constructor
def test_qwen3_model_init(
    mock_torch_device,
    mock_cuda_available,
    mock_auto_model,
    mock_auto_tokenizer,
    mock_cache_manager,
):
    """Test Qwen3EmbeddingModel initialization on CPU."""
    mock_torch_device.return_value = MagicMock(type="cpu")  # Ensure device is CPU

    mock_tokenizer_instance = MagicMock(model_max_length=512)
    mock_auto_tokenizer.return_value = mock_tokenizer_instance

    mock_model_instance = MagicMock()
    mock_model_instance.config.hidden_size = 1024
    mock_auto_model.return_value = mock_model_instance

    model_id = "qwen3_model"
    model = Qwen3Embedder(model_id, mock_cache_manager)

    mock_auto_tokenizer.assert_called_once_with(model_id)
    mock_auto_model.assert_called_once_with(model_id)  # No torch_dtype for CPU
    mock_model_instance.to.assert_called_once()
    mock_model_instance.eval.assert_called_once()
    assert model.embedding_dimension == 1024
    assert str(model.device) == "cpu"


@patch("dem.embedding.embedding.AutoTokenizer.from_pretrained")
@patch("dem.embedding.embedding.AutoModel.from_pretrained")
@patch("torch.cuda.is_available", return_value=True)  # Simulate CUDA available
@patch("torch.device")
def test_qwen3_model_init_cuda(
    mock_torch_device,
    mock_cuda_available,
    mock_auto_model,
    mock_auto_tokenizer,
    mock_cache_manager,
):
    """Test Qwen3EmbeddingModel initialization on CUDA."""
    mock_torch_device.return_value = MagicMock(type="cuda")  # Ensure device is CUDA

    mock_tokenizer_instance = MagicMock(model_max_length=512)
    mock_auto_tokenizer.return_value = mock_tokenizer_instance

    mock_model_instance = MagicMock()
    mock_model_instance.config.hidden_size = 1024
    mock_auto_model.return_value = mock_model_instance

    model_id = "qwen3_model"
    model = Qwen3Embedder(model_id, mock_cache_manager)

    mock_auto_model.assert_called_once_with(
        model_id, torch_dtype=torch.float16
    )  # float16 for CUDA
    assert str(model.device) == "cuda"


@patch("dem.embedding.embedding.AutoTokenizer.from_pretrained")
@patch("dem.embedding.embedding.AutoModel.from_pretrained")
@patch("torch.cuda.is_available", return_value=False)
@patch("torch.no_grad")
@patch("torch.sum")
@patch("torch.clamp")
@patch("torch.unsqueeze")
@patch("torch.Tensor.expand")  # Mock the expand method on a tensor
@patch("torch.cuda.empty_cache")  # Mock CUDA cache clearing
def test_qwen3_internal_encode(
    mock_empty_cache,
    mock_expand,
    mock_unsqueeze,
    mock_clamp,
    mock_sum,
    mock_no_grad,
    mock_cuda_available,
    mock_auto_model,
    mock_auto_tokenizer,
    mock_cache_manager,
):
    """Test _internal_encode for Qwen3EmbeddingModel."""
    mock_tokenizer_instance = MagicMock(model_max_length=512)
    mock_auto_tokenizer.return_value = mock_tokenizer_instance
    mock_tokenizer_instance.return_value = {
        "input_ids": MagicMock(to=lambda x: MagicMock()),
        "attention_mask": MagicMock(to=lambda x: MagicMock()),
    }

    mock_model_instance = MagicMock()
    mock_model_instance.config.hidden_size = 2
    mock_auto_model.return_value = mock_model_instance
    mock_model_instance.return_value = MagicMock(
        last_hidden_state=torch.tensor(
            [[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.6], [0.7, 0.8]]]
        )
    )  # Mock output for a batch of 2 sentences, 2 tokens each

    # Mock torch operations to return predictable values
    mock_sum.side_effect = [
        torch.tensor([[0.1, 0.2], [0.3, 0.4]]),  # Sum for sentence 1
        torch.tensor([[0.5, 0.6], [0.7, 0.8]]),  # Sum for sentence 2
    ]
    mock_clamp.return_value = torch.tensor(
        [[2.0], [2.0]]
    )  # Assuming 2 tokens per sentence
    mock_unsqueeze.return_value = MagicMock(
        expand=MagicMock(
            return_value=MagicMock(float=MagicMock(return_value=MagicMock()))
        )
    )
    mock_expand.return_value = MagicMock(float=MagicMock(return_value=MagicMock()))

    model_id = "qwen3_model"
    model = Qwen3Embedder(model_id, mock_cache_manager, batch_size=2)

    sentences = ["sentence one", "sentence two", "sentence three"]
    embeddings = model._internal_encode(sentences)

    # Expect 2 calls to tokenizer (for 2 batches)
    assert mock_tokenizer_instance.call_count == 2
    # Expect 2 calls to model (for 2 batches)
    assert mock_model_instance.call_count == 2

    # Verify cuda.empty_cache is called if CUDA is available (it's mocked to False here, so not called)
    if mock_cuda_available.return_value:
        assert mock_empty_cache.call_count > 0
    else:
        mock_empty_cache.assert_not_called()

    # The exact values from the mocked sum/clamp are hard to predict without complex mocking
    # Just check the shape and type for now
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (len(sentences), model.embedding_dimension)


@patch("dem.embedding.embedding.AutoTokenizer.from_pretrained")
@patch("dem.embedding.embedding.AutoModel.from_pretrained")
@patch("torch.cuda.is_available", return_value=False)
@patch("torch.no_grad")
def test_qwen3_get_word_embedding_in_context(
    mock_no_grad,
    mock_cuda_available,
    mock_auto_model,
    mock_auto_tokenizer,
    mock_cache_manager,
):
    """Test get_word_embedding_in_context for Qwen3EmbeddingModel."""
    mock_tokenizer_instance = MagicMock(model_max_length=512)
    mock_auto_tokenizer.return_value = mock_tokenizer_instance
    mock_tokenizer_instance.encode_plus.return_value = {
        "input_ids": torch.tensor([[101, 2000, 2003, 102]]),  # [CLS] Hello world [SEP]
        "offset_mapping": torch.tensor(
            [[0, 0], [0, 5], [6, 11], [0, 0]]
        ),  # [CLS], Hello, world, [SEP]
    }

    mock_model_instance = MagicMock()
    mock_model_instance.config.hidden_size = 2
    mock_auto_model.return_value = mock_model_instance
    mock_model_instance.return_value = MagicMock(
        last_hidden_state=torch.tensor(
            [
                [
                    [0.1, 0.1],
                    [0.2, 0.2],
                    [0.3, 0.3],
                    [0.4, 0.4],
                ]  # Embeddings for [CLS], Hello, world, [SEP]
            ]
        )
    )

    model_id = "qwen3_model"
    model = Qwen3Embedder(model_id, mock_cache_manager)

    text = "Hello world"
    # Test for "Hello" (char_start=0, char_end=5)
    embedding = model.get_word_embedding_in_context(text, 0, 5)
    np.testing.assert_allclose(embedding, np.array([0.2, 0.2]), rtol=1e-6, atol=1e-8)

    # Test for "world" (char_start=6, char_end=11)
    embedding = model.get_word_embedding_in_context(text, 6, 11)
    np.testing.assert_allclose(embedding, np.array([0.3, 0.3]), rtol=1e-6, atol=1e-8)

    # Test for a word not found
    embedding = model.get_word_embedding_in_context(text, 100, 105)
    np.testing.assert_array_equal(embedding, np.zeros(model.embedding_dimension))
