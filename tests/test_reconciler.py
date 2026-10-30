"""
Unit and integration tests for Multi-Way Reconciliation Engine and Idempotency Gateway.
"""
from src.generator import SyntheticDataGenerator
from src.engine import WebhookIngestor, MultiWayReconciler
from src.models.enums import IssueType


def test_webhook_ingestor_idempotency():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()

    ingestor = WebhookIngestor(run_id="TEST-IDEMP")
    clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

    # Raw stream contains duplicates; clean stream should be deduplicated
    assert len(clean_events) < len(data["raw_webhook_stream"])
    assert len(dup_excs) > 0
    assert dup_excs[0].issue_type == IssueType.DUPLICATE_WEBHOOK_INGESTED.value


def test_multi_way_reconciliation_detects_all_edge_cases():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()

    ingestor = WebhookIngestor(run_id="TEST-RECON")
    clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

    reconciler = MultiWayReconciler(run_id="TEST-RECON")
    recon_res = reconciler.reconcile_all(
        orders=data["payment_orders"],
        events=clean_events,
        batches=data["settlement_batches"],
        lines=data["settlement_lines"],
        bank_lines=data["bank_statement_lines"],
        initial_exceptions=dup_excs,
    )

    detected_issues = {e.issue_type for e in recon_res["exceptions"]}

    # Verify detection of all mandatory edge cases
    assert IssueType.DUPLICATE_SETTLEMENT_LINE.value in detected_issues
    assert IssueType.BANK_AMOUNT_FEE_MISMATCH.value in detected_issues
    assert IssueType.REFUND_BEFORE_CAPTURE.value in detected_issues
    assert IssueType.UNMATCHED_DROPPED_RECORD.value in detected_issues
    assert IssueType.CURRENCY_MISMATCH.value in detected_issues
    assert IssueType.DUPLICATE_WEBHOOK_INGESTED.value in detected_issues
    assert IssueType.UNMATCHED_BANK_LINE.value in detected_issues

    # Verify matches
    assert len(recon_res["matches"]) > 4000
    assert recon_res["summary"]["match_rate_percentage"] > 95.0
