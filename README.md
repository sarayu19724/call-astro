# Call-Astro: Production-Ready RAG-Based AI Astrologer Chatbot

Call-Astro is a production-ready, context-aware chatbot designed to behave exactly like an experienced Indian Vedic Astrologer during a WhatsApp or chat conversation. It communicates naturally in Hinglish, Hindi, or English, seamlessly loads user birth details collected via the Dashboard UI from a local database, and responds with short, precise, and human-like predictions grounded in custom astrology books retrieved via a hybrid RAG (Retrieval-Augmented Generation) pipeline.

---

## Features

- **Natural Conversational Astrologer**: Behaves like a real Indian astrologer, starting with:
  > *"🙏 Namaste! Main aapki kya seva kar sakta hoon?"*
- **Automatic Language Detection**: Auto-detects and shifts replies between English, Hindi, and Hinglish dynamically.
- **Dashboard Profile Management**: Users set their Date of Birth 📅, Time ⏰, Place 📍, and Language directly in the dashboard UI for instant, seamless chart generation.
- **Conversational Memory**: Persists profile state and conversation history in an SQLite database.
- **Deep Astrological Calculations**: Automatically computes exact planetary houses, Nakshatras, and Star Lords from APIs to provide highly accurate chart readings without LLM hallucinations.
- **Smart Instant Suggestions**: Dynamically displays categorized, non-repeating contextual follow-up questions to keep users engaged.
- **Hybrid RAG Pipeline**: Combines Vector Similarity Search (dense semantic embeddings via Ollama) and Lexical Matching (TF-IDF keyword score) to retrieve segments from scanned books.
- **Local NumPy-based Vector Store**: Lightweight, fast, and robust vector search written in Python with no compiled C-library compilation dependencies (ideal for out-of-the-box Windows execution).
- **Modern Minimal UI**: Minimalist, clean, white, mobile-friendly ChatGPT-style interface built in React + TypeScript + Tailwind CSS with auto-scroll and profile sidecards.
- **Docker-Compose Ready**: Ready to be orchestrated and run in containers.

---

## Technology Stack

- **Backend**: Python 3.10+, FastAPI, SQLite, Uvicorn, NumPy, PyPDF
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Lucide Icons
- **LLM/Embeddings**: Ollama (supports Llama3, Mistral, Gemma, Phi3, nomic-embed-text)
- **Containerization**: Docker, Docker Compose

---

## Folder Structure

```text
Call-Astro/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── chat.py         # Chat execution & history endpoints
│   │   │   ├── ingest.py       # Indexing triggers and state queries
│   │   │   └── session.py      # Session CRUD operations
│   │   ├── config/
│   │   │   └── settings.py     # Application environment mappings
│   │   ├── memory/
│   │   │   └── database.py     # SQLite manager for sessions & logs
│   │   ├── models/
│   │   │   └── schemas.py      # Pydantic schemas (JSON requests/responses)
│   │   ├── prompts/
│   │   │   └── templates.py    # System prompts (Extraction, Astrologer, Missing Info)
│   │   ├── rag/
│   │   │   ├── chunker.py      # Overlapping recursive splitter
│   │   │   ├── embeddings.py   # Ollama / local SentenceTransformers connector
│   │   │   ├── indexer.py      # Document loader (PDF/DOCX/TXT/MD)
│   │   │   └── vector_store.py # Local NumPy Vector Store
│   │   ├── services/
│   │   │   ├── chat_service.py       # Core conversation coordinator
│   │   │   ├── dasha_api_service.py  # Computes Mahadasha and Antardasha timing periods
│   │   │   ├── dashboard_service.py  # Weekly guidance & profile metrics
│   │   │   ├── geocoding_service.py  # Converts birth place names to lat/long coordinates
│   │   │   ├── kundli_service.py     # Astrological calculations & external API
│   │   │   ├── llm_service.py        # Ollama API adapter
│   │   │   ├── topic_service.py      # Pre-computed contextual follow-up questions
│   │   │   └── yoga_service.py       # Detects classical astrological Yogas (Raj Yoga, etc.)
│   │   ├── utils/
│   │   │   └── logger.py       # Custom log layout
│   │   └── main.py             # FastAPI bootstrap application
│   │
│   ├── knowledge_base/         # Put astrology books here
│   ├── vector_db_data/         # Auto-saved embedding matrices
│   ├── requirements.txt        # Backend dependencies
│   ├── Dockerfile              # Backend container description
│   └── .env.example            # Environment variables configuration template
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInput.tsx        # Interactive input bar
│   │   │   ├── ChatWindow.tsx       # Messages list & auto-scroll view
│   │   │   ├── EditDetailsModal.tsx # Modal to update profile info
│   │   │   ├── KundliChart.tsx      # North Indian diamond chart renderer
│   │   │   ├── LifeDashboard.tsx    # Main dashboard view (guidance, charts)
│   │   │   ├── OnboardingForm.tsx   # Initial data collection form
│   │   │   ├── ProfileCard.tsx      # Birth profile sidecard
│   │   │   ├── QuickTopics.tsx      # Topic suggestion chips
│   │   │   ├── ReasoningTrace.tsx   # Expandable AI logic transparency box
│   │   │   ├── SouthIndianChart.tsx # South Indian square chart renderer
│   │   │   └── WeeklyGuidance.tsx   # AI-generated weekly reflections
│   │   ├── App.tsx                  # Main React shell and router
│   │   ├── main.tsx            # React bootstrap
│   │   └── index.css           # Global styles and tailwind import
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── Dockerfile              # Frontend multi-stage builder
│   └── nginx.conf              # SPA route config and reverse proxy
│
├── docker-compose.yml          # Container stack orchestration config
└── README.md                   # Full documentation
```

