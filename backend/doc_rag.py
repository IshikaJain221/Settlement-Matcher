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
             top_k: int = 4) -> Tuple[List[str], str]:
    """Returns (top_chunks, method_used). method_used is 'gemini_embeddings'
    or 'keyword_overlap' — surfaced to the user so retrieval quality is honest."""
    if embeddings is not None:
        q_vec = embed_query(query)
        if q_vec is not None:
            scored = [(chunk, _cosine(q_vec, emb)) for chunk, emb in zip(chunks, embeddings)]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored[:top_k]], "gemini_embeddings"

    # Fallback: keyword overlap (Jaccard-ish) — no network call needed at all
    q_tokens = _tokenize(query)
    scored = []
    for chunk in chunks:
        c_tokens = _tokenize(chunk)
        overlap = len(q_tokens & c_tokens)
        scored.append((chunk, overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, score in scored[:top_k] if score > 0]
    if not top:
        top = chunks[:top_k]  # nothing matched — just return the first few chunks as context
    return top, "keyword_overlap"


def generate_answer(question: str, context_chunks: List[str], retrieval_method: str) -> str:
    """Generates a grounded answer from the retrieved chunks. Falls back to
    returning the most relevant chunk directly if Gemini generation fails —
    still grounded, just not synthesized into a full sentence."""
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
    except Exception as e:
        snippet = context_chunks[0][:400] if context_chunks else "No relevant content found."
        return f"(generation failed: {type(e).__name__} — showing retrieved excerpt instead)\n\n{snippet}"
