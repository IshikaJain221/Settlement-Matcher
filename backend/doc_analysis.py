"""
doc_analysis.py
----------------
Extracts structured transactions (date, description, amount, category)
from the raw document text, then aggregates them into chart-ready data:
spending by category, monthly trend, totals.

Same pattern as llm_matcher.py: Gemini does the extraction when available
(it can read messy real-world statement formatting far better than regex
ever could), with a regex-based fallback that at least finds amount-like
patterns so the feature still demos without a key — clearly labeled either way.
"""

import os
import re
import json
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict
from pydantic import BaseModel

from llm_matcher import _get_client, _GEMINI_MODEL


class Transaction(BaseModel):
    date: str            # best-effort ISO date, or "" if unknown
    description: str
    amount: float         # positive = credit/income, negative = debit/expense
    category: str          # short label, e.g. "Food", "Shopping", "Salary", "Utilities"


class TransactionList(BaseModel):
    transactions: List[Transaction]


_AMOUNT_RE = re.compile(r"[₹$]\s?[-]?[\d,]+\.?\d*|[-]?[\d,]+\.\d{2}\b")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


_AMOUNT_ALIASES = ["amount", "settled_amount", "amt", "transaction_amount", "settlement_amount"]
_DATE_ALIASES = ["date", "settlement_date", "order_date", "transaction_date", "billing_date"]
_CATEGORY_ALIASES = ["category", "transaction_category", "exception_type"]
_DESC_ALIASES = ["description", "narration", "merchant", "product", "order_ref"]


def _find_column(row: dict, aliases: List[str]) -> Optional[str]:
    """Case-insensitive column lookup — real-world CSVs are inconsistent
    about capitalization (Amount vs amount vs AMOUNT)."""
    lower_map = {k.lower(): k for k in row.keys()}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


def extract_transactions_from_csv_rows(rows: List[dict]) -> Dict:
    """Reads transactions directly from known CSV columns — no regex
    guessing, no LLM call needed. Used whenever the upload is a CSV with
    a recognizable schema, since the structure is already known and
    trustworthy; falls back to the regex/LLM path only if no amount
    column can be found at all."""
    if not rows:
        return {"transactions": [], "method": "csv_columns"}

    amount_col = _find_column(rows[0], _AMOUNT_ALIASES)
    if amount_col is None:
        return {"transactions": [], "method": "csv_columns"}  # caller falls back

    date_col = _find_column(rows[0], _DATE_ALIASES)
    category_col = _find_column(rows[0], _CATEGORY_ALIASES)
    desc_col = _find_column(rows[0], _DESC_ALIASES)

    transactions = []
    for row in rows:
        raw_amount = (row.get(amount_col) or "").replace(",", "").replace("₹", "").replace("$", "").strip()
        try:
            amount = float(raw_amount)
        except ValueError:
            continue
        description = (row.get(desc_col) if desc_col else None) or "Transaction"
        transactions.append({
            "date": row.get(date_col, "") if date_col else "",
            "description": str(description)[:80],
            "amount": amount,   # sign taken exactly as given in the file — not assumed
            "category": (row.get(category_col) if category_col else None) or _guess_category(str(description)),
        })

    return {"transactions": _dedupe(transactions), "method": "csv_columns"}


