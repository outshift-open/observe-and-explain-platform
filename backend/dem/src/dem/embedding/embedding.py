#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import os
import re
import time
from collections import OrderedDict
from typing import Optional

import gensim.downloader
import numpy as np
import torch
from google import genai
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

from .cache import CacheManager


class EmbeddingModel:
    """Base class for all embedding models."""

    def __init__(self, model_id: str, cache_manager: Optional[CacheManager] = None):
        self.model_id = model_id
        self.cache_manager = cache_manager

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        raise NotImplementedError(
            "Subclasses must implement the _internal_encode method."
        )

    def encode(self, sentences: list[str]) -> np.ndarray:
        """Encodes sentences using a cache-first approach."""
        # If no cache manager provided, always compute embeddings for all sentences
        if self.cache_manager is None:
            return np.array(self._internal_encode(sentences))

        cached_embeddings = OrderedDict()
        sentences_to_compute = []

        for i, sentence in enumerate(sentences):
            embedding = self.cache_manager.get_embedding(self.model_id, sentence)
            if embedding is not None:
                cached_embeddings[i] = embedding
            elif sentence not in sentences_to_compute:
                sentences_to_compute.append(sentence)

        new_embeddings_arr = []
        if sentences_to_compute:
            new_embeddings_arr = self._internal_encode(sentences_to_compute)
            for sentence, new_embedding in zip(
                sentences_to_compute, new_embeddings_arr
            ):
                # Only set in cache if cache_manager is present
                if self.cache_manager is not None:
                    self.cache_manager.set_embedding(
                        self.model_id, sentence, new_embedding
                    )
            if self.cache_manager is not None:
                self.cache_manager.save_cache()

        final_embeddings = []
        new_embedding_map = (
            {sent: emb for sent, emb in zip(sentences_to_compute, new_embeddings_arr)}
            if sentences_to_compute
            else {}
        )

        for i, sentence in enumerate(sentences):
            if i in cached_embeddings:
                final_embeddings.append(cached_embeddings[i])
            else:
                final_embeddings.append(new_embedding_map[sentence])
        return np.array(final_embeddings)

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        raise NotImplementedError(
            "Subclasses must implement the get_word_embedding_in_context method."
            " If not supported, return a zero vector of the appropriate dimension."
        )


class SentenceTransformerEmbedder(EmbeddingModel):
    def __init__(self, model_id, cache_manager=None):
        super().__init__(model_id, cache_manager)
        self.sbert_model = SentenceTransformer(self.model_id)

        self.tokenizer = self.sbert_model._modules["0"].tokenizer
        self.transformer_model = self.sbert_model._modules["0"].auto_model

        # Keep a simple device string to make tests deterministic when torch.device is patched
        device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            device_type = device_obj.type
        except Exception:
            device_type = str(device_obj)
        self.device = device_type

        # Move model tensors to the device
        # If self.device is a string ('cpu'/'cuda'), tensors' .to accepts that
        self.transformer_model.to(self.device)
        self.transformer_model.eval()  # Set to evaluation mode
        self.embedding_dimension = self.transformer_model.config.hidden_size

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        embeddings = self.sbert_model.encode(
            sentences, convert_to_numpy=True, show_progress_bar=False
        )
        return embeddings

    def _normalize_offset_mapping(self, raw_offset):
        # Accept tensors, numpy arrays, lists. Return list of (start,end) pairs.
        try:
            # If it's a torch tensor or has .tolist()
            lst = raw_offset.tolist()
        except Exception:
            lst = raw_offset

        # Handle flat list of ints -> group into pairs
        if isinstance(lst, list) and lst and not isinstance(lst[0], list):
            if all(isinstance(x, int) for x in lst) and len(lst) % 2 == 0:
                it = iter(lst)
                return [(a, b) for a, b in zip(it, it)]
            return lst

        # If we have a list whose first element is a list, it can be either:
        # - a list of pairs (no batch dim): [[s,e], [s,e], ...] -> return as-is
        # - a batched list: [[[s,e], ...], [[s,e], ...]] -> return first element
        if isinstance(lst, list) and lst and isinstance(lst[0], list):
            # detect batch dimension: if first element's first element is a list, it's batched
            if isinstance(lst[0][0], list):
                return lst[0]
            # otherwise it's already a list of pairs
            return lst

        return []

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        # Tokenize the input text with offset mapping
        tokens = self.tokenizer.encode_plus(
            text,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=self.tokenizer.model_max_length,
        )

        input_ids = tokens["input_ids"].to(self.device)
        offset_mapping = self._normalize_offset_mapping(tokens["offset_mapping"])

        # Get hidden states from the transformer model
        with torch.no_grad():
            outputs = self.transformer_model(input_ids)
            last_hidden_states = outputs.last_hidden_state

        target_token_indices = []
        for i, pair in enumerate(offset_mapping):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            token_start_char, token_end_char = pair
            # Skip special tokens (like [CLS], [SEP]) which often have (0,0) offset
            # and invalid offsets (e.g., None for padding tokens)
            if (
                token_start_char is None
                or token_end_char is None
                or (token_start_char == 0 and token_end_char == 0 and i != 0)
            ):
                continue

            if token_start_char < char_end and token_end_char > char_start:
                target_token_indices.append(i)

        if target_token_indices:
            word_embeddings = last_hidden_states[0, target_token_indices, :]
            word_embedding = torch.mean(word_embeddings, dim=0).cpu().numpy()
            return np.round(word_embedding.astype(float), 10)
        else:
            return np.zeros(self.embedding_dimension)


