import os
import json
import time
import numpy as np
from typing import List, Dict, Tuple, Optional
from app.config.settings import settings
from app.utils.logger import logger


def _profile(label: str, start: float):
    elapsed = time.perf_counter() - start
    logger.info(f"[Profile][VectorStore] {label}: {elapsed:.3f}s")
    return elapsed


class LocalVectorStore:
    def __init__(self, data_dir: str = settings.VECTOR_DB_DIR):
        self.data_dir = data_dir
        self.chunks_path = os.path.join(data_dir, "chunks.json")
        self.vectors_path = os.path.join(data_dir, "vectors.npy")

        self.chunks: List[Dict] = []
        self.vectors: Optional[np.ndarray] = None
        self._chunk_lookup: Dict[Tuple[str, int], int] = {}

        self.load()

    def _build_chunk_lookup(self):
        """Maps (source, chunk_index) -> position in self.chunks, so
        parent-child context expansion can find neighboring chunks in O(1)
        instead of scanning the whole store per lookup."""
        t0 = time.perf_counter()
        self._chunk_lookup = {}
        for i, chunk in enumerate(self.chunks):
            meta = chunk.get("metadata", {})
            source = meta.get("source")
            idx = meta.get("chunk_index")
            if source is not None and idx is not None:
                self._chunk_lookup[(source, idx)] = i
        _profile("build_chunk_lookup", t0)

    def load(self):
        try:
            if os.path.exists(self.chunks_path) and os.path.exists(self.vectors_path):
                with open(self.chunks_path, "r", encoding="utf-8") as f:
                    self.chunks = json.load(f)
                self.vectors = np.load(self.vectors_path)
                logger.info(f"Loaded {len(self.chunks)} chunks and vectors from local cache.")
            else:
                logger.info("No vector store found. Initialising an empty store.")
                self.chunks = []
                self.vectors = None
        except Exception as e:
            logger.error(f"Error loading vector store: {e}. Starting fresh.")
            self.chunks = []
            self.vectors = None
        self._build_chunk_lookup()

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
        self._chunk_lookup = {}
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
        self._build_chunk_lookup()

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
        t_total = time.perf_counter()

        if not self.chunks or self.vectors is None:
            return []

        t = time.perf_counter()
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
        _profile("vector_search (semantic)", t)

        t = time.perf_counter()
        stop_words = {"a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on", "at", "by", "for", "with", "is", "are", "was", "were", "be", "been", "being"}
        query_tokens = [tok.lower() for tok in query.split() if tok.lower() not in stop_words and len(tok) > 1]
        lexical_scores = np.array([self._lexical_score(chunk["text"], query_tokens) for chunk in self.chunks])

        min_lex, max_lex = lexical_scores.min(), lexical_scores.max()
        range_lex = max_lex - min_lex
        norm_lexical_scores = (lexical_scores - min_lex) / range_lex if range_lex > 0 else np.zeros_like(lexical_scores)
        _profile("keyword_search (lexical)", t)

        t = time.perf_counter()
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
        _profile("reranking (combine+sort+boost)", t)

        _profile(f"hybrid_search TOTAL (query='{query[:40]}...', top_k={top_k})", t_total)
        return results

    def dual_retrieve(self, topic_query: str, global_query: str, query_vector_topic: List[float],
                       query_vector_global: List[float], preferred_sources: Optional[List[str]] = None,
                       top_k_each: int = 6, final_top_k: int = 6, alpha: float = 0.5) -> List[Dict]:
        t_total = time.perf_counter()

        t = time.perf_counter()
        topic_hits = self.hybrid_search(
            query=topic_query, query_vector=query_vector_topic,
            top_k=top_k_each, alpha=alpha, preferred_sources=preferred_sources
        ) if preferred_sources else []
        _profile("dual_retrieve: topic-preferred pass", t)

        t = time.perf_counter()
        global_hits = self.hybrid_search(
            query=global_query, query_vector=query_vector_global,
            top_k=top_k_each, alpha=alpha, preferred_sources=None
        )
        _profile("dual_retrieve: global pass", t)

        t = time.perf_counter()
        merged: Dict[Tuple[str, int], Dict] = {}
        for hit in topic_hits + global_hits:
            source = hit.get("metadata", {}).get("source", "unknown")
            chunk_idx = hit.get("metadata", {}).get("chunk_index", -1)
            key = (source, chunk_idx)
            if key not in merged or hit["score"] > merged[key]["score"]:
                merged[key] = hit

        reranked = sorted(merged.values(), key=lambda h: h["score"], reverse=True)
        result = reranked[:final_top_k]
        _profile("dual_retrieve: merge+dedupe+rerank", t)

        _profile(f"dual_retrieve TOTAL (final_top_k={final_top_k})", t_total)
        return result

    # ------------------------------------------------------------------
    # PARENT-CHILD / CONTEXT EXPANSION
    # ------------------------------------------------------------------
    def expand_with_context(self, hits: List[Dict], window: int = 1, top_n: int = 3) -> List[Dict]:
        """Adds a 'prompt_text' field to the top_n hits (already ranked and
        deduped by the CALLER — this must run AFTER dedup, never before, or
        overlapping neighbor text makes adjacent hits look like near-
        duplicates and breaks similarity-based dedup) containing the
        matched chunk plus up to `window` chunks immediately before/after
        it from the SAME source document. Hits beyond top_n, or hits with
        no chunk_index/source, are returned unchanged with prompt_text
        falling back to their original 'text'.

        Expects each hit dict to have "source", "chunk_index", and "text"
        keys (the caller's own shaped hit format, not the raw vector_store
        chunk format) — this keeps vector_store's public API decoupled
        from chat_service's internal hit-dict shape while still allowing
        lookups against the internal self._chunk_lookup index.
        """
        t0 = time.perf_counter()
        if not hits:
            return hits

        expanded = []
        for i, hit in enumerate(hits):
            if i >= top_n:
                hit = dict(hit)
                hit["prompt_text"] = hit.get("text", "")
                expanded.append(hit)
                continue

            source = hit.get("source")
            idx = hit.get("chunk_index")

            if source is None or idx is None:
                hit = dict(hit)
                hit["prompt_text"] = hit.get("text", "")
                expanded.append(hit)
                continue

            neighbor_texts: List[Tuple[int, str]] = []
            for offset in range(-window, window + 1):
                if offset == 0:
                    continue
                pos = self._chunk_lookup.get((source, idx + offset))
                if pos is not None:
                    neighbor_texts.append((offset, self.chunks[pos]["text"]))

            hit = dict(hit)
            if neighbor_texts:
                neighbor_texts.sort(key=lambda x: x[0])
                before = [text for offset, text in neighbor_texts if offset < 0]
                after = [text for offset, text in neighbor_texts if offset > 0]
                combined = before + [hit.get("text", "")] + after
                hit["prompt_text"] = "\n".join(combined)
                hit["context_expanded"] = True
            else:
                hit["prompt_text"] = hit.get("text", "")

            expanded.append(hit)

        _profile(f"context_expansion (top_n={top_n}, window={window})", t0)
        return expanded


vector_store = LocalVectorStore()