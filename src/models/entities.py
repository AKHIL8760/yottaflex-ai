"""
Data models and entities for YottaFlex Payment Reconciliation System.
Implements Pydantic schemas for master, transaction, settlement, reconciliation, and audit entities.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Merchant(BaseModel):
    merchant_id: str = Field(description="Primary Key, format MRC-2026-XXXXX")
    name: str
    mcc: str = Field(description="4-digit Merchant Category Code")
    currency: str = Field(default="USD")
    fee_rate_bps: float = Field(description="Variable fee in basis points (e.g. 175 = 1.75%)")
    fixed_fee: float = Field(description="Fixed fee per transaction (e.g. 0.30)")
    payout_schedule: str = Field(default="DAILY")
    status: str = Field(default="ACTIVE")
    created_at: str


class PaymentOrder(BaseModel):
    payment_order_id: str = Field(description="Primary Key, format PAY-2026-XXXXXXXX")
    merchant_id: str = Field(description="Foreign Key referencing Merchant")
    customer_id: str
    amount: float = Field(description="Monetary transaction amount in specified currency")
    currency: str = Field(default="USD")
    order_type: str = Field(default="PAYMENT", description="PAYMENT or REFUND")
    parent_order_id: Optional[str] = Field(default=None, description="Parent payment order ID if this is a refund")
    status: str = Field(default="PENDING")
    payment_method: str = Field(default="CARD")
    channel: str = Field(default="WEB")
    created_at: str
    updated_at: str


class PaymentAttempt(BaseModel):
    payment_attempt_id: str = Field(description="Primary Key, format ATT-<payment-id>-XX")
    payment_order_id: str = Field(description="Foreign Key referencing PaymentOrder")
    processor_id: str = Field(default="STRIPE")
    attempt_number: int = Field(default=1)
    amount: float
    currency: str = Field(default="USD")
    status: str = Field(default="SUCCESS")
    error_code: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class ProcessorEvent(BaseModel):
    processor_event_id: str = Field(description="Primary Key, format PRC-2026-XXXXXXXX")
    payment_attempt_id: str = Field(description="Foreign Key referencing PaymentAttempt")
    payment_order_id: str = Field(description="Foreign Key referencing PaymentOrder")
    event_type: str = Field(description="AUTHORIZATION, CAPTURE, REFUND, CHARGEBACK")
    event_status: str = Field(default="PROCESSED")
    gross_amount: float
    fee_amount: float
    net_amount: float = Field(description="Derived: gross_amount - fee_amount")
    currency: str = Field(default="USD")
    processor_reference: str
    idempotency_key: str
    event_timestamp: str
    ingested_at: str


class SettlementBatch(BaseModel):
    batch_id: str = Field(description="Primary Key, format SET-2026-XXXXXX")
    processor_id: str = Field(default="STRIPE")
    merchant_id: str = Field(default="AGGREGATE")
    batch_date: str
    period_start: str
    period_end: str
    total_gross: float = Field(description="Sum of settlement line gross amounts")
    total_fee: float = Field(description="Sum of settlement line fee amounts")
    total_net: float = Field(description="Sum of settlement line net amounts")
    line_count: int
    currency: str = Field(default="USD")
    status: str = Field(default="CLOSED")
    payout_reference: str
    created_at: str


class SettlementLine(BaseModel):
    settlement_line_id: str = Field(description="Primary Key, format STL-<batch-id>-XXX")
    batch_id: str = Field(description="Foreign Key referencing SettlementBatch")
    processor_event_id: str = Field(description="Foreign Key referencing ProcessorEvent")
    payment_order_id: str = Field(description="Foreign Key referencing PaymentOrder")
    line_type: str = Field(default="CAPTURE")
    gross_amount: float
    fee_amount: float
    net_amount: float = Field(description="Derived: gross_amount - fee_amount")
    currency: str = Field(default="USD")
    settlement_date: str
    created_at: str


class BankStatementLine(BaseModel):
    bank_line_id: str = Field(description="Primary Key, format BANK-2026-XXXXXX")
    account_number: str
    booking_date: str
    value_date: str
    amount: float = Field(description="Positive credit deposit amount or negative debit")
    currency: str = Field(default="USD")
    bank_tx_type: str = Field(default="CREDIT")
    narrative: str = Field(description="Bank line text containing payout reference or batch ID")
    running_balance: float
    created_at: str


class ReconciliationMatch(BaseModel):
    match_id: str = Field(description="Primary Key, format REC-2026-XXXXXX")
    reconciliation_run_id: str
    match_type: str = Field(description="ORDER_TO_PROCESSOR, EVENT_TO_SETTLEMENT, SETTLEMENT_TO_BANK")
    left_entity_type: str
    left_entity_id: str
    right_entity_type: str
    right_entity_id: str
    match_status: str = Field(default="EXACT_MATCH")
    confidence_score: float = Field(default=1.0)
    left_amount: float
    right_amount: float
    discrepancy_amount: float = Field(default=0.0)
    match_rule: str
    matched_at: str


class ExceptionRecord(BaseModel):
    exception_id: str = Field(description="Primary Key, format EXC-2026-XXXXXX")
    reconciliation_run_id: str
    issue_type: str
    severity: str = Field(default="MEDIUM")
    status: str = Field(default="OPEN")
    entity_type: str
    entity_id: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    discrepancy_amount: float = Field(default=0.0)
    detected_at: str
    details: Dict[str, Any] = Field(default_factory=dict)
    ground_truth_label: Optional[str] = None


class Resolution(BaseModel):
    resolution_id: str = Field(description="Primary Key, format RES-2026-XXXXXX")
    exception_id: str = Field(description="Foreign Key referencing ExceptionRecord")
    actor_role: str
    actor_id: str
    resolution_type: str
    notes: str
    financial_adjustment_amount: float = Field(default=0.0)
    previous_state: str = Field(default="OPEN")
    new_state: str = Field(default="RESOLVED")
    resolved_at: str


class GroundTruthAnomaly(BaseModel):
    anomaly_id: str
    issue_type: str
    entity_type: str
    entity_id: str
    expected_decision: str
    expected_severity: str
    expected_discrepancy: float = 0.0
    details: str
