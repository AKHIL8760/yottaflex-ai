"""
Deterministic synthetic data generator for payment reconciliation.
Generates master, transactional, event, settlement, and bank statement data.
Supports configurable scale ('starter' and 'full') with deterministic seeding.
"""
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import numpy as np

from src.models.entities import (
    Merchant,
    PaymentOrder,
    PaymentAttempt,
    ProcessorEvent,
    SettlementBatch,
    SettlementLine,
    BankStatementLine,
    GroundTruthAnomaly,
)
from src.generator.anomalies import inject_anomalies


class SyntheticDataGenerator:
    """
    High-performance deterministic data generator for multi-way payment reconciliation.
    Adheres strictly to zero-padded ID conventions and domain lifecycle constraints.
    """

    def __init__(self, seed: int = 20261022, scale: str = "full"):
        self.seed = seed
        self.scale = scale.lower()
        self.rng = np.random.default_rng(seed)

        if self.scale == "starter":
            self.num_merchants = 100
            self.num_orders = 2500
            self.target_attempts = 2750
            self.num_batches = 50
            self.num_bank_lines = 250
            self.scale_factor = 0.05
        else:  # 'full'
            self.num_merchants = 2000
            self.num_orders = 50000
            self.target_attempts = 55000
            self.num_batches = 1000
            self.num_bank_lines = 5000
            self.scale_factor = 1.0

        # Base date anchor: 2026-10-01T00:00:00Z
        self.base_date = datetime(2026, 10, 1, 0, 0, 0)

        # Standard Merchant Category Codes (MCC) and fee structures
        self.mcc_list = ["5411", "5732", "5812", "5999", "7372", "4722", "5311"]
        self.currencies = ["USD", "EUR", "GBP", "CAD"]
        self.currency_weights = [0.80, 0.10, 0.06, 0.04]
        self.processors = ["STRIPE", "ADYEN", "CHASE_PAYMENTECH"]
        self.processor_weights = [0.60, 0.25, 0.15]

    def generate_all(self) -> Dict[str, Any]:
        """
        Executes end-to-end deterministic data generation workflow.
        Returns dictionary containing all 10 entity datasets, raw webhook stream, and ground truth.
        """
        merchants = self._generate_merchants()
        orders, attempts, events = self._generate_orders_attempts_events(merchants)
        batches, lines = self._generate_settlements(events)
        bank_lines = self._generate_bank_statements(batches)

        # Step 5: Inject labeled anomalies & edge cases
        (
            mod_orders,
            mod_attempts,
            mod_events,
            mod_batches,
            mod_lines,
            mod_bank_lines,
            ground_truth,
            raw_webhook_stream,
        ) = inject_anomalies(
            self.rng,
            merchants,
            orders,
            attempts,
            events,
            batches,
            lines,
            bank_lines,
            scale_factor=self.scale_factor,
        )

        return {
            "merchants": merchants,
            "payment_orders": mod_orders,
            "payment_attempts": mod_attempts,
            "processor_events": mod_events,
            "settlement_batches": mod_batches,
            "settlement_lines": mod_lines,
            "bank_statement_lines": mod_bank_lines,
            "ground_truth": ground_truth,
            "raw_webhook_stream": raw_webhook_stream,
            "metadata": {
                "seed": self.seed,
                "scale": self.scale,
                "generated_at": (self.base_date + timedelta(days=21)).isoformat() + "Z",
                "counts": {
                    "merchants": len(merchants),
                    "payment_orders": len(mod_orders),
                    "payment_attempts": len(mod_attempts),
                    "processor_events": len(mod_events),
                    "settlement_batches": len(mod_batches),
                    "settlement_lines": len(mod_lines),
                    "bank_statement_lines": len(mod_bank_lines),
                    "ground_truth_anomalies": len(ground_truth),
                    "raw_webhooks": len(raw_webhook_stream),
                },
            },
        }

    def _generate_merchants(self) -> List[Merchant]:
        merchants: List[Merchant] = []
        for i in range(1, self.num_merchants + 1):
            merchant_id = f"MRC-2026-{i:05d}"
            name = f"Merchant Enterprise {i}"
            mcc = str(self.rng.choice(self.mcc_list))
            currency = str(self.rng.choice(self.currencies, p=self.currency_weights))
            # Basis points: between 120 (1.2%) and 290 (2.9%)
            fee_bps = float(self.rng.integers(120, 290))
            fixed_fee = float(self.rng.choice([0.15, 0.20, 0.30, 0.35]))
            created_at = (self.base_date - timedelta(days=int(self.rng.integers(30, 180)))).isoformat() + "Z"

            merchants.append(
                Merchant.model_construct(
                    merchant_id=merchant_id,
                    name=name,
                    mcc=mcc,
                    currency=currency,
                    fee_rate_bps=fee_bps,
                    fixed_fee=fixed_fee,
                    payout_schedule="DAILY",
                    status="ACTIVE",
                    created_at=created_at,
                )
            )
        return merchants

    def _generate_orders_attempts_events(
        self, merchants: List[Merchant]
    ) -> Tuple[List[PaymentOrder], List[PaymentAttempt], List[ProcessorEvent]]:
        merchant_map = {m.merchant_id: m for m in merchants}
        merchant_ids = list(merchant_map.keys())

        orders: List[PaymentOrder] = []
        attempts: List[PaymentAttempt] = []
        events: List[ProcessorEvent] = []

        event_counter = 0

        # We allocate orders across 20 calendar days in October 2026
        # Target attempts is ~1.1x orders (55k attempts for 50k orders)
        order_amounts = np.round(self.rng.lognormal(mean=3.9, sigma=0.8, size=self.num_orders) + 1.0, 2)
        order_amounts = np.clip(order_amounts, 2.0, 10000.0)

        time_offsets_seconds = self.rng.integers(0, 20 * 86400, size=self.num_orders)
        time_offsets_seconds.sort()

        captured_orders_pool: List[Tuple[PaymentOrder, Merchant]] = []

        for i in range(self.num_orders):
            order_num = i + 1
            order_id = f"PAY-2026-{order_num:08d}"
            m_id = str(self.rng.choice(merchant_ids))
            merchant = merchant_map[m_id]
            cust_id = f"CUST-2026-{self.rng.integers(1, 100000):08d}"
            amount = float(order_amounts[i])
            currency = merchant.currency

            order_time = self.base_date + timedelta(seconds=int(time_offsets_seconds[i]))
            order_time_str = order_time.isoformat() + "Z"

            is_refund = False
            parent_id = None
            if len(captured_orders_pool) > 50 and self.rng.random() < 0.03:
                is_refund = True
                parent_order, parent_m = captured_orders_pool[int(self.rng.integers(0, len(captured_orders_pool)))]
                parent_id = parent_order.payment_order_id
                m_id = parent_m.merchant_id
                merchant = parent_m
                currency = parent_order.currency
                if self.rng.random() < 0.4:
                    amount = parent_order.amount
                else:
                    amount = round(parent_order.amount * float(self.rng.uniform(0.2, 0.8)), 2)

            roll = self.rng.random()
            if roll < 0.88 or is_refund:
                order_status = "CAPTURED" if not is_refund else "REFUNDED"
                attempt_scenarios = [("SUCCESS", None)]
            elif roll < 0.96:
                order_status = "CAPTURED"
                attempt_scenarios = [("FAILED", "INSUFFICIENT_FUNDS"), ("SUCCESS", None)]
            else:
                order_status = "FAILED"
                attempt_scenarios = [("FAILED", "CARD_DECLINED"), ("FAILED", "DO_NOT_HONOR")]

            order_obj = PaymentOrder.model_construct(
                payment_order_id=order_id,
                merchant_id=m_id,
                customer_id=cust_id,
                amount=amount,
                currency=currency,
                order_type="REFUND" if is_refund else "PAYMENT",
                parent_order_id=parent_id,
                status=order_status,
                payment_method=str(self.rng.choice(["CARD", "DIGITAL_WALLET", "ACH"], p=[0.75, 0.20, 0.05])),
                channel="WEB",
                created_at=order_time_str,
                updated_at=order_time_str,
            )
            orders.append(order_obj)

            if order_status == "CAPTURED" and not is_refund:
                captured_orders_pool.append((order_obj, merchant))

            curr_attempt_time = order_time
            proc_id = str(self.rng.choice(self.processors, p=self.processor_weights))

            for att_idx, (att_status, err_code) in enumerate(attempt_scenarios, start=1):
                attempt_id = f"ATT-{order_id}-{att_idx:02d}"
                att_time_str = curr_attempt_time.isoformat() + "Z"
                comp_time = curr_attempt_time + timedelta(seconds=int(self.rng.integers(1, 4)))
                comp_time_str = comp_time.isoformat() + "Z"

                attempt_obj = PaymentAttempt.model_construct(
                    payment_attempt_id=attempt_id,
                    payment_order_id=order_id,
                    processor_id=proc_id,
                    attempt_number=att_idx,
                    amount=amount,
                    currency=currency,
                    status=att_status,
                    error_code=err_code,
                    created_at=att_time_str,
                    completed_at=comp_time_str,
                )
                attempts.append(attempt_obj)

                if att_status == "SUCCESS":
                    event_counter += 1
                    event_id = f"PRC-2026-{event_counter:08d}"
                    event_type = "REFUND" if is_refund else "CAPTURE"

                    fee = round(merchant.fixed_fee + (amount * merchant.fee_rate_bps / 10000.0), 2)
                    if is_refund:
                        fee = round(merchant.fixed_fee, 2)
                        net_amount = round(amount - fee, 2)
                    else:
                        net_amount = round(amount - fee, 2)

                    event_obj = ProcessorEvent.model_construct(
                        processor_event_id=event_id,
                        payment_attempt_id=attempt_id,
                        payment_order_id=order_id,
                        event_type=event_type,
                        event_status="PROCESSED",
                        gross_amount=amount,
                        fee_amount=fee,
                        net_amount=net_amount,
                        currency=currency,
                        processor_reference=f"ch_2026_{self.rng.integers(10000000, 99999999)}",
                        idempotency_key=f"IDEMP-{attempt_id}-{event_type}",
                        event_timestamp=comp_time_str,
                        ingested_at=(comp_time + timedelta(seconds=int(self.rng.integers(1, 10)))).isoformat() + "Z",
                    )
                    events.append(event_obj)

                curr_attempt_time = comp_time + timedelta(minutes=int(self.rng.integers(1, 5)))

        return orders, attempts, events

    def _generate_settlements(
        self, events: List[ProcessorEvent]
    ) -> Tuple[List[SettlementBatch], List[SettlementLine]]:
        batches: List[SettlementBatch] = []
        lines: List[SettlementLine] = []

        if not events:
            return batches, lines

        events_per_batch = max(1, len(events) // self.num_batches)
        batch_counter = 0
        current_idx = 0

        while current_idx < len(events) and batch_counter < self.num_batches:
            batch_counter += 1
            batch_id = f"SET-2026-{batch_counter:06d}"
            chunk = events[current_idx : current_idx + events_per_batch]
            current_idx += events_per_batch

            if not chunk:
                break

            currency = chunk[0].currency
            chunk_time = datetime.fromisoformat(chunk[0].event_timestamp.rstrip("Z"))
            settle_date = (chunk_time + timedelta(days=int(self.rng.choice([1, 2])))).date().isoformat()
            period_start = chunk[0].event_timestamp
            period_end = chunk[-1].event_timestamp

            batch_gross = 0.0
            batch_fee = 0.0
            batch_net = 0.0

            line_idx = 0
            for ev in chunk:
                line_idx += 1
                line_id = f"STL-{batch_id}-{line_idx:03d}"
                line_type = ev.event_type

                if line_type == "REFUND":
                    eff_gross = -ev.gross_amount
                    eff_fee = ev.fee_amount
                    eff_net = eff_gross - eff_fee
                else:
                    eff_gross = ev.gross_amount
                    eff_fee = ev.fee_amount
                    eff_net = ev.net_amount

                batch_gross = round(batch_gross + eff_gross, 2)
                batch_fee = round(batch_fee + eff_fee, 2)
                batch_net = round(batch_net + eff_net, 2)

                s_line = SettlementLine.model_construct(
                    settlement_line_id=line_id,
                    batch_id=batch_id,
                    processor_event_id=ev.processor_event_id,
                    payment_order_id=ev.payment_order_id,
                    line_type=line_type,
                    gross_amount=ev.gross_amount,
                    fee_amount=ev.fee_amount,
                    net_amount=ev.net_amount,
                    currency=ev.currency,
                    settlement_date=settle_date,
                    created_at=(chunk_time + timedelta(hours=2)).isoformat() + "Z",
                )
                lines.append(s_line)

            payout_ref = f"po_2026_{batch_counter:06d}"
            s_batch = SettlementBatch.model_construct(
                batch_id=batch_id,
                processor_id="STRIPE",
                merchant_id="AGGREGATE",
                batch_date=settle_date,
                period_start=period_start,
                period_end=period_end,
                total_gross=batch_gross,
                total_fee=batch_fee,
                total_net=batch_net,
                line_count=len(chunk),
                currency=currency,
                status="CLOSED",
                payout_reference=payout_ref,
                created_at=(chunk_time + timedelta(hours=3)).isoformat() + "Z",
            )
            batches.append(s_batch)

        return batches, lines

    def _generate_bank_statements(self, batches: List[SettlementBatch]) -> List[BankStatementLine]:
        """
        Generates bank statement lines matching settlement batches PLUS operational banking activities
        (e.g., merchant payouts, reserve adjustments, interest credits) to reach the target 5,000 lines.
        """
        bank_lines: List[BankStatementLine] = []
        running_bal = 10000000.00  # $10M starting treasury account balance
        bank_line_counter = 0

        # 1. Generate bank deposit lines corresponding to each settlement batch
        for batch in batches:
            bank_line_counter += 1
            b_id = f"BANK-2026-{bank_line_counter:06d}"
            b_date = batch.batch_date
            deposit_amt = batch.total_net
            running_bal = round(running_bal + deposit_amt, 2)

            b_line = BankStatementLine.model_construct(
                bank_line_id=b_id,
                account_number="US99YOTTA0001234567",
                booking_date=b_date,
                value_date=b_date,
                amount=deposit_amt,
                currency=batch.currency,
                bank_tx_type="CREDIT",
                narrative=f"STRIPE SETTLEMENT PAYOUT REF: {batch.payout_reference} / BATCH: {batch.batch_id}",
                running_balance=running_bal,
                created_at=f"{b_date}T08:00:00Z",
            )
            bank_lines.append(b_line)

        # 2. Generate operational bank lines (merchant daily payouts, reserve debits, treasury wires)
        remaining_bank_lines = max(0, self.num_bank_lines - len(bank_lines))
        for j in range(remaining_bank_lines):
            bank_line_counter += 1
            b_id = f"BANK-2026-{bank_line_counter:06d}"
            day_offset = int(self.rng.integers(1, 25))
            op_date = (self.base_date + timedelta(days=day_offset)).date().isoformat()
            
            # Merchant payout debit or treasury transfer
            is_debit = self.rng.random() < 0.85
            op_amt = round(float(self.rng.uniform(500.0, 15000.0)), 2)
            if is_debit:
                tx_type = "DEBIT"
                amount = -op_amt
                narrative = f"ACH OUTBOUND MERCHANT DISBURSEMENT TRACE-{self.rng.integers(100000, 999999)}"
            else:
                tx_type = "CREDIT"
                amount = op_amt
                narrative = f"TREASURY SWEEP / INTEREST CREDIT TRACE-{self.rng.integers(100000, 999999)}"

            running_bal = round(running_bal + amount, 2)
            op_line = BankStatementLine.model_construct(
                bank_line_id=b_id,
                account_number="US99YOTTA0001234567",
                booking_date=op_date,
                value_date=op_date,
                amount=amount,
                currency="USD",
                bank_tx_type=tx_type,
                narrative=narrative,
                running_balance=running_bal,
                created_at=f"{op_date}T16:00:00Z",
            )
            bank_lines.append(op_line)

        return bank_lines
