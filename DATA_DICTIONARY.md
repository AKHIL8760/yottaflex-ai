# YottaFlex.ai Payment Reconciliation Platform — Enterprise Data Dictionary

This Data Dictionary defines the formal specification, structural constraints, field data types, nullability, uniqueness rules, units, permitted enumerations, and validation criteria for all 10 core entities in the YottaFlex multi-way reconciliation system.

---

## 1. Merchant (`merchants`)
Parent master table representing registered business clients initiating payment orders and receiving settlements.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `merchant_id` | String | **Required** | Regex: `^MRC-2026-\d{5}$` | None | **Primary Key** | Must follow uniform zero-padded pattern `MRC-2026-00001` |
| `name` | String | **Required** | Non-empty string (1–128 chars) | None | Non-unique | Must not contain illegal control characters |
| `mcc` | String | **Required** | 4-digit ISO 18245 MCC code (e.g. `5411`, `5732`, `5812`, `7372`) | Categorical | Non-unique | Must be valid numeric string of exactly 4 digits |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Must match standard supported 3-letter currency code |
| `fee_rate_bps` | Numeric(8,2) | **Required** | `50.00` to `500.00` | Basis Points (1 bp = 0.01%) | Non-unique | Must be non-negative; rate applied as `gross * (bps / 10000)` |
| `fixed_fee` | Numeric(8,2) | **Required** | `0.10` to `2.00` | Currency units ($/€/£) | Non-unique | Must be >= 0.00 |
| `payout_schedule` | String | **Required** | `DAILY`, `WEEKLY`, `MONTHLY` | Schedule Enum | Non-unique | Default is `DAILY` |
| `status` | String | **Required** | `ACTIVE`, `SUSPENDED`, `TERMINATED` | Status Enum | Non-unique | Only `ACTIVE` merchants can initiate payment orders |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be prior to any associated payment order |

---

## 2. PaymentOrder (`payment_orders`)
The commercial instruction representing customer intent to pay or receive a refund.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `payment_order_id` | String | **Required** | Regex: `^PAY-2026-\d{8}$` | None | **Primary Key** | Must follow uniform 8-digit zero-padded pattern `PAY-2026-00000001` |
| `merchant_id` | String | **Required** | Foreign key to `merchants.merchant_id` | None | Non-unique | Must reference an existing merchant record |
| `customer_id` | String | **Required** | `CUST-\d{8}` | None | Non-unique | Non-empty customer identifier |
| `amount` | Numeric(14,2)| **Required** | `0.50` to `50000.00` | Currency units | Non-unique | Must be strictly positive (> 0.00); 2 decimal precision |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Must be supported currency code |
| `order_type` | String | **Required** | `PAYMENT`, `REFUND` | Order Type Enum | Non-unique | `REFUND` orders must have valid `parent_order_id` |
| `parent_order_id` | String | **Optional** | Foreign key to `payment_orders.payment_order_id` | None | Non-unique | Must be null for `PAYMENT`; must reference captured payment for `REFUND` |
| `status` | String | **Required** | `PENDING`, `AUTHORIZED`, `CAPTURED`, `FAILED`, `REFUNDED`, `PARTIALLY_REFUNDED` | Status Enum | Non-unique | Must respect valid state machine transitions |
| `payment_method` | String | **Required** | `CARD`, `ACH`, `DIGITAL_WALLET`, `WIRE` | Method Enum | Non-unique | Non-empty method description |
| `channel` | String | **Required** | `WEB`, `MOBILE_APP`, `POS`, `API` | Channel Enum | Non-unique | Channel of origin |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Ordering: `created_at <= updated_at` |
| `updated_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= `created_at` |

---

## 3. PaymentAttempt (`payment_attempts`)
A discrete transactional attempt to route a payment order through an external payment processor.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `payment_attempt_id`| String | **Required** | Regex: `^ATT-PAY-2026-\d{8}-\d{2}$` | None | **Primary Key** | E.g. `ATT-PAY-2026-00000001-01` |
| `payment_order_id` | String | **Required** | Foreign key to `payment_orders.payment_order_id` | None | Non-unique | Must reference valid parent order |
| `processor_id` | String | **Required** | `STRIPE`, `ADYEN`, `CHASE_PAYMENTECH` | Processor ID | Non-unique | Authorized processing gateway identifier |
| `attempt_number` | Integer | **Required** | `>= 1` | Sequential Index | Composite Unique (`order_id`, `attempt_number`) | 1-based monotonically increasing counter per order |
| `amount` | Numeric(14,2)| **Required** | Matches parent `payment_orders.amount` | Currency units | Non-unique | Must equal order amount unless partial refund |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Must match parent order currency |
| `status` | String | **Required** | `SUCCESS`, `FAILED`, `TIMED_OUT` | Attempt Status | Non-unique | State of processor attempt |
| `error_code` | String | **Optional** | `INSUFFICIENT_FUNDS`, `EXPIRED_CARD`, `DO_NOT_HONOR`, null | None | Non-unique | Mandatory if status != `SUCCESS` |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= parent `payment_orders.created_at` |
| `completed_at` | Timestamp | **Optional** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= `created_at` if present |

---

## 4. ProcessorEvent (`processor_events`)
Asynchronous webhook or gateway ledger events emitted by the processor (authorization, capture, refund).

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `processor_event_id`| String | **Required** | Regex: `^PRC-2026-\d{8}$` | None | **Primary Key** | Zero-padded unique event identifier |
| `payment_attempt_id`| String | **Required** | Foreign key to `payment_attempts.payment_attempt_id` | None | Non-unique | Valid attempt reference |
| `payment_order_id` | String | **Required** | Foreign key to `payment_orders.payment_order_id` | None | Non-unique | Valid order reference |
| `event_type` | String | **Required** | `AUTHORIZATION`, `CAPTURE`, `REFUND`, `CHARGEBACK` | Event Type Enum | Non-unique | Type of lifecycle action |
| `event_status` | String | **Required** | `PROCESSED`, `DUPLICATE_SKIPPED`, `REJECTED` | Status Enum | Non-unique | Processing outcome at gateway |
| `gross_amount` | Numeric(14,2)| **Required** | Positive (or negative for refund lines) | Currency units | Non-unique | Gross transaction monetary amount |
| `fee_amount` | Numeric(14,2)| **Required** | Non-negative (or 0.00) | Currency units | Non-unique | Interchange + processing fee deducted |
| `net_amount` | Numeric(14,2)| **Required** | Arithmetic formula | Currency units | Non-unique | **Validation**: `net_amount == round(gross_amount - fee_amount, 2)` |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Currency of the processed event |
| `processor_reference`| String| **Required** | E.g. `ch_3Mv8...` | External ID | Non-unique (unique per event) | Processor gateway charge/transaction ID |
| `idempotency_key` | String | **Required** | E.g. `IDEMP-<attempt_id>-<type>` | UUID/Hash | Non-unique (duplicate indicates replay) | Ingestion deduplication key |
| `event_timestamp` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Event generation time at processor |
| `ingested_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= `event_timestamp` |

