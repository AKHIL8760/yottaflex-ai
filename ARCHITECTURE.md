# YottaFlex.ai Payment Reconciliation Platform — System Architecture & Design Specification

## 1. Executive Summary

The **YottaFlex Payment Reconciliation Platform** is an enterprise-grade financial engineering system designed to reconcile commercial payment instructions, asynchronous payment gateway processor events, processor settlement clearing batches, and treasury commercial bank statement lines.

The platform provides:
1. **Multi-Way Invariant Matching**: Cross-entity deterministic binding across Commercial Instructions ($Order$), Gateway Events ($ProcessorEvent$), Payout Batches ($SettlementBatch$), and Cash Movements ($BankStatementLine$).
2. **Idempotency Gateway**: Strict at-most-once webhook processing semantics to neutralize duplicate deliveries without mutating or corrupting accounting ledgers.
3. **Automated Anomaly Detection & Exception Isolation**: Detection of duplicate lines, unannounced fee breaks, temporal lifecycle inversions (refund before capture), silent upstream drops, currency mismatches, and orphan treasury deposits.
4. **Role-Based Exception Governance & Resolution Engine**: Workspaces for Operations Analysts, Risk & Compliance Officers, and System Administrators, backed by an append-only immutable audit ledger.
5. **Segregated Ground Truth & Benchmarking**: Pure zero-leakage evaluation measuring Precision, Recall, F1-Score, and Financial Discrepancy Reconciliation.

---

## 2. Actors & System Boundaries

```mermaid
flowchart TD
    subgraph Primary Actors
        CUST["Customer / Account Holder\n(Initiates Orders & Refunds)"]
        OPS["Operations Analyst\n(Discrepancy Triage & Adjustments)"]
        RISK["Risk & Compliance Reviewer\n(Temporal Violations & Fraud Escalation)"]
        ADMIN["System Administrator\n(Rule Governance & Pipeline Operations)"]
    end

    subgraph Ingestion & Gateway
        WEBHOOK["Webhook Ingestion Gateway\n(Idempotency Key Verification)"]
        CACHE["Idempotency Cache\n(Deduplication Store)"]
    end

    subgraph Multi-Way Reconciliation Engine
        P1["Phase 1: Orders <-> Processor Events\n(Capture Verification & Timing Checks)"]
        P2["Phase 2: Processor Events <-> Settlement Lines\n(Gross, Fee, Net & Duplicate Scan)"]
        P3["Phase 3: Settlement Batches <-> Bank Statements\n(Payout Matching & Wire Fee Isolation)"]
    end

    subgraph State Management & Ledgers
        REC_DB[("Core Database\n(SQLite / PostgreSQL)")]
        EXC_STORE[("Exception Store\n(State Transitions)")]
        AUDIT_LOG[("Immutable Audit Trail\n(Resolution Log)")]
    end

    CUST -->|Submits Payment / Refund| WEBHOOK
    WEBHOOK <-->|Check Replay Attack| CACHE
    WEBHOOK -->|Clean Stream| P1
    P1 --> P2
    P2 --> P3
    P3 --> REC_DB

    P1 & P2 & P3 -->|Flag Discrepancies| EXC_STORE
    OPS -->|Manual Match & Write-Off| EXC_STORE
    RISK -->|Freeze / Escalate Fraud| EXC_STORE
    ADMIN -->|Rule Config & Auto-Policy| EXC_STORE
    EXC_STORE -->|Immutable History| AUDIT_LOG
```

---

## 3. Entity-Relationship Model & Cardinality

The system models 10 core entities with strict referential integrity, standardized zero-padded ID nomenclatures, and validated primary/foreign key joins.

