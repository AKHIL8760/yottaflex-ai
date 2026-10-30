"""
Reconciliation matching rules, tolerance configurations, and scoring logic.
"""
from typing import Optional, Tuple
from dataclasses import dataclass
from src.models.enums import MatchStatus


@dataclass
class ReconciliationConfig:
    """
    Configuration parameters for matching tolerances and thresholds.
    """
    # Amount tolerance in currency units (e.g. $0.05 for minor currency rounding / FX variance)
    amount_tolerance: float = 0.05
    # Date window tolerance in days (settlement to bank statement booking)
    date_window_days: int = 7
    # Minimum confidence score required to assert an automatic match
    min_confidence_score: float = 0.85
    # Allow automatic resolution of fee breaks within wire fee policy ($10 - $35)
    auto_resolve_standard_wire_fees: bool = True
    # Maximum financial discrepancy eligible for automatic rounding adjustment
    auto_adjustment_limit: float = 0.05


def evaluate_amount_match(
    left_amt: float, right_amt: float, tolerance: float = 0.05
) -> Tuple[MatchStatus, float, float]:
    """
    Evaluates monetary match between two operands.
    Returns (MatchStatus, discrepancy_amount, confidence_score).
    """
    diff = round(abs(left_amt - right_amt), 2)
    if diff == 0.0:
        return MatchStatus.EXACT_MATCH, 0.0, 1.00
    elif diff <= tolerance:
        # High confidence tolerance match (e.g. 1-2 cents rounding)
        score = max(0.90, round(1.0 - (diff / (tolerance * 10)), 4))
        return MatchStatus.TOLERANCE_MATCH, diff, score
    else:
        # Significant discrepancy
        score = max(0.20, round(1.0 - min(1.0, diff / max(left_amt, right_amt, 1.0)), 4))
        return MatchStatus.SUSPECTED_MISMATCH, diff, score