---

## 5. SettlementBatch (`settlement_batches`)
Aggregated batch summary produced by the processor representing net settlement payouts to be transferred to the bank.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `batch_id` | String | **Required** | Regex: `^SET-2026-\d{6}$` | None | **Primary Key** | Format `SET-2026-000001` |
| `processor_id` | String | **Required** | `STRIPE`, `ADYEN`, `CHASE_PAYMENTECH` | Processor ID | Non-unique | Processing institution |
| `merchant_id` | String | **Required** | `AGGREGATE` or specific merchant ID | None | Non-unique | Merchant or pool identifier |
| `batch_date` | Date | **Required** | `YYYY-MM-DD` | Calendar Date | Non-unique | Date of batch compilation |
| `period_start` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Start of batch window |
| `period_end` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Ordering: `period_start < period_end` |
| `total_gross` | Numeric(16,2)| **Required** | Sum of child lines | Currency units | Non-unique | **Validation**: `total_gross == sum(settlement_lines.gross_amount)` |
| `total_fee` | Numeric(16,2)| **Required** | Sum of child lines | Currency units | Non-unique | **Validation**: `total_fee == sum(settlement_lines.fee_amount)` |
| `total_net` | Numeric(16,2)| **Required** | Sum of child lines | Currency units | Non-unique | **Validation**: `total_net == sum(settlement_lines.net_amount)` and `total_net == total_gross - total_fee` |
| `line_count` | Integer | **Required** | `>= 1` | Count | Non-unique | **Validation**: `line_count == count(settlement_lines)` |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Batch settlement currency |
| `status` | String | **Required** | `OPEN`, `CLOSED`, `SETTLED`, `DISCREPANCY` | Status Enum | Non-unique | Settlement state |
| `payout_reference` | String | **Required** | `po_2026_\d{8}` or `WIRE-SET-...` | Trace ID | Unique | Used to match bank statement line narrative |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= `period_end` |

---

