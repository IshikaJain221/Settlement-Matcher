"""
generator_tax.py
------------------
Scenario: Order amount should include 18% GST. Sometimes the settlement
reflects the pre-tax amount, or an incorrectly calculated tax amount.

Anomalies:
  CLEAN            -> settled == expected_after_tax
  TAX_NOT_APPLIED  -> settled == expected_before_tax (pre-tax amount)
  WRONG_TAX_RATE   -> settled reflects a different tax % (e.g. 12% or 28% instead of 18%)
  MISSING          -> no settlement at all
"""
import csv, random, argparse
from datetime import datetime, timedelta

CUSTOMERS = ["Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
             "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy"]
ITEMS = ["Laptop Stand", "Office Chair", "Wireless Mouse", "Standing Desk", "Monitor Arm",
         "Mechanical Keyboard", "Webcam HD", "Desk Lamp"]
GST_RATE = 0.18
WRONG_RATES = [0.12, 0.28, 0.05]
SCENARIOS = ["CLEAN", "TAX_NOT_APPLIED", "WRONG_TAX_RATE", "MISSING"]
WEIGHTS =   [0.55,     0.20,              0.15,             0.10]

def random_date(start, days_range=45):
    return start + timedelta(days=random.randint(0, days_range))

def generate(count, seed, out_dir):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)
    orders, settlements = [], []
    oid, utr = 6000, 1100000

    for _ in range(count):
        oid += 1
        order_id = f"ORD{oid}"
        customer = random.choice(CUSTOMERS)
        item = random.choice(ITEMS)
        pre_tax = round(random.uniform(499, 19999), 2)
        after_tax = round(pre_tax * (1 + GST_RATE), 2)
        order_date = random_date(start_date)

        orders.append({
            "order_id": order_id, "customer": customer, "item": item,
            "expected_before_tax": pre_tax, "expected_after_tax": after_tax,
            "order_date": order_date.strftime("%Y-%m-%d"),
        })

        scenario = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        if scenario == "MISSING":
            continue

        utr += 1
        settle_date = order_date + timedelta(days=1)
        if scenario == "CLEAN":
            amt = after_tax
        elif scenario == "TAX_NOT_APPLIED":
            amt = pre_tax
        else:  # WRONG_TAX_RATE
            amt = round(pre_tax * (1 + random.choice(WRONG_RATES)), 2)

        settlements.append({
            "utr": f"UTR{utr}", "order_ref": order_id, "amount": amt,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })

    with open(f"{out_dir}/tax_orders.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "customer", "item", "expected_before_tax",
                                           "expected_after_tax", "order_date"])
        w.writeheader(); w.writerows(orders)
    with open(f"{out_dir}/tax_settlements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        w.writeheader(); w.writerows(settlements)
    print(f"[tax] {len(orders)} orders, {len(settlements)} settlements -> {out_dir}/")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="../data")
    a = p.parse_args()
    generate(a.count, a.seed, a.out)