def _dedupe(transactions: List[Dict]) -> List[Dict]:
    """Drops exact-duplicate transactions (same date + description + amount).
    A legitimate statement won't have byte-identical repeated lines — but a
    glitchy export or a stress-test file very well might, and duplicates
    silently multiply every total by however many times they repeat."""
    seen = set()
    deduped = []
    for t in transactions:
        key = (t["date"], t["description"], t["amount"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped


def extract_transactions(text: str, csv_rows: Optional[List[dict]] = None) -> Dict:
    """Returns {"transactions": [...], "method": "csv_columns" | "gemini_llm" | "regex_fallback"}"""
    # CSV with a recognizable schema: read it directly. Deterministic, free,
    # and more accurate than re-parsing already-structured data with regex.
    if csv_rows:
        result = extract_transactions_from_csv_rows(csv_rows)
        if result["transactions"]:
            return result
        # no amount column found — fall through to the general-purpose paths below

    client = _get_client()

    if client is not None:
        try:
            from google.genai import types
            prompt = (
                "Extract every financial transaction from this document text. For each one, give: "
                "date (ISO format if possible, else best guess or empty string), description, "
                "amount (positive for money in/credits, negative for money out/debits), and a short "
                "category label (Food, Shopping, Utilities, Salary, Transport, Entertainment, Rent, "
                "Transfer, Other, etc). Only extract real transactions, not headers or totals.\n\n"
                f"Document text:\n{text[:12000]}"
            )
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TransactionList,
                    temperature=0.0,
                ),
            )
            parsed = TransactionList.model_validate_json(response.text)
            return {"transactions": _dedupe([t.model_dump() for t in parsed.transactions]), "method": "gemini_llm"}
        except Exception:
            pass  # fall through to regex fallback below

    return {"transactions": _dedupe(_regex_fallback(text)), "method": "regex_fallback"}


_CATEGORY_KEYWORDS = {
    "Food": ["swiggy", "zomato", "restaurant", "cafe", "grocery", "bigbasket", "food"],
    "Shopping": ["amazon", "myntra", "flipkart", "ajio", "shopping", "purchase"],
    "Utilities": ["electricity", "bill", "internet", "airtel", "jio", "recharge", "water"],
    "Rent": ["rent", "landlord"],
    "Transport": ["uber", "ola", "cab", "fuel", "petrol"],
    "Entertainment": ["netflix", "movie", "pvr", "spotify", "prime"],
    "Health & Fitness": ["gym", "hospital", "pharmacy", "clinic"],
    "Income": ["salary", "credit", "freelance", "payment received", "refund"],
}


def _guess_category(description: str) -> str:
    desc_lower = description.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return "Other"


def _regex_fallback(text: str) -> List[Dict]:
    """Crude line-based extraction: any line with a date-like AND amount-like
    token is treated as a transaction. Nowhere near as good as the LLM at
    understanding real statement layouts, but keeps the feature demoable
    without an API key, and is honest about being the fallback."""
    transactions = []
    for line in text.split("\n"):
        amount_match = _AMOUNT_RE.search(line)
        if not amount_match:
            continue
        date_match = _DATE_RE.search(line)
        amount_str = amount_match.group().replace("₹", "").replace("$", "").replace(",", "").strip()
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        description = line[:amount_match.start()].strip(" |:-")
        if date_match:
            description = description.replace(date_match.group(), "").strip(" |:-")
        description = description or "Unlabeled transaction"
        transactions.append({
            "date": date_match.group() if date_match else "",
            "description": description[:80],
            "amount": amount,
            "category": _guess_category(description),
        })
    return transactions


def build_analysis(transactions: List[Dict]) -> Dict:
    """Aggregates raw transactions into the numbers the dashboard charts need."""
    total_in = sum(t["amount"] for t in transactions if t["amount"] > 0)
    total_out = sum(-t["amount"] for t in transactions if t["amount"] < 0)

    by_category = defaultdict(float)
    for t in transactions:
        # Use absolute value so a category chart isn't empty just because a
        # document is all incoming money (e.g. a settlements file) — this
        # shows category weight regardless of direction, not just spending.
        by_category[t["category"]] += abs(t["amount"])
    category_breakdown = [{"category": k, "amount": round(v, 2)} for k, v in
                           sorted(by_category.items(), key=lambda x: -x[1])]

    by_month = defaultdict(float)
    for t in transactions:
        month = _safe_month(t["date"])
        if month:
            by_month[month] += t["amount"]
    monthly_trend = [{"month": k, "net": round(v, 2)} for k, v in sorted(by_month.items())]

    top_transactions = sorted(transactions, key=lambda t: abs(t["amount"]), reverse=True)[:10]

    return {
        "total_transactions": len(transactions),
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),
        "net": round(total_in - total_out, 2),
        "category_breakdown": category_breakdown,
        "monthly_trend": monthly_trend,
        "top_transactions": top_transactions,
    }


def _safe_month(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None