---

## Prerequisites

Before starting, ensure you have the following installed:
1. **Python 3.10+** (if running locally without Docker)
2. **Ollama** (for local LLM execution). Download from [ollama.ai](https://ollama.ai).
3. **Docker & Docker Compose** (optional, for containerised setup)

---

## Installation & Setup

### 1. Ollama Model Setup
Call-Astro runs on Ollama for both the LLM and Embeddings. 
Ensure Ollama is running and pull the default models:
```bash
# Pull the default LLM (Llama3)
ollama pull llama3

# Pull the default Embedding Model (nomic-embed-text)
ollama pull nomic-embed-text
```

### 2. Add Astrology Books
Place your astrology textbooks in the `backend/knowledge_base/` folder. Supported formats include:
- `.pdf` (e.g. Classic Vedic Texts)
- `.docx` (Word Documents)
- `.txt` (Plain text files)
- `.md` (Markdown manuals)

A sample text file `vedic_astrology_basics.txt` is already present inside `backend/knowledge_base/` to get you started immediately.

---

### Run Option A: Running Locally (Development)

#### Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment config and adjust settings if necessary:
   ```bash
   cp .env.example .env
   ```
5. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --reload
   ```
   The backend will be running at `http://localhost:8000`.

#### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd ../frontend
   ```
2. Install npm packages:
   ```bash
   npm install
   ```
3. Launch Vite development server:
   ```bash
   npm run dev
   ```
   Open `http://localhost:5173` in your browser. Vite is configured to proxy all `/api` requests to the FastAPI backend automatically.

---

### Run Option B: Running with Docker Compose (Recommended)

Docker Compose builds both services and routes requests through Nginx automatically.
1. Run from the root directory:
   ```bash
   docker-compose up --build
   ```
2. Open `http://localhost` in your browser. Nginx serves the frontend on port 80 and handles API requests under `http://localhost/api` by routing them to the FastAPI container.

---

## Knowledge Base Indexing

**Automatic Indexing on Server Startup** ⚡

The knowledge base is now indexed automatically when the FastAPI server starts:

1. **Backend automatically processes** all documents (.pdf, .docx, .txt, .md) from `backend/knowledge_base/` directory.
2. **Chunks are generated**, embeddings are created, and the vector store is populated before the server is ready.
3. **Zero manual steps required** - simply start the server and the RAG system is ready to answer questions.
4. **Status visible in UI**: The frontend displays the RAG status badge:
   - 🟢 **RAG Active: N Chunks** - Knowledge base is indexed and ready
   - 🔵 **RAG: Initializing** - Indexing in progress (check backend logs)

### Adding New Books

To add astrology books after the server is running:
1. Place new `.pdf`, `.docx`, `.txt`, or `.md` files in `backend/knowledge_base/` 
2. **Restart the FastAPI server** - indexing will automatically run on startup and load all documents

### Check Indexing Status via API
```bash
curl http://localhost:8000/api/ingest/status
```

**Response Example:**
```json
{
  "status": "success",
  "indexing_completed": true,
  "total_chunks": 247
}
```

---

## API Endpoints

- **Chat Endpoints**:
  - `POST /api/chat`: Process a message.
    - Body: `{"session_id": "optional-id", "message": "user-message-text"}`
  - `GET /api/chat/history/{session_id}`: Fetch all previous messages in a conversation.
- **Session Endpoints**:
  - `GET /api/session/{session_id}`: Fetch current profile (DOB, birth time, place, language).
  - `POST /api/session/{session_id}`: Manually patch session details.
  - `DELETE /api/session/{session_id}`: Clear session database records.
- **Indexing Endpoints**:
  - `GET /api/ingest/status`: Check how many chunks are indexed and loaded in memory.
    - Response: `{"status": "success", "indexing_completed": true/false, "total_chunks": int}`
    - **Note**: Knowledge base indexing happens automatically on server startup. No manual trigger needed.

---

## Example Conversations

### Example 1: Direct Astrological Consultation
*(User has already saved their Date of Birth, Time, and Place via the Dashboard Profile)*
- **Bot**: "🙏 Namaste! Main aapki kya seva kar sakta hoon?"
- **User**: "Career kaisa rahega?"
- **Bot**: *(Analyzes saved profile + exact planetary houses + RAG context instantly)*: "Aapki Kundali ke anusar, aapka janm Meen Lagna mein hua hai. Jupiter as your 10th Lord in Virgo (7th House) indicates strong career growth. Shani ki upasthiti 5th House mein mehnat mangti hai, par safalta sthayi hogi. Aapke bhagyodaya ka samay kareeb hai! 🌟"

---

## Troubleshooting

1. **Ollama connection errors**:
   - Verify Ollama is running (`ollama serve` or open desktop app).
   - Ensure the LLM model is pulled: `ollama pull llama3`.
2. **Missing `PyMuPDF` warning**:
   - If loading PDFs fails, run `pip install PyMuPDF` (pre-installed inside the Docker image).
3. **No responses or "Ollama model is not pulled"**:
   - Verify that your model name matching `.env` is exact. If you use a custom model like `mistral`, set `OLLAMA_LLM_MODEL=mistral`.
