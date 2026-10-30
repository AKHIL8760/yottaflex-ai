"""
Resolution Engine and immutable state transition audit logging.
Manages automated and actor-driven resolutions for Operations, Risk/Compliance, and Admins.
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from src.models.entities import ExceptionRecord, Resolution
from src.models.enums import (
    ActorRole,
    ResolutionType,
    ExceptionStatus,
    IssueType,
)
from src.engine.rules import ReconciliationConfig


class ResolutionEngine:
    """
    State transition engine for reconciling payment exceptions.
    Ensures complete traceability and immutable audit logging.
    """

    def __init__(self, execution_timestamp: Optional[str] = None):
        self.resolutions: List[Resolution] = []
        self._res_counter = 0
        self.execution_timestamp = execution_timestamp or "2026-10-22T18:00:00Z"

    def _next_res_id(self) -> str:
        self._res_counter += 1
        return f"RES-2026-{self._res_counter:06d}"

    def auto_resolve_batch(
        self,
        exceptions: List[ExceptionRecord],
        config: Optional[ReconciliationConfig] = None,
    ) -> List[Resolution]:
        """
        Applies documented policy rules to automatically resolve standard, low-risk exceptions:
        1. Bank wire fee discrepancies ($10 - $35) -> Auto-adjusted to fee ledger
        2. Trivial rounding variances (<= $0.05) -> Accepted within tolerance
        """
        cfg = config or ReconciliationConfig()
        created_resolutions: List[Resolution] = []

        for exc in exceptions:
            if exc.status != ExceptionStatus.OPEN.value:
                continue

            # Policy 1: Auto-resolve recognized wire fee discrepancies
            if exc.issue_type == IssueType.BANK_AMOUNT_FEE_MISMATCH.value and cfg.auto_resolve_standard_wire_fees:
                if 9.99 <= exc.discrepancy_amount <= 35.01:
                    prev_state = exc.status
                    exc.status = ExceptionStatus.RESOLVED.value
                    res = Resolution(
                        resolution_id=self._next_res_id(),
                        exception_id=exc.exception_id,
                        actor_role=ActorRole.SYSTEM_ADMIN.value,
                        actor_id="AUTO_POLICY_ENGINE",
                        resolution_type=ResolutionType.AUTO_ADJUSTED.value,
                        notes=f"Auto-applied bank wire expense adjustment of ${exc.discrepancy_amount:.2f} per treasury policy.",
                        financial_adjustment_amount=exc.discrepancy_amount,
                        previous_state=prev_state,
                        new_state=ExceptionStatus.RESOLVED.value,
                        resolved_at=self.execution_timestamp,
                    )
                    self.resolutions.append(res)
                    created_resolutions.append(res)

            # Policy 2: Auto-resolve minor rounding variance
            elif exc.issue_type == IssueType.AMOUNT_TOLERANCE_EXCEEDED.value:
                if exc.discrepancy_amount <= cfg.auto_adjustment_limit:
                    prev_state = exc.status
                    exc.status = ExceptionStatus.RESOLVED.value
                    res = Resolution(
                        resolution_id=self._next_res_id(),
                        exception_id=exc.exception_id,
                        actor_role=ActorRole.SYSTEM_ADMIN.value,
                        actor_id="AUTO_POLICY_ENGINE",
                        resolution_type=ResolutionType.ACCEPT_TOLERANCE.value,
                        notes=f"Accepted trivial currency rounding difference of ${exc.discrepancy_amount:.2f}.",
                        financial_adjustment_amount=exc.discrepancy_amount,
                        previous_state=prev_state,
                        new_state=ExceptionStatus.RESOLVED.value,
                        resolved_at=self.execution_timestamp,
                    )
                    self.resolutions.append(res)
                    created_resolutions.append(res)

        return created_resolutions

    def apply_manual_resolution(
        self,
        exception: ExceptionRecord,
        actor_role: str,
        actor_id: str,
        resolution_type: str,
        notes: str,
        financial_adjustment: float = 0.0,
    ) -> Resolution:
        """
        Executes actor-driven resolution with role-based validation and state change auditing.
        """
        valid_roles = {r.value for r in ActorRole}
        if actor_role not in valid_roles:
            raise ValueError(f"Invalid actor role: {actor_role}. Allowed: {valid_roles}")

        # Check role-specific governance rules
        if exception.issue_type == IssueType.REFUND_BEFORE_CAPTURE.value:
            if actor_role not in (ActorRole.RISK_COMPLIANCE.value, ActorRole.SYSTEM_ADMIN.value):
                raise PermissionError("Temporal refund violations require RISK_COMPLIANCE or SYSTEM_ADMIN review.")

        prev_state = exception.status
        new_state = (
            ExceptionStatus.RESOLVED.value
            if resolution_type != ResolutionType.ESCALATE_FRAUD.value
            else ExceptionStatus.IN_REVIEW.value
        )
        exception.status = new_state

        res = Resolution(
            resolution_id=self._next_res_id(),
            exception_id=exception.exception_id,
            actor_role=actor_role,
            actor_id=actor_id,
            resolution_type=resolution_type,
            notes=notes,
            financial_adjustment_amount=financial_adjustment,
            previous_state=prev_state,
            new_state=new_state,
            resolved_at=self.execution_timestamp,
        )
        self.resolutions.append(res)
        return res

    def get_audit_trail_for_exception(self, exception_id: str) -> List[Resolution]:
        """Returns all resolution log entries associated with an exception."""
        return [r for r in self.resolutions if r.exception_id == exception_id]