## 6. SettlementLine (`settlement_lines`)
Individual transaction records composing a settlement batch.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `settlement_line_id`| String | **Required** | Regex: `^STL-SET-2026-\d{6}-\d{3}$` | None | **Primary Key** | E.g. `STL-SET-2026-000001-001` |
| `batch_id` | String | **Required** | Foreign key to `settlement_batches.batch_id` | None | Non-unique | Must link to existing batch |
| `processor_event_id`| String | **Required** | Foreign key to `processor_events.processor_event_id` | None | Unique in valid baseline (duplicate injected in anomalies) | Links line to underlying capture/refund event |
| `payment_order_id` | String | **Required** | Foreign key to `payment_orders.payment_order_id` | None | Non-unique | Links directly to commercial payment order |
| `line_type` | String | **Required** | `CAPTURE`, `REFUND`, `CHARGEBACK`, `ADJUSTMENT` | Type Enum | Non-unique | Reflects action |
| `gross_amount` | Numeric(14,2)| **Required** | Monetary amount | Currency units | Non-unique | Must match processor event gross amount |
| `fee_amount` | Numeric(14,2)| **Required** | Non-negative fee | Currency units | Non-unique | Must match processor event fee |
| `net_amount` | Numeric(14,2)| **Required** | `gross_amount - fee_amount` | Currency units | Non-unique | **Validation**: `net_amount == round(gross_amount - fee_amount, 2)` |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Must match batch currency |
| `settlement_date` | Date | **Required** | `YYYY-MM-DD` | Calendar Date | Non-unique | Effective value date |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= processor event timestamp |

---

## 7. BankStatementLine (`bank_statement_lines`)
Actual cash movements recorded on commercial bank account ledger (CAMT.053 / BAI2 / MT940).

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `bank_line_id` | String | **Required** | Regex: `^BANK-2026-\d{6}$` | None | **Primary Key** | Format `BANK-2026-000001` |
| `account_number` | String | **Required** | Masked IBAN or account (e.g. `US99YOTTA0001234567`) | Bank Acct | Non-unique | Target corporate settlement account |
| `booking_date` | Date | **Required** | `YYYY-MM-DD` | Calendar Date | Non-unique | Must be >= SettlementBatch `batch_date` |
| `value_date` | Date | **Required** | `YYYY-MM-DD` | Calendar Date | Non-unique | Typically `booking_date` or `booking_date + 1` |
| `amount` | Numeric(16,2)| **Required** | Positive (Credit) or Negative (Debit) | Currency units | Non-unique | Net deposited cash. Should equal settlement batch `total_net` (unless wire fee deducted) |
| `currency` | String | **Required** | `USD`, `EUR`, `GBP`, `CAD` | ISO 4217 | Non-unique | Must match account & batch currency |
| `bank_tx_type` | String | **Required** | `CREDIT`, `DEBIT` | Tx Type Enum | Non-unique | Settlement deposit is `CREDIT` |
| `narrative` | String | **Required** | Text containing batch payout reference | Free text | Non-unique | Parsed to match against `SettlementBatch.payout_reference` or `batch_id` |
| `running_balance` | Numeric(18,2)| **Required** | Account ledger balance | Currency units | Non-unique | **Validation**: `running_balance_i == running_balance_{i-1} + amount_i` |
| `created_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Feed ingestion timestamp |

---

## 8. ReconciliationMatch (`reconciliation_matches`)
Result of the multi-way deterministic matching engine binding instructions, events, settlements, and bank cash lines.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `match_id` | String | **Required** | Regex: `^REC-2026-\d{6}$` | None | **Primary Key** | Format `REC-2026-000001` |
| `reconciliation_run_id`| String | **Required** | `RUN-YYYYMMDD-HHMMSS` | Job ID | Non-unique | Batch job / pipeline run identifier |
| `match_type` | String | **Required** | `ORDER_TO_PROCESSOR`, `EVENT_TO_SETTLEMENT`, `SETTLEMENT_TO_BANK` | Match Type | Non-unique | Stage of reconciliation |
| `left_entity_type` | String | **Required** | `PaymentOrder`, `ProcessorEvent`, `SettlementBatch` | Entity Name | Non-unique | Left side entity type |
| `left_entity_id` | String | **Required** | Valid PK of left entity | Entity ID | Non-unique | Join key |
| `right_entity_type` | String | **Required** | `ProcessorEvent`, `SettlementLine`, `BankStatementLine` | Entity Name | Non-unique | Right side entity type |
| `right_entity_id` | String | **Required** | Valid PK of right entity | Entity ID | Non-unique | Join key |
| `match_status` | String | **Required** | `EXACT_MATCH`, `TOLERANCE_MATCH`, `PARTIAL_MATCH`, `SUSPECTED_MISMATCH` | Match Status | Non-unique | Matching classification outcome |
| `confidence_score` | Numeric(5,4) | **Required** | `0.0000` to `1.0000` | Score (0-1) | Non-unique | Deterministic score (1.0 = exact ref, amt, cur, date match) |
| `left_amount` | Numeric(16,2)| **Required** | Monetary amount | Currency units | Non-unique | Left comparison operand |
| `right_amount` | Numeric(16,2)| **Required** | Monetary amount | Currency units | Non-unique | Right comparison operand |
| `discrepancy_amount`| Numeric(16,2)| **Required** | `abs(left_amount - right_amount)` | Currency units | Non-unique | Arithmetic difference between matched pair |
| `match_rule` | String | **Required** | E.g. `EXACT_REF_AND_AMOUNT`, `BATCH_PAYOUT_REF_MATCH`, `WINDOWED_TOLERANCE_MATCH` | Rule ID | Non-unique | Engine rule identifier triggered |
| `matched_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Execution timestamp |

