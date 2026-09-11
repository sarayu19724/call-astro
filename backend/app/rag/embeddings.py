import hashlib
import requests
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from app.config.settings import settings
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------
# Bounded LRU cache keyed by provider, model, and exact text.
# Prevents repeated embedding calls for identical queries/chunks.
_CACHE_MAX_ENTRIES = 1000

_embedding_cache: "OrderedDict[str, List[float]]" = OrderedDict()
_cache_lock = threading.Lock()


# Conservative parallelism for Ollama.
OLLAMA_BATCH_WORKERS = 4


def _cache_key(provider: str, model: str, text: str) -> str:
    h = hashlib.sha1(
        f"{provider}|{model}|{text}".encode("utf-8")
    ).hexdigest()
    return h


def _cache_get(key: str) -> Optional[List[float]]:
    with _cache_lock:
        value = _embedding_cache.get(key)

        if value is not None:
            _embedding_cache.move_to_end(key)

        return value


def _cache_put(key: str, value: List[float]) -> None:
    with _cache_lock:
        _embedding_cache[key] = value
        _embedding_cache.move_to_end(key)

        while len(_embedding_cache) > _CACHE_MAX_ENTRIES:
            _embedding_cache.popitem(last=False)


class EmbeddingsProvider:
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER.lower()
        self.ollama_host = settings.OLLAMA_HOST
        self.ollama_model = settings.OLLAMA_EMBED_MODEL
        self.local_model_name = settings.LOCAL_EMBEDDING_MODEL
        self.local_model = None

        logger.info(
            f"Embeddings provider initialised with mode: {self.provider}"
        )

        if self.provider == "local":
            self._load_local_model()

    def _load_local_model(self):
        """Load the local SentenceTransformer embedding model."""
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                f"Loading local SentenceTransformer model: "
                f"{self.local_model_name}"
            )

            # Keep friend's explicit CPU configuration.
            self.local_model = SentenceTransformer(
                self.local_model_name,
                device="cpu"
            )

            logger.info(
                "Local SentenceTransformer model loaded successfully."
            )

        except ImportError as e:
            logger.error(
                "sentence-transformers is not installed. "
                "Add 'sentence-transformers' to requirements.txt "
                "or set EMBEDDING_PROVIDER=ollama."
            )

            raise ImportError(
                "sentence-transformers is required when "
                "EMBEDDING_PROVIDER=local."
            ) from e

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate an embedding vector for one text string.

        Uses the bounded cache first so repeated queries do not require
        another local-model inference or Ollama network request.
        """
        if not text:
            return []

        model_name = (
            self.ollama_model
            if self.provider == "ollama"
            else self.local_model_name
        )

        key = _cache_key(
            self.provider,
            model_name,
            text
        )

        cached = _cache_get(key)

        if cached is not None:
            return cached

        if self.provider == "local":
            if self.local_model is None:
                self._load_local_model()

            vector = self.local_model.encode(
                text,
                convert_to_numpy=True
            ).tolist()

        elif self.provider == "ollama":
            vector = self._get_ollama_embedding(text)

        else:
            raise ValueError(
                f"Unknown embedding provider: {self.provider}"
            )

        _cache_put(key, vector)

        return vector

    def get_embeddings_parallel(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate multiple independent embeddings concurrently.

        Cached texts are returned immediately. Uncached texts are processed
        concurrently while preserving the original input order.
        """
        if not texts:
            return []

        if len(texts) == 1:
            return [self.get_embedding(texts[0])]

        results: List[Optional[List[float]]] = [None] * len(texts)
        to_fetch = []

        model_name = (
            self.ollama_model
            if self.provider == "ollama"
            else self.local_model_name
        )

        for i, text in enumerate(texts):
            if not text:
                results[i] = []
                continue

            key = _cache_key(
                self.provider,
                model_name,
                text
            )

            cached = _cache_get(key)

            if cached is not None:
                results[i] = cached
            else:
                to_fetch.append(i)

        if to_fetch:
            workers = min(
                OLLAMA_BATCH_WORKERS,
                len(to_fetch)
            )

            with ThreadPoolExecutor(
                max_workers=workers
            ) as executor:

                future_to_idx = {
                    executor.submit(
                        self.get_embedding,
                        texts[i]
                    ): i
                    for i in to_fetch
                }

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]

                    try:
                        results[idx] = future.result()

                    except Exception as e:
                        logger.error(
                            f"[EmbeddingsParallel] "
                            f"failed for text index {idx}: {e}"
                        )
                        results[idx] = []

        return [
            result if result is not None else []
            for result in results
        ]

    def get_embeddings(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embedding vectors for multiple text strings.

        Local SentenceTransformer uses its native batch encoding.
        Ollama uses bounded parallel requests and the same embedding cache
        used by get_embedding().
        """
        if not texts:
            return []

        if self.provider == "local":
            if self.local_model is None:
                self._load_local_model()

            vectors = self.local_model.encode(
                texts,
                convert_to_numpy=True
            ).tolist()

            return vectors

        elif self.provider == "ollama":
            results: List[Optional[List[float]]] = [None] * len(texts)

            with ThreadPoolExecutor(
                max_workers=OLLAMA_BATCH_WORKERS
            ) as executor:

                future_to_idx = {
                    executor.submit(
                        self.get_embedding,
                        text
                    ): i
                    for i, text in enumerate(texts)
                }

                done = 0

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    done += 1

                    if done % 20 == 0 or done == len(texts):
                        logger.info(
                            f"Embedding {done}/{len(texts)}"
                        )

                    try:
                        results[idx] = future.result()

                    except Exception as e:
                        logger.error(
                            f"[EmbeddingsBatch] "
                            f"failed for chunk index {idx}: {e}"
                        )
                        results[idx] = []

            return [
                result if result is not None else []
                for result in results
            ]

        else:
            raise ValueError(
                f"Unknown embedding provider: {self.provider}"
            )

    def _get_ollama_embedding(
        self,
        text: str
    ) -> List[float]:
        """Fetch an embedding vector from Ollama."""

        # Older / standard Ollama endpoint.
        url = f"{self.ollama_host}/api/embeddings"

        payload = {
            "model": self.ollama_model,
            "prompt": text,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()

                if "embedding" in data:
                    return data["embedding"]

            logger.debug(
                f"/api/embeddings returned "
                f"{response.status_code}; trying /api/embed"
            )

        except Exception as e:
            logger.debug(
                f"/api/embeddings failed; "
                f"trying /api/embed. Error: {e}"
            )

        # Newer Ollama endpoint.
        url_newer = f"{self.ollama_host}/api/embed"

        payload_newer = {
            "model": self.ollama_model,
            "input": [text],
        }

        try:
            response = requests.post(
                url_newer,
                json=payload_newer,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()

                if (
                    "embeddings" in data
                    and data["embeddings"]
                ):
                    return data["embeddings"][0]

            raise Exception(
                f"Ollama server returned "
                f"{response.status_code}: {response.text}"
            )

        except Exception as e:
            logger.error(
                f"Failed to generate embeddings from Ollama "
                f"server at {self.ollama_host}: {e}"
            )

            raise Exception(
                "Ollama embedding generation failed. "
                f"Verify that Ollama is running and that the "
                f"embedding model '{self.ollama_model}' is available."
            ) from e