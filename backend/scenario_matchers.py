"""
scenario_matchers.py
---------------------
Each new scenario has its own matching logic, because "does this match?"
means something different for a discount order vs. a split payment vs.
a subscription renewal. Same STRATEGY PATTERN as matchers.py — every
scenario matcher exposes a `.run(orders, settlements)` method and returns
(results: list[dict], stats: dict), so the API layer treats them uniformly.
"""

from datetime import datetime
from typing import List, Dict
from llm_matcher import resolve_with_llm


def _pdate(d): return datetime.strptime(d, "%Y-%m-%d")


# ---------------------------------------------------------------- discount
def match_discount(orders: List[Dict], settlements: List[Dict]):
    by_ref = {}
    for s in settlements:
        by_ref.setdefault(s["order_ref"], []).append(s)

    results = []
    for o in orders:
        candidates = by_ref.get(o["order_id"], [])
        expected_before = float(o["expected_before"])
        expected_after = float(o["expected_after"])

        if not candidates:
            results.append(_rec(o, None, "unresolved", "missing_settlement",
                f"No settlement found — payment likely never went through.", 0.9))
            continue

        s = candidates[0]
        settled = float(s["amount"])
        if abs(settled - expected_after) <= 1:
            results.append(_rec(o, s, "matched_rule", "none",
                f"Discount of {o['discount_pct']}% applied correctly — customer charged ₹{expected_after}.", 1.0))
        elif abs(settled - expected_before) <= 1:
            results.append(_rec(o, s, "unresolved", "discount_not_applied",
                f"Discount did NOT apply — customer charged full ₹{expected_before} instead of the "
                f"discounted ₹{expected_after} ({o['discount_pct']}% off). Overcharged by ₹{round(settled-expected_after,2)}.", 0.3))
        else:
            # GENUINELY AMBIGUOUS: settled amount matches neither the full price nor the
            # correct discount — could be double-discount, wrong %, or something else.
            # This is exactly the kind of case a rule can't confidently label, so it goes to the LLM.
            def fallback():
                if settled < expected_after:
                    return {"status": "matched_ai", "exception_type": "double_discount",
                            "reason": f"Settled amount (₹{settled}) is lower than the correct discounted "
                                      f"price (₹{expected_after}) — looks like the coupon was applied twice.",
                            "confidence": 0.75, "resolved_by": "ai_assisted"}
                return {"status": "matched_ai", "exception_type": "wrong_discount_pct",
                        "reason": f"Settled ₹{settled} matches neither the full price (₹{expected_before}) "
                                  f"nor the correct discount (₹{expected_after}) — a different discount % "
                                  f"was likely applied by mistake.",
                        "confidence": 0.6, "resolved_by": "ai_assisted"}

            llm_result = resolve_with_llm(
                context="An e-commerce order had a discount coupon applied. We're checking whether the "
                        "settled amount reflects the correct discounted price, no discount at all, a "
                        "double-applied discount, or a wrong discount percentage.",
                order_snapshot={"expected_before_discount": expected_before, "discount_pct": o["discount_pct"],
                                 "expected_after_discount": expected_after},
                candidate_snapshot={"settled_amount": settled},
                fallback_fn=fallback,
            )
            results.append(_rec(o, s, llm_result["status"], llm_result["exception_type"],
                                 llm_result["reason"], llm_result["confidence"],
                                 resolved_by=llm_result.get("resolved_by", "ai_assisted")))
    return results


# ---------------------------------------------------------------- refund
def match_refund(orders: List[Dict], settlements: List[Dict]):
    by_ref = {}
    for s in settlements:
        by_ref.setdefault(s["order_ref"], []).append(s)

    results = []
    for o in orders:
        candidates = by_ref.get(o["order_id"], [])
        refund_amount = float(o["refund_amount"])

        if not candidates:
            results.append(_rec(o, None, "unresolved", "not_reversed",
                f"Refund of ₹{refund_amount} was approved ({o['reason']}) but no reversal appears in the "
                f"bank feed at all — customer was never actually refunded.", 0.9))
            continue

        s = candidates[0]
        reversed_amt = abs(float(s["amount"]))
        date_diff = (_pdate(s["settlement_date"]) - _pdate(o["refund_approved_date"])).days

        if abs(reversed_amt - refund_amount) <= 1 and date_diff <= 4:
            results.append(_rec(o, s, "matched_rule", "none",
                f"Refund of ₹{refund_amount} reversed correctly within {date_diff} day(s).", 1.0))
        elif abs(reversed_amt - refund_amount) <= 1:
            results.append(_rec(o, s, "matched_ai", "delayed_reversal",
                f"Refund reversed correctly but took {date_diff} days — slower than expected, worth flagging to ops.", 0.8))
        else:
            results.append(_rec(o, s, "unresolved", "partial_reversed",
                f"Only ₹{reversed_amt} was reversed against an approved refund of ₹{refund_amount} — "
                f"customer was under-refunded by ₹{round(refund_amount-reversed_amt,2)}.", 0.4))
    return results


