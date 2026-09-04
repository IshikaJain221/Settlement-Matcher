"""
llm_matcher.py
--------------
Real LLM reasoning for the genuinely ambiguous reconciliation cases —
this is what makes the "AI-assisted matcher" actually AI-assisted,
instead of an if/else block with a hardcoded confidence number.

Uses Google's Gemini API (free tier) via the `google-genai` SDK.

Design choice, stated plainly: we do NOT call the LLM for every record.
The rule-based matcher already resolves clean matches and simple fee/date
math instantly and for free — burning an API call on those would be
wasteful and slower, and a rule can already explain them perfectly.
The LLM is reserved for cases where genuine judgment is needed: amount
mismatches that don't fit a known pattern, ambiguous duplicate settlements,
wrong discount/tax percentages, etc.

Fallback behavior: if GEMINI_API_KEY isn't set, or the API call fails for
any reason (network, rate limit, bad response), we fall back to a
deterministic heuristic — and the returned reason/confidence CLEARLY
say so, rather than silently pretending the LLM ran. Honesty about
what actually made the decision matters here as much as the decision.
"""

import os
import json
from typing import Optional
from pydantic import BaseModel

_client = None
_GEMINI_MODEL = "gemini-2.5-flash"


class MatchVerdict(BaseModel):
    matched: bool          # is this settlement the correct match for this order, at all?
    confidence: float      # 0.0 - 1.0, the model's own stated confidence
    exception_type: str    # short snake_case label, e.g. "wrong_discount_pct", "duplicate_settlement"
    reasoning: str         # plain-English explanation, shown directly to the user


def _get_client():
    """Lazily creates the Gemini client. Returns None if no API key is configured,
    so callers can fall back cleanly instead of crashing the whole pipeline."""
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        return _client
    except Exception:
        return None


def resolve_with_llm(context: str, order_snapshot: dict, candidate_snapshot: Optional[dict],
                      fallback_fn) -> dict:
    """
    context: plain-English description of the scenario and why this case is ambiguous
    order_snapshot / candidate_snapshot: the actual record data, passed as-is so the
        model reasons over real numbers, not a paraphrase
    fallback_fn: a zero-arg function returning a dict with the same shape as below,
        used if the LLM is unavailable or fails — keeps the pipeline always runnable

    Returns: {"status": "matched_ai"|"unresolved", "exception_type": str,
              "reason": str, "confidence": float, "resolved_by": str}
    """
    client = _get_client()
    if client is None:
        result = fallback_fn()
        result["reason"] += " (heuristic fallback — no GEMINI_API_KEY configured)"
        return result

    prompt = (
        f"You are a financial reconciliation assistant. Two records may or may not "
        f"correspond to the same transaction. Decide if they match, and explain why.\n\n"
        f"Context: {context}\n\n"
        f"Order record: {json.dumps(order_snapshot, default=str)}\n"
        f"Candidate settlement record: {json.dumps(candidate_snapshot, default=str) if candidate_snapshot else 'None available'}\n\n"
        f"Reason step by step about the amounts and dates, then give your verdict. "
        f"Use a short snake_case exception_type label (e.g. 'wrong_discount_pct', "
        f"'duplicate_settlement', 'amount_mismatch'), or 'none' if it's a clean match. "
        f"Keep reasoning to 1-2 sentences, written for a non-technical reader."
    )

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MatchVerdict,
                temperature=0.1,  # low temperature — this is a judgment call, not creative writing
            ),
        )
        verdict = MatchVerdict.model_validate_json(response.text)
        return {
            "status": "matched_ai" if verdict.matched else "unresolved",
            "exception_type": verdict.exception_type,
            "reason": verdict.reasoning,
            "confidence": round(verdict.confidence, 2),
            "resolved_by": "gemini_llm",
        }
    except Exception as e:
        result = fallback_fn()
        result["reason"] += f" (heuristic fallback — Gemini call failed: {type(e).__name__})"
        return result
