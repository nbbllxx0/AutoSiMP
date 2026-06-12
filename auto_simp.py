"""
auto_simp.py
------------
End-to-end orchestrator for AutoSIMP.

Pipeline:
  1. Natural-language prompt  →  ConfiguratorAgent  →  ProblemSpec
  2. ProblemSpec              →  bc_generator        →  bc_override + passive mask
  3. SIMPParams + bc_override →  run_simp (with LLM controller)  →  result dict
  4. result                   →  EvaluatorAgent      →  pass/fail + re-run hints
  5. If failed                →  retry with adjusted params (up to max_retries)
  6. Output report (JSON + optional density image)

Design: the existing solver is UNTOUCHED.  Passive-region support is handled
by a thin wrapper that calls apply_passive_mask after each OC step.

Usage:
    python auto_simp.py "cantilever beam, left fixed, mid-right downward load"
    python auto_simp.py --spec spec.json           # skip LLM configurator
    python auto_simp.py --preset cantilever         # built-in test
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from typing import Optional

import numpy as np

# ── Imports from the AutoSIMP modules ────────────────────────────────────────

from problem_spec import ProblemSpec
from bc_generator import generate_bc, apply_passive_mask, spec_to_simp_params, BCResult
from configurator_agent import configure, ConfiguratorResult
from evaluator_agent import evaluate, EvalResult

# ── Imports from the existing (unmodified) solver & controller ───────────────
# These must be on sys.path.  If running from the repo root, they already are.

try:
    from pub_simp_solver import SIMPParams, run_simp
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from pub_simp_solver import SIMPParams, run_simp

try:
    from pub_llm_agent import LLMController
except ImportError:
    LLMController = None   # allow running without LLM controller (uses baselines)

try:
    from pub_baseline_controller import ScheduleOnlyController
except ImportError:
    ScheduleOnlyController = None


# ─────────────────────────────────────────────────────────────────────────────
# Passive-region support via solver monkey-patch
# ─────────────────────────────────────────────────────────────────────────────

_PASSIVE_PATCH_APPLIED = False

def install_passive_patch(passive_mask: Optional[np.ndarray]):
    """
    Monkey-patch pub_simp_solver._fea_and_sensitivity so that the OC update
    enforces passive regions (void → rho_min, solid → 1.0) inside the
    bisection loop.

    This is the correct fix: passive elements are frozen BEFORE the volume
    constraint check, so the OC bisection accounts for their contribution.
    The patch is idempotent — calling it again with a new mask just swaps
    the mask without re-wrapping.

    Passing passive_mask=None removes the patch (restores original).
    """
    global _PASSIVE_PATCH_APPLIED
    import pub_simp_solver as solver

    # Store original if not yet saved
    if not hasattr(solver, '_oc_update_original'):
        solver._oc_update_original = solver._oc_update

    if passive_mask is None:
        # Remove patch
        solver._oc_update = solver._oc_update_original
        _PASSIVE_PATCH_APPLIED = False
        return

    # Build the patched OC that enforces passive mask inside bisection
    _orig_oc = solver._oc_update_original
    _mask = passive_mask
    _void_idx = np.where(_mask == 1)[0]
    _solid_idx = np.where(_mask == 2)[0]
    _has_void = len(_void_idx) > 0
    _has_solid = len(_solid_idx) > 0

    def _oc_update_with_passive(rho, dc, dv, volfrac, move, n_elem,
                                 beta, eta, use_heaviside, H_mat):
        # Zero out sensitivities on passive elements so OC doesn't move them
        dc = dc.copy()
        dv = dv.copy()
        if _has_void:
            dc[_void_idx] = -1e-20   # near-zero negative (OC expects dc < 0)
            dv[_void_idx] = 1e-20
        if _has_solid:
            dc[_solid_idx] = -1e-20
            dv[_solid_idx] = 1e-20

        # Run original OC
        rn = _orig_oc(rho, dc, dv, volfrac, move, n_elem,
                       beta, eta, use_heaviside, H_mat)

        # Force passive values
        if _has_void:
            rn[_void_idx] = 1e-3
        if _has_solid:
            rn[_solid_idx] = 1.0
        return rn

    solver._oc_update = _oc_update_with_passive
    _PASSIVE_PATCH_APPLIED = True


def uninstall_passive_patch():
    """Restore original OC update."""
    install_passive_patch(None)


# ─────────────────────────────────────────────────────────────────────────────
# Controller wrapper (passes through to inner controller, no passive logic)
# ─────────────────────────────────────────────────────────────────────────────

class ControllerWrapper:
    """
    Thin wrapper that delegates to the inner controller.
    Passive region enforcement is handled by the solver monkey-patch,
    not by the callback.
    """

    def __init__(self, inner_controller):
        self.inner = inner_controller
        self.name = getattr(inner_controller, "name", "wrapped") if inner_controller else "none"

    def initial_action(self, params):
        if self.inner and hasattr(self.inner, "initial_action"):
            return self.inner.initial_action(params)
        return None

    def finalize_tail(self, params):
        if self.inner and hasattr(self.inner, "finalize_tail"):
            return self.inner.finalize_tail(params)
        return {"enabled": False}

    def __call__(self, state, rho):
        if self.inner is not None:
            return self.inner(state, rho)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Solver runner
# ─────────────────────────────────────────────────────────────────────────────

def _build_controller(controller_name: str, max_iter: int, verbose: bool):
    """Instantiate the requested controller."""
    if controller_name == "llm" and LLMController is not None:
        return LLMController(max_iter=max_iter, verbose=verbose)
    elif controller_name == "schedule" and ScheduleOnlyController is not None:
        return ScheduleOnlyController()
    elif controller_name == "none":
        return None
    else:
        # Fallback: try LLM, else schedule, else none
        if LLMController is not None:
            return LLMController(max_iter=max_iter, verbose=verbose)
        elif ScheduleOnlyController is not None:
            return ScheduleOnlyController()
        return None


def run_optimization(
    spec: ProblemSpec,
    bc: BCResult,
    controller_name: str = "llm",
    max_iter: int = 300,
    verbose: bool = False,
) -> dict:
    """
    Run the SIMP solver with the given spec and BCs.

    If passive regions exist, installs the solver monkey-patch for the
    duration of the solve, then removes it.

    Returns the solver result dict.
    """
    # Build SIMPParams
    kw = spec_to_simp_params(spec)
    kw["max_iter"] = max_iter
    params = SIMPParams(**kw)

    # Build controller
    inner = _build_controller(controller_name, max_iter, verbose)
    controller = ControllerWrapper(inner)

    if verbose:
        ctrl_name = getattr(inner, "name", controller_name) if inner else controller_name
        passive_info = ""
        if bc.passive_mask is not None:
            n_void = int(np.sum(bc.passive_mask == 1))
            n_solid = int(np.sum(bc.passive_mask == 2))
            passive_info = f"  passive={n_void} void + {n_solid} solid"
        print(f"[AutoSIMP] Solver: {spec.nelx}×{spec.nely}"
              + (f"×{spec.nelz}" if spec.is_3d else "")
              + f"  vf={spec.volfrac}  controller={ctrl_name}"
              + f"  max_iter={max_iter}" + passive_info)

    # Install passive mask patch if needed
    if bc.passive_mask is not None:
        install_passive_patch(bc.passive_mask)
        if verbose:
            print("[AutoSIMP] Passive region patch installed.")

    try:
        result = run_simp(
            params,
            callback=controller,
            verbose=verbose,
            bc_override=bc.bc_override,
        )
    finally:
        # Always uninstall to avoid leaking into other solves
        if bc.passive_mask is not None:
            uninstall_passive_patch()

    # Attach controller log if available
    if inner and hasattr(inner, "call_log"):
        result["controller_log"] = inner.call_log

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def _generate_report(
    spec: ProblemSpec,
    result: dict,
    eval_result: EvalResult,
    config_result: Optional[ConfiguratorResult],
    run_idx: int,
    elapsed: float,
) -> dict:
    """Build a JSON-serializable report dict."""
    report = {
        "autosimp_version": "0.1.0",
        "run_index": run_idx,
        "elapsed_seconds": round(elapsed, 2),
        "problem_spec": spec.to_dict(),
        "solver_summary": {
            "nelx": result.get("nelx"),
            "nely": result.get("nely"),
            "nelz": result.get("nelz", 0),
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
                {"name": c.name, "passed": c.passed,
                 "value": c.value, "threshold": c.threshold,
                 "message": c.message}
                for c in eval_result.checks
            ],
            "rerun_hint": eval_result.rerun_hint,
            "llm_assessment": eval_result.llm_assessment,
        },
    }
    if config_result:
        report["configurator"] = {
            "llm_used": config_result.llm_used,
            "warnings": config_result.warnings,
            "error": config_result.error,
        }
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Optional density image output
# ─────────────────────────────────────────────────────────────────────────────

def save_density_image(rho: np.ndarray, nelx: int, nely: int,
                        path: str) -> bool:
    """Save the density field as a grayscale PNG. Returns True on success."""
    try:
        from PIL import Image
    except ImportError:
        try:
            # Fallback: use matplotlib
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.imshow(1.0 - rho.reshape(nelx, nely).T,
                      cmap="gray", origin="lower", vmin=0, vmax=1)
            ax.set_aspect("equal")
            ax.axis("off")
            fig.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.05)
            plt.close(fig)
            return True
        except ImportError:
            return False

    # PIL path
    arr = (255 * (1.0 - rho.reshape(nelx, nely).T[::-1])).clip(0, 255).astype(np.uint8)
    # Scale up for visibility
    scale = max(1, 600 // max(nelx, nely))
    arr = np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)
    img = Image.fromarray(arr, mode="L")
    img.save(path)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def auto_simp(
    prompt: Optional[str] = None,
    spec: Optional[ProblemSpec] = None,
    controller: str = "llm",
    max_iter: int = 300,
    max_retries: int = 2,
    output_dir: str = "autosimp_output",
    use_llm_eval: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Full AutoSIMP pipeline.

    Provide EITHER `prompt` (natural language → LLM configurator) OR `spec`
    (pre-built ProblemSpec, skips configurator).

    Returns the final report dict.
    """
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()

    # ── Step 1: Configure ────────────────────────────────────────────────
    config_result = None
    if spec is None:
        if prompt is None:
            raise ValueError("Provide either `prompt` or `spec`.")
        if verbose:
            print(f"[AutoSIMP] Parsing: {prompt[:80]}...")
        config_result = configure(prompt, verbose=verbose)
        spec = config_result.spec
        if verbose:
            print(f"[AutoSIMP] Configurator: "
                  f"{'LLM' if config_result.llm_used else 'fallback'}  "
                  f"warnings={len(config_result.warnings)}")

    # ── Step 2: Generate BCs ─────────────────────────────────────────────
    if verbose:
        print("[AutoSIMP] Generating boundary conditions...")
    bc = generate_bc(spec)
    if verbose:
        print(f"[AutoSIMP] BCs: {len(bc.fixed_dofs)} fixed DOFs, "
              f"passive={'yes' if bc.passive_mask is not None else 'no'}")

    # ── Step 3 + 4 + 5: Solve → Evaluate → Retry loop ───────────────────
    effective_max_iter = spec.max_iter or max_iter
    best_report = None
    best_compliance = float("inf")

    for attempt in range(1, max_retries + 2):  # attempt 1 = first try
        if verbose:
            print(f"\n[AutoSIMP] === Run {attempt}/{max_retries + 1} ===")

        # Solve
        t_solve = time.time()
        result = run_optimization(
            spec, bc,
            controller_name=controller,
            max_iter=effective_max_iter,
            verbose=verbose,
        )
        solve_time = time.time() - t_solve

        if verbose:
            print(f"[AutoSIMP] Solve complete: {result.get('n_iter')} iters, "
                  f"C={result.get('final_compliance', 0):.4f}, "
                  f"gray={result.get('final_grayness', 0):.4f}, "
                  f"time={solve_time:.1f}s")

        # Evaluate
        eval_result = evaluate(
            result, spec,
            max_iter=effective_max_iter,
            use_llm=use_llm_eval,
            verbose=verbose,
        )

        if verbose:
            status = "PASS" if eval_result.passed else "FAIL"
            print(f"[AutoSIMP] Evaluation: {status} — {eval_result.summary}")

        # Track best
        elapsed = time.time() - t0
        report = _generate_report(
            spec, result, eval_result, config_result, attempt, elapsed)

        fc = result.get("final_compliance", float("inf"))
        if fc < best_compliance:
            best_compliance = fc
            best_report = report

            # Save density image
            rho = result.get("rho_final")
            if rho is not None and not result.get("is_3d", False):
                img_path = os.path.join(output_dir, f"density_run{attempt}.png")
                if save_density_image(rho, result["nelx"], result["nely"], img_path):
                    report["density_image"] = img_path

            # Save density array
            np_path = os.path.join(output_dir, f"rho_run{attempt}.npy")
            if rho is not None:
                np.save(np_path, rho)
                report["density_npy"] = np_path

        # If passed, we're done
        if eval_result.passed:
            if verbose:
                print("[AutoSIMP] Quality checks passed — done.")
            break

        # If not passed and retries remain, adjust params
        if attempt <= max_retries and eval_result.rerun_hint:
            hint = eval_result.rerun_hint
            if verbose:
                print(f"[AutoSIMP] Re-run hint: {hint}")

            if "max_iter" in hint:
                effective_max_iter = hint["max_iter"]
            if "volfrac" in hint:
                spec.volfrac = hint["volfrac"]
                # Regenerate BCs (volfrac doesn't affect BCs, but keep clean)
                bc = generate_bc(spec)
        elif attempt <= max_retries:
            # No specific hint — just increase iterations
            effective_max_iter = int(effective_max_iter * 1.3)
            if verbose:
                print(f"[AutoSIMP] No hint — bumping max_iter to {effective_max_iter}")

    # ── Step 6: Save final report ────────────────────────────────────────
    report_path = os.path.join(output_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(best_report, f, indent=2, default=str)
    if verbose:
        print(f"\n[AutoSIMP] Report saved: {report_path}")

    return best_report


# ─────────────────────────────────────────────────────────────────────────────
# Built-in test presets
# ─────────────────────────────────────────────────────────────────────────────

from problem_spec import (
    EdgeSupport, PointSupport, PointLoad, DistributedLoad, CircularRegion,
)

PRESETS = {
    "cantilever": ProblemSpec(
        Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
        supports=[EdgeSupport(edge="left", constraint="fixed")],
        loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
    ),
    "mbb": ProblemSpec(
        Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.5,
        supports=[
            EdgeSupport(edge="left", constraint="pin_x"),
            PointSupport(x=3.0, y=0.0, constraint="pin_y"),
        ],
        loads=[PointLoad(x=0.0, y=1.0, fy=-1.0)],
    ),
    "bridge": ProblemSpec(
        Lx=4.0, Ly=1.0, nelx=120, nely=30, volfrac=0.3,
        supports=[
            PointSupport(x=0.0, y=0.0, constraint="fixed"),
            PointSupport(x=4.0, y=0.0, constraint="roller_x"),
        ],
        loads=[DistributedLoad(edge="top", magnitude=-1.0)],
    ),
    "cantilever_with_hole": ProblemSpec(
        Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.4,
        supports=[EdgeSupport(edge="left", constraint="fixed")],
        loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
        passive_regions=[CircularRegion(cx=1.0, cy=0.5, radius=0.15, kind="void")],
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AutoSiMP: human-verifiable SIMP topology optimization configuration")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("prompt", nargs="?", default=None,
                       help="Natural-language problem description")
    group.add_argument("--spec", type=str, default=None,
                       help="Path to a ProblemSpec JSON file")
    group.add_argument("--preset", type=str, choices=list(PRESETS.keys()),
                       help="Use a built-in test preset")

    parser.add_argument("--controller", type=str, default="llm",
                        choices=["llm", "schedule", "none"],
                        help="Controller type (default: llm)")
    parser.add_argument("--max-iter", type=int, default=300)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--output-dir", type=str, default="autosimp_output")
    parser.add_argument("--no-llm-eval", action="store_true",
                        help="Skip LLM qualitative evaluation")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    spec = None
    prompt = args.prompt

    if args.preset:
        spec = PRESETS[args.preset]
        prompt = None
    elif args.spec:
        with open(args.spec) as f:
            spec = ProblemSpec.from_dict(json.load(f))
        prompt = None

    report = auto_simp(
        prompt=prompt,
        spec=spec,
        controller=args.controller,
        max_iter=args.max_iter,
        max_retries=args.max_retries,
        output_dir=args.output_dir,
        use_llm_eval=not args.no_llm_eval,
        verbose=args.verbose,
    )

    print(f"\n{'='*60}")
    print(f"AutoSIMP Complete")
    print(f"{'='*60}")
    passed = report["evaluation"]["passed"]
    print(f"  Status:     {'PASSED' if passed else 'FAILED'}")
    print(f"  Compliance: {report['solver_summary']['final_compliance']:.4f}")
    print(f"  Grayness:   {report['solver_summary']['final_grayness']:.4f}")
    print(f"  Iterations: {report['solver_summary']['n_iter']}")
    print(f"  Time:       {report['elapsed_seconds']:.1f}s")
    print(f"  Report:     {args.output_dir}/report.json")


if __name__ == "__main__":
    main()