# ---------------------------------------------------------------- split payment
def match_split(orders: List[Dict], settlements: List[Dict]):
    by_ref = {}
    for s in settlements:
        by_ref.setdefault(s["order_ref"], []).append(s)

    results = []
    for o in orders:
        candidates = by_ref.get(o["order_id"], [])
        total = float(o["total_amount"])
        settled_sum = round(sum(float(s["amount"]) for s in candidates), 2)

        if len(candidates) == 0:
            results.append(_rec(o, None, "unresolved", "missing_settlement",
                f"Neither payment leg ({o['leg1_method']} + {o['leg2_method']}) settled at all.", 0.9))
        elif len(candidates) == 1:
            results.append(_rec(o, candidates[0], "unresolved", "one_leg_missing",
                f"Only one payment leg settled (₹{settled_sum} of ₹{total} expected via "
                f"{o['leg1_method']} + {o['leg2_method']}) — the other leg never arrived.", 0.35))
        elif abs(settled_sum - total) <= 1:
            results.append(_rec(o, candidates[0], "matched_rule", "none",
                f"Both legs settled correctly ({o['leg1_method']} + {o['leg2_method']} = ₹{settled_sum}).", 1.0))
        else:
            results.append(_rec(o, candidates[0], "matched_ai", "leg_amount_off",
                f"Both legs settled but sum to ₹{settled_sum} instead of ₹{total} — a "
                f"₹{round(total-settled_sum,2)} shortfall across the split payment.", 0.55))
    return results


# ---------------------------------------------------------------- subscription
def match_subscription(orders: List[Dict], settlements: List[Dict]):
    by_ref = {}
    for s in settlements:
        by_ref.setdefault(s["order_ref"], []).append(s)

    results = []
    for o in orders:
        candidates = by_ref.get(o["order_id"], [])
        plan_price = float(o["plan_price"])

        if not candidates:
            results.append(_rec(o, None, "unresolved", "missing_renewal",
                f"No renewal charge found for the {o['plan_name']} plan (₹{plan_price}) — subscription may have silently failed to bill.", 0.9))
            continue

        s = candidates[0]
        settled = float(s["amount"])
        if abs(settled - plan_price) <= 1:
            results.append(_rec(o, s, "matched_rule", "none",
                f"Renewal charged correctly at the {o['plan_name']} plan price (₹{plan_price}).", 1.0))
        elif settled < plan_price:
            results.append(_rec(o, s, "matched_ai", "stale_plan_price",
                f"Charged ₹{settled}, lower than the current {o['plan_name']} plan price (₹{plan_price}) — "
                f"likely still billing at an old (lower) plan price after an upgrade.", 0.7))
        else:
            # GENUINELY AMBIGUOUS: charged MORE than the plan price, with no obvious pattern
            # (not a known old plan price, not a simple proration) — needs real judgment.
            def fallback():
                return {"status": "unresolved", "exception_type": "wrong_renewal_amount",
                        "reason": f"Charged ₹{settled} against a {o['plan_name']} plan price of ₹{plan_price} "
                                  f"— doesn't match any known plan price, likely a billing calculation bug.",
                        "confidence": 0.35, "resolved_by": "ai_assisted"}

            llm_result = resolve_with_llm(
                context="A subscription renewal was charged. We're checking whether the charged amount "
                        "reflects the current plan price, a stale (old) plan price, or an unexplained "
                        "billing error — could also be a valid proration for a mid-cycle upgrade.",
                order_snapshot={"plan_name": o["plan_name"], "current_plan_price": plan_price,
                                 "billing_date": o.get("billing_date")},
                candidate_snapshot={"charged_amount": settled},
                fallback_fn=fallback,
            )
            results.append(_rec(o, s, llm_result["status"], llm_result["exception_type"],
                                 llm_result["reason"], llm_result["confidence"],
                                 resolved_by=llm_result.get("resolved_by", "ai_assisted")))
    return results


