import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional
from app.config.settings import settings
from app.utils.logger import logger
from app.rag.chunker import RecursiveCharacterTextSplitter
from app.rag.embeddings import EmbeddingsProvider
from app.rag.vector_store import vector_store

class DocumentIndexer:
    def __init__(self):
        self.chunker = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        self.embeddings_provider = EmbeddingsProvider()

    def extract_docx_text(self, file_path: str) -> str:
        try:
            with zipfile.ZipFile(file_path) as docx:
                xml_content = docx.read('word/document.xml')
                root = ET.fromstring(xml_content)
                namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                paragraphs = []
                for p in root.findall('.//w:p', namespaces):
                    texts = [t.text for t in p.findall('.//w:t', namespaces) if t.text]
                    if texts:
                        paragraphs.append("".join(texts))
                return "\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Error parsing DOCX file {file_path}: {e}")
            raise

    def extract_pdf_text_with_pages(self, file_path: str) -> List[Tuple[int, str]]:
        """Returns [(page_number, page_text), ...] with 1-indexed page
        numbers straight from pypdf. This is the ONLY place a page number
        is ever assigned — every chunk downstream inherits it from here,
        nothing downstream (chunker, vector store, LLM) ever guesses it."""
        try:
            import pypdf
        except ImportError:
            logger.error("pypdf package is not installed. PDF extraction will be skipped.")
            raise RuntimeError("pypdf package is required for indexing PDF documents. Please run 'pip install pypdf'.")

        try:
            reader = pypdf.PdfReader(file_path)
            pages: List[Tuple[int, str]] = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    pages.append((i + 1, page_text))
            return pages
        except Exception as e:
            logger.error(f"Error parsing PDF file {file_path}: {e}")
            raise

    def extract_pdf_text(self, file_path: str) -> str:
        """Kept for any external caller that just wants the plain full
        text with no page tracking. Internal indexing no longer uses this —
        see extract_pdf_text_with_pages / load_document_with_pages."""
        pages = self.extract_pdf_text_with_pages(file_path)
        return "\n".join(text for _, text in pages)

    def load_document(self, file_path: str) -> str:
        """Kept for backward compatibility with any external caller that
        doesn't care about page numbers. Internal indexing uses
        load_document_with_pages instead."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".docx":
            return self.extract_docx_text(file_path)
        elif ext == ".pdf":
            return self.extract_pdf_text(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def load_document_with_pages(self, file_path: str) -> List[Tuple[Optional[int], str]]:
        """Returns [(page_number_or_None, text), ...]. PDFs get a real
        1-indexed page number per entry. .txt/.md/.docx have no native page
        concept, so they come back as a single (None, full_text) entry —
        the citation UI should simply omit the page line for those sources."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return [(None, f.read())]
        elif ext == ".docx":
            return [(None, self.extract_docx_text(file_path))]
        elif ext == ".pdf":
            return self.extract_pdf_text_with_pages(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _index_single_file(self, file_path: str) -> int:
        """Load, chunk, embed, and store ONE file. Returns chunk count.

        Chunking now happens PER PAGE rather than on the whole concatenated
        document — every chunk this produces can carry an exact page
        number. Tradeoff: chunk overlap no longer spans a page boundary
        (a chunk near the top of page 43 won't include trailing context
        from page 42). That's an intentional, worthwhile trade for a
        citation feature — an exact, non-guessed page number on every
        chunk matters more here than a few extra words of cross-page
        overlap. Non-PDF sources (page=None) are unaffected: they still
        chunk as one continuous document, same as before."""
        filename = os.path.basename(file_path)
        logger.info(f"Processing document: {filename}...")

        pages = self.load_document_with_pages(file_path)
        if not pages or all(not text.strip() for _, text in pages):
            logger.warning(f"File {filename} is empty. Skipping.")
            return 0

        all_chunk_texts: List[str] = []
        all_pages: List[Optional[int]] = []
        for page_num, page_text in pages:
            if not page_text.strip():
                continue
            page_chunks = self.chunker.split_text(page_text)
            all_chunk_texts.extend(page_chunks)
            all_pages.extend([page_num] * len(page_chunks))

        if not all_chunk_texts:
            return 0

        total_chunks = len(all_chunk_texts)
        logger.info(f"Generated {total_chunks} chunks for {filename} across {len(pages)} page(s)")

        metadatas = [
            {"source": filename, "page": all_pages[idx], "chunk_index": idx, "total_chunks": total_chunks}
            for idx in range(total_chunks)
        ]

        embeddings = self.embeddings_provider.get_embeddings(all_chunk_texts)
        vector_store.add_documents(all_chunk_texts, metadatas, embeddings)
        logger.info(f"Successfully indexed {filename}.")
        return total_chunks

    def ingest_knowledge_base(self, force_rebuild: bool = False) -> Tuple[List[str], int]:
        """Scan knowledge_base directory and index documents.

        If force_rebuild=False (default): INCREMENTAL mode — only processes
        files not already present in the vector store (tracked by filename
        in existing chunk metadata). Existing embeddings are preserved,
        no re-embedding of already-indexed books.

        If force_rebuild=True: wipes and re-indexes everything from scratch
        (use this if chunking/embedding settings changed, or to fix a
        corrupted index).

        IMPORTANT for the page-number feature: books indexed BEFORE this
        change have chunks with no "page" key in their metadata — they
        will simply show no page number in citations (handled gracefully
        downstream) until you run force_rebuild=True to re-index them with
        page tracking.
        """
        kb_dir = settings.KNOWLEDGE_BASE_DIR
        if not os.path.exists(kb_dir):
            os.makedirs(kb_dir, exist_ok=True)
            logger.info(f"Created empty knowledge base folder at {kb_dir}")
            return [], 0

        supported_extensions = (".txt", ".md", ".docx", ".pdf")
        files_on_disk = {
            f for f in os.listdir(kb_dir)
            if os.path.splitext(f)[1].lower() in supported_extensions
        }

        if not files_on_disk:
            logger.info("No documents found in knowledge base directory to index.")
            return [], 0

        if force_rebuild:
            logger.info("Force rebuild requested — clearing existing vector store.")
            vector_store.clear()
            already_indexed = set()
        else:
            already_indexed = {
                chunk.get("metadata", {}).get("source")
                for chunk in vector_store.chunks
            }
            already_indexed.discard(None)

        files_to_process = sorted(files_on_disk - already_indexed)

        if not files_to_process:
            logger.info(f"All {len(files_on_disk)} documents already indexed. Nothing new to process.")
            return [], len(vector_store.chunks)

        logger.info(f"Found {len(files_to_process)} new document(s) to index "
                    f"(skipping {len(already_indexed)} already-indexed file(s)).")

        processed_files = []
        total_new_chunks = 0

        for filename in files_to_process:
            file_path = os.path.join(kb_dir, filename)
            try:
                chunk_count = self._index_single_file(file_path)
                if chunk_count > 0:
                    processed_files.append(filename)
                    total_new_chunks += chunk_count
            except Exception as e:
                logger.error(f"Failed to index file {filename}: {e}. Skipping this file.")
                continue

        return processed_files, total_new_chunks

document_indexer = DocumentIndexer()

