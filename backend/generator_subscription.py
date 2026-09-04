"""
generator_subscription.py
--------------------------
Scenario: Recurring subscription billing. Each customer has a plan
with a fixed renewal price; occasionally they upgrade/downgrade,
which should change the price from that cycle onward.

Anomalies:
  CLEAN              -> settled amount == current plan price
  WRONG_RENEWAL_AMT  -> settled amount doesn't match plan price at all (billing bug)
  STALE_PLAN_PRICE   -> settled amount == OLD plan price (upgrade/downgrade didn't take effect)
  MISSING_RENEWAL    -> no charge went through at all
"""
import csv, random, argparse
from datetime import datetime, timedelta

CUSTOMERS = ["Aarav Mehta", "Priya Singh", "Rohan Gupta", "Sneha Iyer", "Vikram Rao",
             "Ananya Joshi", "Karan Malhotra", "Divya Nair", "Arjun Kapoor", "Neha Reddy"]
PLANS = [("Basic", 199), ("Standard", 499), ("Pro", 999), ("Enterprise", 2499)]
SCENARIOS = ["CLEAN", "WRONG_RENEWAL_AMT", "STALE_PLAN_PRICE", "MISSING_RENEWAL"]
WEIGHTS =   [0.55,     0.15,                0.18,               0.12]

def random_date(start, days_range=45):
    return start + timedelta(days=random.randint(0, days_range))

def generate(count, seed, out_dir):
    random.seed(seed)
    start_date = datetime(2026, 6, 1)
    orders, settlements = [], []
    oid, utr = 5000, 1000000

    for _ in range(count):
        oid += 1
        order_id = f"ORD{oid}"
        customer = random.choice(CUSTOMERS)
        plan_name, plan_price = random.choice(PLANS)
        old_plan_name, old_plan_price = random.choice([p for p in PLANS if p[0] != plan_name])
        billing_date = random_date(start_date)

        orders.append({
            "order_id": order_id, "customer": customer, "plan_name": plan_name,
            "plan_price": float(plan_price), "billing_date": billing_date.strftime("%Y-%m-%d"),
        })

        scenario = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
        if scenario == "MISSING_RENEWAL":
            continue

        utr += 1
        settle_date = billing_date
        if scenario == "CLEAN":
            amt = float(plan_price)
        elif scenario == "STALE_PLAN_PRICE":
            amt = float(old_plan_price)
        else:  # WRONG_RENEWAL_AMT
            amt = round(plan_price * random.uniform(1.1, 1.5), 2)

        settlements.append({
            "utr": f"UTR{utr}", "order_ref": order_id, "amount": amt,
            "settlement_date": settle_date.strftime("%Y-%m-%d"),
        })

    with open(f"{out_dir}/subscription_orders.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "customer", "plan_name", "plan_price", "billing_date"])
        w.writeheader(); w.writerows(orders)
    with open(f"{out_dir}/subscription_settlements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utr", "order_ref", "amount", "settlement_date"])
        w.writeheader(); w.writerows(settlements)
    print(f"[subscription] {len(orders)} orders, {len(settlements)} settlements -> {out_dir}/")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="../data")
    a = p.parse_args()
    generate(a.count, a.seed, a.out)
