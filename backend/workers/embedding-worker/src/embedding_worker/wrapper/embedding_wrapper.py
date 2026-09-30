#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import csv
import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

AVAILABLE_EMBEDDERS = {
    "SentenceTransformerEmbedder",
    "OpenAIEmbedder",
}
DEFAULT_EMBEDDER = "SentenceTransformerEmbedder"
DEFAULT_MODEL = "all-MiniLM-L6-v2"
EMPTY_STATE_CONTENT = "OXP_EMPTY_STATE"


class EmbeddingDALHandler(Protocol):
    def get_state_content(self, session_id: str) -> List[Dict[str, Any]]: ...

    def ingest_embeddings(self, embeddings: List[Dict[str, Any]]) -> None: ...


def _build_embedder(embedder_name: str, model: str):
    from dem import embedding

    embedder_map = {
        "SentenceTransformerEmbedder": embedding.SentenceTransformerEmbedder,
        "OpenAIEmbedder": embedding.OpenAIEmbedder,
    }
    return embedder_map[embedder_name](model_id=model)


class EmbeddingWrapper:
    def __init__(
        self,
        args,
        db_handler: EmbeddingDALHandler,
        debug: bool = False,
        embedder: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize the EmbeddingWrapper.

        Args:
            args: Command-line arguments (unused, for compatibility)
            db_handler: KG access handler (state content lookup + embedding ingestion)
            debug: Enable debug mode (saves embeddings to CSV)
            embedder: Embedder type (e.g., 'OpenAIEmbedder', 'SentenceTransformerEmbedder')
            model: Model identifier (e.g., 'azure/text-embedding-3-small')
        """
        self.args = args
        self.db_handler = db_handler
        self.debug = debug

        # Set model with fallback to default
        self.model = model if model else DEFAULT_MODEL
        logger.info(f"Using model: {self.model}")

        # Select embedder with fallback to default
        embedder_str = embedder if embedder in AVAILABLE_EMBEDDERS else DEFAULT_EMBEDDER
        logger.info(f"Using embedder: {embedder_str}")
        self.embedder = _build_embedder(embedder_str, self.model)

    def process_session(self, session_id: str):
        """
        Process a single session by generating embeddings for its content.

        Args:
            session_id: The session ID to process
        """
        logger.info(f"Processing session: {session_id}")

        # Every State belonging to this session -- a session's own boundary
        # states are shared with (not distinct from) whichever ExecutionElement
        # actually owns them (see oxp-ontology's SessionInitialStateShared/
        # FinalStateShared shapes), so this single scan already covers what a
        # separate "session io" fetch used to try to cover on its own.
        transitions = self.db_handler.get_state_content(session_id)

        logger.info(f"Retrieved {len(transitions)} transitions/content items for session: {session_id}")

        # Build in-memory records for embedding payload
        records = []
        for t in transitions:
            d = {
                "SessionId": session_id,
                "Timestamp": "",
                "Content": t.get("content", ""),
                "ApplicationId": "",
                "AgentId": "",
                "TraceId": "",
                "SpanId": t.get("id", ""),
            }
            if d.get("Content") == "":
                d["Content"] = EMPTY_STATE_CONTENT
            records.append(d)

        if len(records) == 0:
            logger.warning(f"No content found to embed for session: {session_id}")
            return

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(records)} items")
        embeddings = self.embedder.encode([record["Content"] for record in records]).tolist()

        for record, vector in zip(records, embeddings):
            record["EntityType"] = "Content"
            record["EmbeddingModel"] = self.model
            record["Embedding"] = vector
            record.pop("Content", None)

        logger.debug(f"Embedding results sample: {records[:3]}")

        if self.debug:
            csv_path = f"/tmp/embedding_embeddings_{session_id}.csv"
            with open(csv_path, "w", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            logger.info(f"Saved embeddings to {csv_path}")

        # Ingest embeddings into knowledge graph
        logger.info(f"Ingesting {len(records)} embeddings into knowledge graph")
        self.db_handler.ingest_embeddings(records)

        logger.info(f"Completed embedding processing for session: {session_id}")

    def process_session2(self, session_id: str):
        """Backward-compatible alias for process_session."""
        self.process_session(session_id)
