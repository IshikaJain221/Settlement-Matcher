"""
data_generator.py
------------------
Generates two synthetic datasets for Settlement Matcher:
  1. internal_orders.csv   -> "our records" (what we expect to be paid)
  2. bank_settlements.csv  -> "bank records" (what actually arrived)

Deliberately injects realistic mismatches so the matching engine has
real problems to solve:
  - FEE_DEDUCTED   : settlement amount is slightly less (gateway fee)
  - DELAYED        : settlement date is a few days after the order date
  - MISSING        : order has no corresponding settlement at all
  - DUPLICATE      : settlement appears twice for one order
  - EXTRA_UNKNOWN  : a settlement exists with no matching order
                      (e.g. a stray/duplicate bank credit)
  - CLEAN          : matches perfectly (the "easy" case)

Run:
    python data_generator.py --count 80 --seed 42
"""

import csv
import random
import argparse
from datetime import datetime, timedelta

CUSTOMERS = [
    "Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
    "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy",
    "Sameer Khan", "Ishita Sharma", "Aditya Verma", "Pooja Desai", "Rahul Bose",
]

MISMATCH_TYPES = ["CLEAN", "FEE_DEDUCTED", "DELAYED", "MISSING", "DUPLICATE", "EXTRA_UNKNOWN"]
# Weighted so most records are clean, like real life
WEIGHTS =         [0.55,    0.15,            0.10,      0.08,      0.07,        0.05]


def random_date(start, days_range=60):
    return start + timedelta(days=random.randint(0, days_range))


def generate(count: int, seed: int, out_dir: str):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)

    orders = []
    settlements = []

    order_id_counter = 1000
    utr_counter = 500000

    for _ in range(count):
        order_id_counter += 1
        order_id = f"ORD{order_id_counter}"
        customer = random.choice(CUSTOMERS)
        amount = round(random.uniform(299, 24999), 2)
        order_date = random_date(start_date)

        mismatch = random.choices(MISMATCH_TYPES, weights=WEIGHTS, k=1)[0]

        orders.append({
            "order_id": order_id,
            "customer": customer,
            "amount": amount,
            "order_date": order_date.strftime("%Y-%m-%d"),
        })

        if mismatch == "MISSING":
            # No settlement generated at all -> genuine exception
            continue

        utr_counter += 1
        utr = f"UTR{utr_counter}"
        settle_amount = amount
        settle_date = order_date

        if mismatch == "FEE_DEDUCTED":
            fee = round(amount * random.uniform(0.015, 0.025), 2)  # 1.5-2.5% gateway fee
            settle_amount = round(amount - fee, 2)
            settle_date = order_date + timedelta(days=1)
        elif mismatch == "DELAYED":
            settle_date = order_date + timedelta(days=random.randint(4, 9))
        elif mismatch == "DUPLICATE":
            settle_date = order_date + timedelta(days=1)
        else:  # CLEAN
            settle_date = order_date + timedelta(days=1)

        settlements.append({
            "utr": utr,
            "order_ref": order_id,
            "amount": settle_amount,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })

        if mismatch == "DUPLICATE":
            # Same settlement recorded twice by mistake (a real bank-feed bug)
            utr_counter += 1
            settlements.append({
                "utr": f"UTR{utr_counter}",
                "order_ref": order_id,
                "amount": settle_amount,
                "settlement_date": settle_date.strftime("%Y-%m-%d"),
            })

    # A few stray settlements with no matching order at all
    extra_unknowns = max(1, count // 20)
    for _ in range(extra_unknowns):
        utr_counter += 1
        settlements.append({
            "utr": f"UTR{utr_counter}",
            "order_ref": f"ORD{random.randint(1, 999)}",  # doesn't exist in orders
            "amount": round(random.uniform(299, 24999), 2),
            "settlement_date": random_date(start_date).strftime("%Y-%m-%d"),
        })

    random.shuffle(orders)
    random.shuffle(settlements)

    with open(f"{out_dir}/internal_orders.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "customer", "amount", "order_date"])
        writer.writeheader()
        writer.writerows(orders)

    with open(f"{out_dir}/bank_settlements.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        writer.writeheader()
        writer.writerows(settlements)

    print(f"Generated {len(orders)} orders and {len(settlements)} settlements -> {out_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="../data")
    args = parser.parse_args()
    generate(args.count, args.seed, args.out)
