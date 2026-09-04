"""
doc_processor.py
-----------------
Turns an uploaded file (PDF, CSV, or plain text) into clean text, then
splits it into overlapping chunks for retrieval. This is the "ingest"
half of the RAG pipeline — see doc_rag.py for embedding + retrieval,
and doc_analysis.py for structured transaction extraction.
"""

import csv
import io
from typing import List


def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Dispatches on file extension. Returns plain text either way,
    so everything downstream (chunking, embedding, analysis) doesn't
    need to know or care what the original file format was."""
    lower = filename.lower()

    if lower.endswith(".pdf"):
        return _extract_pdf(raw_bytes)
    elif lower.endswith(".csv"):
        return _extract_csv(raw_bytes)
    else:  # .txt or anything else — treat as plain text
        return raw_bytes.decode("utf-8", errors="ignore")


def _extract_pdf(raw_bytes: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(f"[Page {i + 1}]\n{text}")
    return "\n\n".join(pages)


def _extract_csv(raw_bytes: bytes) -> str:
    """Converts CSV rows into readable text lines — e.g. bank statement
    exports — so the same chunking/embedding pipeline works on them too."""
    text = raw_bytes.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    lines = []
    for row in reader:
        line = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
        lines.append(line)
    return "\n".join(lines)


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    """Simple sliding-window chunker. Overlap keeps context from being
    severed mid-sentence at chunk boundaries — important for financial
    documents where a transaction line and its total might straddle a cut."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap

    return chunks
