"""
Unit tests for Resolution Engine, Role-based Governance, and State Audit Trail.
"""
import pytest
from src.models.entities import ExceptionRecord
from src.models.enums import ActorRole, ResolutionType, ExceptionStatus, IssueType
from src.engine import ResolutionEngine


def test_auto_resolution_policy():
    resolver = ResolutionEngine()
    exc = ExceptionRecord(
        exception_id="EXC-2026-000001",
        reconciliation_run_id="RUN-TEST",
        issue_type=IssueType.BANK_AMOUNT_FEE_MISMATCH.value,
        severity="MEDIUM",
        status=ExceptionStatus.OPEN.value,
        entity_type="BankStatementLine",
        entity_id="BANK-2026-000001",
        discrepancy_amount=15.00,
        detected_at="2026-10-22T10:00:00Z",
        details={"reason": "Standard wire fee"},
    )

    resolutions = resolver.auto_resolve_batch([exc])
    assert len(resolutions) == 1
    assert exc.status == ExceptionStatus.RESOLVED.value
    assert resolutions[0].resolution_type == ResolutionType.AUTO_ADJUSTED.value
    assert resolutions[0].financial_adjustment_amount == 15.00


def test_manual_resolution_and_audit_trail():
    resolver = ResolutionEngine()
    exc = ExceptionRecord(
        exception_id="EXC-2026-000002",
        reconciliation_run_id="RUN-TEST",
        issue_type=IssueType.UNMATCHED_BANK_LINE.value,
        severity="HIGH",
        status=ExceptionStatus.OPEN.value,
        entity_type="BankStatementLine",
        entity_id="BANK-2026-000002",
        discrepancy_amount=2500.00,
        detected_at="2026-10-22T10:00:00Z",
        details={"reason": "Orphan deposit"},
    )

    res = resolver.apply_manual_resolution(
        exception=exc,
        actor_role=ActorRole.OPERATIONS_ANALYST.value,
        actor_id="ops_analyst_01",
        resolution_type=ResolutionType.MANUAL_MATCH.value,
        notes="Manually bound orphan deposit to external settlement reference wire #88392",
        financial_adjustment=2500.00,
    )

    assert exc.status == ExceptionStatus.RESOLVED.value
    assert res.previous_state == ExceptionStatus.OPEN.value
    assert res.new_state == ExceptionStatus.RESOLVED.value

    # Verify audit trail
    history = resolver.get_audit_trail_for_exception("EXC-2026-000002")
    assert len(history) == 1
    assert history[0].actor_id == "ops_analyst_01"


def test_role_governance_on_refund_violations():
    resolver = ResolutionEngine()
    exc = ExceptionRecord(
        exception_id="EXC-2026-000003",
        reconciliation_run_id="RUN-TEST",
        issue_type=IssueType.REFUND_BEFORE_CAPTURE.value,
        severity="HIGH",
        status=ExceptionStatus.OPEN.value,
        entity_type="PaymentOrder",
        entity_id="PAY-2026-00000001",
        discrepancy_amount=100.00,
        detected_at="2026-10-22T10:00:00Z",
        details={"reason": "Refund preceding capture"},
    )

    # Operations Analyst should NOT be allowed to resolve temporal refund anomalies (Risk required)
    with pytest.raises(PermissionError):
        resolver.apply_manual_resolution(
            exception=exc,
            actor_role=ActorRole.OPERATIONS_ANALYST.value,
            actor_id="ops_user",
            resolution_type=ResolutionType.WRITE_OFF.value,
            notes="Attempting write-off",
        )

    # Risk & Compliance reviewer IS allowed
    res = resolver.apply_manual_resolution(
        exception=exc,
        actor_role=ActorRole.RISK_COMPLIANCE.value,
        actor_id="risk_officer_04",
        resolution_type=ResolutionType.ESCALATE_FRAUD.value,
        notes="Escalated out-of-order refund to fraud detection team for merchant freeze",
    )
    assert res.actor_role == ActorRole.RISK_COMPLIANCE.value
