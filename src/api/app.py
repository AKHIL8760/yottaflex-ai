"""
FastAPI backend for YottaFlex Payment Reconciliation & Exception Resolution Platform.
Exposes REST endpoints for pipeline execution, entity exploration, exception management, and benchmarking.
"""
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.generator import SyntheticDataGenerator, DatasetValidator
from src.engine import WebhookIngestor, MultiWayReconciler, ResolutionEngine, ReconciliationConfig
from src.evaluation.benchmark import GroundTruthBenchmark
from scripts.export_data import export_dataset

app = FastAPI(
    title="YottaFlex Payment Reconciliation Platform",
    description="Enterprise multi-way reconciliation, idempotency enforcement, and exception resolution API.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory application state
STATE: Dict[str, Any] = {
    "data": None,
    "recon_results": None,
    "resolutions": [],
    "resolver": ResolutionEngine(),
    "benchmark_results": None,
    "scale": "starter",
    "seed": 20261022,
}


class GenerateRequest(BaseModel):
    scale: str = "starter"
    seed: int = 20261022


class ReconcileRequest(BaseModel):
    amount_tolerance: float = 0.05
    auto_resolve_wire_fees: bool = True


class ResolveExceptionRequest(BaseModel):
    actor_role: str
    actor_id: str
    resolution_type: str
    notes: str
    financial_adjustment: float = 0.0


def initialize_default_pipeline():
    """Initializes starter pipeline on startup if empty."""
    if STATE["data"] is None:
        gen = SyntheticDataGenerator(seed=STATE["seed"], scale=STATE["scale"])
        data = gen.generate_all()

        ingestor = WebhookIngestor(run_id=f"RUN-{STATE['seed']}")
        clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

        reconciler = MultiWayReconciler(run_id=f"RUN-{STATE['seed']}")
        recon_results = reconciler.reconcile_all(
            orders=data["payment_orders"],
            events=clean_events,
            batches=data["settlement_batches"],
            lines=data["settlement_lines"],
            bank_lines=data["bank_statement_lines"],
            initial_exceptions=dup_excs,
        )

        resolver = ResolutionEngine()
        resolutions = resolver.auto_resolve_batch(recon_results["exceptions"])

        benchmark = GroundTruthBenchmark(
            ground_truth=data["ground_truth"],
            exceptions=recon_results["exceptions"],
            matches=recon_results["matches"],
        )
        eval_results = benchmark.evaluate()

        STATE["data"] = data
        STATE["recon_results"] = recon_results
        STATE["resolutions"] = resolutions
        STATE["resolver"] = resolver
        STATE["benchmark_results"] = eval_results


@app.on_event("startup")
def on_startup():
    initialize_default_pipeline()


@app.get("/api/status")
def get_status():
    initialize_default_pipeline()
    data = STATE["data"]
    recon = STATE["recon_results"]
    return {
        "status": "READY",
        "scale": STATE["scale"],
        "seed": STATE["seed"],
        "entities_loaded": data["metadata"]["counts"] if data else {},
        "reconciliation_summary": recon["summary"] if recon else {},
    }


@app.post("/api/generate")
def generate_dataset(req: GenerateRequest):
    STATE["scale"] = req.scale
    STATE["seed"] = req.seed

    gen = SyntheticDataGenerator(seed=req.seed, scale=req.scale)
    data = gen.generate_all()

    ingestor = WebhookIngestor(run_id=f"RUN-{req.seed}")
    clean_events, dup_excs = ingestor.ingest_stream(data["raw_webhook_stream"])

    reconciler = MultiWayReconciler(run_id=f"RUN-{req.seed}")
    recon_results = reconciler.reconcile_all(
        orders=data["payment_orders"],
        events=clean_events,
        batches=data["settlement_batches"],
        lines=data["settlement_lines"],
        bank_lines=data["bank_statement_lines"],
        initial_exceptions=dup_excs,
    )

    resolver = ResolutionEngine()
    resolutions = resolver.auto_resolve_batch(recon_results["exceptions"])

    benchmark = GroundTruthBenchmark(
        ground_truth=data["ground_truth"],
        exceptions=recon_results["exceptions"],
        matches=recon_results["matches"],
    )
    eval_results = benchmark.evaluate()

    STATE["data"] = data
    STATE["recon_results"] = recon_results
    STATE["resolutions"] = resolutions
    STATE["resolver"] = resolver
    STATE["benchmark_results"] = eval_results

    # Export to disk
    export_dataset(data, recon_results, resolutions, output_dir="data")

    return {
        "message": f"Successfully generated {req.scale} dataset with seed {req.seed}.",
        "counts": data["metadata"]["counts"],
        "reconciliation_summary": recon_results["summary"],
        "evaluation_metrics": eval_results["overall_metrics"],
    }


@app.get("/api/summary")
def get_summary():
    initialize_default_pipeline()
    recon = STATE["recon_results"]
    bench = STATE["benchmark_results"]
    return {
        "reconciliation": recon["summary"],
        "benchmark": bench["overall_metrics"],
        "resolutions_count": len(STATE["resolutions"]),
    }


@app.get("/api/exceptions")
def list_exceptions(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    issue_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    initialize_default_pipeline()
    all_excs = STATE["recon_results"]["exceptions"]
    filtered = all_excs

    if status:
        filtered = [e for e in filtered if e.status == status]
    if severity:
        filtered = [e for e in filtered if e.severity == severity]
    if issue_type:
        filtered = [e for e in filtered if e.issue_type == issue_type]

    total = len(filtered)
    paged = filtered[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [e.model_dump() for e in paged],
    }


@app.get("/api/exceptions/{exception_id}")
def get_exception(exception_id: str):
    initialize_default_pipeline()
    for exc in STATE["recon_results"]["exceptions"]:
        if exc.exception_id == exception_id:
            audit = STATE["resolver"].get_audit_trail_for_exception(exception_id)
            return {
                "exception": exc.model_dump(),
                "audit_trail": [a.model_dump() for a in audit],
            }
    raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found")


@app.post("/api/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: str, req: ResolveExceptionRequest):
    initialize_default_pipeline()
    target_exc = None
    for exc in STATE["recon_results"]["exceptions"]:
        if exc.exception_id == exception_id:
            target_exc = exc
            break

    if not target_exc:
        raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found")

    try:
        res = STATE["resolver"].apply_manual_resolution(
            exception=target_exc,
            actor_role=req.actor_role,
            actor_id=req.actor_id,
            resolution_type=req.resolution_type,
            notes=req.notes,
            financial_adjustment=req.financial_adjustment,
        )
        STATE["resolutions"].append(res)
        return {
            "message": f"Exception {exception_id} transitioned to {target_exc.status}",
            "resolution": res.model_dump(),
            "exception": target_exc.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/matches")
def list_matches(limit: int = 50, offset: int = 0, match_type: Optional[str] = None):
    initialize_default_pipeline()
    all_matches = STATE["recon_results"]["matches"]
    filtered = all_matches
    if match_type:
        filtered = [m for m in filtered if m.match_type == match_type]
    total = len(filtered)
    paged = filtered[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [m.model_dump() for m in paged],
    }


@app.get("/api/benchmark")
def get_benchmark():
    initialize_default_pipeline()
    return STATE["benchmark_results"]


@app.get("/api/resolutions")
def list_resolutions():
    initialize_default_pipeline()
    return {
        "total": len(STATE["resolutions"]),
        "items": [r.model_dump() for r in STATE["resolutions"]],
    }


@app.get("/api/entities/{entity_name}")
def get_entities(entity_name: str, limit: int = 25, offset: int = 0):
    initialize_default_pipeline()
    data = STATE["data"]
    if entity_name not in data:
        raise HTTPException(status_code=404, detail=f"Entity {entity_name} not found")

    records = data[entity_name]
    total = len(records)
    paged = records[offset : offset + limit]
    return {
        "entity": entity_name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [r.model_dump() for r in paged],
    }


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Serves the integrated single-page interactive operations cockpit."""
    html_file = "src/web/index.html"
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception:
        return HTMLResponse(content="<h1>YottaFlex Reconciliation Platform</h1><p>UI loading error. Check src/web/index.html</p>")
