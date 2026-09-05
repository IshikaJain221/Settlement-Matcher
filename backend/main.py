"""
main.py
-------
FastAPI application. Supports:
  - the original order/settlement dataset ("original")
  - 5 new scenario datasets (discount, refund, split, subscription, tax)
  - a "combined" mode that runs all 6 together as one larger dataset

Endpoints:
  GET  /api/health
  GET  /api/scenarios              -> list of available datasets to switch between
  POST /api/match/run?scenario=X   -> runs the pipeline for scenario X (or "combined")
  GET  /api/stats?scenario=X
  GET  /api/records?scenario=X
  GET  /api/exceptions?scenario=X
  POST /api/qa?scenario=X
  GET  /api/qa/suggestions?scenario=X
"""

import csv
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from repository import DataRepository
from matchers import build_default_pipeline
from scenario_matchers import SCENARIO_REGISTRY
from qa import answer_question, suggested_questions
from doc_processor import extract_text, chunk_text, extract_csv_rows
from doc_rag import embed_chunks, retrieve, generate_answer
from doc_analysis import extract_transactions, build_analysis
import document_store

app = FastAPI(title="Settlement Matcher API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
repo = DataRepository(str(DATA_DIR))

_cache: dict = {}  # scenario -> {"records": [...]}


class QARequest(BaseModel):
    question: str


class DocQARequest(BaseModel):
    question: str


def _read_csv(filename: str):
    with open(DATA_DIR / filename, newline="") as f:
        return list(csv.DictReader(f))


def _run_original():
    orders = repo.get_orders()
    settlements = repo.get_settlements()
    pipeline = build_default_pipeline()
    results, unknowns = pipeline.run(orders, settlements)
    records = [r.to_dict() for r in results]
    unknown_dicts = [u.to_dict() for u in unknowns]
    return records, unknown_dicts


def _run_scenario(key: str):
    cfg = SCENARIO_REGISTRY[key]
    orders = _read_csv(cfg["orders_file"])
    settlements = _read_csv(cfg["settlements_file"])
    records = cfg["matcher"](orders, settlements)
    return records, []  # scenario matchers don't currently track "unknown settlements" separately


def _run(scenario: str):
    if scenario in _cache:
        return _cache[scenario]

    if scenario == "original":
        records, unknowns = _run_original()
    elif scenario == "combined":
        all_records, all_unknowns = [], []
        orig_records, orig_unknowns = _run_original()
        for r in orig_records:
            r["scenario"] = "original"
        all_records += orig_records
        all_unknowns += orig_unknowns
        for key in SCENARIO_REGISTRY:
            recs, unk = _run_scenario(key)
            for r in recs:
                r["scenario"] = key
            all_records += recs
            all_unknowns += unk
        records, unknowns = all_records, all_unknowns
    elif scenario in SCENARIO_REGISTRY:
        records, unknowns = _run_scenario(scenario)
        for r in records:
            r["scenario"] = scenario
    else:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario}'")

    _cache[scenario] = {"records": records, "unknowns": unknowns}
    return _cache[scenario]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/scenarios")
def list_scenarios():
    items = [{"key": "original", "label": "Orders & Settlements (Original)",
              "description": "Fees, delays, duplicates, missing settlements."}]
    for key, cfg in SCENARIO_REGISTRY.items():
        items.append({"key": key, "label": cfg["label"], "description": cfg["description"]})
    items.append({"key": "combined", "label": "Combined (All Scenarios)",
                  "description": "All 6 datasets run together as one larger, messier dataset."})
    return {"scenarios": items}


@app.post("/api/match/run")
def run_match(scenario: str = "original"):
    _cache.pop(scenario, None)  # force re-run
    data = _run(scenario)
    return {"message": "Matching pipeline complete.", "scenario": scenario, "total_records": len(data["records"])}


@app.get("/api/stats")
def get_stats(scenario: str = "original"):
    data = _run(scenario)
    records = data["records"]
    total = len(records)
    matched_rule = sum(1 for r in records if r["status"] == "matched_rule")
    matched_ai = sum(1 for r in records if r["status"] == "matched_ai")
    unresolved = sum(1 for r in records if r["status"] == "unresolved")
    return {
        "scenario": scenario,
        "total_orders": total,
        "matched_rule": matched_rule,
        "matched_ai": matched_ai,
        "unresolved": unresolved,
        "unknown_settlements": len(data["unknowns"]),
        "match_rate_pct": round(((matched_rule + matched_ai) / total) * 100, 1) if total else 0,
        "rule_resolution_pct": round((matched_rule / total) * 100, 1) if total else 0,
        "ai_assist_pct": round((matched_ai / total) * 100, 1) if total else 0,
    }


@app.get("/api/records")
def get_records(scenario: str = "original"):
    data = _run(scenario)
    return {"records": data["records"], "unknown_settlements": data["unknowns"]}


@app.get("/api/exceptions")
def get_exceptions(scenario: str = "original"):
    data = _run(scenario)
    exceptions = [r for r in data["records"] if r["status"] != "matched_rule"]
    return {"exceptions": exceptions, "unknown_settlements": data["unknowns"]}


@app.post("/api/qa")
def ask_question(req: QARequest, scenario: str = "original"):
    data = _run(scenario)
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    return answer_question(req.question, data["records"])


@app.get("/api/qa/suggestions")
def get_suggestions(scenario: str = "original"):
    data = _run(scenario)
    return {"suggestions": suggested_questions(data["records"])}


