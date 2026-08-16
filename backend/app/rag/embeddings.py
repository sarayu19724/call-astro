import requests
from typing import List, Optional
from app.config.settings import settings
from app.utils.logger import logger

class EmbeddingsProvider:
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER.lower()
        self.ollama_host = settings.OLLAMA_HOST
        self.ollama_model = settings.OLLAMA_EMBED_MODEL
        self.local_model_name = settings.LOCAL_EMBEDDING_MODEL
        self.local_model = None

        logger.info(f"Embeddings provider initialised with mode: {self.provider}")
        if self.provider == "local":
            self._load_local_model()

    def _load_local_model(self):
        """Lazy load sentence-transformers to avoid startup delays or torch import errors if not used."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local SentenceTransformer model: {self.local_model_name}")
            self.local_model = SentenceTransformer(self.local_model_name)
            logger.info("Local SentenceTransformer model loaded successfully.")
        except ImportError:
            logger.error(
                "Failed to import 'sentence-transformers'. Please install it using 'pip install sentence-transformers' "
                "or switch EMBEDDING_PROVIDER to 'ollama' in your .env file."
            )
            raise

    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string."""
        if self.provider == "ollama":
            return self._get_ollama_embedding(text)
        elif self.provider == "local":
            if not self.local_model:
                self._load_local_model()
            # Local sentence-transformers model call
            vector = self.local_model.encode(text).tolist()
            return vector
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a list of text strings."""
        if not texts:
            return []
            
        if self.provider == "ollama":
            # For Ollama, we can call in a batch if the server supports `/api/embed`, 
            # otherwise fetch individually.
            embeddings = []

            for i, text in enumerate(texts):
             logger.info(f"Embedding {i+1}/{len(texts)}")
             embeddings.append(self._get_ollama_embedding(text))

            return embeddings  
           
        elif self.provider == "local":
            if not self.local_model:
                self._load_local_model()
            vectors = self.local_model.encode(texts).tolist()
            return vectors
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """Fetch embedding vector from local Ollama service."""
        # Try /api/embeddings (older/standard) first, then fallback to /api/embed (newer batch version)
        url = f"{self.ollama_host}/api/embeddings"
        payload = {
            "model": self.ollama_model,
            "prompt": text
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data["embedding"]
        except Exception as e:
            logger.debug(f"/api/embeddings failed, attempting newer /api/embed. Error: {e}")

        # Fallback to newer API endpoint
        url_newer = f"{self.ollama_host}/api/embed"
        payload_newer = {
            "model": self.ollama_model,
            "input": [text]
        }
        try:
            response = requests.post(url_newer, json=payload_newer, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data["embeddings"][0]
            else:
                raise Exception(f"Ollama server returned {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to generate embeddings from Ollama server at {self.ollama_host}: {e}")
            # If Ollama embedding fails, we can log it. For production resilience, we could raise or fall back.
            raise Exception(
                f"Ollama embedding generator failed. Please verify that Ollama is running and model "
                f"'{self.ollama_model}' is installed (run: `ollama pull {self.ollama_model}`)."
            ) from e