```mermaid
erDiagram
    MERCHANT ||--o{ PAYMENT_ORDER : "issues (1:N)"
    PAYMENT_ORDER ||--o{ PAYMENT_ATTEMPT : "attempts (1:N)"
    PAYMENT_ORDER ||--o| PAYMENT_ORDER : "refund_parent (0:1)"
    PAYMENT_ATTEMPT ||--o{ PROCESSOR_EVENT : "emits (1:N)"
    PROCESSOR_EVENT ||--o{ SETTLEMENT_LINE : "settles (1:N)"
    SETTLEMENT_BATCH ||--|{ SETTLEMENT_LINE : "contains (1:N)"
    SETTLEMENT_BATCH ||--o| BANK_STATEMENT_LINE : "transfers (1:1)"
    RECONCILIATION_MATCH }o--|| PAYMENT_ORDER : "binds"
    RECONCILIATION_MATCH }o--|| PROCESSOR_EVENT : "binds"
    RECONCILIATION_MATCH }o--|| SETTLEMENT_BATCH : "binds"
    RECONCILIATION_MATCH }o--|| BANK_STATEMENT_LINE : "binds"
    EXCEPTION_RECORD ||--o{ RESOLUTION : "transitions (1:N)"

    MERCHANT {
        string merchant_id PK "MRC-2026-XXXXX"
        string name
        string mcc "ISO 18245"
        string currency "ISO 4217"
        numeric fee_rate_bps "Basis Points"
        numeric fixed_fee "Fixed Tx Fee"
        string status "ACTIVE/SUSPENDED"
    }

    PAYMENT_ORDER {
        string payment_order_id PK "PAY-2026-XXXXXXXX"
        string merchant_id FK
        string customer_id
        numeric amount "2 decimal precision"
        string currency
        string order_type "PAYMENT/REFUND"
        string parent_order_id FK
        string status "CAPTURED/FAILED/REFUNDED"
    }

    PAYMENT_ATTEMPT {
        string payment_attempt_id PK "ATT-PAY-2026-XXXXXXXX-XX"
        string payment_order_id FK
        string processor_id "STRIPE/ADYEN"
        int attempt_number "Sequential"
        string status "SUCCESS/FAILED"
        string error_code
    }

    PROCESSOR_EVENT {
        string processor_event_id PK "PRC-2026-XXXXXXXX"
        string payment_attempt_id FK
        string payment_order_id FK
        string event_type "AUTHORIZATION/CAPTURE/REFUND"
        numeric gross_amount
        numeric fee_amount
        numeric net_amount "gross - fee"
        string currency
        string idempotency_key
    }

    SETTLEMENT_BATCH {
        string batch_id PK "SET-2026-XXXXXX"
        string processor_id
        date batch_date
        numeric total_gross
        numeric total_fee
        numeric total_net
        int line_count
        string payout_reference "po_2026_XXXXXX"
    }

    SETTLEMENT_LINE {
        string settlement_line_id PK "STL-SET-2026-XXXXXX-XXX"
        string batch_id FK
        string processor_event_id FK
        string payment_order_id FK
        numeric gross_amount
        numeric fee_amount
        numeric net_amount
    }

    BANK_STATEMENT_LINE {
        string bank_line_id PK "BANK-2026-XXXXXX"
        string account_number
        date booking_date
        numeric amount "Net deposit/debit"
        string narrative "References payout_ref"
        numeric running_balance
    }

    RECONCILIATION_MATCH {
        string match_id PK "REC-2026-XXXXXX"
        string match_type "ORDER_TO_PROC/EVENT_TO_SETTLE/SETTLE_TO_BANK"
        string left_entity_id
        string right_entity_id
        string match_status "EXACT_MATCH/TOLERANCE_MATCH"
        numeric confidence_score
        numeric discrepancy_amount
    }

    EXCEPTION_RECORD {
        string exception_id PK "EXC-2026-XXXXXX"
        string issue_type "DUPLICATE_LINE/FEE_BREAK/etc"
        string severity "CRITICAL/HIGH/MEDIUM/LOW"
        string status "OPEN/IN_REVIEW/RESOLVED"
        string entity_id
        numeric discrepancy_amount
    }

    RESOLUTION {
        string resolution_id PK "RES-2026-XXXXXX"
        string exception_id FK
        string actor_role "OPS/RISK/ADMIN"
        string actor_id
        string resolution_type "AUTO_ADJUSTED/MANUAL_MATCH/etc"
        numeric financial_adjustment_amount
        string previous_state
        string new_state
    }
```

