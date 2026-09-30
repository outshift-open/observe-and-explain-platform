#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import sqlite3

from dem.embedding.cache import CacheManager


@pytest.fixture
def in_memory_cache_manager():
    """Provides a CacheManager instance using an in-memory SQLite database."""
    # Use ':memory:' for an in-memory database that exists only for the duration of the connection
    cache_manager = CacheManager(cache_path=":memory:")
    yield cache_manager
    # The connection will be closed automatically when the fixture goes out of scope
    # or can be explicitly closed if needed for specific tests
    cache_manager.close_cache()


def test_cache_manager_init(in_memory_cache_manager):
    """Test that CacheManager initializes and creates the table."""
    assert in_memory_cache_manager.conn is not None
    assert in_memory_cache_manager.cursor is not None
    # Verify table exists by trying to query it
    in_memory_cache_manager.cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings';"
    )
    assert in_memory_cache_manager.cursor.fetchone() is not None, (
        "Embeddings table should be created"
    )


def test_set_and_get_embedding(in_memory_cache_manager):
    """Test setting and getting a single embedding."""
    model_id = "test_model_1"
    sentence = "Hello world"
    embedding = np.array([0.1, 0.2, 0.3])

    in_memory_cache_manager.set_embedding(model_id, sentence, embedding)
    retrieved_embedding = in_memory_cache_manager.get_embedding(model_id, sentence)

    np.testing.assert_array_equal(retrieved_embedding, embedding)


def test_get_non_existent_embedding(in_memory_cache_manager):
    """Test getting an embedding that does not exist."""
    model_id = "non_existent_model"
    sentence = "Non existent sentence"
    retrieved_embedding = in_memory_cache_manager.get_embedding(model_id, sentence)
    assert retrieved_embedding is None


def test_update_embedding(in_memory_cache_manager):
    """Test updating an existing embedding."""
    model_id = "test_model_2"
    sentence = "Sentence to update"
    initial_embedding = np.array([0.5, 0.6])
    updated_embedding = np.array([0.9, 0.8])

    in_memory_cache_manager.set_embedding(model_id, sentence, initial_embedding)
    in_memory_cache_manager.set_embedding(model_id, sentence, updated_embedding)
    retrieved_embedding = in_memory_cache_manager.get_embedding(model_id, sentence)

    np.testing.assert_array_equal(retrieved_embedding, updated_embedding)


def test_multiple_embeddings(in_memory_cache_manager):
    """Test setting and getting multiple embeddings for different models/sentences."""
    embeddings_data = {
        ("model_A", "sentence_1"): np.array([0.1, 0.1]),
        ("model_A", "sentence_2"): np.array([0.2, 0.2]),
        ("model_B", "sentence_1"): np.array([0.3, 0.3]),
    }

    for (model_id, sentence), embedding in embeddings_data.items():
        in_memory_cache_manager.set_embedding(model_id, sentence, embedding)

    for (model_id, sentence), expected_embedding in embeddings_data.items():
        retrieved_embedding = in_memory_cache_manager.get_embedding(model_id, sentence)
        np.testing.assert_array_equal(retrieved_embedding, expected_embedding)


def test_close_cache(in_memory_cache_manager):
    """Test that closing the cache sets conn to None."""
    in_memory_cache_manager.close_cache()
    assert in_memory_cache_manager.conn is None
    # Attempting to use a closed connection should raise an error
    with pytest.raises(sqlite3.ProgrammingError):
        in_memory_cache_manager.cursor.execute("SELECT 1")


def test_save_cache_commits_changes(monkeypatch):
    """Test that save_cache calls commit."""
    mock_conn = MagicMock()
    # Temporarily replace the real connection with a mock
    with patch("sqlite3.connect", return_value=mock_conn):
        cache_manager = CacheManager(cache_path=":memory:")
        cache_manager.save_cache()
        mock_conn.commit.assert_called_once()
    cache_manager.close_cache()


def test_set_embedding_rollback_on_error(monkeypatch):
    """Test that set_embedding rolls back on SQLite error."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.side_effect = sqlite3.Error("Test error")

    with patch("sqlite3.connect", return_value=mock_conn):
        cache_manager = CacheManager(cache_path=":memory:")
        model_id = "error_model"
        sentence = "error_sentence"
        embedding = np.array([0.1, 0.2])
        cache_manager.set_embedding(model_id, sentence, embedding)
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
    cache_manager.close_cache()
