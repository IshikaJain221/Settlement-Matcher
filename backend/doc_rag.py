"""
doc_rag.py
----------
Embedding + retrieval for the document Q&A chat. Same honesty principle
as llm_matcher.py: if Gemini isn't available, we fall back to a simple
keyword-overlap retriever rather than crashing — but every answer says
which retrieval method actually ran, so nothing is silently degraded
without the user knowing.
"""

import os
import re
import math
from typing import List, Tuple, Optional

from llm_matcher import _get_client, _GEMINI_MODEL

_EMBED_MODEL = "text-embedding-004"

_STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "of", "to",
              "and", "or", "for", "what", "how", "why", "did", "do", "does", "this", "that"}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def embed_chunks(chunks: List[str]) -> Optional[List[List[float]]]:
    """Returns a list of embedding vectors, or None if Gemini isn't
    available — callers should fall back to keyword retrieval in that case."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = client.models.embed_content(model=_EMBED_MODEL, contents=chunks)
        return [e.values for e in result.embeddings]
    except Exception:
        return None


def embed_query(query: str) -> Optional[List[float]]:
    client = _get_client()
    if client is None:
        return None
    try:
        result = client.models.embed_content(model=_EMBED_MODEL, contents=[query])
        return result.embeddings[0].values
    except Exception:
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve(query: str, chunks: List[str], embeddings: Optional[List[List[float]]],
             top_k: int = 4) -> Tuple[List[str], str, bool]:
    """Returns (top_chunks, method_used, matched). `matched` is False when
    nothing genuinely relevant was found — callers should treat that as an
    off-topic or unanswerable question rather than forcing an answer from
    unrelated content."""
    if embeddings is not None:
        q_vec = embed_query(query)
        if q_vec is not None:
            scored = [(chunk, _cosine(q_vec, emb)) for chunk, emb in zip(chunks, embeddings)]
            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:top_k]
            matched = bool(top) and top[0][1] >= 0.5  # similarity threshold — below this, treat as no real match
            return [c for c, _ in top], "gemini_embeddings", matched

    # Fallback: keyword overlap (Jaccard-ish) — no network call needed at all
    q_tokens = _tokenize(query)
    scored = []
    for chunk in chunks:
        c_tokens = _tokenize(chunk)
        overlap = len(q_tokens & c_tokens)
        scored.append((chunk, overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, score in scored[:top_k] if score > 0]
    matched = len(top) > 0
    if not top:
        top = chunks[:top_k]  # still give the caller something, but flagged as unmatched
    return top, "keyword_overlap", matched


_SUGGESTIONS_MESSAGE = (
    "I couldn't find anything relevant to that in the document. Try asking things like:\n"
    "- \"What's my total profit or loss?\"\n"
    "- \"What was my biggest expense?\"\n"
    "- \"Show me the category breakdown\"\n"
    "- Or mention a specific date, amount, or order/transaction ID from the document."
)


def generate_answer(question: str, context_chunks: List[str], retrieval_method: str, matched: bool = True) -> str:
    """Generates a grounded answer from the retrieved chunks. If nothing
    relevant matched, or generation genuinely fails, returns a friendly
    suggestions message instead of a raw error or an unrelated excerpt —
    and skips the Gemini call entirely when there's no real match, since
    there's nothing worth spending a call on."""
    if not matched:
        return _SUGGESTIONS_MESSAGE

    context = "\n\n---\n\n".join(context_chunks)
    client = _get_client()

    if client is None:
        snippet = context_chunks[0][:400] if context_chunks else "No relevant content found."
        return (f"(keyword-based excerpt — no GEMINI_API_KEY configured)\n\n{snippet}")

    prompt = (
        f"Answer the question using ONLY the context below. If the context doesn't contain "
        f"the answer, say so honestly instead of guessing. Be concise.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    try:
        response = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        return response.text.strip()
    except Exception:
        # Don't surface raw exception details to the user — a clean,
        # actionable message is more useful than a technical error string.
        return _SUGGESTIONS_MESSAGE
