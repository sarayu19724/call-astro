"""
Cross-Encoder Re-Ranking Stage

Uses a lightweight Cross-Encoder model to accurately re-rank chunks retrieved
by the fast Hybrid Search (BM25 + Cosine). The Cross-Encoder sees the full
(query, passage) pair together, giving it vastly superior relevance judgement
compared to the bi-encoder similarity score from the initial retrieval pass.

Workflow:
  1. Hybrid Search retrieves Top-10 candidate chunks (fast, approximate)
  2. CrossEncoderReRanker scores all 10 pairs against the query (CPU, ~50ms)
  3. Only the Top-3 highest-scoring chunks are passed to the LLM prompt

Model choice: cross-encoder/ms-marco-MiniLM-L-6-v2
  - ~90MB, optimized for fast CPU inference
  - Trained on MS MARCO passage ranking (180M real query/passage relevance pairs)
  - No network calls at inference time -- model loaded once at startup
"""

from typing import List, Dict
from app.utils.logger import logger


class CrossEncoderReRanker:
    """
    Lazy-loading singleton wrapper around the cross-encoder model.
    The model is downloaded and initialized on the first call to rerank(),
    so it does not slow down server startup.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Load the CrossEncoder model on first use."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"[ReRanker] Loading Cross-Encoder model: {self.model_name}")
            self._model = CrossEncoder(self.model_name, max_length=512)
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
        top_k: int = 3,
    ) -> List[Dict]:
        """
        Re-rank a list of retrieved chunks against the query using the
        Cross-Encoder, and return the top_k most relevant ones.

        Each returned chunk has an additional 'rerank_score' field injected
        so the log and reasoning trace can show both the original hybrid score
        and the more accurate cross-encoder score.

        Falls back to original hybrid-score ordering if the model is unavailable.
        """
        if not chunks:
            return chunks

        # Ensure the model is loaded
        self._load_model()

        if self._model is None:
            logger.warning("[ReRanker] Model unavailable -- returning top_k by hybrid score.")
            return chunks[:top_k]

        try:
            # Build (query, passage) pairs
            pairs = [[query, chunk["text"]] for chunk in chunks]

            # Predict relevance scores -- higher is more relevant
            scores = self._model.predict(pairs)

            # Inject rerank_score into each chunk dict
            scored_chunks = []
            for chunk, score in zip(chunks, scores):
                chunk = chunk.copy()  # do not mutate original
                chunk["rerank_score"] = float(score)
                scored_chunks.append(chunk)

            # Sort descending by cross-encoder score
            scored_chunks.sort(key=lambda c: c["rerank_score"], reverse=True)

            # Log the re-ranking results for observability
            logger.info(f"[ReRanker] Re-ranked {len(chunks)} chunks -> keeping top {top_k}")
            for i, c in enumerate(scored_chunks[:top_k]):
                logger.info(
                    f"[ReRanker]   #{i+1} rerank={c['rerank_score']:.3f} "
                    f"hybrid={c.get('score', 0):.3f} "
                    f"source={c['metadata'].get('source', 'Unknown')}"
                )

            return scored_chunks[:top_k]

        except Exception as e:
            logger.error(f"[ReRanker] Re-ranking failed: {e} -- falling back to hybrid score order.")
            return chunks[:top_k]


# Module-level singleton -- loaded once, reused across all requests
reranker = CrossEncoderReRanker()