# ---------------------------------------------------------------- tax/GST
def match_tax(orders: List[Dict], settlements: List[Dict]):
    by_ref = {}
    for s in settlements:
        by_ref.setdefault(s["order_ref"], []).append(s)

    results = []
    for o in orders:
        candidates = by_ref.get(o["order_id"], [])
        before = float(o["expected_before_tax"])
        after = float(o["expected_after_tax"])

        if not candidates:
            results.append(_rec(o, None, "unresolved", "missing_settlement",
                f"No settlement found for this order at all.", 0.9))
            continue

        s = candidates[0]
        settled = float(s["amount"])
        if abs(settled - after) <= 1:
            results.append(_rec(o, s, "matched_rule", "none",
                f"18% GST applied correctly — settled ₹{settled} on a ₹{before} pre-tax price.", 1.0))
        elif abs(settled - before) <= 1:
            results.append(_rec(o, s, "unresolved", "tax_not_applied",
                f"Settled ₹{settled} matches the PRE-TAX price (₹{before}) — GST was never applied, "
                f"under-collected by ₹{round(after-before,2)}.", 0.3))
        else:
            implied_rate = round(((settled / before) - 1) * 100, 1)

            def fallback():
                return {"status": "matched_ai", "exception_type": "wrong_tax_rate",
                        "reason": f"Settled ₹{settled} implies a {implied_rate}% tax rate was applied "
                                  f"instead of the correct 18% GST.",
                        "confidence": 0.6, "resolved_by": "ai_assisted"}

            llm_result = resolve_with_llm(
                context="An order should have 18% GST applied on top of a pre-tax price. We're checking "
                        "whether the settled amount reflects the correct tax, no tax, or a wrong tax rate.",
                order_snapshot={"pre_tax_price": before, "correct_post_tax_price": after, "correct_gst_rate_pct": 18},
                candidate_snapshot={"settled_amount": settled, "implied_rate_pct": implied_rate},
                fallback_fn=fallback,
            )
            results.append(_rec(o, s, llm_result["status"], llm_result["exception_type"],
                                 llm_result["reason"], llm_result["confidence"],
                                 resolved_by=llm_result.get("resolved_by", "ai_assisted")))
    return results


def _rec(order, settlement, status, exception_type, reason, confidence, resolved_by=None):
    return {
        "order_id": order["order_id"],
        "customer": order["customer"],
        "order_amount": float(order.get("expected_after") or order.get("refund_amount") or
                               order.get("total_amount") or order.get("plan_price") or
                               order.get("expected_after_tax") or 0),
        "order_date": order.get("order_date") or order.get("refund_approved_date") or order.get("billing_date"),
        "settlement_utr": settlement["utr"] if settlement else None,
        "settlement_amount": float(settlement["amount"]) if settlement else None,
        "settlement_date": settlement["settlement_date"] if settlement else None,
        "status": status,
        "exception_type": exception_type,
        "reason": reason,
        "confidence": confidence,
        "resolved_by": resolved_by or ("rule_engine" if status == "matched_rule" else ("ai_assisted" if status == "matched_ai" else "none")),
    }


SCENARIO_REGISTRY = {
    "discount": {"matcher": match_discount, "orders_file": "discount_orders.csv", "settlements_file": "discount_settlements.csv",
                 "label": "Discount / Coupon Mismatch", "description": "Order discounts vs. what the bank actually charged."},
    "refund": {"matcher": match_refund, "orders_file": "refund_orders.csv", "settlements_file": "refund_settlements.csv",
               "label": "Refund / Reversal", "description": "Approved refunds vs. actual bank reversals."},
    "split": {"matcher": match_split, "orders_file": "split_orders.csv", "settlements_file": "split_settlements.csv",
              "label": "Split Payment", "description": "Multi-method payments (card + wallet/UPI) vs. settled legs."},
    "subscription": {"matcher": match_subscription, "orders_file": "subscription_orders.csv", "settlements_file": "subscription_settlements.csv",
                      "label": "Subscription Billing", "description": "Recurring plan renewals vs. actual charges."},
    "tax": {"matcher": match_tax, "orders_file": "tax_orders.csv", "settlements_file": "tax_settlements.csv",
            "label": "Tax / GST Mismatch", "description": "Pre-tax vs. post-tax settlement amounts."},
}
