import os
import sys
import shutil
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.app.config.settings import settings
from backend.app.memory.database import db
from backend.app.rag.chunker import RecursiveCharacterTextSplitter
from backend.app.rag.vector_store import vector_store

def run_tests():
    print("==================================================")
    print("          Call-Astro Backend Verification           ")
    print("==================================================")
    
    # 1. Test Chunker
    print("\n[1/3] Testing Chunker...")
    chunker = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
    sample_text = "Vedic astrology is an ancient science. It studies planetary positions. " \
                  "Sun governs the soul. Moon governs the mind. Jupiter governs wisdom."
    chunks = chunker.split_text(sample_text)
    print(f"Generated {len(chunks)} chunks:")
    for i, c in enumerate(chunks):
        print(f"  Chunk {i+1}: '{c}' (len={len(c)})")
    
    assert len(chunks) > 0, "Chunker failed to split text"
    print("[OK] Chunker test passed successfully.")

    # 2. Test SQLite Database Manager
    print("\n[2/3] Testing SQLite Memory Database...")
    test_session = "verify_test_session_123"
    
    # Ensure starting fresh
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM sessions WHERE session_id = ?", (test_session,))
        conn.cursor().execute("DELETE FROM messages WHERE session_id = ?", (test_session,))
        conn.commit()
        
    session = db.get_or_create_session(test_session)
    print(f"Created Session: {session['session_id']}, DOB: {session['dob']}, Lang: {session['language']}")
    assert session['dob'] is None, "New session DOB should be None"

    # Update session profile details
    db.update_session(test_session, {
        "dob": "14-02-2003",
        "birth_time": "17:30",
        "birth_place": "Lucknow",
        "language": "Hinglish"
    })
    
    updated = db.get_or_create_session(test_session)
    print(f"Updated Session: {updated['session_id']}, DOB: {updated['dob']}, Place: {updated['birth_place']}, Lang: {updated['language']}")
    assert updated['dob'] == "14-02-2003", "DOB update failed"
    assert updated['birth_place'] == "Lucknow", "Birth Place update failed"
    
    # Add messages
    db.add_message(test_session, "user", "Career kaisa rahega?")
    db.add_message(test_session, "assistant", "Aapka career accha rahega.")
    
    history = db.get_history(test_session)
    print(f"Retrieved history: {len(history)} messages logged.")
    assert len(history) == 2, "Chat history should contain 2 messages"
    assert history[0]['role'] == "user"
    assert history[1]['role'] == "assistant"
    
    # Clean up test session
    with db._get_connection() as conn:
        conn.cursor().execute("DELETE FROM sessions WHERE session_id = ?", (test_session,))
        conn.cursor().execute("DELETE FROM messages WHERE session_id = ?", (test_session,))
        conn.commit()
    print("[OK] SQLite memory database transactions verified.")

    # 3. Test Local Vector Store Search
    print("\n[3/3] Testing Local Vector Store Search...")
    vector_store.clear()
    
    mock_chunks = [
        "Sun in the 10th house is excellent for high administrative authority and government job placements.",
        "Venus is the Karaka for marriage, love, partnerships and relationship harmony for men.",
        "Jupiter transit over the 7th house brings proposals, weddings, and marital bliss.",
        "Mercury in the 10th house is highly suited for business, communications, banking and marketing."
    ]
    
    # Create fake embedding vectors of size 4 (usually 384 or 768)
    mock_embeddings = [
        [1.0, 0.0, 0.0, 0.0], # Chunk 0 (Sun/Admin/Govt)
        [0.0, 1.0, 0.0, 0.0], # Chunk 1 (Venus/Marriage)
        [0.0, 0.9, 0.1, 0.0], # Chunk 2 (Jupiter/Wedding/Bliss)
        [0.8, 0.0, 0.0, 0.6]  # Chunk 3 (Mercury/Business/Bank)
    ]
    
    mock_metadatas = [{"source": "mock_book.txt"} for _ in range(4)]
    
    # Ingest into store
    vector_store.add_documents(mock_chunks, mock_metadatas, mock_embeddings)
    print(f"Loaded {len(vector_store.chunks)} mock chunks in Vector Store.")
    
    # Search for Career (we expect Chunk 0 and 3 to score higher)
    # Query vector close to Chunk 0: [0.95, 0.05, 0.0, 0.1]
    query_text = "job government administrative career"
    query_vector = [0.95, 0.05, 0.0, 0.1]
    
    results = vector_store.hybrid_search(
        query=query_text, 
        query_vector=query_vector, 
        top_k=2, 
        alpha=0.5
    )
    
    print(f"Search results for career/job query:")
    for r in results:
        print(f"  Score: {r['score']:.4f} | Text: '{r['text']}'")
        
    assert len(results) == 2, "Search should return 2 documents"
    assert "Sun" in results[0]["text"] or "Mercury" in results[0]["text"], "Top match should be Sun or Mercury chunk"
    
    # Clean up index
    vector_store.clear()
    print("[OK] Vector Store hybrid retrieval indexing passed.")
    
    print("\n==================================================")
    print("      Verification completed: ALL TESTS PASSED     ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
