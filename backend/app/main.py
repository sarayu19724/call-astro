import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.utils.logger import logger
from app.api import chat, session, ingest
from app.memory.database import db
from app.rag.indexer import document_indexer
from app.rag.vector_store import vector_store

app = FastAPI(
    title=settings.APP_NAME,
    description="A production-ready RAG-based AI Astrologer Chatbot that behaves like a professional Indian astrologer.",
    version="1.0.0"
)

# Configure CORS to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production environments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background indexing task (runs in separate thread)
def background_index_knowledge_base():
    """Run knowledge base indexing in background thread.
    Skips entirely if a valid vector store already exists on disk —
    only new/unindexed files get processed (incremental indexing)."""
    logger.info("Checking knowledge base index status...")
    try:
        if vector_store.vectors is not None and len(vector_store.chunks) > 0:
            logger.info(f"✓ Existing vector store loaded: {len(vector_store.chunks)} chunks already indexed.")
            # Still check for any NEW files that weren't indexed yet
            processed_files, total_chunks = document_indexer.ingest_knowledge_base()
            if processed_files:
                logger.info(f"✓ Indexed {len(processed_files)} new file(s), added chunks. Total now: {len(vector_store.chunks)}")
            else:
                logger.info("No new files to index — knowledge base up to date.")
        else:
            logger.info("No existing vector store found. Performing full indexing...")
            processed_files, chunks_count = document_indexer.ingest_knowledge_base(force_rebuild=False)
            if chunks_count > 0:
                logger.info(f"✓ Knowledge base indexed successfully: {chunks_count} chunks from {len(processed_files)} files")
            else:
                logger.warning("⚠ No documents found in knowledge_base directory. Place .txt, .md, .docx, or .pdf files there.")
    except Exception as e:
        logger.error(f"✗ Failed to index knowledge base: {e}")

# Startup: Initialize DB and start background indexing
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Call-Astro FastAPI Server...")
    
    # Initialize database tables
    db.init_db()
    
    # Start indexing in background thread (non-blocking)
    indexing_thread = threading.Thread(target=background_index_knowledge_base, daemon=True)
    indexing_thread.start()

# Mount routers
app.include_router(chat.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")

@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "description": "Vedic Astrologer RAG Backend is ready. Connect via /api",
        "configuration": {
            "llm_model": settings.OLLAMA_LLM_MODEL,
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "embedding_model": settings.OLLAMA_EMBED_MODEL if settings.EMBEDDING_PROVIDER == "ollama" else settings.LOCAL_EMBEDDING_MODEL
        }
    }

if __name__ == "__main__":
    # Start app via uvicorn if script is executed directly
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)