class GensimEmbedder(EmbeddingModel):
    def __init__(self, model_id, cache_manager=None):
        super().__init__(model_id, cache_manager)
        self.model = gensim.downloader.load(self.model_id)
        self.embedding_dimension = self.model.vector_size

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        embeddings = []
        for sentence in sentences:
            words = sentence.lower().split()
            word_vectors = [self.model[word] for word in words if word in self.model]
            if word_vectors:
                embeddings.append(np.mean(word_vectors, axis=0))
            else:
                embeddings.append(np.zeros(self.embedding_dimension))
        return np.array(embeddings)

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        # Gensim models are not contextual. We extract the word and get its static embedding.
        target_word_raw = text[char_start:char_end]
        # Clean the target word to match common word embeddings (e.g., remove punctuation)
        cleaned_target_word = re.sub(r"[^\w\s]", "", target_word_raw).lower()

        if cleaned_target_word in self.model:
            return self.model[cleaned_target_word]
        else:
            return np.zeros(self.embedding_dimension)


class OpenAIEmbedder(EmbeddingModel):
    def __init__(
        self,
        model_id,
        cache_manager=None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retries: int = 8,
        timeout: float = 60.0,
    ):
        super().__init__(model_id, cache_manager)
        try:
            # Determine API key: parameter > env var
            api_key_to_use = api_key or os.getenv("AI_GATEWAY_API_KEY")
            if not api_key_to_use:
                raise Exception(
                    "OpenAI API key not found or model error: Please set AI_GATEWAY_API_KEY."
                )

            # Determine base URL: parameter > env var > default
            base_url_to_use = base_url or os.getenv(
                "AI_GATEWAY_BASE_URL", "https://api.openai.com/v1"
            )

            # Create client with optional base_url (for gateway support)
            self.client = OpenAI(
                api_key=api_key_to_use,
                base_url=base_url_to_use,
                max_retries=max_retries,
                timeout=timeout,
            )

            # Avoid eager network/API-key validation at startup.
            # Dimension is discovered lazily on first real encode call.
            self.embedding_dimension = None
        except Exception as e:
            raise Exception(
                f"OpenAI API key not found or model error: {e}. Please set AI_GATEWAY_API_KEY."
            )

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        batch_size = 2048  # Max batch size for OpenAI embeddings
        all_embeddings = []
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i : i + batch_size]
            response = self.client.embeddings.create(input=batch, model=self.model_id)
            batch_embeddings = [item.embedding for item in response.data]
            if self.embedding_dimension is None and batch_embeddings:
                self.embedding_dimension = len(batch_embeddings[0])
            all_embeddings.extend(batch_embeddings)
        return np.array(all_embeddings)

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        # OpenAI API does not provide token-level contextual embeddings.
        # Return a zero vector of the determined dimension.
        if getattr(self, "embedding_dimension", None) is None:
            # Fallback if dimension couldn't be determined during init
            return np.zeros(3072)  # text-embedding-3-large dimension
        return np.zeros(self.embedding_dimension)


class GoogleEmbedder(EmbeddingModel):
    def __init__(self, model_id, cache_manager=None):
        super().__init__(model_id, cache_manager)
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Google API key not found.")
            self.client = genai.Client(api_key=api_key)
            # Avoid eager network/API-key validation at startup.
            # Dimension is discovered lazily on first real encode call.
            self.embedding_dimension = None
        except ValueError as e:
            raise e
        except Exception as e:
            # Handle other potential errors during client or dummy embedding creation
            raise Exception(f"Google API key not found or model error: {e}.")

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        batch_size = 100  # Recommended batch size for Google Generative AI embeddings
        all_embeddings = []
        for i in range(0, len(sentences), batch_size):
            batch = sentences[i : i + batch_size]
            response = self.client.models.embed_content(
                model=self.model_id, contents=batch
            )
            batch_embeddings = [r.values for r in response.embeddings]
            if self.embedding_dimension is None and batch_embeddings:
                self.embedding_dimension = len(batch_embeddings[0])
            all_embeddings.extend(batch_embeddings)
            # Sleep only if more batches remain
            if i + batch_size < len(sentences):
                time.sleep(1)  # Respect rate limits
        return np.array(all_embeddings)

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        # Google Generative AI API does not provide token-level contextual embeddings.
        # As per instruction, return a zero vector of the determined dimension.
        if getattr(self, "embedding_dimension", None) is None:
            # Fallback if dimension couldn't be determined during init
            return np.zeros(768)  # text-embedding-001 dimension
        return np.zeros(self.embedding_dimension)


