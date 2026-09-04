"""
models.py
---------
Shared data structures used across the matching pipeline.
Kept framework-agnostic (plain dataclasses) so matchers, the API layer,
and the Q&A layer all speak the same language.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum


class MatchStatus(str, Enum):
    MATCHED_RULE = "matched_rule"          # resolved by the fast rule engine
    MATCHED_AI = "matched_ai"              # resolved by the AI-assisted step
    UNRESOLVED = "unresolved"              # genuine exception, no match found


class ExceptionType(str, Enum):
    FEE_DEDUCTED = "fee_deducted"
    DELAYED = "delayed"
    MISSING_SETTLEMENT = "missing_settlement"
    DUPLICATE_SETTLEMENT = "duplicate_settlement"
    UNKNOWN_SETTLEMENT = "unknown_settlement"     # settlement with no matching order
    AMOUNT_MISMATCH = "amount_mismatch"
    NONE = "none"


@dataclass
class Order:
    order_id: str
    customer: str
    amount: float
    order_date: str


@dataclass
class Settlement:
    utr: str
    order_ref: str
    amount: float
    settlement_date: str


@dataclass
class MatchResult:
    """The unit of output the whole pipeline produces per order."""
    order: Order
    settlement: Optional[Settlement]
    status: MatchStatus
    exception_type: ExceptionType
    reason: str                 # plain-English explanation, always populated
    confidence: float = 1.0     # 1.0 for rule matches, model-reported for AI matches
    resolved_by: str = "rule_engine"   # which strategy handled this record

    def to_dict(self):
        return {
            "order_id": self.order.order_id,
            "customer": self.order.customer,
            "order_amount": self.order.amount,
            "order_date": self.order.order_date,
            "settlement_utr": self.settlement.utr if self.settlement else None,
            "settlement_amount": self.settlement.amount if self.settlement else None,
            "settlement_date": self.settlement.settlement_date if self.settlement else None,
            "status": self.status.value,
            "exception_type": self.exception_type.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "resolved_by": self.resolved_by,
        }


@dataclass
class UnknownSettlement:
    """A settlement that doesn't map to any known order at all."""
    settlement: Settlement
    reason: str

    def to_dict(self):
        return {
            "utr": self.settlement.utr,
            "order_ref": self.settlement.order_ref,
            "amount": self.settlement.amount,
            "settlement_date": self.settlement.settlement_date,
            "reason": self.reason,
            "exception_type": ExceptionType.UNKNOWN_SETTLEMENT.value,
        }
