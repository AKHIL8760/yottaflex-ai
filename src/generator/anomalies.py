"""
Edge case and anomaly injection module for synthetic reconciliation data.
Injects the 6 mandatory negative scenarios and produces an isolated ground truth catalog.
"""
from typing import List, Dict, Tuple, Any
from datetime import datetime, timedelta
import numpy as np

from src.models.enums import IssueType, Severity
from src.models.entities import (
    PaymentOrder,
    PaymentAttempt,
    ProcessorEvent,
    SettlementBatch,
    SettlementLine,
    BankStatementLine,
    GroundTruthAnomaly,
)


def inject_anomalies(
    rng: np.random.Generator,
    merchants: list,
    orders: List[PaymentOrder],
    attempts: List[PaymentAttempt],
    events: List[ProcessorEvent],
    batches: List[SettlementBatch],
    lines: List[SettlementLine],
    bank_lines: List[BankStatementLine],
    scale_factor: float = 1.0,
) -> Tuple[
    List[PaymentOrder],
    List[PaymentAttempt],
    List[ProcessorEvent],
    List[SettlementBatch],
    List[SettlementLine],
    List[BankStatementLine],
    List[GroundTruthAnomaly],
    List[ProcessorEvent],  # raw webhook stream with duplicate events
]:
    """
    Injects 6 mandatory edge cases and outputs modified datasets along with segregated ground truth.
    Edge Cases:
    1. Duplicate settlement line
    2. Bank amount differs by fee (e.g. $15 wire fee deducted)
    3. Refund appears before capture
    4. Unmatched record silently dropped (dropped processor events / orphaned bank lines)
    5. Currency mismatch (order in USD, settlement in EUR)
    6. Duplicate webhook event ingested twice
    """
    ground_truth: List[GroundTruthAnomaly] = []
    anomaly_counter = 0

    def next_anomaly_id():
        nonlocal anomaly_counter
        anomaly_counter += 1
        return f"ANO-2026-{anomaly_counter:06d}"

    # Calculate proportional counts based on scale
    count_dup_lines = max(2, int(50 * scale_factor))
    count_bank_fee_breaks = max(2, int(40 * scale_factor))
    count_refund_before_capture = max(2, int(30 * scale_factor))
    count_dropped_orders = max(2, int(40 * scale_factor))
    count_currency_mismatches = max(2, int(35 * scale_factor))
    count_dup_webhooks = max(2, int(50 * scale_factor))

    # Work on copies
    mod_orders = list(orders)
    mod_attempts = list(attempts)
    mod_events = list(events)
    mod_batches = list(batches)
    mod_lines = list(lines)
    mod_bank_lines = list(bank_lines)
    raw_webhook_stream = list(events)

    # -------------------------------------------------------------------------
    # 1. DUPLICATE SETTLEMENT LINE
    # -------------------------------------------------------------------------
    if len(mod_lines) > count_dup_lines:
        dup_indices = rng.choice(len(mod_lines), size=count_dup_lines, replace=False)
        for idx in dup_indices:
            src_line = mod_lines[idx]
            dup_line = src_line.model_copy()
            dup_line.settlement_line_id = f"{src_line.settlement_line_id}-DUP"
            mod_lines.append(dup_line)

            gt = GroundTruthAnomaly(
                anomaly_id=next_anomaly_id(),
                issue_type=IssueType.DUPLICATE_SETTLEMENT_LINE.value,
                entity_type="SettlementLine",
                entity_id=dup_line.settlement_line_id,
                expected_decision="FLAG_DUPLICATE_SETTLEMENT_LINE",
                expected_severity=Severity.HIGH.value,
                expected_discrepancy=float(dup_line.net_amount),
                details=f"Duplicate settlement line for processor event {src_line.processor_event_id} in batch {src_line.batch_id}",
            )
            ground_truth.append(gt)

    # -------------------------------------------------------------------------
    # 2. BANK AMOUNT DIFFERS BY FEE (e.g. $15.00 intermediary wire deduction)
    # -------------------------------------------------------------------------
    # Select settlement deposit bank lines specifically (which match settlement batches)
    settlement_bank_lines = [b for b in mod_bank_lines if "po_2026_" in b.narrative]
    if len(settlement_bank_lines) > count_bank_fee_breaks:
        selected_bank_lines = rng.choice(settlement_bank_lines, size=count_bank_fee_breaks, replace=False)
        for bank_line in selected_bank_lines:
            fee_deduction = float(rng.choice([15.00, 25.00, 35.00, 10.00]))
            orig_amount = bank_line.amount
            bank_line.amount = round(orig_amount - fee_deduction, 2)

            gt = GroundTruthAnomaly(
                anomaly_id=next_anomaly_id(),
                issue_type=IssueType.BANK_AMOUNT_FEE_MISMATCH.value,
                entity_type="BankStatementLine",
                entity_id=bank_line.bank_line_id,
                expected_decision="FLAG_BANK_FEE_BREAK",
                expected_severity=Severity.MEDIUM.value,
                expected_discrepancy=fee_deduction,
                details=f"Bank deposited {bank_line.amount} instead of expected batch amount {orig_amount} due to ${fee_deduction:.2f} wire fee deduction",
            )
            ground_truth.append(gt)

    # -------------------------------------------------------------------------
    # 3. REFUND APPEARS BEFORE CAPTURE
    # -------------------------------------------------------------------------
    refund_orders = [o for o in mod_orders if o.order_type == "REFUND" and o.parent_order_id]
    if len(refund_orders) >= count_refund_before_capture:
        selected_refunds = rng.choice(refund_orders, size=count_refund_before_capture, replace=False)
        order_dict = {o.payment_order_id: o for o in mod_orders}
        events_by_order = {}
        for ev in mod_events:
            events_by_order.setdefault(ev.payment_order_id, []).append(ev)

        for refund_order in selected_refunds:
            parent_order = order_dict.get(refund_order.parent_order_id)
            if parent_order:
                parent_time = datetime.fromisoformat(parent_order.created_at.rstrip("Z"))
                anom_time = (parent_time - timedelta(hours=2)).isoformat() + "Z"
                refund_order.created_at = anom_time
                refund_order.updated_at = anom_time

                for ev in events_by_order.get(refund_order.payment_order_id, []):
                    ev.event_timestamp = anom_time
                    ev.ingested_at = anom_time

                gt = GroundTruthAnomaly(
                    anomaly_id=next_anomaly_id(),
                    issue_type=IssueType.REFUND_BEFORE_CAPTURE.value,
                    entity_type="PaymentOrder",
                    entity_id=refund_order.payment_order_id,
                    expected_decision="FLAG_TEMPORAL_SEQUENCE_VIOLATION",
                    expected_severity=Severity.HIGH.value,
                    expected_discrepancy=float(refund_order.amount),
                    details=f"Refund {refund_order.payment_order_id} timestamp {anom_time} precedes original payment {parent_order.payment_order_id} timestamp {parent_order.created_at}",
                )
                ground_truth.append(gt)

    # -------------------------------------------------------------------------
    # 4. UNMATCHED RECORD SILENTLY DROPPED (Internal orders missing downstream)
    # -------------------------------------------------------------------------
    eligible_orders = [o for o in mod_orders if o.status == "CAPTURED" and o.order_type == "PAYMENT"]
    if len(eligible_orders) > count_dropped_orders:
        dropped_orders = rng.choice(eligible_orders, size=count_dropped_orders, replace=False)
        dropped_order_ids = {o.payment_order_id for o in dropped_orders}

        mod_events = [ev for ev in mod_events if ev.payment_order_id not in dropped_order_ids]
        mod_lines = [sl for sl in mod_lines if sl.payment_order_id not in dropped_order_ids]
        raw_webhook_stream = [ev for ev in raw_webhook_stream if ev.payment_order_id not in dropped_order_ids]

        for dropped_order in dropped_orders:
            gt = GroundTruthAnomaly(
                anomaly_id=next_anomaly_id(),
                issue_type=IssueType.UNMATCHED_DROPPED_RECORD.value,
                entity_type="PaymentOrder",
                entity_id=dropped_order.payment_order_id,
                expected_decision="FLAG_SILENTLY_DROPPED_TRANSACTION",
                expected_severity=Severity.CRITICAL.value,
                expected_discrepancy=float(dropped_order.amount),
                details=f"PaymentOrder {dropped_order.payment_order_id} of {dropped_order.amount} {dropped_order.currency} dropped: missing processor event and settlement",
            )
            ground_truth.append(gt)

    # Injected unmatched orphaned BankStatementLines
    orphaned_bank_count = max(2, int(20 * scale_factor))
    for i in range(orphaned_bank_count):
        orphan_id = f"BANK-2026-99{i:04d}"
        orphan_amt = round(float(rng.uniform(500.0, 5000.0)), 2)
        orphan_line = BankStatementLine.model_construct(
            bank_line_id=orphan_id,
            account_number="US99YOTTA0001234567",
            booking_date="2026-10-15",
            value_date="2026-10-15",
            amount=orphan_amt,
            currency="USD",
            bank_tx_type="CREDIT",
            narrative=f"UNKNOWN WIRE DEPOSIT / REF NONEXISTENT-{i:04d}",
            running_balance=100000.00 + (i * orphan_amt),
            created_at="2026-10-15T10:00:00Z",
        )
        mod_bank_lines.append(orphan_line)
        gt = GroundTruthAnomaly(
            anomaly_id=next_anomaly_id(),
            issue_type=IssueType.UNMATCHED_BANK_LINE.value,
            entity_type="BankStatementLine",
            entity_id=orphan_id,
            expected_decision="FLAG_UNMATCHED_BANK_DEPOSIT",
            expected_severity=Severity.HIGH.value,
            expected_discrepancy=orphan_amt,
            details=f"Orphaned bank line {orphan_id} of {orphan_amt} USD has no corresponding settlement batch payout reference",
        )
        ground_truth.append(gt)

    # -------------------------------------------------------------------------
    # 5. CURRENCY MISMATCH
    # -------------------------------------------------------------------------
    usd_lines = [sl for sl in mod_lines if sl.currency == "USD"]
    if len(usd_lines) > count_currency_mismatches:
        curr_mismatch_lines = rng.choice(usd_lines, size=count_currency_mismatches, replace=False)
        for line in curr_mismatch_lines:
            line.currency = "EUR"
            gt = GroundTruthAnomaly(
                anomaly_id=next_anomaly_id(),
                issue_type=IssueType.CURRENCY_MISMATCH.value,
                entity_type="SettlementLine",
                entity_id=line.settlement_line_id,
                expected_decision="FLAG_CURRENCY_MISMATCH",
                expected_severity=Severity.HIGH.value,
                expected_discrepancy=float(line.net_amount),
                details=f"Settlement line {line.settlement_line_id} currency EUR does not match payment order {line.payment_order_id} currency USD",
            )
            ground_truth.append(gt)

    # -------------------------------------------------------------------------
    # 6. SAME PROCESSOR EVENT INGESTED TWICE (DUPLICATE WEBHOOK)
    # -------------------------------------------------------------------------
    if len(mod_events) > count_dup_webhooks:
        dup_webhook_events = rng.choice(mod_events, size=count_dup_webhooks, replace=False)
        for ev in dup_webhook_events:
            dup_ev = ev.model_copy()
            ev_dt = datetime.fromisoformat(ev.event_timestamp.rstrip("Z"))
            dup_ev.ingested_at = (ev_dt + timedelta(minutes=5)).isoformat() + "Z"
            raw_webhook_stream.append(dup_ev)

            gt = GroundTruthAnomaly(
                anomaly_id=next_anomaly_id(),
                issue_type=IssueType.DUPLICATE_WEBHOOK_INGESTED.value,
                entity_type="ProcessorEvent",
                entity_id=ev.processor_event_id,
                expected_decision="IDEMPOTENT_DEDUPLICATE",
                expected_severity=Severity.MEDIUM.value,
                expected_discrepancy=float(ev.gross_amount),
                details=f"Processor event {ev.processor_event_id} (ref: {ev.processor_reference}) delivered twice via webhook. Idempotency layer must deduplicate.",
            )
            ground_truth.append(gt)

    return (
        mod_orders,
        mod_attempts,
        mod_events,
        mod_batches,
        mod_lines,
        mod_bank_lines,
        ground_truth,
        raw_webhook_stream,
    )
