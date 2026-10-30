"""
Unit and integration tests for Synthetic Data Generator and edge case injection.
"""
import pytest
import re
from src.generator import SyntheticDataGenerator
from src.models.enums import IssueType


def test_starter_generation_counts_and_ids():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()
    counts = data["metadata"]["counts"]

    assert counts["merchants"] == 100
    assert counts["payment_orders"] == 2500
    assert counts["payment_attempts"] >= 2500
    assert counts["settlement_batches"] == 50
    assert counts["bank_statement_lines"] >= 250
    assert counts["ground_truth_anomalies"] > 0

    # Test ID Nomenclature
    assert re.match(r"^MRC-2026-\d{5}$", data["merchants"][0].merchant_id)
    assert re.match(r"^PAY-2026-\d{8}$", data["payment_orders"][0].payment_order_id)
    assert re.match(r"^ATT-PAY-2026-\d{8}-\d{2}$", data["payment_attempts"][0].payment_attempt_id)
    assert re.match(r"^PRC-2026-\d{8}$", data["processor_events"][0].processor_event_id)
    assert re.match(r"^SET-2026-\d{6}$", data["settlement_batches"][0].batch_id)
    assert re.match(r"^STL-SET-2026-\d{6}-\d{3}$", data["settlement_lines"][0].settlement_line_id)
    assert re.match(r"^BANK-2026-\d{6}$", data["bank_statement_lines"][0].bank_line_id)


def test_deterministic_reproducibility():
    gen1 = SyntheticDataGenerator(seed=20261022, scale="starter")
    d1 = gen1.generate_all()

    gen2 = SyntheticDataGenerator(seed=20261022, scale="starter")
    d2 = gen2.generate_all()

    assert len(d1["payment_orders"]) == len(d2["payment_orders"])
    assert d1["payment_orders"][0].payment_order_id == d2["payment_orders"][0].payment_order_id
    assert d1["payment_orders"][0].amount == d2["payment_orders"][0].amount
    assert d1["settlement_batches"][0].total_net == d2["settlement_batches"][0].total_net


def test_edge_cases_present_in_ground_truth():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()
    gt_types = {gt.issue_type for gt in data["ground_truth"]}

    expected_issues = {
        IssueType.DUPLICATE_SETTLEMENT_LINE.value,
        IssueType.BANK_AMOUNT_FEE_MISMATCH.value,
        IssueType.REFUND_BEFORE_CAPTURE.value,
        IssueType.UNMATCHED_DROPPED_RECORD.value,
        IssueType.CURRENCY_MISMATCH.value,
        IssueType.DUPLICATE_WEBHOOK_INGESTED.value,
        IssueType.UNMATCHED_BANK_LINE.value,
    }

    for exp in expected_issues:
        assert exp in gt_types, f"Expected anomaly type {exp} missing from ground truth catalog"
