"""
document_store.py
------------------
In-memory store for uploaded documents, keyed by a generated doc_id.
Same Repository-pattern spirit as repository.py: one place that owns
document state, so the API layer doesn't manage storage directly.

Hackathon-scoped on purpose: resets on server restart. A production
version would persist chunks/embeddings in a real vector DB (Qdrant,
as used in FinSight) — noted here rather than silently pretended away.
"""

import uuid
from typing import Dict, List, Optional

_store: Dict[str, dict] = {}


def create_document(filename: str, text: str, chunks: List[str],
                     embeddings: Optional[List[List[float]]]) -> str:
    doc_id = str(uuid.uuid4())[:8]
    _store[doc_id] = {
        "doc_id": doc_id,
        "filename": filename,
        "text": text,
        "chunks": chunks,
        "embeddings": embeddings,
        "analysis": None,       # filled in lazily on first analysis request
        "transactions": None,
    }
    return doc_id


def get_document(doc_id: str) -> Optional[dict]:
    return _store.get(doc_id)


def set_analysis(doc_id: str, transactions: List[dict], analysis: dict, method: str):
    if doc_id in _store:
        _store[doc_id]["transactions"] = transactions
        _store[doc_id]["analysis"] = analysis
        _store[doc_id]["analysis_method"] = method


def list_documents() -> List[dict]:
    return [{"doc_id": d["doc_id"], "filename": d["filename"], "chunk_count": len(d["chunks"])}
            for d in _store.values()]
