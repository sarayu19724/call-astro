import os
import json
import pickle
import numpy as np
from typing import List, Dict, Tuple, Optional
from app.config.settings import settings
from app.utils.logger import logger

class LocalVectorStore:
    def __init__(self, data_dir: str = settings.VECTOR_DB_DIR):
        self.data_dir = data_dir
        self.chunks_path = os.path.join(data_dir, "chunks.json")
        self.vectors_path = os.path.join(data_dir, "vectors.npy")

        self.chunks: List[Dict] = []
        self.vectors: Optional[np.ndarray] = None

        self.load()

    def load(self):
        logger.info(f"[VectorStore] data_dir = {self.data_dir}")
        logger.info(f"[VectorStore] chunks_path = {self.chunks_path}")
        logger.info(f"[VectorStore] vectors_path = {self.vectors_path}")

        try:
            if os.path.exists(self.chunks_path) and os.path.exists(self.vectors_path):
              with open(self.chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)

              self.vectors = np.load(self.vectors_path)

              logger.info(
                f"[VectorStore] Loaded {len(self.chunks)} chunks and vectors from local cache."
             )
            else:
              logger.warning(
                "[VectorStore] VECTOR STORE NOT FOUND — starting with empty store."
            )
              self.chunks = []
              self.vectors = None

        except Exception as e:
            logger.error(f"[VectorStore] Error loading vector store: {e}")
            self.chunks = []
            self.vectors = None

    def save(self):
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.chunks_path, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f, ensure_ascii=False, indent=2)
            if self.vectors is not None:
                np.save(self.vectors_path, self.vectors)
            logger.info(f"Successfully saved {len(self.chunks)} chunks to {self.data_dir}")
        except Exception as e:
            logger.error(f"Failed to save vector store: {e}")
            raise

    def clear(self):
        self.chunks = []
        self.vectors = None
        if os.path.exists(self.chunks_path):
            os.remove(self.chunks_path)
        if os.path.exists(self.vectors_path):
            os.remove(self.vectors_path)
        logger.info("Cleared vector store cache.")

    def add_documents(self, texts: List[str], metadatas: List[Dict], embeddings: List[List[float]]):
        if not texts or not embeddings:
            return
        new_chunks = [{"text": t, "metadata": m} for t, m in zip(texts, metadatas)]
        new_vectors = np.array(embeddings, dtype=np.float32)
        if self.vectors is None:
            self.chunks = new_chunks
            self.vectors = new_vectors
        else:
            self.chunks.extend(new_chunks)
            self.vectors = np.vstack([self.vectors, new_vectors])
        self.save()

    def _lexical_score(self, text: str, query_tokens: List[str]) -> float:
        if not query_tokens:
            return 0.0
        text_lower = text.lower()
        score = 0.0
        for token in query_tokens:
            count = text_lower.count(token)
            if count > 0:
                score += 1.0 + np.log(count)
        return score / (np.log(len(text_lower)) + 1.0)

    def hybrid_search(self, query: str, query_vector: List[float], top_k: int = 5,
                       alpha: float = 0.5, preferred_sources: Optional[List[str]] = None,
                       boost_factor: float = 1.4) -> List[Dict]:
        """Combined semantic + lexical search. If preferred_sources is given,
        chunks from those source files get a scoring boost — they are NOT
        the only chunks searchable, the whole store stays in play (per your
        architecture principle: 'the entire knowledge base should remain
        searchable', TOPIC_RELEVANT_BOOKS is a preference, not a filter)."""
        if not self.chunks or self.vectors is None:
            return []

        q_vec = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        v_norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        v_norms[v_norms == 0] = 1.0
        normalized_vectors = self.vectors / v_norms
        cosine_scores = np.dot(normalized_vectors, q_vec)

        min_cos, max_cos = cosine_scores.min(), cosine_scores.max()
        range_cos = max_cos - min_cos
        norm_semantic_scores = (cosine_scores - min_cos) / range_cos if range_cos > 0 else np.ones_like(cosine_scores)

        stop_words = {"a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on", "at", "by", "for", "with", "is", "are", "was", "were", "be", "been", "being"}
        query_tokens = [t.lower() for t in query.split() if t.lower() not in stop_words and len(t) > 1]
        lexical_scores = np.array([self._lexical_score(chunk["text"], query_tokens) for chunk in self.chunks])

        min_lex, max_lex = lexical_scores.min(), lexical_scores.max()
        range_lex = max_lex - min_lex
        norm_lexical_scores = (lexical_scores - min_lex) / range_lex if range_lex > 0 else np.zeros_like(lexical_scores)

        combined_scores = alpha * norm_semantic_scores + (1 - alpha) * norm_lexical_scores

        if preferred_sources:
            preferred_lower = {s.lower() for s in preferred_sources}
            for i, chunk in enumerate(self.chunks):
                source = chunk.get("metadata", {}).get("source", "")
                source_stem = source.rsplit(".", 1)[0].lower()
                if any(pref in source_stem or source_stem in pref for pref in preferred_lower):
                    combined_scores[i] *= boost_factor

        top_indices = np.argsort(combined_scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            chunk = self.chunks[idx].copy()
            chunk["score"] = float(combined_scores[idx])
            chunk["semantic_score"] = float(cosine_scores[idx])
            chunk["lexical_score"] = float(lexical_scores[idx])
            results.append(chunk)

        return results

    def dual_retrieve(self, topic_query: str, global_query: str, query_vector_topic: List[float],
                       query_vector_global: List[float], preferred_sources: Optional[List[str]] = None,
                       top_k_each: int = 6, final_top_k: int = 6, alpha: float = 0.5) -> List[Dict]:
        """Implements: Topic-preferred Search + Global Search → Merge +
        Deduplicate → Rerank → Best Relevant Chunks (per your architecture
        diagram). Two retrieval passes:
          1. topic_query, boosted toward preferred_sources (if any)
          2. global_query (usually the raw user message), unboosted — covers
             the whole knowledge base without topic bias, so a good chunk
             from an unrelated-seeming book isn't excluded just because it
             wasn't in TOPIC_RELEVANT_BOOKS.
        Results are merged, deduplicated by (source, chunk_index), then
        reranked by combined_score across the merged set."""
        topic_hits = self.hybrid_search(
            query=topic_query, query_vector=query_vector_topic,
            top_k=top_k_each, alpha=alpha, preferred_sources=preferred_sources
        ) if preferred_sources else []

        global_hits = self.hybrid_search(
            query=global_query, query_vector=query_vector_global,
            top_k=top_k_each, alpha=alpha, preferred_sources=None
        )

        merged: Dict[Tuple[str, int], Dict] = {}
        for hit in topic_hits + global_hits:
            source = hit.get("metadata", {}).get("source", "unknown")
            chunk_idx = hit.get("metadata", {}).get("chunk_index", -1)
            key = (source, chunk_idx)
            # Deduplicate: if this exact chunk appeared in both passes,
            # keep whichever scored higher (it may have been boosted in
            # the topic pass, which is a meaningful signal to keep).
            if key not in merged or hit["score"] > merged[key]["score"]:
                merged[key] = hit

        reranked = sorted(merged.values(), key=lambda h: h["score"], reverse=True)
        return reranked[:final_top_k]

vector_store = LocalVectorStore()