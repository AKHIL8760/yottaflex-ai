"""
Master End-to-End Orchestrator for YottaFlex Payment Reconciliation Platform.
Executes Generation -> Validation -> Ingestion -> Reconciliation -> Resolution -> Benchmark -> Export.
"""
import sys
import argparse
from pathlib import Path
from tabulate import tabulate

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator import SyntheticDataGenerator, DatasetValidator
from src.engine import WebhookIngestor, MultiWayReconciler, ResolutionEngine
from src.evaluation.benchmark import GroundTruthBenchmark
from scripts.export_data import export_dataset


def run_pipeline(scale: str = "starter", seed: int = 20261022, output_dir: str = "data"):
    print("=" * 80)
    print(" YOTTAFLEX.AI — MULTI-WAY PAYMENT RECONCILIATION & RESOLUTION PLATFORM")
    print(f" Scale: {scale.upper()} | Seed: {seed} | Target Directory: {output_dir}")
    print("=" * 80)

    # 1. GENERATION
    print("\n[Step 1/6] Generating synthetic datasets (master, child, batch, bank)...")
    gen = SyntheticDataGenerator(seed=seed, scale=scale)
    data = gen.generate_all()
    counts = data["metadata"]["counts"]
    print(f"      -> Generated {counts['merchants']:,} Merchants, {counts['payment_orders']:,} Orders, "
          f"{counts['payment_attempts']:,} Attempts, {counts['processor_events']:,} Events, "
          f"{counts['settlement_batches']:,} Batches, {counts['settlement_lines']:,} Lines, "
          f"{counts['bank_statement_lines']:,} Bank Lines.")
    print(f"      -> Injected {counts['ground_truth_anomalies']} labeled anomalies across 6 edge case classes.")

    # 2. VALIDATION (Step 8)
    print("\n[Step 2/6] Running dataset integrity & business rule validation suite...")
    validator = DatasetValidator(data)
    val_results = validator.validate_all()
    val_summary = val_results["summary"]
    print(f"      -> Total Checks: {val_summary['total_checks']} | "
          f"Passed: {val_summary['passed_checks']} | "
          f"Failed: {val_summary['failed_checks']} | "
          f"Status: {'VALID' if val_results['is_valid'] else 'INVALID'}")

    # 3. INGESTION & IDEMPOTENCY
    print("\n[Step 3/6] Ingesting processor webhooks through idempotency gateway...")
    run_id = f"RUN-{seed}-{scale}"
    ingestor = WebhookIngestor(run_id=run_id)
    clean_events, duplicate_exceptions = ingestor.ingest_stream(data["raw_webhook_stream"])
    print(f"      -> Processed {len(data['raw_webhook_stream']):,} webhooks. "
          f"Emitted {len(clean_events):,} clean events. "
          f"Flagged {len(duplicate_exceptions):,} duplicate deliveries.")

    # 4. RECONCILIATION (Multi-way matching)
    print("\n[Step 4/6] Executing multi-way reconciliation pipeline (Orders <-> Events <-> Batches <-> Bank)...")
    reconciler = MultiWayReconciler(run_id=run_id)
    recon_results = reconciler.reconcile_all(
        orders=data["payment_orders"],
        events=clean_events,
        batches=data["settlement_batches"],
        lines=data["settlement_lines"],
        bank_lines=data["bank_statement_lines"],
        initial_exceptions=duplicate_exceptions,
    )
    r_sum = recon_results["summary"]
    print(f"      -> Reconciliation Matches: {r_sum['total_matches']:,}")
    print(f"      -> Total Exceptions Detected: {r_sum['total_exceptions']:,}")
    print(f"      -> Total Discrepancy Amount: ${r_sum['total_discrepancy_amount']:,.2f}")
    print(f"      -> Match Rate: {r_sum['match_rate_percentage']:.2f}%")

    # 5. RESOLUTION (Automated policy & audit trail)
    print("\n[Step 5/6] Applying automated policy resolutions (wire fees, tolerances)...")
    resolver = ResolutionEngine()
    resolutions = resolver.auto_resolve_batch(recon_results["exceptions"])
    print(f"      -> Automatically resolved {len(resolutions)} exceptions per documented policy.")
    open_exceptions = sum(1 for e in recon_results["exceptions"] if e.status == "OPEN")
    print(f"      -> Remaining Open for Analyst/Risk Review: {open_exceptions}")

    # 6. BENCHMARKING (Ground truth evaluation)
    print("\n[Step 6/6] Benchmarking against segregated ground-truth catalog...")
    benchmark = GroundTruthBenchmark(
        ground_truth=data["ground_truth"],
        exceptions=recon_results["exceptions"],
        matches=recon_results["matches"],
    )
    eval_results = benchmark.evaluate()
    metrics = eval_results["overall_metrics"]

    print("\n" + "=" * 80)
    print(" EVALUATION METRICS SUMMARY (AGAINST GROUND TRUTH)")
    print("=" * 80)
    summary_table = [
        ["Total Injected Anomalies", f"{metrics['total_ground_truth_anomalies']:,}"],
        ["Total Detected Exceptions", f"{metrics['total_exceptions_detected']:,}"],
        ["True Positives (TP)", f"{metrics['true_positives']:,}"],
        ["False Positives (FP)", f"{metrics['false_positives']:,}"],
        ["False Negatives (FN)", f"{metrics['false_negatives']:,}"],
        ["Precision", f"{metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)"],
        ["Recall", f"{metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)"],
        ["F1-Score", f"{metrics['f1_score']:.4f} ({metrics['f1_score']*100:.2f}%)"],
        ["Anomaly Detection Rate", f"{metrics['detection_accuracy_percentage']:.2f}%"],
    ]
    print(tabulate(summary_table, headers=["Metric", "Value"], tablefmt="github"))

    print("\n BREAKDOWN BY EDGE CASE CATEGORY:")
    cat_rows = []
    for itype, cat_data in eval_results["category_breakdown"].items():
        cat_rows.append([
            itype,
            cat_data["ground_truth_count"],
            cat_data["detected_count"],
            cat_data["true_positives"],
            cat_data["false_positives"],
            cat_data["false_negatives"],
            f"{cat_data['precision']:.2f}",
            f"{cat_data['recall']:.2f}",
            f"{cat_data['f1_score']:.2f}",
        ])
    print(tabulate(
        cat_rows,
        headers=["Issue Type", "GT", "Detected", "TP", "FP", "FN", "Prec", "Rec", "F1"],
        tablefmt="github",
    ))

    # 7. EXPORT DATA (Step 9)
    print(f"\n[Export] Exporting CSV, JSON, SQLite database, and manifest to '{output_dir}/'...")
    manifest = export_dataset(data, recon_results, resolutions, output_dir=output_dir)
    print(f"      -> Export complete. SQLite DB: {output_dir}/sqlite/yottaflex_recon.db")
    print(f"      -> Manifest: {output_dir}/manifest.json ({len(manifest['files'])} artifacts)")
    print("=" * 80)

    return {
        "data": data,
        "recon_results": recon_results,
        "eval_results": eval_results,
        "resolutions": resolutions,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YottaFlex Payment Reconciliation Platform Runner")
    parser.add_argument("--scale", type=str, default="starter", choices=["starter", "full"], help="Dataset scale")
    parser.add_argument("--seed", type=int, default=20261022, help="Fixed random seed")
    parser.add_argument("--output-dir", type=str, default="data", help="Output directory")
    args = parser.parse_args()

    run_pipeline(scale=args.scale, seed=args.seed, output_dir=args.output_dir)
