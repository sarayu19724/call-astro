"""
Cross-Encoder Re-Ranking Stage

Uses a lightweight Cross-Encoder model to accurately re-rank chunks retrieved
by the fast Hybrid Search (BM25 + Cosine). The Cross-Encoder sees the full
(query, passage) pair together, giving it a stronger relevance judgement than
the initial bi-encoder similarity score.

Workflow:
  1. Hybrid Search retrieves candidate chunks
  2. CrossEncoderReRanker scores the query/passage pairs
  3. The highest-scoring chunks are passed to the evidence pipeline

Model choice: cross-encoder/ms-marco-MiniLM-L-6-v2
  - ~90MB
  - CPU-compatible
  - Model is loaded once and reused for subsequent requests
"""

import os
import threading
import time
from typing import List, Dict

from app.utils.logger import logger


class CrossEncoderReRanker:
    """
    Lazy-loading singleton wrapper around the cross-encoder model.

    The model is downloaded and initialized on the first call to rerank(),
    then reused for all subsequent requests in the same backend process.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._load_lock = threading.Lock()

    def _load_model(self):
        """Load the CrossEncoder model once, safely across concurrent requests."""
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    f"[ReRanker] Loading Cross-Encoder model: {self.model_name}"
                )

                # Limit PyTorch CPU thread oversubscription on small Railway
                # containers. Too many threads can make tiny inference batches
                # unexpectedly slow.
                try:
                    import torch
                    cpu_count = os.cpu_count() or 1
                    torch.set_num_threads(min(4, cpu_count))
                    torch.set_num_interop_threads(1)
                except Exception as thread_err:
                    logger.warning(
                        f"[ReRanker] Could not tune PyTorch CPU threads: {thread_err}"
                    )

                self._model = CrossEncoder(
                    self.model_name,
                    max_length=512,
                    device="cpu",
                )

                logger.info("[ReRanker] Cross-Encoder model loaded successfully.")

            except ImportError:
                logger.error(
                    "[ReRanker] sentence-transformers not installed. "
                    "CrossEncoder re-ranking disabled."
                )
                self._model = None

            except Exception as e:
                logger.error(f"[ReRanker] Failed to load Cross-Encoder model: {e}")
                self._model = None

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = 6,
    ) -> List[Dict]:
        """
        Re-rank retrieved chunks against the query using the Cross-Encoder.

        The original hybrid score is preserved as `score`; the Cross-Encoder
        score is stored as `rerank_score`.

        Falls back to the original hybrid ordering if the model is unavailable
        or inference fails.
        """
        if not chunks:
            return []

        top_k = max(1, min(top_k, len(chunks)))

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

            start = time.perf_counter()

            scores = self._model.predict(
                pairs,
                batch_size=min(8, len(pairs)),
                show_progress_bar=False,
            )

            elapsed = time.perf_counter() - start
            logger.info(
                f"[ReRanker] Cross-Encoder inference: {len(pairs)} pairs "
                f"in {elapsed:.3f}s"
            )

            scored_chunks = []
            for chunk, score in zip(chunks, scores):
                scored = chunk.copy()
                scored["rerank_score"] = float(score)
                scored_chunks.append(scored)

            scored_chunks.sort(
                key=lambda c: c["rerank_score"],
                reverse=True,
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


# Module-level singleton -- loaded once and reused across all requests
reranker = CrossEncoderReRanker()