---

## 4. Multi-Way Reconciliation Pipeline Workflow

The reconciliation pipeline operates in three sequential deterministic phases:

```mermaid
sequenceDiagram
    autonumber
    participant Order as Commercial Orders
    participant Gate as Webhook Gateway
    participant Event as Processor Events
    participant Settle as Settlement Batches
    participant Bank as Bank Statements
    participant Engine as Reconciliation Engine
    participant Exc as Exception Store
    participant Audit as Immutable Audit

    Note over Order,Gate: Stage 1: Ingestion & Idempotency
    Gate->>Gate: Verify Idempotency Key & Event Hash
    alt Replay / Duplicate Webhook
        Gate->>Exc: Create EXC_DUPLICATE_WEBHOOK
    else Valid Webhook
        Gate->>Event: Ingest Clean Event
    end

    Note over Order,Event: Stage 2: Phase 1 Reconcile (Order <-> Event)
    Engine->>Order: Fetch Captured/Refunded Instructions
    Engine->>Event: Match by Order ID & Amount
    alt Dropped Upstream
        Engine->>Exc: Create EXC_UNMATCHED_DROPPED
    else Refund Before Capture
        Engine->>Exc: Create EXC_REFUND_BEFORE_CAPTURE
    else Currency Code Mismatch
        Engine->>Exc: Create EXC_CURRENCY_MISMATCH
    else Match Verified
        Engine->>Engine: Record Match (ORDER_TO_PROCESSOR)
    end

    Note over Event,Settle: Stage 3: Phase 2 Reconcile (Event <-> Settlement)
    Engine->>Settle: Match Settlement Lines to Events
    alt Duplicate Line Detected
        Engine->>Exc: Create EXC_DUPLICATE_SETTLEMENT_LINE
    else Exact Match
        Engine->>Engine: Record Match (EVENT_TO_SETTLEMENT)
    end

    Note over Settle,Bank: Stage 4: Phase 3 Reconcile (Settlement <-> Bank)
    Engine->>Bank: Match Payout Reference in Bank Narrative
    alt Discrepancy == Wire Fee ($10-$35)
        Engine->>Exc: Create EXC_BANK_AMOUNT_FEE_MISMATCH
    else Unmatched Incoming Deposit
        Engine->>Exc: Create EXC_UNMATCHED_BANK_LINE
    else Net Amount Matches
        Engine->>Engine: Record Match (SETTLEMENT_TO_BANK)
    end

    Note over Exc,Audit: Stage 5: Resolution & Traceability
    Exc->>Engine: Apply Policy Auto-Resolutions
    Engine->>Audit: Append Resolution Event (No History Overwrite)
```

---

## 5. Architectural Invariants & Guarantees

1. **Idempotent Ingestion**: Raw webhook deliveries cannot cause double accounting. Duplicate payloads with identical idempotency keys or transaction references are immediately filtered into an exception quarantine.
2. **Arithmetic Conservation**:
   $$\text{Line Net} = \text{Line Gross} - \text{Line Fee}$$
   $$\text{Batch Net} = \sum \text{Line Net}$$
   $$\text{Bank Running Balance}_i = \text{Bank Running Balance}_{i-1} + \text{Deposit Amount}_i$$
3. **Temporal Lifecycle Validity**:
   $$\text{Order Created} \le \text{Attempt Created} \le \text{Event Timestamp} \le \text{Settlement Date} \le \text{Bank Booking Date}$$
   For refunds, the parent payment capture must strictly precede the refund issuance. Inversions are flagged as Critical/High priority compliance anomalies.
4. **Segregated Ground Truth**:
   The engine evaluates raw transactional data purely through domain rules. Ground-truth labels are stored in isolated catalogs (`ground_truth.csv` and `ground_truth.json`) and are never exposed to the matcher.
5. **Immutable History**:
   State transitions are recorded as append-only `Resolution` events linked to `ExceptionRecord`. Historical state is preserved for SOC 1/2 and SOX compliance.
