"""Mesh-sensitivity solves for the normalized multi-load bracket case.

Run with the compatible local conda environment:

    conda run -n PY python experiments\realistic_mesh_sensitivity.py

The experiment deliberately avoids LLM/API calls. It checks whether the
normalized workflow case remains solver-valid across coarser and finer meshes.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REVISION_ROOT = THIS_DIR.parent
WORKSPACE_ROOT = REVISION_ROOT.parent
IMPL_ROOT = WORKSPACE_ROOT
sys.path.insert(0, str(IMPL_ROOT))

from auto_simp import run_optimization, save_density_image  # noqa: E402
from bc_generator import generate_bc  # noqa: E402
from evaluator_agent import evaluate  # noqa: E402
from problem_spec import CircularRegion, EdgeSupport, PointLoad, ProblemSpec, RectangularRegion  # noqa: E402


def build_normalized_bracket_spec(nelx: int, nely: int) -> ProblemSpec:
    return ProblemSpec(
        Lx=4.0,
        Ly=1.5,
        nelx=nelx,
        nely=nely,
        volfrac=0.35,
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
    )


def run_case(label: str, nelx: int, nely: int, out_dir: Path) -> dict[str, object]:
    spec = build_normalized_bracket_spec(nelx=nelx, nely=nely)
    max_iter = 60
    start = time.time()
    bc = generate_bc(spec)
    result = run_optimization(
        spec=spec,
        bc=bc,
        controller_name="schedule",
        max_iter=max_iter,
        verbose=False,
    )
    elapsed = time.time() - start
    eval_result = evaluate(result, spec, max_iter=max_iter, use_llm=False, verbose=False)

    image_path = out_dir / f"normalized_bracket_{label}_density.png"
    save_density_image(result["rho_final"], spec.nelx, spec.nely, str(image_path))

    return {
        "case": label,
        "nelx": nelx,
        "nely": nely,
        "elements": nelx * nely,
        "elapsed_seconds": elapsed,
        "controller": "schedule",
        "max_iter": max_iter,
        "n_iter": result.get("n_iter"),
        "final_compliance": result.get("final_compliance"),
        "best_compliance": result.get("best_compliance"),
        "best_iteration": result.get("best_iteration"),
        "final_grayness": result.get("final_grayness"),
        "best_grayness": result.get("best_grayness"),
        "best_is_valid": result.get("best_is_valid"),
        "evaluation_passed": eval_result.passed,
        "evaluation_summary": eval_result.summary,
        "density_png": str(image_path),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    out_dir = REVISION_ROOT / "experiment_results_major_overhaul" / "mesh_sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        ("coarse_60x24", 60, 24),
        ("medium_80x30", 80, 30),
        ("fine_90x34", 90, 34),
    ]
    rows = [run_case(label, nelx, nely, out_dir) for label, nelx, nely in cases]
    passed = sum(1 for row in rows if row["evaluation_passed"])
    compliances = [float(row["final_compliance"]) for row in rows]
    summary = {
        "case_family": "normalized_multiload_bracket_mesh_sensitivity",
        "n": len(rows),
        "passed": passed,
        "min_elements": min(int(row["elements"]) for row in rows),
        "max_elements": max(int(row["elements"]) for row in rows),
        "min_final_compliance": min(compliances),
        "max_final_compliance": max(compliances),
        "notes": (
            "Mesh-sensitivity evidence for workflow robustness. Compliance values "
            "are not directly certified engineering allowables."
        ),
    }

    payload = {"summary": summary, "rows": rows}
    (out_dir / "normalized_bracket_mesh_sensitivity.json").write_text(
        json.dumps(payload, indent=2, default=float),
        encoding="utf-8",
    )
    write_csv(out_dir / "normalized_bracket_mesh_sensitivity.csv", rows)
    lines = [
        "# Normalized Bracket Mesh-Sensitivity Summary",
        "",
        f"- Cases: {summary['n']}",
        f"- Evaluator passed: {summary['passed']}/{summary['n']}",
        f"- Element range: {summary['min_elements']} to {summary['max_elements']}",
        f"- Final compliance range: {summary['min_final_compliance']:.3f} to {summary['max_final_compliance']:.3f}",
        "",
        "This is workflow sensitivity evidence, not certified engineering validation.",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
