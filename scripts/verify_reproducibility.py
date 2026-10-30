"""
Step 10: Reproducibility Verification Script.
Regenerates datasets twice with identical seed (20261022), exports to independent directories,
and computes cryptographic SHA-256 checksums to verify bit-exact reproducibility.
"""
import sys
import shutil
import hashlib
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tabulate import tabulate
from src.generator import SyntheticDataGenerator
from src.engine import WebhookIngestor, MultiWayReconciler, ResolutionEngine
from scripts.export_data import export_dataset, calculate_sha256


def run_pipeline(seed: int, scale: str, output_dir: str):
    # 1. Generate data
    gen = SyntheticDataGenerator(seed=seed, scale=scale)
    data = gen.generate_all()

    # 2. Ingest with idempotency
    ing = WebhookIngestor(f"REPRO-RUN-{seed}")
    clean_events, dup_excs = ing.ingest_stream(data["raw_webhook_stream"])

    # 3. Multi-way reconciliation
    recon = MultiWayReconciler(f"REPRO-RUN-{seed}")
    recon_res = recon.reconcile_all(
        data["payment_orders"],
        clean_events,
        data["settlement_batches"],
        data["settlement_lines"],
        data["bank_statement_lines"],
        dup_excs,
    )

    # 4. Auto resolution
    resolver = ResolutionEngine()
    resolutions = resolver.auto_resolve_batch(recon_res["exceptions"])

    # 5. Export
    export_dataset(data, recon_res, resolutions, output_dir=output_dir)


def verify_reproducibility(seed: int = 20261022, scale: str = "starter"):
    print(f"\n================================================================================")
    print(f" YottaFlex Payment Reconciliation — Step 10: Reproducibility Verification")
    print(f" Seed: {seed} | Scale: {scale}")
    print(f"================================================================================")

    dir_run1 = Path("data/.repro_run1")
    dir_run2 = Path("data/.repro_run2")

    # Clean existing
    if dir_run1.exists():
        shutil.rmtree(dir_run1)
    if dir_run2.exists():
        shutil.rmtree(dir_run2)

    print("\n[1/3] Generating Run 1 with seed...")
    run_pipeline(seed=seed, scale=scale, output_dir=str(dir_run1))
    print("      -> Run 1 generated and exported.")

    print("\n[2/3] Generating Run 2 with identical seed...")
    run_pipeline(seed=seed, scale=scale, output_dir=str(dir_run2))
    print("      -> Run 2 generated and exported.")

    print("\n[3/3] Comparing SHA-256 checksums and row counts across all exported files...")

    files_to_check = [
        "csv/merchants.csv",
        "csv/payment_orders.csv",
        "csv/payment_attempts.csv",
        "csv/processor_events.csv",
        "csv/settlement_batches.csv",
        "csv/settlement_lines.csv",
        "csv/bank_statement_lines.csv",
        "csv/reconciliation_matches.csv",
        "csv/exception_records.csv",
        "csv/resolutions.csv",
        "csv/ground_truth.csv",
        "json/ground_truth.json",
    ]

    comparison_table = []
    all_match = True

    for rel_path in files_to_check:
        p1 = dir_run1 / rel_path
        p2 = dir_run2 / rel_path

        if not p1.exists() or not p2.exists():
            comparison_table.append([rel_path, "MISSING", "MISSING", "FAIL"])
            all_match = False
            continue

        h1 = calculate_sha256(str(p1))
        h2 = calculate_sha256(str(p2))

        # Check line counts
        with open(p1, "r", encoding="utf-8") as f:
            lines1 = sum(1 for _ in f)
        with open(p2, "r", encoding="utf-8") as f:
            lines2 = sum(1 for _ in f)

        matches = (h1 == h2) and (lines1 == lines2)
        if not matches:
            all_match = False

        status = "MATCH (100% IDENTICAL)" if matches else "MISMATCH"
        comparison_table.append([
            rel_path,
            f"{lines1} rows | {h1[:12]}...",
            f"{lines2} rows | {h2[:12]}...",
            status,
        ])

    print("\n" + tabulate(
        comparison_table,
        headers=["File Target", "Run 1 (SHA-256 / Rows)", "Run 2 (SHA-256 / Rows)", "Verification Status"],
        tablefmt="github",
    ))

    # Clean up temp directories
    shutil.rmtree(dir_run1)
    shutil.rmtree(dir_run2)

    if all_match:
        print("\n [PASSED] PERFECT REPRODUCIBILITY DEMONSTRATED! 100% bit-exact SHA-256 match across all tables.")
        return True
    else:
        print("\n [FAILED] Checksum mismatch detected between Run 1 and Run 2.")
        sys.exit(1)


if __name__ == "__main__":
    scale_arg = sys.argv[1] if len(sys.argv) > 1 else "starter"
    verify_reproducibility(seed=20261022, scale=scale_arg)
