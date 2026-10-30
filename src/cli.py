"""
Unified Command-Line Interface (CLI) for YottaFlex Payment Reconciliation Platform.
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import uvicorn
from tabulate import tabulate

from src.generator import SyntheticDataGenerator, DatasetValidator
from src.engine import WebhookIngestor, MultiWayReconciler, ResolutionEngine
from src.evaluation.benchmark import GroundTruthBenchmark
from scripts.export_data import export_dataset
from scripts.verify_reproducibility import verify_reproducibility as do_verify_repro


@click.group()
def main():
    """YottaFlex Payment Reconciliation & Exception Resolution CLI."""
    pass


@main.command()
@click.option("--scale", default="starter", type=click.Choice(["starter", "full"]), help="Dataset scale volume")
@click.option("--seed", default=20261022, type=int, help="Fixed random seed")
@click.option("--output-dir", default="data", type=str, help="Target export directory")
def generate(scale: str, seed: int, output_dir: str):
    """Generate deterministic synthetic datasets and export CSV/JSON/SQLite."""
    click.echo(f"Generating {scale} dataset with seed {seed}...")
    gen = SyntheticDataGenerator(seed=seed, scale=scale)
    data = gen.generate_all()

    ingestor = WebhookIngestor(f"CLI-RUN-{seed}")
    clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

    reconciler = MultiWayReconciler(f"CLI-RUN-{seed}")
    recon_res = reconciler.reconcile_all(
        data["payment_orders"],
        clean_events,
        data["settlement_batches"],
        data["settlement_lines"],
        data["bank_statement_lines"],
        dup_excs,
    )

    resolver = ResolutionEngine()
    resolutions = resolver.auto_resolve_batch(recon_res["exceptions"])

    manifest = export_dataset(data, recon_res, resolutions, output_dir=output_dir)
    click.echo(click.style(f"Export complete to '{output_dir}/'. Manifest contains {len(manifest['files'])} files.", fg="green"))


@main.command()
@click.option("--scale", default="starter", type=click.Choice(["starter", "full"]), help="Dataset scale")
@click.option("--seed", default=20261022, type=int, help="Fixed random seed")
def reconcile(scale: str, seed: int):
    """Run full multi-way reconciliation pipeline and output metrics."""
    from scripts.run_all import run_pipeline
    run_pipeline(scale=scale, seed=seed)


@main.command()
@click.option("--scale", default="starter", type=click.Choice(["starter", "full"]), help="Dataset scale")
@click.option("--seed", default=20261022, type=int, help="Fixed random seed")
def verify_reproducibility(scale: str, seed: int):
    """Verify 100% bit-exact reproducibility across two successive generations."""
    do_verify_repro(seed=seed, scale=scale)


@main.command()
@click.option("--port", default=8000, type=int, help="HTTP server port")
@click.option("--host", default="127.0.0.1", type=str, help="Host address")
def serve(host: str, port: int):
    """Launch interactive Web Operations Cockpit & REST API."""
    click.echo(click.style(f"Starting YottaFlex Reconciliation Server at http://{host}:{port}", fg="cyan", bold=True))
    uvicorn.run("src.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
