"""
Ingestion layer with idempotency key enforcement and duplicate webhook detection.
Guarantees at-most-once processing semantics for processor webhooks.
"""
from typing import List, Tuple, Dict, Set, Optional
from datetime import datetime
from src.models.entities import ProcessorEvent, ExceptionRecord
from src.models.enums import IssueType, Severity, ExceptionStatus


class WebhookIngestor:
    """
    Idempotent gateway for ingesting processor webhooks and events.
    Detects replay attacks and duplicate webhook deliveries without corrupting ledgers.
    """

    def __init__(self, run_id: str, execution_timestamp: Optional[str] = None):
        self.run_id = run_id
        self.execution_timestamp = execution_timestamp or "2026-10-22T18:00:00Z"
        # Idempotency cache: tracks processed (processor_reference, event_type) and idempotency_key
        self.seen_keys: Set[str] = set()
        self.seen_refs: Set[Tuple[str, str]] = set()
        self.duplicate_exceptions: List[ExceptionRecord] = []
        self._exc_counter = 0

    def _next_exc_id(self) -> str:
        self._exc_counter += 1
        return f"EXC-2026-{self._exc_counter:06d}"

    def ingest_stream(
        self, raw_events: List[ProcessorEvent]
    ) -> Tuple[List[ProcessorEvent], List[ExceptionRecord]]:
        """
        Ingests a stream of processor events, enforcing idempotency.
        Returns:
            clean_events: Deduplicated events safe for reconciliation and settlement.
            duplicate_exceptions: Logged exception records for duplicate deliveries.
        """
        clean_events: List[ProcessorEvent] = []

        for ev in raw_events:
            ref_key = (ev.processor_reference, ev.event_type)
            is_dup_idemp = ev.idempotency_key in self.seen_keys
            is_dup_ref = ref_key in self.seen_refs

            if is_dup_idemp or is_dup_ref:
                # Idempotent skip: Do not double-process
                exc = ExceptionRecord(
                    exception_id=self._next_exc_id(),
                    reconciliation_run_id=self.run_id,
                    issue_type=IssueType.DUPLICATE_WEBHOOK_INGESTED.value,
                    severity=Severity.MEDIUM.value,
                    status=ExceptionStatus.OPEN.value,
                    entity_type="ProcessorEvent",
                    entity_id=ev.processor_event_id,
                    related_entity_type="PaymentOrder",
                    related_entity_id=ev.payment_order_id,
                    discrepancy_amount=float(ev.gross_amount),
                    detected_at=self.execution_timestamp,
                    details={
                        "processor_reference": ev.processor_reference,
                        "idempotency_key": ev.idempotency_key,
                        "ingested_at": ev.ingested_at,
                        "reason": "Duplicate webhook received; skipped to guarantee idempotency",
                    },
                    ground_truth_label=IssueType.DUPLICATE_WEBHOOK_INGESTED.value,
                )
                self.duplicate_exceptions.append(exc)
            else:
                self.seen_keys.add(ev.idempotency_key)
                self.seen_refs.add(ref_key)
                clean_events.append(ev)

        return clean_events, self.duplicate_exceptions
