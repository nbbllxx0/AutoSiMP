"""Bounded solve for the normalized multi-load bracket workflow case.

Run with the compatible local conda environment:

    conda run -n PY python experiments\realistic_case_solve.py

The script deliberately avoids LLM/API calls. It uses a coarser 80x30 mesh
variant of the normalized bracket specification so SciPy's direct solver can finish
without pyamg in the local PY environment.
"""

from __future__ import annotations

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


def build_coarse_normalized_bracket_spec() -> ProblemSpec:
    return ProblemSpec(
        Lx=4.0,
        Ly=1.5,
        nelx=80,
        nely=30,
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


def main() -> None:
    out_dir = REVISION_ROOT / "experiment_results_major_overhaul" / "normalized_bracket_solve"
    out_dir.mkdir(parents=True, exist_ok=True)

    spec = build_coarse_normalized_bracket_spec()
    max_iter = 60
    t0 = time.time()
    bc = generate_bc(spec)
    result = run_optimization(
        spec=spec,
        bc=bc,
        controller_name="schedule",
        max_iter=max_iter,
        verbose=False,
    )
    elapsed = time.time() - t0
    eval_result = evaluate(result, spec, max_iter=max_iter, use_llm=False, verbose=False)

    image_path = out_dir / "normalized_bracket_density.png"
    save_density_image(result["rho_final"], spec.nelx, spec.nely, str(image_path))

    payload = {
        "case": "normalized_multiload_bracket_coarse_solve",
        "notes": (
            "Coarser 80x30 solve of the normalized multi-load bracket workflow case. "
            "This is evidence of workflow execution, not certified engineering validation."
        ),
        "elapsed_seconds": elapsed,
        "spec": spec.to_dict(),
        "solver": {
            "controller": "schedule",
            "max_iter": max_iter,
            "n_iter": result.get("n_iter"),
            "final_compliance": result.get("final_compliance"),
            "best_compliance": result.get("best_compliance"),
            "best_iteration": result.get("best_iteration"),
            "final_grayness": result.get("final_grayness"),
            "best_grayness": result.get("best_grayness"),
            "best_is_valid": result.get("best_is_valid"),
        },
        "evaluation": {
            "passed": eval_result.passed,
            "summary": eval_result.summary,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "value": check.value,
                    "threshold": check.threshold,
                    "message": check.message,
                }
                for check in eval_result.checks
            ],
        },
        "artifacts": {
            "density_png": str(image_path),
        },
    }
    (out_dir / "normalized_bracket_solve.json").write_text(
        json.dumps(payload, indent=2, default=float),
        encoding="utf-8",
    )
    print(json.dumps(payload["solver"], indent=2, default=float))
    print(json.dumps(payload["evaluation"], indent=2, default=float))
    print(f"elapsed_seconds={elapsed:.2f}")


if __name__ == "__main__":
    main()
