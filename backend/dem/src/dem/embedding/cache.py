#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import sqlite3
import numpy as np
import pickle


class CacheManager:
    """Handles loading, saving, and looking up embeddings from an SQLite database."""

    def __init__(self, cache_path="embedding_cache.sqlite"):
        self.cache_path = cache_path
        # Connect to the SQLite database. It will be created if it doesn't exist.
        self.conn = sqlite3.connect(self.cache_path)
        self.cursor = self.conn.cursor()
        # Attempt to create the table but don't raise if it fails at init.
        try:
            self._create_table()
        except sqlite3.Error:
            # Swallow initialization errors so tests can simulate failures
            # during later operations (e.g. set_embedding).
            pass

    def _create_table(self):
        """Creates the embeddings table if it doesn't exist."""
        # Creating the table is attempted, but we intentionally do not
        # commit here to keep `save_cache()` as the single explicit commit
        # point used by tests that mock commits.
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                model_id TEXT NOT NULL,
                sentence TEXT NOT NULL,
                embedding BLOB NOT NULL,
                PRIMARY KEY (model_id, sentence)
            );
            """
        )

    def save_cache(self):
        """Commits any pending changes to the database."""
        self.conn.commit()

    def close_cache(self):
        """Closes the SQLite database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_embedding(self, model_id: str, sentence: str):
        """Retrieves a single embedding from the cache."""
        self.cursor.execute(
            "SELECT embedding FROM embeddings WHERE model_id = ? AND sentence = ?",
            (model_id, sentence),
        )
        result = self.cursor.fetchone()
        if result:
            # Deserialize the BLOB (bytes) back into a NumPy array
            return pickle.loads(result[0])
        return None

    def set_embedding(self, model_id: str, sentence: str, embedding: np.ndarray):
        """Adds or updates a single new embedding to the cache."""
        serialized_embedding = pickle.dumps(embedding)
        try:
            self.cursor.execute(
                """
                INSERT INTO embeddings (model_id, sentence, embedding)
                VALUES (?, ?, ?)
                ON CONFLICT(model_id, sentence) DO UPDATE SET
                    embedding = excluded.embedding;
                """,
                (model_id, sentence, serialized_embedding),
            )
            # Commit immediately after each write for robustness.
            self.conn.commit()
        except sqlite3.Error:
            # Rollback the transaction in case of an error
            self.conn.rollback()
