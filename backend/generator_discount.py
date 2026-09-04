"""
generator_discount.py
----------------------
Scenario: E-commerce purchase with a coupon/discount applied.
Tracks THREE amounts so the matcher can tell exactly where things broke:
  expected_before  -> listed price before any discount
  expected_after   -> what the customer should actually be charged
  actual_settled   -> what the bank/gateway actually recorded

Anomalies injected:
  CLEAN              -> settled == expected_after (discount applied correctly)
  DISCOUNT_NOT_APPLIED -> settled == expected_before (customer overcharged)
  WRONG_DISCOUNT_PCT  -> settled matches neither (a different % was applied)
  DOUBLE_DISCOUNT     -> settled is lower than expected_after (coupon stacked/applied twice)
  MISSING             -> no settlement at all
"""

import csv
import random
import argparse
from datetime import datetime, timedelta

PRODUCTS = [
    ("Myntra", "Floral Wrap Dress", 2499),
    ("Myntra", "Slim Fit Chinos", 1799),
    ("Ajio", "Leather Sneakers", 3499),
    ("Nykaa", "Skincare Combo Set", 1299),
    ("Amazon", "Wireless Earbuds", 2999),
    ("Flipkart", "Cotton Bedsheet Set", 1599),
    ("Myntra", "Denim Jacket", 3299),
    ("Ajio", "Formal Shirt", 1499),
]
CUSTOMERS = ["Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
             "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy"]

SCENARIOS = ["CLEAN", "DISCOUNT_NOT_APPLIED", "WRONG_DISCOUNT_PCT", "DOUBLE_DISCOUNT", "MISSING"]
WEIGHTS =   [0.55,     0.20,                   0.10,                 0.08,               0.07]


def random_date(start, days_range=45):
    return start + timedelta(days=random.randint(0, days_range))


def generate(count, seed, out_dir):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)
    orders, settlements = [], []
    oid, utr = 2000, 700000

    for _ in range(count):
        oid += 1
        order_id = f"ORD{oid}"
        merchant, product, price = random.choice(PRODUCTS)
        customer = random.choice(CUSTOMERS)
        discount_pct = random.choice([10, 20, 30, 40, 50])
        expected_before = float(price)
        expected_after = round(price * (1 - discount_pct / 100), 2)
        order_date = random_date(start_date)

        orders.append({
            "order_id": order_id, "customer": customer, "merchant": merchant, "product": product,
            "expected_before": expected_before, "discount_pct": discount_pct,
            "expected_after": expected_after, "order_date": order_date.strftime("%Y-%m-%d"),
        })

        scenario = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        if scenario == "MISSING":
            continue

        utr += 1
        settle_date = order_date + timedelta(days=1)
        if scenario == "CLEAN":
            settled = expected_after
        elif scenario == "DISCOUNT_NOT_APPLIED":
            settled = expected_before
        elif scenario == "WRONG_DISCOUNT_PCT":
            wrong_pct = random.choice([p for p in [10, 20, 30, 40, 50] if p != discount_pct])
            settled = round(price * (1 - wrong_pct / 100), 2)
        else:  # DOUBLE_DISCOUNT
            settled = round(expected_after * (1 - discount_pct / 100), 2)

        settlements.append({
            "utr": f"UTR{utr}", "order_ref": order_id, "amount": settled,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })

    with open(f"{out_dir}/discount_orders.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "customer", "merchant", "product",
                                           "expected_before", "discount_pct", "expected_after", "order_date"])
        w.writeheader(); w.writerows(orders)

    with open(f"{out_dir}/discount_settlements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        w.writeheader(); w.writerows(settlements)

    print(f"[discount] {len(orders)} orders, {len(settlements)} settlements -> {out_dir}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="../data")
    a = p.parse_args()
    generate(a.count, a.seed, a.out)
