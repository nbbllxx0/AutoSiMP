"""Post-solve retry recovery stress test for the revision.

The existing revision harness tests deterministic pre-solve repairs. This
script exercises the solver/evaluator retry path after a completed but failed
solve. In normal mode it starts from a short iteration budget, reads the
evaluator's deterministic rerun hint, increases the budget, and re-solves.
With ``--inject-first-failure`` it deliberately evaluates a uniform-gray copy
of the first completed density field to trigger the post-solve evaluator gate
before re-solving the original case. That mode is a retry-path stress test,
not natural failure-rate evidence.

The experiment deliberately uses small 2-D cases and the schedule controller so
it can run locally without LLM/API calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


THIS_DIR = Path(__file__).resolve().parent
REVISION_ROOT = THIS_DIR.parent
WORKSPACE_ROOT = REVISION_ROOT.parent
IMPL_ROOT = WORKSPACE_ROOT
sys.path.insert(0, str(IMPL_ROOT))
sys.path.insert(0, str(REVISION_ROOT / "diagnostic_suite"))

from auto_simp import run_optimization  # noqa: E402
from bc_generator import generate_bc  # noqa: E402
from evaluator_agent import evaluate  # noqa: E402
from problem_spec import CircularRegion, EdgeSupport, PointLoad, ProblemSpec, RectangularRegion  # noqa: E402
from revision_experiments import PIPELINE_TEST_CASES  # noqa: E402


CASE_NAMES = [
    "cantilever_basic",
    "mbb_beam",
    "bridge",
    "cantilever_with_hole",
    "cantilever_low_vf",
    "deep_beam_shear",
    "simply_supported_center",
    "dual_load",
    "lbracket",
    "high_aspect",
]


EXTRA_RETRY_CASES = [
    {
        "name": "retry_rect_void_cantilever",
        "prompt": "Left-clamped cantilever with a rectangular passive window and a downward free-end load.",
        "spec": ProblemSpec(
            Lx=2.0,
            Ly=1.0,
            nelx=80,
            nely=40,
            volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
            passive_regions=[RectangularRegion(x0=0.85, y0=0.35, x1=1.15, y1=0.65, kind="void")],
        ),
    },
    {
        "name": "retry_void_and_pad_cantilever",
        "prompt": "Left-clamped cantilever with a central circular void, protected solid tip pad, and downward load.",
        "spec": ProblemSpec(
            Lx=2.0,
            Ly=1.0,
            nelx=80,
            nely=40,
            volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
            passive_regions=[
                CircularRegion(cx=1.0, cy=0.5, radius=0.15, kind="void"),
                RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid"),
            ],
        ),
    },
]


def core_failures(eval_result: Any) -> list[str]:
    return [check.name for check in eval_result.checks[:5] if not check.passed]


def check_rows(eval_result: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": check.name,
            "passed": bool(check.passed),
            "value": float(check.value),
            "threshold": float(check.threshold),
            "message": check.message,
        }
        for check in eval_result.checks
    ]


def inject_uniform_gray_failure(result: dict[str, Any], volfrac: float) -> dict[str, Any]:
    degraded = dict(result)
    rho = np.asarray(result.get("rho_final", np.array([])))
    if rho.size:
        degraded["rho_final"] = np.full_like(rho, volfrac, dtype=float)
    gray = float(4.0 * volfrac * (1.0 - volfrac))
    degraded["final_grayness"] = gray
    degraded["best_grayness"] = min(float(result.get("best_grayness", gray)), gray)
    degraded["failure_injection"] = "uniform_gray_density"
    return degraded


def run_case(
    case: dict[str, Any],
    initial_iter: int,
    retry_iter: int,
    max_attempts: int,
    inject_first_failure: bool,
) -> dict[str, Any]:
    spec = case["spec"]
    bc = generate_bc(spec)
    attempts: list[dict[str, Any]] = []
    current_iter = initial_iter

    for attempt_idx in range(1, max_attempts + 1):
        t0 = time.time()
        result = run_optimization(
            spec=spec,
            bc=bc,
            controller_name="schedule",
            max_iter=current_iter,
            verbose=False,
        )
        elapsed = time.time() - t0
        eval_source = result
        failure_injection = ""
        if inject_first_failure and attempt_idx == 1:
            eval_source = inject_uniform_gray_failure(result, spec.volfrac)
            failure_injection = "uniform_gray_density"
        eval_result = evaluate(eval_source, spec, max_iter=current_iter, use_llm=False, verbose=False)
        failures = core_failures(eval_result)
        attempts.append(
            {
                "attempt": attempt_idx,
                "max_iter": current_iter,
                "elapsed_seconds": elapsed,
                "failure_injection": failure_injection,
                "passed": bool(eval_result.passed),
                "core_failures": failures,
                "rerun_hint": eval_result.rerun_hint,
                "n_iter": result.get("n_iter"),
                "final_compliance": eval_source.get("final_compliance"),
                "best_compliance": eval_source.get("best_compliance"),
                "final_grayness": eval_source.get("final_grayness"),
                "best_grayness": eval_source.get("best_grayness"),
                "checks": check_rows(eval_result),
            }
        )
        if eval_result.passed:
            break
        hinted_iter = None
        if eval_result.rerun_hint:
            hinted_iter = eval_result.rerun_hint.get("max_iter")
        current_iter = max(int(hinted_iter or 0), retry_iter, int(current_iter * 1.5))

    return {
        "case": case["name"],
        "initial_iter": initial_iter,
        "retry_iter_floor": retry_iter,
        "attempts": attempts,
        "initial_passed": attempts[0]["passed"],
        "final_passed": attempts[-1]["passed"],
        "attempts_used": len(attempts),
        "recovered": (not attempts[0]["passed"]) and attempts[-1]["passed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=REVISION_ROOT / "experiment_results_post_solve_retry")
    parser.add_argument("--initial-iter", type=int, default=10)
    parser.add_argument("--retry-iter", type=int, default=80)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--inject-first-failure", action="store_true")
    args = parser.parse_args()

    selected = [case for case in PIPELINE_TEST_CASES if case["name"] in CASE_NAMES]
    selected.extend(EXTRA_RETRY_CASES)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = [
        run_case(case, args.initial_iter, args.retry_iter, args.max_attempts, args.inject_first_failure)
        for case in selected
    ]
    summary = {
        "cases": len(results),
        "initial_failures": sum(not row["initial_passed"] for row in results),
        "recovered": sum(row["recovered"] for row in results),
        "final_passed": sum(row["final_passed"] for row in results),
        "mean_attempts": sum(row["attempts_used"] for row in results) / max(len(results), 1),
        "initial_iter": args.initial_iter,
        "retry_iter_floor": args.retry_iter,
        "failure_injection": "uniform_gray_density" if args.inject_first_failure else None,
    }
    payload = {"summary": summary, "cases": results}
    (args.output_dir / "post_solve_retry_recovery.json").write_text(
        json.dumps(payload, indent=2, default=float),
        encoding="utf-8",
    )

    with (args.output_dir / "post_solve_retry_recovery.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "attempt",
                "max_iter",
                "passed",
                "failure_injection",
                "core_failures",
                "rerun_hint",
                "n_iter",
                "final_compliance",
                "best_compliance",
                "final_grayness",
                "elapsed_seconds",
            ],
        )
        writer.writeheader()
        for result in results:
            for attempt in result["attempts"]:
                writer.writerow(
                    {
                        "case": result["case"],
                        "attempt": attempt["attempt"],
                        "max_iter": attempt["max_iter"],
                        "passed": attempt["passed"],
                        "failure_injection": attempt["failure_injection"],
                        "core_failures": ";".join(attempt["core_failures"]),
                        "rerun_hint": json.dumps(attempt["rerun_hint"], sort_keys=True),
                        "n_iter": attempt["n_iter"],
                        "final_compliance": attempt["final_compliance"],
                        "best_compliance": attempt["best_compliance"],
                        "final_grayness": attempt["final_grayness"],
                        "elapsed_seconds": f"{attempt['elapsed_seconds']:.3f}",
                    }
                )

    lines = [
        "# Post-Solve Retry Recovery Summary",
        "",
        f"- Cases: {summary['cases']}",
        f"- Initial iteration budget: {summary['initial_iter']}",
        f"- Retry iteration floor: {summary['retry_iter_floor']}",
        f"- Failure injection: {summary['failure_injection'] or 'none'}",
        f"- Initial failures: {summary['initial_failures']}/{summary['cases']}",
        f"- Recovered after retry: {summary['recovered']}/{summary['cases']}",
        f"- Final passed: {summary['final_passed']}/{summary['cases']}",
        f"- Mean attempts: {summary['mean_attempts']:.2f}",
        "",
        "## Per Case",
    ]
    for result in results:
        first = result["attempts"][0]
        last = result["attempts"][-1]
        lines.append(
            f"- {result['case']}: first={first['passed']} "
            f"failures={','.join(first['core_failures']) or 'none'}; "
            f"final={last['passed']} attempts={result['attempts_used']}"
        )
    (args.output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