# ---------------------------------------------------------------- documents (RAG)

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    text = extract_text(file.filename, raw_bytes)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Couldn't extract any text from this file.")

    chunks = chunk_text(text)
    embeddings = embed_chunks(chunks)  # None if Gemini unavailable — retrieve() falls back cleanly

    csv_rows = extract_csv_rows(raw_bytes) if file.filename.lower().endswith(".csv") else None
    doc_id = document_store.create_document(file.filename, text, chunks, embeddings, csv_rows)
    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "chunk_count": len(chunks),
        "embedding_method": "gemini_embeddings" if embeddings is not None else "keyword_fallback",
    }


@app.get("/api/documents")
def list_documents():
    return {"documents": document_store.list_documents()}


def _ensure_analysis(doc_id: str) -> dict:
    """Computes and caches the document's analysis if it hasn't been already.
    Shared by both the chat endpoint (for aggregate questions) and the
    analysis endpoint, so totals are always computed once and reused —
    never re-derived differently in two places."""
    doc = document_store.get_document(doc_id)
    if doc["analysis"] is None:
        extraction = extract_transactions(doc["text"], doc.get("csv_rows"))
        analysis = build_analysis(extraction["transactions"])
        document_store.set_analysis(doc_id, extraction["transactions"], analysis, extraction["method"])
        doc = document_store.get_document(doc_id)
    return doc


# Keywords that signal the question is about a DOCUMENT-WIDE total, not a
# specific line item. These must be answered from the full computed analysis
# (accurate across every transaction) — never from a handful of retrieved
# chunks, which can only ever see a partial, potentially misleading slice.
_AGGREGATE_KEYWORDS = {
    "profit": ["profit"],
    "loss": ["loss"],
    "spend": ["spend", "spent", "expense", "expenses", "money out", "outgoing"],
    "income": ["income", "earn", "earned", "credited", "money in", "incoming"],
    "net": ["net", "balance", "overall"],
    "biggest_expense": ["biggest expense", "largest expense", "top expense", "highest expense"],
    "category": ["category", "categories", "breakdown"],
}


def _classify_aggregate_intent(question: str) -> Optional[str]:
    q = question.lower()
    # Check more specific multi-word intents FIRST — "biggest expense" would
    # otherwise match the generic "expense" keyword under "spend" and never
    # reach the more specific handler.
    priority_order = ["biggest_expense", "category", "profit", "loss", "net", "spend", "income"]
    for intent in priority_order:
        keywords = _AGGREGATE_KEYWORDS[intent]
        if any(kw in q for kw in keywords):
            return intent
    return None


def _answer_from_analysis(intent: str, analysis: dict) -> str:
    net = analysis["net"]
    total_in = analysis["total_in"]
    total_out = analysis["total_out"]

    if intent == "profit":
        if net > 0:
            return f"Net profit: ₹{net:,.2f} (money in ₹{total_in:,.2f} minus money out ₹{total_out:,.2f})."
        return f"There's no profit here — it's actually a net loss of ₹{abs(net):,.2f} (money in ₹{total_in:,.2f}, money out ₹{total_out:,.2f})."

    if intent == "loss":
        if net < 0:
            return f"Net loss: ₹{abs(net):,.2f} (money out ₹{total_out:,.2f} exceeded money in ₹{total_in:,.2f})."
        return f"There's no loss here — it's actually a net profit of ₹{net:,.2f} (money in ₹{total_in:,.2f}, money out ₹{total_out:,.2f})."

    if intent == "spend":
        return f"Total spending (money out): ₹{total_out:,.2f} across {analysis['total_transactions']} transactions."

    if intent == "income":
        return f"Total income (money in): ₹{total_in:,.2f}."

    if intent == "net":
        direction = "profit" if net >= 0 else "loss"
        return f"Net {direction}: ₹{abs(net):,.2f} (money in ₹{total_in:,.2f}, money out ₹{total_out:,.2f})."

    if intent == "biggest_expense":
        expenses = [t for t in analysis["top_transactions"] if t["amount"] < 0]
        if not expenses:
            return "No expenses (money out) found in this document."
        biggest = expenses[0]
        return f"Biggest expense: {biggest['description']} — ₹{abs(biggest['amount']):,.2f} on {biggest['date'] or 'an unknown date'}."

    if intent == "category":
        if not analysis["category_breakdown"]:
            return "No category breakdown available for this document."
        lines = [f"- {c['category']}: ₹{c['amount']:,.2f}" for c in analysis["category_breakdown"]]
        return "Spending by category:\n" + "\n".join(lines)

    return ""  # unreachable, but keeps the function total


@app.post("/api/documents/{doc_id}/chat")
def chat_with_document(doc_id: str, req: DocQARequest):
    doc = document_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Aggregate questions (profit, loss, totals, categories) are answered
    # directly from the full computed analysis — accurate across every
    # transaction, not a guess from a handful of retrieved chunks.
    intent = _classify_aggregate_intent(req.question)
    if intent:
        doc = _ensure_analysis(doc_id)
        answer = _answer_from_analysis(intent, doc["analysis"])
        return {"answer": answer, "retrieval_method": "computed_analysis", "chunks_used": 0}

    # Everything else (specific line items, "what did I buy on X") still
    # uses chunk retrieval — deduplicated, since overlapping chunks or
    # repeated rows in the source document can otherwise surface the same
    # line multiple times and pad out the context with redundant text.
    top_chunks, method = retrieve(req.question, doc["chunks"], doc["embeddings"])
    top_chunks = list(dict.fromkeys(top_chunks))  # dedupe while preserving order
    answer = generate_answer(req.question, top_chunks, method)
    return {"answer": answer, "retrieval_method": method, "chunks_used": len(top_chunks)}


@app.get("/api/documents/{doc_id}/analysis")
def get_analysis(doc_id: str):
    doc = document_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = _ensure_analysis(doc_id)
    return {
        "analysis": doc["analysis"],
        "transactions": doc["transactions"],
        "extraction_method": doc.get("analysis_method"),
    }
