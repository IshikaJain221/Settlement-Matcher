"""
repository.py
--------------
Repository Pattern: the ONLY place in the app that touches raw CSV files.
Everything else asks this module for data — it never touches disk directly.

Why this matters: if we later swap CSV files for a real database, only
this file needs to change. Nothing downstream (matchers, API routes,
Q&A layer) needs to know or care where the data physically lives.
"""

import csv
from pathlib import Path
from typing import List
from models import Order, Settlement


class DataRepository:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def get_orders(self) -> List[Order]:
        path = self.data_dir / "internal_orders.csv"
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return [
                Order(
                    order_id=row["order_id"],
                    customer=row["customer"],
                    amount=float(row["amount"]),
                    order_date=row["order_date"],
                )
                for row in reader
            ]

    def get_settlements(self) -> List[Settlement]:
        path = self.data_dir / "bank_settlements.csv"
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return [
                Settlement(
                    utr=row["utr"],
                    order_ref=row["order_ref"],
                    amount=float(row["amount"]),
                    settlement_date=row["settlement_date"],
                )
                for row in reader
            ]
