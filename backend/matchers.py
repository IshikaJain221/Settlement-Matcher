"""
matchers.py
-----------
This is the heart of the app: the matching engine.

Design patterns used here (see the "Explained Simply" doc for the
plain-English versions of these):

1. STRATEGY PATTERN
   RuleBasedMatcher and AIAssistedMatcher both implement the same
   interface (a `.try_match()` method). The pipeline that runs them
   doesn't care which one is doing the work — they're interchangeable
   strategies for solving "does this order have a matching settlement?"

2. CHAIN OF RESPONSIBILITY PATTERN
   MatchingPipeline runs strategies in order: rule-based first (fast,
   cheap, handles the obvious cases), and only passes unresolved
   records down the chain to the AI-assisted matcher. Each handler
   either resolves the record or passes it on — neither handler needs
   to know the other exists.

Note on the AI step: for offline/no-API-key runs, `AIAssistedMatcher`
falls back to a documented heuristic reasoner (still explainable,
still produces a reason string) so the whole pipeline is runnable out
of the box. Swap in a real LLM call (see `call_llm_for_match`) by
setting ANTHROPIC_API_KEY — the interface doesn't change either way.
"""

import os
from datetime import datetime
from typing import List, Optional, Protocol
from models import Order, Settlement, MatchResult, MatchStatus, ExceptionType, UnknownSettlement
from llm_matcher import resolve_with_llm

AMOUNT_TOLERANCE_PCT = 0.005      # 0.5% — treated as "same amount"
FEE_TOLERANCE_PCT = 0.03          # up to 3% deduction is treated as "plausible fee"
DATE_WINDOW_DAYS_RULE = 2         # rule engine only accepts near-same-day settlements
DATE_WINDOW_DAYS_AI = 10          # AI step allows a wider, more lenient window


def _parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


class MatcherStrategy(Protocol):
    """The shared interface every matching strategy implements (Strategy Pattern)."""
    name: str

    def try_match(self, order: Order, candidates: List[Settlement]) -> Optional[MatchResult]:
        ...


class RuleBasedMatcher:
    """
    Step 1 of the chain: fast, deterministic, explainable-by-construction.
    No AI involved — just arithmetic and date math.
    """
    name = "rule_engine"

    def try_match(self, order: Order, candidates: List[Settlement]) -> Optional[MatchResult]:
        best = None
        for s in candidates:
            amount_diff_pct = abs(s.amount - order.amount) / order.amount
            date_diff = abs((_parse_date(s.settlement_date) - _parse_date(order.order_date)).days)

            if amount_diff_pct <= AMOUNT_TOLERANCE_PCT and date_diff <= DATE_WINDOW_DAYS_RULE:
                # Exact-ish match, close date -> clean match
                return MatchResult(
                    order=order, settlement=s,
                    status=MatchStatus.MATCHED_RULE,
                    exception_type=ExceptionType.NONE,
                    reason=f"Amount matches within {AMOUNT_TOLERANCE_PCT*100:.1f}% and settled "
                           f"{date_diff} day(s) after the order — clean match.",
                    confidence=1.0, resolved_by=self.name,
                )

            if FEE_TOLERANCE_PCT >= (order.amount - s.amount) / order.amount > AMOUNT_TOLERANCE_PCT \
                    and date_diff <= DATE_WINDOW_DAYS_RULE:
                # Amount slightly lower, looks like a gateway fee
                fee = round(order.amount - s.amount, 2)
                best = MatchResult(
                    order=order, settlement=s,
                    status=MatchStatus.MATCHED_RULE,
                    exception_type=ExceptionType.FEE_DEDUCTED,
                    reason=f"Settlement is ₹{fee} less than the order amount "
                           f"({(fee/order.amount)*100:.1f}%) — consistent with a gateway fee deduction.",
                    confidence=0.95, resolved_by=self.name,
                )
        return best  # None if nothing matched the rules


