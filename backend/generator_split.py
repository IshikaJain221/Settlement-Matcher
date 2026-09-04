"""
generator_split.py
-------------------
Scenario: One order paid using two payment legs (e.g. card + wallet,
or card + UPI). Both legs should show up as separate settlements
that sum to the order total.

Anomalies:
  CLEAN           -> both legs present, sum matches order total
  ONE_LEG_MISSING -> only one of the two legs settled
  LEG_AMOUNT_OFF  -> both legs present but sum doesn't match order total
"""
import csv, random, argparse
from datetime import datetime, timedelta

CUSTOMERS = ["Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
             "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy"]
METHOD_PAIRS = [("Card", "Wallet"), ("Card", "UPI"), ("UPI", "Wallet"), ("Card", "Gift Card")]
SCENARIOS = ["CLEAN", "ONE_LEG_MISSING", "LEG_AMOUNT_OFF"]
WEIGHTS =   [0.60,     0.25,              0.15]

def random_date(start, days_range=45):
    return start + timedelta(days=random.randint(0, days_range))

def generate(count, seed, out_dir):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)
    orders, settlements = [], []
    oid, utr = 4000, 900000

    for _ in range(count):
        oid += 1
        order_id = f"ORD{oid}"
        customer = random.choice(CUSTOMERS)
        total = round(random.uniform(999, 15999), 2)
        split_pct = random.uniform(0.3, 0.7)
        leg1_amt = round(total * split_pct, 2)
        leg2_amt = round(total - leg1_amt, 2)
        m1, m2 = random.choice(METHOD_PAIRS)
        order_date = random_date(start_date)

        orders.append({
            "order_id": order_id, "customer": customer, "total_amount": total,
            "leg1_method": m1, "leg1_expected": leg1_amt,
            "leg2_method": m2, "leg2_expected": leg2_amt,
            "order_date": order_date.strftime("%Y-%m-%d"),
        })

        scenario = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        settle_date = order_date + timedelta(days=1)

        if scenario == "CLEAN":
            legs = [leg1_amt, leg2_amt]
        elif scenario == "ONE_LEG_MISSING":
            legs = [leg1_amt]  # only first leg settles
        else:  # LEG_AMOUNT_OFF
            legs = [leg1_amt, round(leg2_amt * random.uniform(0.7, 0.9), 2)]

        for amt in legs:
            utr += 1
            settlements.append({
                "utr": f"UTR{utr}", "order_ref": order_id, "amount": amt,
                "settlement_date": settle_date.strftime("%Y-%m-%d"),
            })

    with open(f"{out_dir}/split_orders.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "customer", "total_amount", "leg1_method",
                                           "leg1_expected", "leg2_method", "leg2_expected", "order_date"])
        w.writeheader(); w.writerows(orders)
    with open(f"{out_dir}/split_settlements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        w.writeheader(); w.writerows(settlements)
    print(f"[split] {len(orders)} orders, {len(settlements)} settlements -> {out_dir}/")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="../data")
    a = p.parse_args()
    generate(a.count, a.seed, a.out)
