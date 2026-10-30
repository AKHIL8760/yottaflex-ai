"""
Export utility to serialize reconciliation datasets to CSV, JSON, and SQLite database.
Produces source manifest with SHA-256 checksums and row counts (Step 9).
"""
import os
import sys
import csv
import json
import sqlite3
import hashlib
from typing import Dict, Any, List
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def calculate_sha256(filepath: str) -> str:
    """Calculates SHA-256 checksum for a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def export_dataset(
    data: Dict[str, Any],
    recon_results: Dict[str, Any],
    resolutions: list,
    output_dir: str = "data",
) -> Dict[str, Any]:
    """
    Exports all 10 core entities + ground truth to CSV, JSON, and SQLite formats.
    """
    base_path = Path(output_dir)
    csv_dir = base_path / "csv"
    json_dir = base_path / "json"
    sqlite_dir = base_path / "sqlite"

    csv_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    sqlite_dir.mkdir(parents=True, exist_ok=True)

    # Prepare table dicts
    tables: Dict[str, List[dict]] = {
        "merchants": [m.model_dump() for m in data.get("merchants", [])],
        "payment_orders": [o.model_dump() for o in data.get("payment_orders", [])],
        "payment_attempts": [a.model_dump() for a in data.get("payment_attempts", [])],
        "processor_events": [pe.model_dump() for pe in data.get("processor_events", [])],
        "settlement_batches": [b.model_dump() for b in data.get("settlement_batches", [])],
        "settlement_lines": [sl.model_dump() for sl in data.get("settlement_lines", [])],
        "bank_statement_lines": [bl.model_dump() for bl in data.get("bank_statement_lines", [])],
        "reconciliation_matches": [m.model_dump() for m in recon_results.get("matches", [])],
        "exception_records": [
            {**e.model_dump(), "details_json": json.dumps(e.details)}
            for e in recon_results.get("exceptions", [])
        ],
        "resolutions": [r.model_dump() for r in resolutions],
        "ground_truth": [gt.model_dump() for gt in data.get("ground_truth", [])],
    }

    manifest = {
        "seed": data.get("metadata", {}).get("seed", 20261022),
        "scale": data.get("metadata", {}).get("scale", "starter"),
        "generated_at": data.get("metadata", {}).get("generated_at"),
        "files": {},
    }

    # 1. Export CSV and JSON files
    for table_name, rows in tables.items():
        # JSON export
        json_file = json_dir / f"{table_name}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

        # CSV export
        csv_file = csv_dir / f"{table_name}.csv"
        if rows:
            fieldnames = list(rows[0].keys())
            # Exclude dict field 'details' if 'details_json' is present
            if "details" in fieldnames and "details_json" in fieldnames:
                fieldnames.remove("details")

            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        else:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                f.write("")

        manifest["files"][f"csv/{table_name}.csv"] = {
            "row_count": len(rows),
            "sha256": calculate_sha256(str(csv_file)),
            "size_bytes": os.path.getsize(csv_file),
        }
        manifest["files"][f"json/{table_name}.json"] = {
            "row_count": len(rows),
            "sha256": calculate_sha256(str(json_file)),
            "size_bytes": os.path.getsize(json_file),
        }

    # 2. Export to SQLite
    db_path = sqlite_dir / "yottaflex_recon.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    # Load schema DDL
    schema_path = Path("src/models/schema.sql")
    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

    # Insert rows
    for table_name, rows in tables.items():
        if table_name == "ground_truth":
            # Store ground truth in separate table for verification
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ground_truth (
                    anomaly_id VARCHAR(32) PRIMARY KEY,
                    issue_type VARCHAR(64) NOT NULL,
                    entity_type VARCHAR(32) NOT NULL,
                    entity_id VARCHAR(64) NOT NULL,
                    expected_decision VARCHAR(64) NOT NULL,
                    expected_severity VARCHAR(16) NOT NULL,
                    expected_discrepancy NUMERIC(16, 2) NOT NULL,
                    details TEXT NOT NULL
                )
                """
            )
        if not rows:
            continue
        cols = [c for c in rows[0].keys() if not (c == "details" and "details_json" in rows[0])]
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"
        data_tuples = [tuple(r.get(c) for c in cols) for r in rows]
        conn.executemany(sql, data_tuples)

    conn.commit()
    conn.close()

    manifest["files"]["sqlite/yottaflex_recon.db"] = {
        "sha256": calculate_sha256(str(db_path)),
        "size_bytes": os.path.getsize(db_path),
    }

    # Write manifest.json
    manifest_path = base_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest
