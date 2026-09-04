"""
qa.py (v2)
----------
Now answers THREE distinct question types per record, not just one:
  1. "why didn't X match / settle"      -> status + reason
  2. "what was the amount for X" /
     "breakdown for X"                  -> before/after/settled amount breakdown
  3. "how confident are you about X"    -> confidence + which matcher resolved it

Also exposes `suggested_questions()` so the frontend can show clickable
"try asking this" chips instead of a blank input box.
"""

import re
from typing import List, Dict, Optional

# General concept questions the chat should answer WITHOUT needing an order ID.
# Checked before order lookup, so "what is matched ai" doesn't fail just
# because it doesn't mention an order.
GLOSSARY = [
    (["matched ai", "matched · ai", "ai matched", "matched by ai", "ai assisted", "ai-assisted"],
     "\"Matched · AI\" means the simple rule-based checks (amount + date) couldn't resolve the record on "
     "their own, so the AI-assisted matcher stepped in and made a judgment call — like recognizing a "
     "delayed settlement, a duplicate, or a fee deduction — and explained its reasoning. It's a lower-confidence "
     "match than a rule match, but still explained, not guessed silently."),
    (["matched rule", "matched · rule", "rule matched", "rule based", "rule-based"],
     "\"Matched · rules\" means simple, deterministic checks (amount within tolerance + date close enough) "
     "resolved the record instantly — no AI involved. These are the fast, obvious matches."),
    (["unresolved", "what does unresolved mean", "what is unresolved"],
     "\"Unresolved\" means neither the rule-based matcher nor the AI-assisted matcher could confidently "
     "resolve the record — it's a genuine exception, shown honestly instead of being hidden or guessed at."),
    (["match rate"],
     "Match rate is the percentage of records successfully resolved (by rules or AI combined) out of the total. "
     "It's the headline number on the dashboard."),
    (["confidence score", "what is confidence", "what does confidence mean"],
     "Confidence is how sure the matcher is about a given match — rule-based matches are usually 100%, "
     "AI-assisted matches vary based on how strong the evidence was."),
    (["exception list", "what is an exception", "what are exceptions"],
     "The exception list is every record that didn't get a clean rule-based match — this includes both "
     "AI-resolved records (with reasoning) and genuinely unresolved ones. Nothing is hidden from it."),
]


def _check_glossary(question: str) -> Optional[str]:
    q = question.lower()
    for keywords, answer in GLOSSARY:
        if any(kw in q for kw in keywords):
            return answer
    return None


def _find_by_order_id(question: str, records: List[Dict]) -> Optional[Dict]:
    ids = re.findall(r"ord\d+", question, re.IGNORECASE)
    if not ids:
        return None
    target = ids[0].lower()
    for r in records:
        if r["order_id"].lower() == target:
            return r
    return None


def _classify_intent(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["amount", "breakdown", "how much", "price", "charged", "expected"]):
        return "amount"
    if any(w in q for w in ["confiden", "sure", "certain", "how do you know"]):
        return "confidence"
    return "reason"


def answer_question(question: str, records: List[Dict]) -> Dict:
    if not question.strip():
        return {"answer": "Ask me something about an order — try mentioning an order ID.", "sources": []}

    record = _find_by_order_id(question, records)

    if record is None:
        q = question.lower()

        # "show me unresolved records" etc. — an ACTION request (list them),
        # checked before the glossary so it doesn't get treated as a definition question.
        wants_list = any(v in q for v in ["show", "list", "find", "give me", "see"])
        if wants_list and any(w in q for w in ["exception", "unresolved", "problem", "issue", "unmatched", "fail"]):
            relevant = [r for r in records if r["status"] != "matched_rule"][:8]
            if not relevant:
                return {"answer": "No exceptions right now — everything matched cleanly.", "sources": []}
            lines = [f"Found {len(relevant)} records that needed attention:"]
            for r in relevant:
                lines.append(f"- {r['order_id']} ({r['customer']}): {r['reason']}")
            return {"answer": "\n".join(lines), "sources": relevant}

        # General concept questions ("what is matched ai", "what does unresolved mean")
        glossary_answer = _check_glossary(question)
        if glossary_answer:
            return {"answer": glossary_answer, "sources": []}

        return {
            "answer": "I couldn't find that order or concept. Try mentioning an order ID (e.g. \"why didn't "
                      "ORD1060 settle?\") or ask about a term like \"what does matched AI mean?\"",
            "sources": [],
        }

    intent = _classify_intent(question)

    if intent == "amount":
        parts = [f"Order {record['order_id']} ({record['customer']}):"]
        parts.append(f"Expected amount: \u20b9{record['order_amount']}")
        if record.get("settlement_amount") is not None:
            parts.append(f"Actual settled amount: \u20b9{record['settlement_amount']}")
        else:
            parts.append("Actual settled amount: none \u2014 no settlement was recorded.")
        diff = None
        if record.get("settlement_amount") is not None:
            diff = round(abs(record["settlement_amount"] - record["order_amount"]), 2)
        if diff:
            parts.append(f"Difference: \u20b9{diff}")
        answer = " ".join(parts)

    elif intent == "confidence":
        conf_pct = round(record["confidence"] * 100)
        who = {"rule_engine": "the rule-based matcher (deterministic, high confidence)",
               "ai_assisted": "the AI-assisted matcher (reasoned judgment call)",
               "none": "no matcher \u2014 this is unresolved"}[record["resolved_by"]]
        answer = (f"For {record['order_id']}: confidence is {conf_pct}%, resolved by {who}. "
                  f"Reason given: {record['reason']}")

    else:
        answer = f"Order {record['order_id']} ({record['customer']}): {record['reason']}"

    return {"answer": answer, "sources": [record]}


def suggested_questions(records: List[Dict]) -> List[str]:
    unresolved = [r for r in records if r["status"] == "unresolved"]
    ai_matched = [r for r in records if r["status"] == "matched_ai"]

    suggestions = []
    if unresolved:
        suggestions.append(f"Why didn't {unresolved[0]['order_id']} settle?")
    if ai_matched:
        suggestions.append(f"How confident are you about {ai_matched[0]['order_id']}?")
    target_for_amount = (unresolved[1] if len(unresolved) > 1 else (ai_matched[0] if ai_matched else (records[0] if records else None)))
    if target_for_amount:
        suggestions.append(f"What's the amount breakdown for {target_for_amount['order_id']}?")
    if len(suggestions) < 3:
        suggestions.append("Show me unresolved records")
    return suggestions[:3]
