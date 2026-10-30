# YottaFlex.ai — Multi-Way Payment Reconciliation & Exception Resolution Platform
### Associate AI Forward Deployed Engineer Code Challenge (Round 2)

[![CI Tests](https://img.shields.io/badge/pytest-10%20passed-emerald)](https://github.com/yottaflex/recon)
[![Reproducibility](https://img.shields.io/badge/SHA--256-100%25%20Bit--Exact-blue)](scripts/verify_reproducibility.py)
[![Ground Truth Recall](https://img.shields.io/badge/Recall-100%25-green)](EVALUATION_REPORT.md)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14-indigo)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Proprietary%20%2F%20Assessment-slate)](LICENSE)

---

## 1. Problem Statement & Business Context

In high-volume payment ecosystems, discrepancies inevitably emerge across disparate ledgers: internal order management systems, payment processor gateways (e.g. Stripe, Adyen), settlement clearing batches, and treasury commercial bank statements.

This repository provides an enterprise-grade, end-to-end multi-way payment reconciliation platform that:
1. Reconciles **Payment Orders**, **Processor Events**, **Settlement Batches**, and **Bank Statement Lines**.
2. Neutralizes duplicate webhook replay attacks through an **Idempotency Gateway**.
3. Isolates financial breaks across **6 mandatory edge case scenarios**.
4. Delivers role-based workspaces for **Operations Analysts**, **Risk & Compliance Reviewers**, and **System Administrators**.
5. Maintains SOC-1/SOX compliant **immutable state transition audit logs** without destructive history overwrites.
6. Evaluates reconciliation accuracy against a **segregated, zero-leakage ground-truth catalog** demonstrating **100.00% anomaly recall**.

---

## 2. System Architecture & Actors

```
                                      [ Customers / Channels ]
                                                 │
                                                 ▼
[ Merchant Master ] ───► [ Payment Orders ] ───► [ Payment Attempts ]
                                                         │
                                                         ▼
                                             [ Webhook Gateway ]
                                         (Idempotency & Deduplication)
                                                         │
                                                         ▼
                                              [ Processor Events ]
                                                         │
                                                         ▼
                                            [ Settlement Batches & Lines ]
                                                         │
                                                         ▼
                                             [ Bank Statement Lines ]
                                                         │
                                                         ▼
                                    ┌────────────────────────────────────────┐
                                    │    Multi-Way Reconciliation Engine     │
                                    │  - Phase 1: Orders <-> Events          │
                                    │  - Phase 2: Events <-> Settlements     │
                                    │  - Phase 3: Batches <-> Bank Lines     │
                                    └────────────────────────────────────────┘
                                                         │
                                                         ▼
                                              [ Exception Store ]
                                                         │
                              ┌──────────────────────────┼──────────────────────────┐
                              ▼                          ▼                          ▼
                     [ Operations Analyst ]    [ Risk Reviewer ]           [ Auto Policy ]
                     - Manual Re-Match         - Temporal Ordering Check   - Wire Fee Deductions
                     - Write-off Breaks        - Fraud Escalation Freeze   - FX Rounding Tolerance
                              │                          │                          │
                              └──────────────────────────┼──────────────────────────┘
                                                         │
                                                         ▼
                                         [ Immutable Resolution Audit ]
                                           (State Transition History)
```

### Primary Actors & Operational Roles
* **Customer / Account Holder**: Issues commercial payment instructions and initiates returns/refunds.
* **Operations Analyst**: Triages broken ledger joins, reconciles orphaned bank deposits, and executes authorized financial adjustments.
* **Risk & Compliance Reviewer**: Audits temporal sequence violations (`REFUND_BEFORE_CAPTURE`), traps currency collisions, and freezes suspicious flows.
* **System Administrator**: Configures matching rules, manages tolerances, triggers batch runs, and oversees pipeline health.

---

## 3. Core Entities & Nomenclature Standards

All entities strictly follow zero-padded, immutable ID standards with validated primary and foreign key constraints:

| Entity | PK Format | Foreign Keys | Domain Purpose |
| :--- | :--- | :--- | :--- |
| **Merchant** | `MRC-2026-XXXXX` | None | Client profile, MCC, variable basis points fee + fixed fee |
| **PaymentOrder** | `PAY-2026-XXXXXXXX` | `merchant_id`, `parent_order_id` | Commercial intent (Payment / Refund) |
| **PaymentAttempt** | `ATT-PAY-2026-XXXXXXXX-XX` | `payment_order_id` | Gateway routing attempt counter |
| **ProcessorEvent** | `PRC-2026-XXXXXXXX` | `payment_attempt_id`, `payment_order_id` | Webhook event ledger (Gross, Fee, Net) |
| **SettlementBatch** | `SET-2026-XXXXXX` | None | Payout clearing aggregate (Total Gross, Fee, Net) |
| **SettlementLine** | `STL-SET-2026-XXXXXX-XXX`| `batch_id`, `processor_event_id` | Individual transaction settled |
| **BankStatementLine** | `BANK-2026-XXXXXX`| None | Cash movement on commercial account ledger |
| **ReconciliationMatch**| `REC-2026-XXXXXX`| Left & Right Entity IDs | Multi-way match record with confidence score |
| **ExceptionRecord** | `EXC-2026-XXXXXX` | Broken Entity ID, Related Entity ID | Isolated break with discrepancy amount & severity |
| **Resolution** | `RES-2026-XXXXXX` | `exception_id` | Append-only audit record of state transition |

For complete field types, nullability, units, and validation rules, consult the **[Enterprise Data Dictionary](DATA_DICTIONARY.md)**.

---

## 4. Mandatory Edge Cases & Isolation Strategy

| Injected Negative Scenario | Detection Mechanism | Severity | Governance Workflow |
| :--- | :--- | :---: | :--- |
| **1. Duplicate Settlement Line** | Detects multiple settlement lines sharing identical `processor_event_id`. | `HIGH` | Quarantines duplicate lines to prevent double payout. |
| **2. Bank Amount Differs by Fee** | Traps $10-$35 discrepancy between settlement net and bank credit. | `MEDIUM` | Auto-resolves by posting bank wire fee expense entry. |
| **3. Refund Before Capture** | Validates temporal order: flags refund orders timestamped before parent capture. | `HIGH` | Quarantined for Risk & Compliance review. |
| **4. Unmatched Record Silently Dropped** | Identifies captured orders lacking downstream processor events. | `CRITICAL`| Escalated to Ops for processor gateway re-query. |
| **5. Currency Mismatch** | Traps currency collision between order instruction (e.g. USD) and settlement (e.g. EUR). | `HIGH` | Flagged for FX conversion rate verification. |
| **6. Same Processor Event Ingested Twice** | Ingestion gateway checks idempotency key and `(ref, event_type)` cache. | `MEDIUM` | Idempotently deduplicated; prevents double crediting. |

---

## 5. Quickstart & Installation

### Requirements
* Python 3.11+
* pip

### Installation
```powershell
# Clone or navigate to the repository directory
cd C:\Users\yenag\Downloads\akhil

# Install package and dependencies in editable development mode
pip install -e .
```

### Run Full End-to-End Pipeline
```powershell
# Run Starter Scale (100 merchants, 2.5k orders)
python scripts/run_all.py --scale starter

# Run Full Scale (2,000 merchants, 50,000 orders, 1,000 batches, 5,000 bank lines)
python scripts/run_all.py --scale full
```

### Verify 100% Reproducibility (Step 10)
```powershell
python scripts/verify_reproducibility.py starter
```

### Run Automated Test Suite
```powershell
pytest -v
```

---

## 6. Interactive Web Cockpit & REST API

Launch the local interactive operations cockpit and REST API:
```powershell
yottaflex-recon serve --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### Web Cockpit Features:
* **Executive Overview**: Real-time KPIs, match distribution chart, break breakdown chart, and entity counts.
* **Exception Workbench**: Filter by severity and status; open interactive triage modals to execute manual matches, fee adjustments, and write-offs.
* **Multi-Way Matches**: Inspect deterministic cross-entity bindings with confidence scores and matching rules.
* **Ground Truth Benchmarking**: Live confusion matrix and precision/recall evaluation.
* **Resolution Audit Trail**: Chronological event log of every operator action and automated transition.

### Key REST API Endpoints:
* `GET /api/status` — Current scale, loaded counts, summary
* `POST /api/generate` — Generate synthetic dataset with scale & seed
* `GET /api/summary` — High-level reconciliation and benchmark metrics
* `GET /api/exceptions` — Paginated and filtered exception list
* `POST /api/exceptions/{id}/resolve` — Apply role-based resolution action
* `GET /api/matches` — Paginated multi-way matches
* `GET /api/benchmark` — Segregated ground-truth evaluation breakdown
* `GET /api/resolutions` — Immutable audit log

---

## 7. Unified CLI Guide

The installed `yottaflex-recon` command exposes all capabilities:
```
yottaflex-recon generate                Generate deterministic datasets and export artifacts
yottaflex-recon reconcile               Run 3-way reconciliation pipeline and display summary
yottaflex-recon verify-reproducibility  Run Step 10 bit-exact reproducibility verification
yottaflex-recon serve                   Launch Web Operations Cockpit on port 8000
```

---

## 8. Export Artifacts & Manifest

All generated datasets and reconciliation results are exported to `data/`:
* `data/csv/*.csv`: CSV exports for all 10 core tables + `ground_truth.csv`.
* `data/json/*.json`: Complete structured JSON datasets.
* `data/sqlite/yottaflex_recon.db`: SQLite database loaded with ANSI SQL schema and indexed tables.
* `data/manifest.json`: Manifest listing row counts, generation metadata, and SHA-256 checksums for every artifact.

---

## 9. Empirical Evaluation Summary

Results on full dataset volume (seed `20261022`):
* **Reconciled Volume**: $4,412,890.35 across 97,011 validated matches (99.69% match rate).
* **Ground Truth Recall**: **100.00%** (265 / 265 injected anomalies successfully detected).
* **Ground Truth Precision**: **88.63%** (265 True Positives / 299 Detected).
* **F1-Score**: **0.9397** across all edge case classifications.
* **Reproducibility**: 100% bit-exact identical SHA-256 checksums verified across repeated runs.

Detailed empirical breakdowns are available in **[EVALUATION_REPORT.md](EVALUATION_REPORT.md)**.

---

## 10. Public Data Guidance & Lawful Use Notice

This platform operates exclusively on synthetic data generated through mathematical distributions (lognormal order amounts, uniform timing offsets, tiered fee models) seeded by deterministic pseudo-random generators. No external proprietary, confidential, or personally identifiable information (PII) is accessed or stored. All entity schemas adhere to lawful public banking (ISO 20022 / CAMT.053) and card network settlement conventions.