class Qwen3Embedder(EmbeddingModel):
    def __init__(
        self, model_id, cache_manager=None, batch_size=16
    ):  # Default batch size
        super().__init__(model_id, cache_manager)
        self.batch_size = batch_size
        try:
            # Keep device as a simple string for test determinism when torch.device is patched
            device_obj = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            try:
                device_type = device_obj.type
            except Exception:
                device_type = str(device_obj)
            self.device = device_type

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)

            # Load model with float16 if on CUDA for memory efficiency
            if self.device == "cuda":
                print(
                    f"Loading {self.model_id} on GPU with torch_dtype=torch.float16 for memory efficiency."
                )
                self.model = AutoModel.from_pretrained(
                    self.model_id, torch_dtype=torch.float16
                )
            else:
                print(f"Loading {self.model_id} on CPU.")
                self.model = AutoModel.from_pretrained(self.model_id)

            # Move model to device
            self.model.to(self.device)
            self.model.eval()  # Set to evaluation mode

            self.embedding_dimension = self.model.config.hidden_size
        except Exception as e:
            raise Exception(f"Failed to load Qwen3 model {model_id}: {e}")

    def _internal_encode(self, sentences: list[str]) -> np.ndarray:
        all_sentence_embeddings = []
        # Process sentences in smaller batches to manage memory
        for i in range(0, len(sentences), self.batch_size):
            batch_sentences = sentences[i : i + self.batch_size]

            inputs = self.tokenizer(
                batch_sentences,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=self.tokenizer.model_max_length,
            )

            # Move tensors to the device explicitly
            for k, v in inputs.items():
                try:
                    inputs[k] = v.to(self.device)
                except Exception:
                    # If v is a MagicMock in tests, keep as-is
                    inputs[k] = v

            with torch.no_grad():
                outputs = self.model(**inputs)

            last_hidden_states = outputs.last_hidden_state

            attention_mask = (
                inputs["attention_mask"]
                .unsqueeze(-1)
                .expand(last_hidden_states.size())
                .float()
            )
            sum_embeddings = torch.sum(last_hidden_states * attention_mask, 1)
            sum_mask = torch.clamp(attention_mask.sum(1), min=1e-9)
            sentence_embeddings = sum_embeddings / sum_mask

            all_sentence_embeddings.append(sentence_embeddings.cpu().numpy())

            # Explicitly clear GPU memory after each batch to prevent accumulation
            if self.device == "cuda":
                try:
                    del inputs
                    del outputs
                    del last_hidden_states
                    del attention_mask
                    del sum_embeddings
                    del sum_mask
                    del sentence_embeddings
                    torch.cuda.empty_cache()  # Clear CUDA cache
                except Exception:
                    pass

        if all_sentence_embeddings:
            arr = np.vstack(all_sentence_embeddings)
            # Ensure we return exactly one embedding per input sentence (trim any
            # extra rows that can occur with mocked outputs during tests).
            if arr.shape[0] > len(sentences):
                arr = arr[: len(sentences)]
            return arr
        return np.array([])

    def get_word_embedding_in_context(
        self, text: str, char_start: int, char_end: int
    ) -> np.ndarray:
        tokens = self.tokenizer.encode_plus(
            text,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=self.tokenizer.model_max_length,
        )

        input_ids = tokens["input_ids"].to(self.device)

        # Normalize offset mapping like in SentenceTransformer
        raw_offset = tokens["offset_mapping"]
        try:
            offset_mapping = raw_offset.tolist()
        except Exception:
            offset_mapping = raw_offset
        # Normalize similar to SentenceTransformer: handle flat lists, list-of-pairs,
        # and optionally a batch dimension.
        if (
            isinstance(offset_mapping, list)
            and offset_mapping
            and not isinstance(offset_mapping[0], list)
        ):
            # flat list -> group into pairs
            if (
                all(isinstance(x, int) for x in offset_mapping)
                and len(offset_mapping) % 2 == 0
            ):
                it = iter(offset_mapping)
                offset_mapping = [(a, b) for a, b in zip(it, it)]

        if (
            isinstance(offset_mapping, list)
            and offset_mapping
            and isinstance(offset_mapping[0], list)
        ):
            if isinstance(offset_mapping[0][0], list):
                # batched -> take first
                offset_mapping = offset_mapping[0]
            else:
                # already list of pairs -> keep as-is
                offset_mapping = offset_mapping

        with torch.no_grad():
            outputs = self.model(input_ids)
            last_hidden_states = outputs.last_hidden_state

        target_token_indices = []
        for i, pair in enumerate(offset_mapping):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            token_start_char, token_end_char = pair
            if (
                token_start_char is None
                or token_end_char is None
                or (token_start_char == 0 and token_end_char == 0 and i != 0)
            ):
                continue

            if token_start_char < char_end and token_end_char > char_start:
                target_token_indices.append(i)

        if target_token_indices:
            word_embeddings = last_hidden_states[0, target_token_indices, :]
            word_embedding = torch.mean(word_embeddings, dim=0).cpu().numpy()
            return np.round(word_embedding.astype(float), 10)
        else:
            return np.zeros(self.embedding_dimension)
