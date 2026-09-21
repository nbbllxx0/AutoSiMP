"""Validate whether live model-run CSV files satisfy a reporting scope.

The default mode validates schema and populated rows. Use stricter thresholds
to decide whether data can support provider-diverse or repeated-run claims.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


REQUIRED_COLUMNS = [
    "run_id",
    "model_provider",
    "model_name",
    "model_version",
    "run_timestamp",
    "temperature",
    "prompt_id",
    "prompt_text",
    "schema_version",
    "raw_output_file",
    "parsed_spec_file",
    "parse_success",
    "pre_solve_blocking_errors",
    "pre_solve_warnings",
    "field_accuracy",
    "ambiguity_flagged",
    "manual_repair_required",
    "notes",
]


def load_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
            if missing:
                raise SystemExit(f"{path}: missing required columns: {', '.join(missing)}")
            rows.extend(row for row in reader if any((row.get(col) or "").strip() for col in REQUIRED_COLUMNS))
    return rows


def populated_metric_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if row.get("model_provider", "").strip()
        and row.get("model_name", "").strip()
        and row.get("prompt_id", "").strip()
        and row.get("run_timestamp", "").strip()
        and row.get("parse_success", "").strip()
    ]


def is_true(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_files", nargs="+", type=Path)
    parser.add_argument("--min-providers", type=int, default=1)
    parser.add_argument("--min-models", type=int, default=1)
    parser.add_argument("--min-prompts", type=int, default=1)
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--min-scored-rows", type=int, default=0)
    parser.add_argument("--require-field-accuracy", action="store_true", help="Require at least one scored row.")
    parser.add_argument("--require-raw-or-spec-files", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.csv_files)
    metric_rows = populated_metric_rows(rows)
    providers = sorted({row["model_provider"].strip().lower() for row in metric_rows})
    models = sorted({row["model_name"].strip() for row in metric_rows})
    prompts = sorted({row["prompt_id"].strip() for row in metric_rows})

    if len(metric_rows) < args.min_rows:
        raise SystemExit(f"Only {len(metric_rows)} metric rows; required {args.min_rows}")
    if len(providers) < args.min_providers:
        raise SystemExit(f"Only {len(providers)} providers; required {args.min_providers}: {providers}")
    if len(models) < args.min_models:
        raise SystemExit(f"Only {len(models)} models; required {args.min_models}")
    if len(prompts) < args.min_prompts:
        raise SystemExit(f"Only {len(prompts)} prompts; required {args.min_prompts}")
    if args.require_field_accuracy:
        args.min_scored_rows = max(args.min_scored_rows, 1)
    scored_rows = [row for row in metric_rows if row.get("field_accuracy", "").strip()]
    if len(scored_rows) < args.min_scored_rows:
        raise SystemExit(f"Only {len(scored_rows)} scored rows; required {args.min_scored_rows}")
    if args.require_raw_or_spec_files:
        missing_evidence = [
            row["run_id"] for row in metric_rows
            if not row.get("raw_output_file", "").strip() and not row.get("parsed_spec_file", "").strip()
        ]
        if missing_evidence:
            raise SystemExit(f"Missing raw/spec evidence file path in {len(missing_evidence)} rows")

    print(f"rows={len(metric_rows)}")
    print(f"providers={len(providers)}:{','.join(providers)}")
    print(f"models={len(models)}")
    print(f"prompts={len(prompts)}")
    print(f"scored_rows={len(scored_rows)}")
    print("scope_ok=true")


if __name__ == "__main__":
    main()
