"""Aggregate live multi-model AutoSiMP configuration runs.

Usage:
    python reproducibility/model_checks/aggregate_model_runs.py input.csv output_prefix
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


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


def parse_bool(value: str) -> bool | None:
    value = value.strip().lower()
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    return None


def parse_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    return float(value)


def has_observation(row: dict[str, str]) -> bool:
    metric_columns = [
        "model_name",
        "parse_success",
        "pre_solve_blocking_errors",
        "pre_solve_warnings",
        "field_accuracy",
        "ambiguity_flagged",
        "manual_repair_required",
    ]
    return any(row.get(col, "").strip() for col in metric_columns)


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    field_acc = [v for row in rows if (v := parse_float(row["field_accuracy"])) is not None]
    blocking = [v for row in rows if (v := parse_float(row["pre_solve_blocking_errors"])) is not None]
    warnings = [v for row in rows if (v := parse_float(row["pre_solve_warnings"])) is not None]

    def rate(column: str) -> float | None:
        vals = [parse_bool(row[column]) for row in rows if parse_bool(row[column]) is not None]
        if not vals:
            return None
        return sum(1 for val in vals if val) / len(vals)

    return {
        "n_rows": len(rows),
        "n_models": len({row["model_name"] for row in rows if row["model_name"].strip()}),
        "n_prompts": len({row["prompt_id"] for row in rows if row["prompt_id"].strip()}),
        "parse_success_rate": rate("parse_success"),
        "ambiguity_flag_rate": rate("ambiguity_flagged"),
        "manual_repair_rate": rate("manual_repair_required"),
        "mean_field_accuracy": statistics.fmean(field_acc) if field_acc else None,
        "mean_blocking_errors": statistics.fmean(blocking) if blocking else None,
        "mean_warnings": statistics.fmean(warnings) if warnings else None,
    }


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Missing required columns: {', '.join(missing)}")
        return [row for row in reader if has_observation(row)]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python aggregate_model_runs.py input.csv output_prefix")

    input_path = Path(sys.argv[1])
    output_prefix = Path(sys.argv[2])
    rows = load_rows(input_path)

    by_model: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_prompt: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["model_name"].strip():
            by_model[row["model_name"]].append(row)
        if row["prompt_id"].strip():
            by_prompt[row["prompt_id"]].append(row)

    summary = {
        "overall": summarize(rows),
        "by_model": {key: summarize(value) for key, value in sorted(by_model.items())},
        "by_prompt": {key: summarize(value) for key, value in sorted(by_prompt.items())},
    }

    json_path = output_prefix.with_suffix(".json")
    md_path = output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Multi-Model Run Summary", ""]
    lines.append(f"Rows analyzed: {summary['overall']['n_rows']}")
    lines.append(f"Models: {summary['overall']['n_models']}")
    lines.append(f"Prompts: {summary['overall']['n_prompts']}")
    lines.append("")
    lines.append("## By Model")
    for model, stats in summary["by_model"].items():
        lines.append(
            f"- {model}: n={stats['n_rows']}, parse_success={stats['parse_success_rate']}, "
            f"field_accuracy={stats['mean_field_accuracy']}, manual_repair={stats['manual_repair_rate']}"
        )
    lines.append("")
    lines.append("## Boundary")
    lines.append("- Report completed live runs only within their model/provider scope.")
    lines.append("- Do not generalize to provider-diverse robustness without provider-diverse data.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
