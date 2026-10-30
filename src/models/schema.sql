-- ============================================================================
-- YottaFlex.ai Payment Reconciliation & Settlement Data Platform Schema
-- Target: SQLite & ANSI SQL / PostgreSQL compatible
-- ============================================================================

-- 1. Merchants Table
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    mcc VARCHAR(4) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    fee_rate_bps NUMERIC(8, 2) NOT NULL,
    fixed_fee NUMERIC(8, 2) NOT NULL DEFAULT 0.30,
    payout_schedule VARCHAR(16) NOT NULL DEFAULT 'DAILY',
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL
);

-- 2. Payment Orders Table
CREATE TABLE IF NOT EXISTS payment_orders (
    payment_order_id VARCHAR(32) PRIMARY KEY,
    merchant_id VARCHAR(32) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    order_type VARCHAR(16) NOT NULL DEFAULT 'PAYMENT',
    parent_order_id VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    payment_method VARCHAR(32) NOT NULL DEFAULT 'CARD',
    channel VARCHAR(16) NOT NULL DEFAULT 'WEB',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id),
    FOREIGN KEY (parent_order_id) REFERENCES payment_orders(payment_order_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_orders_merchant ON payment_orders(merchant_id);
CREATE INDEX IF NOT EXISTS idx_payment_orders_created ON payment_orders(created_at);

-- 3. Payment Attempts Table
CREATE TABLE IF NOT EXISTS payment_attempts (
    payment_attempt_id VARCHAR(64) PRIMARY KEY,
    payment_order_id VARCHAR(32) NOT NULL,
    processor_id VARCHAR(32) NOT NULL DEFAULT 'STRIPE',
    attempt_number INTEGER NOT NULL DEFAULT 1,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
    error_code VARCHAR(32),
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    FOREIGN KEY (payment_order_id) REFERENCES payment_orders(payment_order_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_attempts_order ON payment_attempts(payment_order_id);

-- 4. Processor Events Table
CREATE TABLE IF NOT EXISTS processor_events (
    processor_event_id VARCHAR(32) PRIMARY KEY,
    payment_attempt_id VARCHAR(64) NOT NULL,
    payment_order_id VARCHAR(32) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_status VARCHAR(32) NOT NULL DEFAULT 'PROCESSED',
    gross_amount NUMERIC(14, 2) NOT NULL,
    fee_amount NUMERIC(14, 2) NOT NULL,
    net_amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    processor_reference VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    ingested_at TIMESTAMP NOT NULL,
    FOREIGN KEY (payment_attempt_id) REFERENCES payment_attempts(payment_attempt_id),
    FOREIGN KEY (payment_order_id) REFERENCES payment_orders(payment_order_id)
);
CREATE INDEX IF NOT EXISTS idx_processor_events_order ON processor_events(payment_order_id);
CREATE INDEX IF NOT EXISTS idx_processor_events_idemp ON processor_events(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_processor_events_ref ON processor_events(processor_reference);

-- 5. Settlement Batches Table
CREATE TABLE IF NOT EXISTS settlement_batches (
    batch_id VARCHAR(32) PRIMARY KEY,
    processor_id VARCHAR(32) NOT NULL,
    merchant_id VARCHAR(32) NOT NULL,
    batch_date DATE NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    total_gross NUMERIC(16, 2) NOT NULL,
    total_fee NUMERIC(16, 2) NOT NULL,
    total_net NUMERIC(16, 2) NOT NULL,
    line_count INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(16) NOT NULL DEFAULT 'CLOSED',
    payout_reference VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_settlement_batches_payout ON settlement_batches(payout_reference);

-- 6. Settlement Lines Table
CREATE TABLE IF NOT EXISTS settlement_lines (
    settlement_line_id VARCHAR(64) PRIMARY KEY,
    batch_id VARCHAR(32) NOT NULL,
    processor_event_id VARCHAR(32) NOT NULL,
    payment_order_id VARCHAR(32) NOT NULL,
    line_type VARCHAR(16) NOT NULL DEFAULT 'CAPTURE',
    gross_amount NUMERIC(14, 2) NOT NULL,
    fee_amount NUMERIC(14, 2) NOT NULL,
    net_amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    settlement_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (batch_id) REFERENCES settlement_batches(batch_id),
    FOREIGN KEY (processor_event_id) REFERENCES processor_events(processor_event_id),
    FOREIGN KEY (payment_order_id) REFERENCES payment_orders(payment_order_id)
);
CREATE INDEX IF NOT EXISTS idx_settlement_lines_batch ON settlement_lines(batch_id);
CREATE INDEX IF NOT EXISTS idx_settlement_lines_event ON settlement_lines(processor_event_id);
CREATE INDEX IF NOT EXISTS idx_settlement_lines_order ON settlement_lines(payment_order_id);

-- 7. Bank Statement Lines Table
CREATE TABLE IF NOT EXISTS bank_statement_lines (
    bank_line_id VARCHAR(32) PRIMARY KEY,
    account_number VARCHAR(32) NOT NULL,
    booking_date DATE NOT NULL,
    value_date DATE NOT NULL,
    amount NUMERIC(16, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    bank_tx_type VARCHAR(16) NOT NULL DEFAULT 'CREDIT',
    narrative VARCHAR(255) NOT NULL,
    running_balance NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bank_statement_booking ON bank_statement_lines(booking_date);

-- 8. Reconciliation Matches Table
CREATE TABLE IF NOT EXISTS reconciliation_matches (
    match_id VARCHAR(32) PRIMARY KEY,
    reconciliation_run_id VARCHAR(64) NOT NULL,
    match_type VARCHAR(32) NOT NULL,
    left_entity_type VARCHAR(32) NOT NULL,
    left_entity_id VARCHAR(64) NOT NULL,
    right_entity_type VARCHAR(32) NOT NULL,
    right_entity_id VARCHAR(64) NOT NULL,
    match_status VARCHAR(32) NOT NULL DEFAULT 'EXACT_MATCH',
    confidence_score NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    left_amount NUMERIC(16, 2) NOT NULL,
    right_amount NUMERIC(16, 2) NOT NULL,
    discrepancy_amount NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    match_rule VARCHAR(64) NOT NULL,
    matched_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recon_matches_run ON reconciliation_matches(reconciliation_run_id);
CREATE INDEX IF NOT EXISTS idx_recon_matches_left ON reconciliation_matches(left_entity_id);
CREATE INDEX IF NOT EXISTS idx_recon_matches_right ON reconciliation_matches(right_entity_id);

-- 9. Exception Records Table
CREATE TABLE IF NOT EXISTS exception_records (
    exception_id VARCHAR(32) PRIMARY KEY,
    reconciliation_run_id VARCHAR(64) NOT NULL,
    issue_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    entity_type VARCHAR(32) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    related_entity_type VARCHAR(32),
    related_entity_id VARCHAR(64),
    discrepancy_amount NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    detected_at TIMESTAMP NOT NULL,
    details_json TEXT NOT NULL,
    ground_truth_label VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_exception_records_run ON exception_records(reconciliation_run_id);
CREATE INDEX IF NOT EXISTS idx_exception_records_status ON exception_records(status);
CREATE INDEX IF NOT EXISTS idx_exception_records_issue ON exception_records(issue_type);

-- 10. Resolutions Table (Immutable Audit Log)
CREATE TABLE IF NOT EXISTS resolutions (
    resolution_id VARCHAR(32) PRIMARY KEY,
    exception_id VARCHAR(32) NOT NULL,
    actor_role VARCHAR(32) NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    resolution_type VARCHAR(32) NOT NULL,
    notes TEXT NOT NULL,
    financial_adjustment_amount NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    previous_state VARCHAR(16) NOT NULL,
    new_state VARCHAR(16) NOT NULL,
    resolved_at TIMESTAMP NOT NULL,
    FOREIGN KEY (exception_id) REFERENCES exception_records(exception_id)
);
CREATE INDEX IF NOT EXISTS idx_resolutions_exception ON resolutions(exception_id);
