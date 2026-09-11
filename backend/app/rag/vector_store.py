import os
import json
import threading
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple, Optional

from app.config.settings import settings
from app.utils.logger import logger


VECTOR_STORE_V2_ACTIVE = True


# ---------------------------------------------------------------------------
# Cross-Encoder Re-Ranker
# ---------------------------------------------------------------------------
# Hybrid search remains the first-stage retriever.
# The Cross-Encoder is a second-stage relevance judge over the merged
# candidate set. If sentence-transformers/model loading is unavailable,
# retrieval automatically falls back to the existing hybrid-score ordering.
#
# This keeps the user's existing RAG pipeline intact:
# Hybrid Search -> Merge/Deduplicate -> Cross-Encoder -> Final Evidence
# ---------------------------------------------------------------------------

class CrossEncoderReRanker:
    """
    Lazy-loading Cross-Encoder wrapper.

    The model is loaded only on first rerank() call, so server startup is not
    blocked by model initialization.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ):
        self.model_name = model_name
        self._model = None
        self._load_lock = threading.Lock()

    def _load_model(self):
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    f"[ReRanker] Loading Cross-Encoder model: "
                    f"{self.model_name}"
                )

                self._model = CrossEncoder(
                    self.model_name,
                    max_length=512
                )

                logger.info(
                    "[ReRanker] Cross-Encoder model loaded successfully."
                )

            except ImportError:
                logger.error(
                    "[ReRanker] sentence-transformers is not installed. "
                    "Cross-Encoder re-ranking disabled."
                )
                self._model = None

            except Exception as e:
                logger.error(
                    f"[ReRanker] Failed to load Cross-Encoder model: {e}"
                )
                self._model = None

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = 6,
    ) -> List[Dict]:
        """
        Re-rank retrieved chunks using the Cross-Encoder.

        The original hybrid score is preserved as `score`; the Cross-Encoder
        result is stored separately as `rerank_score`.
        """
        if not chunks:
            return []

        self._load_model()

        if self._model is None:
            logger.warning(
                "[ReRanker] Model unavailable -- "
                "returning chunks in hybrid-score order."
            )
            return chunks[:top_k]

        try:
            pairs = [
                [query, chunk.get("text", "")]
                for chunk in chunks
            ]

            scores = self._model.predict(pairs)

            scored_chunks = []

            for chunk, score in zip(chunks, scores):
                scored = chunk.copy()
                scored["rerank_score"] = float(score)
                scored_chunks.append(scored)

            scored_chunks.sort(
                key=lambda c: c["rerank_score"],
                reverse=True
            )

            logger.info(
                f"[ReRanker] Re-ranked {len(chunks)} candidates "
                f"-> keeping top {top_k}"
            )

            for i, chunk in enumerate(scored_chunks[:top_k]):
                metadata = chunk.get("metadata", {})

                logger.info(
                    f"[ReRanker] #{i + 1} "
                    f"rerank={chunk['rerank_score']:.3f} "
                    f"hybrid={chunk.get('score', 0):.3f} "
                    f"source={metadata.get('source', 'Unknown')}"
                )

            return scored_chunks[:top_k]

        except Exception as e:
            logger.error(
                f"[ReRanker] Re-ranking failed: {e} -- "
                "falling back to hybrid score order."
            )
            return chunks[:top_k]


reranker = CrossEncoderReRanker()


# ---------------------------------------------------------------------------
# Local Vector Store
# ---------------------------------------------------------------------------

class LocalVectorStore:
    def __init__(self, data_dir: str = settings.VECTOR_DB_DIR):
        self.data_dir = data_dir
        self.chunks_path = os.path.join(data_dir, "chunks.json")
        self.vectors_path = os.path.join(data_dir, "vectors.npy")

        self.chunks: List[Dict] = []
        self.vectors: Optional[np.ndarray] = None

        # Normalized-vector cache avoids recalculating vector norms on every
        # query.
        self._normalized_vectors: Optional[np.ndarray] = None
        self._norm_lock = threading.Lock()

        # Used to protect against embedding-model dimension mismatches.
        self._embedding_dim: Optional[int] = None

        logger.info(
            "[VectorStore] VECTOR_STORE_V2_ACTIVE — "
            "dimension-mismatch guard enabled"
        )

        self.load()

    def _rebuild_normalized_cache(self):
        with self._norm_lock:
            if self.vectors is None or len(self.vectors) == 0:
                self._normalized_vectors = None
                self._embedding_dim = None
                return

            v_norms = np.linalg.norm(
                self.vectors,
                axis=1,
                keepdims=True
            )

            v_norms[v_norms == 0] = 1.0

            self._normalized_vectors = self.vectors / v_norms
            self._embedding_dim = self.vectors.shape[1]

    def get_embedding_dim(self) -> Optional[int]:
        """Return the dimensionality the on-disk store was built with."""
        return self._embedding_dim

    def load(self):
        logger.info(f"[VectorStore] data_dir = {self.data_dir}")
        logger.info(
            f"[VectorStore] chunks_path = {self.chunks_path}"
        )
        logger.info(
            f"[VectorStore] vectors_path = {self.vectors_path}"
        )

        try:
            if (
                os.path.exists(self.chunks_path)
                and os.path.exists(self.vectors_path)
            ):
                with open(
                    self.chunks_path,
                    "r",
                    encoding="utf-8"
                ) as f:
                    self.chunks = json.load(f)

                self.vectors = np.load(self.vectors_path)

                logger.info(
                    f"[VectorStore] Loaded {len(self.chunks)} chunks "
                    f"and vectors "
                    f"(dim={self.vectors.shape[1] if self.vectors is not None and self.vectors.ndim == 2 else 'unknown'}) "
                    f"from local cache."
                )

            else:
                logger.warning(
                    "[VectorStore] VECTOR STORE NOT FOUND — "
                    "starting with empty store."
                )

                self.chunks = []
                self.vectors = None

        except Exception as e:
            logger.error(
                f"[VectorStore] Error loading vector store: {e}"
            )

            self.chunks = []
            self.vectors = None

        self._rebuild_normalized_cache()

    def save(self):
        try:
            os.makedirs(
                self.data_dir,
                exist_ok=True
            )

            with open(
                self.chunks_path,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    self.chunks,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            if self.vectors is not None:
                np.save(
                    self.vectors_path,
                    self.vectors
                )

            logger.info(
                f"Successfully saved {len(self.chunks)} chunks "
                f"to {self.data_dir}"
            )

        except Exception as e:
            logger.error(
                f"Failed to save vector store: {e}"
            )
            raise

    def clear(self):
        self.chunks = []
        self.vectors = None
        self._normalized_vectors = None
        self._embedding_dim = None

        if os.path.exists(self.chunks_path):
            os.remove(self.chunks_path)

        if os.path.exists(self.vectors_path):
            os.remove(self.vectors_path)

        logger.info(
            "Cleared vector store cache."
        )

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict],
        embeddings: List[List[float]]
    ):
        if not texts or not embeddings:
            return

        new_vectors = np.array(
            embeddings,
            dtype=np.float32
        )

        if (
            self.vectors is not None
            and self.vectors.size > 0
        ):
            existing_dim = self.vectors.shape[1]
            new_dim = (
                new_vectors.shape[1]
                if new_vectors.ndim == 2
                else None
            )

            if (
                new_dim is not None
                and new_dim != existing_dim
            ):
                raise ValueError(
                    f"[VectorStore] Refusing to add "
                    f"{new_dim}-dim embeddings to a store built "
                    f"with {existing_dim}-dim vectors. This means "
                    f"EMBEDDING_PROVIDER or OLLAMA_EMBED_MODEL/"
                    f"LOCAL_EMBEDDING_MODEL in settings.py/.env "
                    f"changed since this knowledge base was last "
                    f"indexed. Fix your embedding config to match "
                    f"what the store was built with, OR wipe and "
                    f"rebuild the whole index with "
                    f"document_indexer.ingest_knowledge_base("
                    f"force_rebuild=True) using the NEW config."
                )

        new_chunks = [
            {
                "text": text,
                "metadata": metadata
            }
            for text, metadata in zip(
                texts,
                metadatas
            )
        ]

        if self.vectors is None:
            self.chunks = new_chunks
            self.vectors = new_vectors

        else:
            self.chunks.extend(new_chunks)

            self.vectors = np.vstack(
                [
                    self.vectors,
                    new_vectors
                ]
            )

        self._rebuild_normalized_cache()
        self.save()

    def _lexical_score(
        self,
        text: str,
        query_tokens: List[str]
    ) -> float:
        if not query_tokens:
            return 0.0

        text_lower = text.lower()
        score = 0.0

        for token in query_tokens:
            count = text_lower.count(token)

            if count > 0:
                score += 1.0 + np.log(count)

        return score / (
            np.log(len(text_lower)) + 1.0
        )

    def _check_dim_match(
        self,
        query_vector: List[float]
    ) -> bool:
        """
        Check that the query embedding dimensionality matches the
        indexed knowledge base.
        """
        if self._embedding_dim is None:
            return True

        query_dim = (
            len(query_vector)
            if query_vector is not None
            else 0
        )

        if query_dim != self._embedding_dim:
            logger.error(
                f"[VectorStore] EMBEDDING DIMENSION MISMATCH: "
                f"the knowledge base index was built with "
                f"{self._embedding_dim}-dim vectors, but the "
                f"current query embedding is {query_dim}-dim. "
                f"This means EMBEDDING_PROVIDER "
                f"(currently '{settings.EMBEDDING_PROVIDER}') "
                f"or the embedding model "
                f"(OLLAMA_EMBED_MODEL='{settings.OLLAMA_EMBED_MODEL}', "
                f"LOCAL_EMBEDDING_MODEL='{settings.LOCAL_EMBEDDING_MODEL}') "
                f"was changed AFTER the knowledge base was indexed. "
                f"RAG retrieval will return NO results until you "
                f"either revert the embedding configuration or wipe "
                f"and re-index the knowledge base."
            )

            return False

        return True

    def hybrid_search(
        self,
        query: str,
        query_vector: List[float],
        top_k: int = 5,
        alpha: float = 0.5,
        preferred_sources: Optional[List[str]] = None,
        boost_factor: float = 1.4
    ) -> List[Dict]:
        """
        Combined semantic + lexical search.

        Preferred sources receive a boost but the entire knowledge base
        remains searchable.
        """
        if (
            not self.chunks
            or self.vectors is None
            or self._normalized_vectors is None
        ):
            return []

        if not self._check_dim_match(query_vector):
            return []

        q_vec = np.array(
            query_vector,
            dtype=np.float32
        )

        q_norm = np.linalg.norm(q_vec)

        if q_norm > 0:
            q_vec = q_vec / q_norm

        cosine_scores = np.dot(
            self._normalized_vectors,
            q_vec
        )

        min_cos = cosine_scores.min()
        max_cos = cosine_scores.max()
        range_cos = max_cos - min_cos

        norm_semantic_scores = (
            (cosine_scores - min_cos) / range_cos
            if range_cos > 0
            else np.ones_like(cosine_scores)
        )

        stop_words = {
            "a", "an", "the", "and", "or", "but",
            "if", "then", "of", "to", "in", "on",
            "at", "by", "for", "with", "is", "are",
            "was", "were", "be", "been", "being"
        }

        query_tokens = [
            token.lower()
            for token in query.split()
            if (
                token.lower() not in stop_words
                and len(token) > 1
            )
        ]

        lexical_scores = np.array([
            self._lexical_score(
                chunk["text"],
                query_tokens
            )
            for chunk in self.chunks
        ])

        min_lex = lexical_scores.min()
        max_lex = lexical_scores.max()
        range_lex = max_lex - min_lex

        norm_lexical_scores = (
            (lexical_scores - min_lex) / range_lex
            if range_lex > 0
            else np.zeros_like(lexical_scores)
        )

        combined_scores = (
            alpha * norm_semantic_scores
            + (1 - alpha) * norm_lexical_scores
        )

        if preferred_sources:
            preferred_lower = {
                source.lower()
                for source in preferred_sources
            }

            for i, chunk in enumerate(self.chunks):
                source = (
                    chunk
                    .get("metadata", {})
                    .get("source", "")
                )

                source_stem = (
                    source
                    .rsplit(".", 1)[0]
                    .lower()
                )

                if any(
                    pref in source_stem
                    or source_stem in pref
                    for pref in preferred_lower
                ):
                    combined_scores[i] *= boost_factor

        top_indices = np.argsort(
            combined_scores
        )[::-1][:top_k]

        results = []

        for idx in top_indices:
            chunk = self.chunks[idx].copy()

            chunk["score"] = float(
                combined_scores[idx]
            )

            chunk["semantic_score"] = float(
                cosine_scores[idx]
            )

            chunk["lexical_score"] = float(
                lexical_scores[idx]
            )

            results.append(chunk)

        return results

    def dual_retrieve(
        self,
        topic_query: str,
        global_query: str,
        query_vector_topic: List[float],
        query_vector_global: List[float],
        preferred_sources: Optional[List[str]] = None,
        top_k_each: int = 6,
        final_top_k: int = 6,
        alpha: float = 0.5
    ) -> List[Dict]:
        """
        Two-stage retrieval:

        1. Topic-preferred hybrid search
        2. Global hybrid search
        3. Merge and exact-chunk deduplication
        4. Cross-Encoder second-stage reranking
        5. Return final evidence

        The Cross-Encoder is deliberately applied AFTER both retrieval
        passes have been merged, so it judges the complete candidate set.
        """

        def _run_topic():
            if not preferred_sources:
                return []

            return self.hybrid_search(
                query=topic_query,
                query_vector=query_vector_topic,
                top_k=top_k_each,
                alpha=alpha,
                preferred_sources=preferred_sources
            )

        def _run_global():
            return self.hybrid_search(
                query=global_query,
                query_vector=query_vector_global,
                top_k=top_k_each,
                alpha=alpha,
                preferred_sources=None
            )

        # Preserve the user's existing parallel retrieval optimization.
        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:

            topic_future = executor.submit(
                _run_topic
            )

            global_future = executor.submit(
                _run_global
            )

            topic_hits = topic_future.result()
            global_hits = global_future.result()

        # Preserve exact-chunk deduplication.
        merged: Dict[
            Tuple[str, int],
            Dict
        ] = {}

        for hit in topic_hits + global_hits:
            source = (
                hit
                .get("metadata", {})
                .get("source", "unknown")
            )

            chunk_idx = (
                hit
                .get("metadata", {})
                .get("chunk_index", -1)
            )

            key = (
                source,
                chunk_idx
            )

            if (
                key not in merged
                or hit["score"] > merged[key]["score"]
            ):
                merged[key] = hit

        candidates = sorted(
            merged.values(),
            key=lambda hit: hit["score"],
            reverse=True
        )

        if not candidates:
            return []

        
        reranked = reranker.rerank(
            query=global_query,
            chunks=candidates,
            top_k=final_top_k
        )

        return reranked


vector_store = LocalVectorStore()