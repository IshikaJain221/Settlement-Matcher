"""
generator_refund.py
--------------------
Scenario: Customer requested/was issued a refund. Internal records show
a refund was approved; the bank settlement feed should show a matching
reversal (negative amount) for it.

Anomalies:
  CLEAN            -> reversal appears, amount matches
  NOT_REVERSED     -> refund approved internally, but no reversal in bank feed at all
  PARTIAL_REVERSED -> reversal amount is less than the approved refund
  DELAYED_REVERSAL -> reversal appears, but many days late
"""
import csv, random, argparse
from datetime import datetime, timedelta

CUSTOMERS = ["Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
             "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy"]
REASONS = ["Product returned", "Order cancelled", "Damaged item", "Wrong item delivered", "Duplicate order"]
SCENARIOS = ["CLEAN", "NOT_REVERSED", "PARTIAL_REVERSED", "DELAYED_REVERSAL"]
WEIGHTS =   [0.55,     0.20,           0.12,               0.13]

def random_date(start, days_range=45):
    return start + timedelta(days=random.randint(0, days_range))

def generate(count, seed, out_dir):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)
    orders, settlements = [], []
    oid, utr = 3000, 800000

    for _ in range(count):
        oid += 1
        order_id = f"ORD{oid}"
        customer = random.choice(CUSTOMERS)
        refund_amount = round(random.uniform(299, 9999), 2)
        refund_date = random_date(start_date)
        reason = random.choice(REASONS)

        orders.append({
            "order_id": order_id, "customer": customer, "refund_amount": refund_amount,
            "reason": reason, "refund_approved_date": refund_date.strftime("%Y-%m-%d"),
        })

        scenario = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        if scenario == "NOT_REVERSED":
            continue

        utr += 1
        if scenario == "CLEAN":
            amt, settle_date = -refund_amount, refund_date + timedelta(days=2)
        elif scenario == "PARTIAL_REVERSED":
            amt = -round(refund_amount * random.uniform(0.5, 0.85), 2)
            settle_date = refund_date + timedelta(days=2)
        else:  # DELAYED_REVERSAL
            amt, settle_date = -refund_amount, refund_date + timedelta(days=random.randint(8, 15))

        settlements.append({
            "utr": f"UTR{utr}", "order_ref": order_id, "amount": amt,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })

    with open(f"{out_dir}/refund_orders.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "customer", "refund_amount", "reason", "refund_approved_date"])
        w.writeheader(); w.writerows(orders)
    with open(f"{out_dir}/refund_settlements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        w.writeheader(); w.writerows(settlements)
    print(f"[refund] {len(orders)} orders, {len(settlements)} settlements -> {out_dir}/")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="../data")
    a = p.parse_args()
    generate(a.count, a.seed, a.out)
