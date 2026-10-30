"""
Unit tests for Ground-Truth Benchmarking and Accuracy Evaluation.
"""
from src.generator import SyntheticDataGenerator
from src.engine import WebhookIngestor, MultiWayReconciler
from src.evaluation.benchmark import GroundTruthBenchmark


def test_ground_truth_benchmark_perfect_accuracy():
    gen = SyntheticDataGenerator(seed=20261022, scale="starter")
    data = gen.generate_all()

    ingestor = WebhookIngestor(run_id="TEST-BENCH")
    clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

    reconciler = MultiWayReconciler(run_id="TEST-BENCH")
    recon_res = reconciler.reconcile_all(
        orders=data["payment_orders"],
        events=clean_events,
        batches=data["settlement_batches"],
        lines=data["settlement_lines"],
        bank_lines=data["bank_statement_lines"],
        initial_exceptions=dup_excs,
    )

    benchmark = GroundTruthBenchmark(
        ground_truth=data["ground_truth"],
        exceptions=recon_res["exceptions"],
        matches=recon_res["matches"],
    )
    eval_results = benchmark.evaluate()
    metrics = eval_results["overall_metrics"]

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1_score"] == 1.0
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0