class AIAssistedMatcher:
    """
    Step 2 of the chain: handles whatever the rule engine couldn't.
    Looks at a wider date window and reasons about *why* a candidate
    might still be the right match, or classifies the genuine exception.
    """
    name = "ai_assisted"

    def try_match(self, order: Order, candidates: List[Settlement]) -> Optional[MatchResult]:
        if not candidates:
            return MatchResult(
                order=order, settlement=None,
                status=MatchStatus.UNRESOLVED,
                exception_type=ExceptionType.MISSING_SETTLEMENT,
                reason="No settlement record references this order at all. "
                       "Likely a failed or not-yet-processed payment.",
                confidence=0.9, resolved_by=self.name,
            )

        # Look for a same-amount settlement that just arrived late
        for s in candidates:
            amount_diff_pct = abs(s.amount - order.amount) / order.amount
            date_diff = (_parse_date(s.settlement_date) - _parse_date(order.order_date)).days
            if amount_diff_pct <= AMOUNT_TOLERANCE_PCT and 0 < date_diff <= DATE_WINDOW_DAYS_AI:
                return MatchResult(
                    order=order, settlement=s,
                    status=MatchStatus.MATCHED_AI,
                    exception_type=ExceptionType.DELAYED,
                    reason=f"Amount matches exactly but settlement landed {date_diff} days "
                           f"after the order — likely a delayed bank settlement, not a real mismatch.",
                    confidence=0.85, resolved_by=self.name,
                )

        # Multiple candidates with the same amount -> likely duplicate feed entries.
        # GENUINELY AMBIGUOUS: which one is the real settlement and which are duplicates
        # isn't always obvious from amount alone (e.g. date order, UTR patterns) — LLM call.
        same_amount = [s for s in candidates if abs(s.amount - order.amount) / order.amount <= AMOUNT_TOLERANCE_PCT]
        if len(same_amount) >= 2:
            def fallback():
                chosen = same_amount[0]
                return {"status": "matched_ai", "exception_type": "duplicate_settlement",
                        "reason": f"Found {len(same_amount)} settlements with the same amount for this "
                                  f"order — likely a duplicate bank feed entry. Matched to the earliest "
                                  f"({chosen.utr}); the rest should be reviewed as duplicates.",
                        "confidence": 0.7, "resolved_by": self.name}

            llm_result = resolve_with_llm(
                context="Multiple bank settlements have the same amount and reference the same order. "
                        "We need to decide which one is the genuine settlement for this order and flag "
                        "the rest as likely duplicate feed entries.",
                order_snapshot={"order_id": order.order_id, "expected_amount": order.amount,
                                 "order_date": order.order_date},
                candidate_snapshot={"candidate_settlements": [
                    {"utr": s.utr, "amount": s.amount, "settlement_date": s.settlement_date} for s in same_amount
                ]},
                fallback_fn=fallback,
            )
            chosen = same_amount[0]  # LLM reasons over all candidates but we still need one Settlement object to attach
            return MatchResult(
                order=order, settlement=chosen,
                status=MatchStatus.MATCHED_AI if llm_result["status"] == "matched_ai" else MatchStatus.UNRESOLVED,
                exception_type=ExceptionType.DUPLICATE_SETTLEMENT,
                reason=llm_result["reason"],
                confidence=llm_result["confidence"], resolved_by=llm_result.get("resolved_by", self.name),
            )

        # Nothing plausible -> genuine amount mismatch, flag honestly
        closest = min(candidates, key=lambda s: abs(s.amount - order.amount))
        diff = round(abs(closest.amount - order.amount), 2)
        return MatchResult(
            order=order, settlement=None,
            status=MatchStatus.UNRESOLVED,
            exception_type=ExceptionType.AMOUNT_MISMATCH,
            reason=f"Closest candidate ({closest.utr}) differs by ₹{diff}, too large to explain "
                   f"as a fee or rounding error. Flagged for manual review rather than guessing.",
            confidence=0.4, resolved_by=self.name,
        )


class MatchingPipeline:
    """
    CHAIN OF RESPONSIBILITY: runs each strategy in order, only passing
    a record to the next handler if the previous one couldn't resolve it.
    """

    def __init__(self, strategies: List[MatcherStrategy]):
        self.strategies = strategies

    def run(self, orders: List[Order], settlements: List[Settlement]):
        # Group settlements by order_ref for fast lookup
        by_order_ref = {}
        for s in settlements:
            by_order_ref.setdefault(s.order_ref, []).append(s)

        known_order_ids = {o.order_id for o in orders}
        results: List[MatchResult] = []

        for order in orders:
            candidates = by_order_ref.get(order.order_id, [])
            resolved = None
            for strategy in self.strategies:
                resolved = strategy.try_match(order, candidates)
                if resolved is not None:
                    break
            if resolved is None:
                resolved = MatchResult(
                    order=order, settlement=None,
                    status=MatchStatus.UNRESOLVED,
                    exception_type=ExceptionType.MISSING_SETTLEMENT,
                    reason="No matching or plausible settlement found by any strategy.",
                    confidence=0.0, resolved_by="none",
                )
            results.append(resolved)

        # Settlements that reference an order_id that doesn't exist at all
        unknowns = [
            UnknownSettlement(
                settlement=s,
                reason=f"References order '{s.order_ref}', which does not exist in internal records. "
                       f"Possible stray credit, refund reversal, or data entry error.",
            )
            for s in settlements if s.order_ref not in known_order_ids
        ]

        return results, unknowns


def build_default_pipeline() -> MatchingPipeline:
    """Factory function: assembles the standard two-step chain."""
    return MatchingPipeline([RuleBasedMatcher(), AIAssistedMatcher()])