---

## 9. ExceptionRecord (`exception_records`)
Exceptions raised by the reconciliation engine for broken flows, anomalies, and integrity breaks.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `exception_id` | String | **Required** | Regex: `^EXC-2026-\d{6}$` | None | **Primary Key** | Format `EXC-2026-000001` |
| `reconciliation_run_id`| String | **Required** | `RUN-YYYYMMDD-HHMMSS` | Job ID | Non-unique | Pipeline run identifier |
| `issue_type` | String | **Required** | `DUPLICATE_SETTLEMENT_LINE`, `BANK_AMOUNT_FEE_MISMATCH`, `REFUND_BEFORE_CAPTURE`, `UNMATCHED_DROPPED_RECORD`, `CURRENCY_MISMATCH`, `DUPLICATE_WEBHOOK_INGESTED`, `UNMATCHED_PROCESSOR_EVENT`, `UNMATCHED_BANK_LINE` | Issue Enum | Non-unique | Standardized classification code |
| `severity` | String | **Required** | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | Severity Enum | Non-unique | Triage priority level |
| `status` | String | **Required** | `OPEN`, `IN_REVIEW`, `RESOLVED`, `WAIVED` | Status Enum | Non-unique | Lifecycle state |
| `entity_type` | String | **Required** | `PaymentOrder`, `ProcessorEvent`, `SettlementBatch`, `SettlementLine`, `BankStatementLine` | Entity Name | Non-unique | Primary broken entity type |
| `entity_id` | String | **Required** | ID of the broken entity | Entity ID | Non-unique | Primary foreign key |
| `related_entity_type`| String | **Optional** | Secondary entity type | Entity Name | Non-unique | Optional correlation link |
| `related_entity_id` | String | **Optional** | ID of related entity | Entity ID | Non-unique | Optional correlation link |
| `discrepancy_amount`| Numeric(16,2)| **Required** | Amount in dispute / break | Currency units | Non-unique | Variance or orphaned value |
| `detected_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Detection time |
| `details_json` | JSON / Text | **Required** | JSON dictionary with break context | Structured Data | Non-unique | Comprehensive diagnostics payload |
| `ground_truth_label`| String | **Optional** | Stored for benchmark evaluation only | Label Enum | Non-unique | Kept segregated; never leaked to matching logic |

---

## 10. Resolution (`resolutions`)
Immutable audit trail and state-transition ledger documenting automated and manual operator actions.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `resolution_id` | String | **Required** | Regex: `^RES-2026-\d{6}$` | None | **Primary Key** | Format `RES-2026-000001` |
| `exception_id` | String | **Required** | Foreign key to `exception_records.exception_id` | None | Non-unique (multiple resolutions per exception allowed for history) | Must link to existing exception |
| `actor_role` | String | **Required** | `OPERATIONS_ANALYST`, `RISK_COMPLIANCE`, `SYSTEM_ADMIN`, `CUSTOMER` | Actor Role | Non-unique | Role of decision maker |
| `actor_id` | String | **Required** | E.g. `ops_analyst_01`, `risk_officer_07`, `auto_engine` | Operator ID | Non-unique | User or automated service ID |
| `resolution_type` | String | **Required** | `AUTO_ADJUSTED`, `MANUAL_MATCH`, `WRITE_OFF`, `ESCALATE_FRAUD`, `REINGEST_EVENT`, `ACCEPT_TOLERANCE`, `REFUND_VOID` | Resolution Enum | Non-unique | Action category |
| `notes` | String | **Required** | Operator justification and resolution rationale | Free text | Non-unique | Audit requirement: non-empty rationale |
| `financial_adjustment_amount` | Numeric(16,2)| **Required** | Ledger adjustment amount | Currency units | Non-unique | Signed adjustment applied |
| `previous_state` | String | **Required** | `OPEN`, `IN_REVIEW` | Exception Status | Non-unique | Previous state before transition |
| `new_state` | String | **Required** | `RESOLVED`, `WAIVED`, `IN_REVIEW` | Exception Status | Non-unique | State after resolution action |
| `resolved_at` | Timestamp | **Required** | ISO 8601 UTC timestamp | UTC Datetime | Non-unique | Must be >= exception `detected_at` |
