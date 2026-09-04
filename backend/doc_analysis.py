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


_AMOUNT_RE = re.compile(r"([+-])?\s*[₹$]\s?[-]?[\d,]+\.?\d*|[-]?[\d,]+\.\d{2}\b")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


def extract_transactions(text: str) -> Dict:
    """Returns {"transactions": [...], "method": "gemini_llm" | "regex_fallback"}"""
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
            return {"transactions": [t.model_dump() for t in parsed.transactions], "method": "gemini_llm"}
        except Exception:
            pass  # fall through to regex fallback below

    return {"transactions": _regex_fallback(text), "method": "regex_fallback"}


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
        full_match = amount_match.group()
        # Capture the sign prefix (group 1) before the currency symbol
        sign_prefix = amount_match.group(1) if amount_match.lastindex and amount_match.group(1) else ""
        amount_str = full_match.replace("₹", "").replace("$", "").replace(",", "").replace("+", "").replace("-", "").strip()
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        # Apply sign: explicit '-' prefix or '-' embedded in the raw match means debit
        if sign_prefix == "-" or (not sign_prefix and "-" in full_match):
            amount = -abs(amount)
        elif sign_prefix == "+":
            amount = abs(amount)
        # If no sign info at all, use keyword heuristics to guess debit vs credit
        else:
            line_lower = line.lower()
            debit_keywords = ["debit", "dr", "withdrawal", "payment", "charge", "spent", "paid"]
            credit_keywords = ["credit", "cr", "deposit", "salary", "refund", "received", "income"]
            if any(k in line_lower for k in debit_keywords):
                amount = -abs(amount)
            elif any(k in line_lower for k in credit_keywords):
                amount = abs(amount)
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
        if t["amount"] < 0:  # only spending goes into the category breakdown
            by_category[t["category"]] += -t["amount"]
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


_CATEGORY_ALIASES = {
    "food": "Food", "swiggy": "Food", "zomato": "Food", "grocery": "Food",
    "shopping": "Shopping", "amazon": "Shopping", "flipkart": "Shopping",
    "utilities": "Utilities", "utility": "Utilities", "bill": "Utilities",
    "rent": "Rent", "transport": "Transport", "cab": "Transport", "fuel": "Transport",
    "entertainment": "Entertainment", "netflix": "Entertainment",
    "health": "Health & Fitness", "fitness": "Health & Fitness", "gym": "Health & Fitness",
    "income": "Income", "salary": "Income",
}


def answer_financial_question(question: str, analysis: Dict, transactions: List[Dict]) -> Optional[str]:
    """Answers common bank-statement questions directly from the already
    -computed analysis/transactions, so the chat gives a precise number
    instead of dumping raw retrieved text. Returns None if the question
    doesn't match a known pattern, so the caller can fall back to RAG."""
    q = question.lower()
    total_out = analysis.get("total_out", 0)

    for alias, category in _CATEGORY_ALIASES.items():
        if alias in q:
            match = next((c for c in analysis["category_breakdown"] if c["category"] == category), None)
            if match:
                pct = round((match["amount"] / total_out) * 100, 1) if total_out else 0
                return f"You spent \u20b9{match['amount']:,.2f} on {category} \u2014 {pct}% of your total spending (\u20b9{total_out:,.2f})."
            return f"I didn't find any {category} transactions in this document."

    if any(w in q for w in ["biggest expense", "largest expense", "highest expense", "biggest transaction"]):
        expenses = [t for t in transactions if t["amount"] < 0]
        if not expenses:
            return "No expenses found in this document."
        biggest = min(expenses, key=lambda t: t["amount"])
        return f"Your biggest expense was \u20b9{abs(biggest['amount']):,.2f} \u2014 {biggest['description']} ({biggest['category']})."

    if any(w in q for w in ["category", "categories", "breakdown by category"]):
        if not analysis["category_breakdown"]:
            return "No categorized spending found in this document."
        lines = ["Spending by category:"]
        for c in analysis["category_breakdown"]:
            pct = round((c["amount"] / total_out) * 100, 1) if total_out else 0
            lines.append(f"- {c['category']}: \u20b9{c['amount']:,.2f} ({pct}%)")
        return "\n".join(lines)

    if any(w in q for w in ["net", "profit", "loss"]):
        net = analysis.get("net", 0)
        verdict = "profit" if net >= 0 else "loss"
        return (f"Net {verdict}: \u20b9{abs(net):,.2f} (money in \u20b9{analysis['total_in']:,.2f} "
                f"minus money out \u20b9{total_out:,.2f}).")

    if any(w in q for w in ["total spend", "total spending", "how much did i spend", "total expense", "money out"]):
        return f"Total spending: \u20b9{total_out:,.2f} across {analysis['total_transactions']} transactions."

    if any(w in q for w in ["total income", "money in", "how much did i earn", "total credit"]):
        return f"Total money in: \u20b9{analysis['total_in']:,.2f}."

    return None


def _safe_month(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None