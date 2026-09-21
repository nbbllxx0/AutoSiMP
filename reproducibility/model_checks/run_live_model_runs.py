"""Run live AutoSiMP configuration prompts through Gemini model conditions.

This script deliberately refuses to count fallback/default configurations as
model data. If no API key is configured, it exits before writing result rows.

Example:
    python reproducibility/model_checks/run_live_model_runs.py \
      --models gemini-3.1-flash-lite-preview \
      --repeats 1 \
      --output reproducibility/model_checks/live_model_runs.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
REVISION_ROOT = THIS_DIR.parent
WORKSPACE_ROOT = REVISION_ROOT.parent
IMPL_ROOT = WORKSPACE_ROOT
sys.path.insert(0, str(IMPL_ROOT))
sys.path.insert(0, str(REVISION_ROOT / "diagnostic_suite"))

from configurator_agent import configure  # noqa: E402
from problem_spec import (  # noqa: E402
    CircularRegion,
    DistributedLoad,
    EdgeSupport,
    PointLoad,
    PointSupport,
    ProblemSpec,
    RectangularRegion,
)
from revision_experiments import (  # noqa: E402
    ambiguity_flags,
    compare_specs,
    pre_solve_model_checks,
)


FIELDNAMES = [
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


def load_prompt_set(path: Path) -> list[tuple[str, str]]:
    prompts: list[tuple[str, str]] = []
    current_id: str | None = None
    current_lines: list[str] = []
    item_re = re.compile(r"^(M\d+)\.\s*(.*)")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = item_re.match(line.strip())
        if match:
            if current_id:
                prompts.append((current_id, " ".join(current_lines).strip()))
            current_id = match.group(1)
            current_lines = [match.group(2).strip()]
        elif current_id and line.strip() and not line.startswith("#"):
            current_lines.append(line.strip())
    if current_id:
        prompts.append((current_id, " ".join(current_lines).strip()))
    if not prompts:
        raise SystemExit(f"No M*-style prompts found in {path}")
    return prompts


def expected_specs() -> dict[str, ProblemSpec]:
    return {
        "M1": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
        ),
        "M2": ProblemSpec(
            Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.5,
            supports=[
                EdgeSupport(edge="left", constraint="pin_x"),
                PointSupport(x=3.0, y=0.0, constraint="pin_y"),
            ],
            loads=[PointLoad(x=0.0, y=1.0, fy=-1.0)],
        ),
        "M3": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
            passive_regions=[CircularRegion(cx=1.0, cy=0.5, radius=0.15, kind="void")],
        ),
        "M4": ProblemSpec(
            Lx=6.0, Ly=1.0, nelx=120, nely=20, volfrac=0.5,
            supports=[
                PointSupport(x=0.0, y=0.0, constraint="pin_y"),
                PointSupport(x=6.0, y=0.0, constraint="pin_y"),
            ],
            loads=[DistributedLoad(edge="top", magnitude=-1.0)],
        ),
        "M5": ProblemSpec(
            Lx=2.0, Ly=2.0, nelx=60, nely=60, volfrac=0.4,
            supports=[EdgeSupport(edge="top", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fx=1.0)],
        ),
        "M7": ProblemSpec(
            Lx=1.0, Ly=2.0, nelx=30, nely=60, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[
                PointLoad(x=1.0, y=2.0, fy=-1.0),
                PointLoad(x=1.0, y=0.0, fy=-1.0),
            ],
        ),
        "M8": ProblemSpec(
            Lx=4.0, Ly=1.5, nelx=160, nely=60, volfrac=0.35,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[
                PointLoad(x=4.0, y=0.75, fy=-1.0),
                PointLoad(x=4.0, y=0.75, fx=-0.25),
            ],
            passive_regions=[
                CircularRegion(cx=0.55, cy=0.45, radius=0.12, kind="void"),
                CircularRegion(cx=0.55, cy=1.05, radius=0.12, kind="void"),
                RectangularRegion(x0=3.65, y0=0.55, x1=4.0, y1=0.95, kind="solid"),
            ],
        ),
    }


def field_accuracy(prompt_id: str, spec: ProblemSpec) -> float | str:
    expected = expected_specs()
    if prompt_id not in expected:
        return ""
    cmp = compare_specs(expected[prompt_id], spec)
    match_keys = [key for key in cmp if key.endswith("_match")]
    matches = sum(1 for key in match_keys if cmp[key])
    return matches / max(len(match_keys), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-set", type=Path, default=THIS_DIR / "prompt_set.md")
    parser.add_argument("--output", type=Path, default=THIS_DIR / "live_model_runs.csv")
    parser.add_argument("--raw-dir", type=Path, default=THIS_DIR / "live_outputs")
    parser.add_argument("--models", nargs="+", default=["gemini-3.1-flash-lite-preview"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--schema-version", default="autosimp-problemspec-v1")
    parser.add_argument("--dry-run", action="store_true", help="Validate prompts and environment only.")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.raw_dir = args.raw_dir.resolve()

    prompts = load_prompt_set(args.prompt_set)
    key_present = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if args.dry_run:
        print(f"prompts={len(prompts)}")
        print(f"models={len(args.models)}")
        print(f"gemini_key_present={key_present}")
        return
    if not key_present:
        raise SystemExit(
            "No GEMINI_API_KEY or GOOGLE_API_KEY is configured. Refusing to write live-model rows."
        )

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for model in args.models:
        for repeat in range(1, args.repeats + 1):
            for prompt_id, prompt_text in prompts:
                run_id = f"{model.replace('/', '_')}__{prompt_id}__r{repeat}"
                base_row = {
                    "run_id": run_id,
                    "model_provider": "google",
                    "model_name": model,
                    "model_version": model,
                    "run_timestamp": datetime.now(timezone.utc).isoformat(),
                    "temperature": args.temperature,
                    "prompt_id": prompt_id,
                    "prompt_text": prompt_text,
                    "schema_version": args.schema_version,
                    "raw_output_file": "",
                    "parsed_spec_file": "",
                    "parse_success": "false",
                    "pre_solve_blocking_errors": "",
                    "pre_solve_warnings": "",
                    "field_accuracy": "",
                    "ambiguity_flagged": bool(ambiguity_flags(prompt_text)),
                    "manual_repair_required": "",
                    "notes": "",
                }
                try:
                    result = configure(
                        prompt_text,
                        model=model,
                        api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
                        temperature=args.temperature,
                        verbose=False,
                    )
                except Exception as exc:
                    row = dict(base_row)
                    row["notes"] = f"configure_exception: {type(exc).__name__}: {exc}"
                    rows.append(row)
                    continue
                if not result.llm_used:
                    row = dict(base_row)
                    row["notes"] = f"model_call_fallback: {result.error or '; '.join(result.warnings)}"
                    rows.append(row)
                    continue

                raw_path = args.raw_dir / f"{run_id}.raw.json"
                spec_path = args.raw_dir / f"{run_id}.spec.json"
                raw_path.write_text(json.dumps(result.raw_dict, indent=2), encoding="utf-8")
                spec_path.write_text(json.dumps(result.spec.to_dict(), indent=2), encoding="utf-8")

                issues = pre_solve_model_checks(result.spec, prompt_text)
                blocking = [issue for issue in issues if issue["severity"] == "error"]
                warnings = [issue for issue in issues if issue["severity"] == "warning"]
                rows.append({
                    **base_row,
                    "raw_output_file": str(raw_path.relative_to(REVISION_ROOT)),
                    "parsed_spec_file": str(spec_path.relative_to(REVISION_ROOT)),
                    "parse_success": "true",
                    "pre_solve_blocking_errors": len(blocking),
                    "pre_solve_warnings": len(warnings),
                    "field_accuracy": field_accuracy(prompt_id, result.spec),
                    "manual_repair_required": bool(blocking),
                    "notes": "; ".join(result.warnings),
                })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
