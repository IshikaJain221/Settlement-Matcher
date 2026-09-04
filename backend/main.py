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
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from repository import DataRepository
from matchers import build_default_pipeline
from scenario_matchers import SCENARIO_REGISTRY
from qa import answer_question, suggested_questions
from doc_processor import extract_text, chunk_text
from doc_rag import embed_chunks, retrieve, generate_answer
from doc_analysis import extract_transactions, build_analysis, answer_financial_question
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

    doc_id = document_store.create_document(file.filename, text, chunks, embeddings)
    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "chunk_count": len(chunks),
        "embedding_method": "gemini_embeddings" if embeddings is not None else "keyword_fallback",
    }


@app.get("/api/documents")
def list_documents():
    return {"documents": document_store.list_documents()}


@app.post("/api/documents/{doc_id}/chat")
def chat_with_document(doc_id: str, req: DocQARequest):
    doc = document_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Make sure structured analysis exists so precise questions (category
    # spend, biggest expense, net, etc.) can be answered directly instead
    # of falling back to raw retrieved text.
    if doc["analysis"] is None:
        extraction = extract_transactions(doc["text"])
        analysis = build_analysis(extraction["transactions"])
        document_store.set_analysis(doc_id, extraction["transactions"], analysis, extraction["method"])
        doc = document_store.get_document(doc_id)

    structured = answer_financial_question(req.question, doc["analysis"], doc["transactions"])
    if structured is not None:
        return {"answer": structured, "retrieval_method": "structured_analysis", "chunks_used": 0}

    top_chunks, method = retrieve(req.question, doc["chunks"], doc["embeddings"])
    answer = generate_answer(req.question, top_chunks, method)
    return {"answer": answer, "retrieval_method": method, "chunks_used": len(top_chunks)}


@app.get("/api/documents/{doc_id}/analysis")
def get_analysis(doc_id: str):
    doc = document_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc["analysis"] is None:
        extraction = extract_transactions(doc["text"])
        analysis = build_analysis(extraction["transactions"])
        document_store.set_analysis(doc_id, extraction["transactions"], analysis, extraction["method"])
        doc = document_store.get_document(doc_id)

    return {
        "analysis": doc["analysis"],
        "transactions": doc["transactions"],
        "extraction_method": doc.get("analysis_method"),
    }
