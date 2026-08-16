import requests
from typing import List

from app.config.settings import settings
from app.utils.logger import logger


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

            self.local_model = SentenceTransformer(
                self.local_model_name
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
        """Generate an embedding vector for one text string."""

        if not text:
            return []

        if self.provider == "local":
            if self.local_model is None:
                self._load_local_model()

            vector = self.local_model.encode(
                text,
                convert_to_numpy=True
            ).tolist()

            return vector

        elif self.provider == "ollama":
            return self._get_ollama_embedding(text)

        else:
            raise ValueError(
                f"Unknown embedding provider: {self.provider}"
            )

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for multiple text strings."""

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
            embeddings = []

            for i, text in enumerate(texts):
                logger.info(
                    f"Embedding {i + 1}/{len(texts)}"
                )

                embeddings.append(
                    self._get_ollama_embedding(text)
                )

            return embeddings

        else:
            raise ValueError(
                f"Unknown embedding provider: {self.provider}"
            )

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """Fetch an embedding vector from Ollama."""

        # Older / standard Ollama endpoint
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

        # Newer Ollama endpoint
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

                if "embeddings" in data and data["embeddings"]:
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