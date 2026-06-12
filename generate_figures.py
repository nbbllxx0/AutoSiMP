"""
generate_figures.py
-------------------
Re-runs selected problems from Table 1, 2, and 3D experiments and saves
density field visualizations for paper figures.

All runs are deterministic (seed=42, same controllers) so results match
the experiment CSV data exactly.

Usage:
    python generate_figures.py --output-dir paper_figures
    python generate_figures.py --table 2 --output-dir paper_figures   # Table 2 only
    python generate_figures.py --table 3d --output-dir paper_figures  # 3D only
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

from problem_spec import ProblemSpec, EdgeSupport, PointSupport, PointLoad, DistributedLoad, CircularRegion
from bc_generator import generate_bc, spec_to_simp_params
from auto_simp import install_passive_patch, uninstall_passive_patch, save_density_image
from run_experiments import PROBLEM_SET, PIPELINE_TEST_CASES, _make_controller

try:
    from pub_simp_solver import SIMPParams, run_simp
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from pub_simp_solver import SIMPParams, run_simp

from configurator_agent import configure


def solve_and_save(name: str, spec: ProblemSpec, controller_name: str,
                   max_iter: int, seed: int, output_dir: str,
                   tag: str = "") -> dict:
    """Run one problem and save density image + npy."""
    bc = generate_bc(spec)
    controller = _make_controller(controller_name, max_iter, verbose=False)

    kw = spec_to_simp_params(spec)
    kw["max_iter"] = max_iter
    kw["seed"] = seed
    params = SIMPParams(**kw)

    has_passive = bc.passive_mask is not None
    if has_passive:
        install_passive_patch(bc.passive_mask)

    t0 = time.time()
    try:
        result = run_simp(params, callback=controller, verbose=False,
                          bc_override=bc.bc_override)
    finally:
        if has_passive:
            uninstall_passive_patch()

    elapsed = time.time() - t0
    rho = result.get("rho_final", np.array([]))
    C = result.get("final_compliance", 0)
    gray = result.get("final_grayness", 0)

    # Build filename
    fname = f"{name}__{controller_name}"
    if tag:
        fname = f"{name}__{tag}__{controller_name}"

    # Save npy
    if rho.size > 0:
        np.save(os.path.join(output_dir, f"{fname}.npy"), rho)

    # Save PNG (2D only)
    is_3d = spec.is_3d
    if not is_3d and rho.size > 0:
        img_path = os.path.join(output_dir, f"{fname}.png")
        save_density_image(rho, spec.nelx, spec.nely, img_path)

    # Save 3D slice images
    if is_3d and rho.size > 0:
        _save_3d_slices(rho, spec.nelx, spec.nely, spec.nelz,
                        os.path.join(output_dir, fname))

    print(f"  {fname}  C={C:.2f}  gray={gray:.4f}  t={elapsed:.1f}s")
    return result


def _save_3d_slices(rho, nelx, nely, nelz, base_path):
    """Save 3D visualizations: X-ray density projections + marching cubes isosurface."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError:
        return

    R = rho.reshape(nelx, nely, nelz)

    # ── 1. X-ray density projections (mean along each axis) ──────────
    proj_xy = np.mean(R, axis=2)   # view from top (z-axis)
    proj_xz = np.mean(R, axis=1)   # view from front (y-axis)
    proj_yz = np.mean(R, axis=0)   # view from side (x-axis)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, proj, title in zip(axes,
                                [proj_xy, proj_xz, proj_yz],
                                ["XY projection (top)", "XZ projection (front)",
                                 "YZ projection (side)"]):
        ax.imshow(1.0 - proj.T, cmap="gray", origin="lower", vmin=0, vmax=1,
                  aspect="equal")
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    fig.suptitle(os.path.basename(base_path), fontsize=12, y=1.02)
    fig.savefig(f"{base_path}_xray.png", dpi=200, bbox_inches="tight",
                pad_inches=0.1)
    plt.close(fig)

    # ── 2. Marching cubes isosurface render ──────────────────────────
    try:
        from skimage.measure import marching_cubes
    except ImportError:
        try:
            from skimage import measure
            marching_cubes = measure.marching_cubes
        except ImportError:
            return

    # Zero-pad for clean boundary
    padded = np.zeros((nelx + 2, nely + 2, nelz + 2))
    padded[1:-1, 1:-1, 1:-1] = R

    try:
        verts, faces, normals, _ = marching_cubes(padded, level=0.5)
    except Exception:
        return

    # Map vertices to physical aspect ratio
    Lx = nelx  # use element counts as physical dimensions
    Ly = nely
    Lz = nelz
    verts[:, 0] = (verts[:, 0] - 1) * (Lx / nelx)
    verts[:, 1] = (verts[:, 1] - 1) * (Ly / nely)
    verts[:, 2] = (verts[:, 2] - 1) * (Lz / nelz)

    # Render from two angles
    for angle_name, elev, azim in [("front", 30, -60), ("top", 75, -60)]:
        fig = plt.figure(figsize=(10, 6))
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor("white")

        mesh = Poly3DCollection(verts[faces], alpha=0.92)
        mesh.set_facecolor("#5A6068")   # dark steel gray
        mesh.set_edgecolor("#3A3E44")   # darker edge
        mesh.set_linewidth(0.05)
        ax.add_collection3d(mesh)

        ax.set_xlim(0, Lx)
        ax.set_ylim(0, Ly)
        ax.set_zlim(0, Lz)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.view_init(elev=elev, azim=azim)
        ax.set_box_aspect([Lx, Ly, Lz])
        ax.set_title(f"{os.path.basename(base_path)} ({angle_name})",
                     fontsize=11)

        fig.savefig(f"{base_path}_iso_{angle_name}.png", dpi=200,
                    bbox_inches="tight", pad_inches=0.1)
        plt.close(fig)


# ─────────────────────────────────────────────────────────────────────
# Table 1 figures: GT vs LLM-configured side-by-side
# ─────────────────────────────────────────────────────────────────────

TABLE1_CASES = [
    "cantilever_basic", "mbb_beam", "cantilever_with_hole",
    "simply_supported_center", "dual_load", "lbracket", "high_aspect",
]


def generate_table1_figures(output_dir: str, max_iter: int = 300):
    """Generate GT and LLM-configured density images for Table 1."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"Table 1 Figures — GT vs LLM-configured")
    print(f"{'='*60}")

    for case in PIPELINE_TEST_CASES:
        if case["name"] not in TABLE1_CASES:
            continue

        name = case["name"]
        gt_spec = case["spec"]
        prompt = case["prompt"]

        print(f"\n── {name} ──")

        # GT run
        print(f"  GT:")
        solve_and_save(name, gt_spec, "schedule", max_iter, 42,
                       output_dir, tag="gt")

        # LLM-configured run
        config = configure(prompt, verbose=False)
        if config.llm_used:
            print(f"  LLM-configured:")
            solve_and_save(name, config.spec, "schedule", max_iter, 42,
                           output_dir, tag="llm")
        else:
            print(f"  [SKIP] No LLM — using GT as fallback")
            solve_and_save(name, gt_spec, "schedule", max_iter, 42,
                           output_dir, tag="llm_fallback")


# ─────────────────────────────────────────────────────────────────────
# Table 2 figures: controller comparison on representative problems
# ─────────────────────────────────────────────────────────────────────

TABLE2_PROBLEMS = [
    "cantilever_60x30", "mbb_90x30", "bridge_120x30",
    "cantilever_hole", "cantilever_6to1", "lbracket_60x60",
]

TABLE2_CONTROLLERS = ["llm", "schedule", "expert", "tail_only", "fixed"]


def generate_table2_figures(output_dir: str, max_iter: int = 300):
    """Generate density images for Table 2 comparison grid."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"Table 2 Figures — Controller comparison")
    print(f"{'='*60}")

    for prob_name in TABLE2_PROBLEMS:
        spec = PROBLEM_SET[prob_name]
        print(f"\n── {prob_name} ──")

        for ctrl in TABLE2_CONTROLLERS:
            solve_and_save(prob_name, spec, ctrl, max_iter, 42, output_dir)


# ─────────────────────────────────────────────────────────────────────
# 3D figures: slice visualizations
# ─────────────────────────────────────────────────────────────────────

TABLE3D_PROBLEMS = ["cantilever_3d", "mbb_3d"]
TABLE3D_CONTROLLERS = ["llm", "schedule", "tail_only", "fixed"]


def generate_3d_figures(output_dir: str, max_iter: int = 300):
    """Generate 3D slice images."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"3D Figures — Slice visualizations")
    print(f"{'='*60}")

    for prob_name in TABLE3D_PROBLEMS:
        spec = PROBLEM_SET[prob_name]
        print(f"\n── {prob_name} ──")

        for ctrl in TABLE3D_CONTROLLERS:
            solve_and_save(prob_name, spec, ctrl, max_iter, 42, output_dir)


# ─────────────────────────────────────────────────────────────────────
# Compliance history plot
# ─────────────────────────────────────────────────────────────────────

def generate_convergence_plot(output_dir: str, max_iter: int = 300):
    """Generate compliance convergence plots for a representative problem."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping convergence plot")
        return

    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"Convergence Plots")
    print(f"{'='*60}")

    spec = PROBLEM_SET["cantilever_60x30"]
    bc = generate_bc(spec)

    histories = {}
    for ctrl_name in ["llm", "schedule", "expert", "tail_only", "fixed"]:
        controller = _make_controller(ctrl_name, max_iter, verbose=False)
        kw = spec_to_simp_params(spec)
        kw["max_iter"] = max_iter
        kw["seed"] = 42
        params = SIMPParams(**kw)

        print(f"  Running {ctrl_name}...", end="", flush=True)
        t0 = time.time()
        result = run_simp(params, callback=controller, verbose=False,
                          bc_override=bc.bc_override)
        print(f" {time.time()-t0:.1f}s")
        histories[ctrl_name] = result["compliance_history"]

    # Plot — two panels: (a) active controllers zoomed in, (b) all controllers log scale
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))
    colors = {
        "llm": "#2471a3", "schedule": "#c0392b", "expert": "#1e8449",
        "tail_only": "#784212", "fixed": "#7f8c8d",
    }
    labels = {
        "llm": "LLM agent", "schedule": "Schedule", "expert": "Expert",
        "tail_only": "Tail-only", "fixed": "Fixed (no cont.)",
    }

    # Panel (a): active controllers only, linear scale, zoomed
    for name in ["llm", "schedule", "expert", "fixed"]:
        hist = histories[name]
        ax1.plot(hist, color=colors[name], label=labels[name],
                 linewidth=2.0 if name == "llm" else 1.2,
                 alpha=1.0 if name == "llm" else 0.7)
    ax1.set_xlabel("Iteration", fontsize=12)
    ax1.set_ylabel("Compliance", fontsize=12)
    ax1.set_title("(a) Active controllers", fontsize=13)
    ax1.legend(fontsize=10, loc="upper right")
    ax1.set_xlim(0, len(max(histories.values(), key=len)))
    ax1.set_ylim(50, 250)
    ax1.grid(True, alpha=0.3)

    # Panel (b): all controllers, log scale
    for name, hist in histories.items():
        ax2.semilogy(hist, color=colors[name], label=labels[name],
                     linewidth=2.0 if name == "llm" else 1.2,
                     alpha=1.0 if name in ("llm", "tail_only") else 0.7)
    ax2.set_xlabel("Iteration", fontsize=12)
    ax2.set_ylabel("Compliance (log scale)", fontsize=12)
    ax2.set_title("(b) All controllers including tail-only", fontsize=13)
    ax2.legend(fontsize=10, loc="upper right")
    ax2.set_xlim(0, len(max(histories.values(), key=len)))
    ax2.grid(True, alpha=0.3, which="both")

    fig.suptitle("Convergence: cantilever 60×30, vf=0.5", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "convergence_cantilever.png"),
                dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, "convergence_cantilever.pdf"),
                bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved convergence plot")


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate paper figures for AutoSIMP")
    parser.add_argument("--output-dir", type=str, default="paper_figures")
    parser.add_argument("--max-iter", type=int, default=300)
    parser.add_argument("--table", type=str, default="all",
                        choices=["all", "1", "2", "3d", "convergence"],
                        help="Which table's figures to generate")
    args = parser.parse_args()

    if args.table in ("all", "1"):
        generate_table1_figures(
            os.path.join(args.output_dir, "table1"), args.max_iter)

    if args.table in ("all", "2"):
        generate_table2_figures(
            os.path.join(args.output_dir, "table2"), args.max_iter)

    if args.table in ("all", "3d"):
        generate_3d_figures(
            os.path.join(args.output_dir, "table3d"), args.max_iter)

    if args.table in ("all", "convergence"):
        generate_convergence_plot(
            os.path.join(args.output_dir, "convergence"), args.max_iter)

    print(f"\n{'='*60}")
    print(f"All figures saved to {args.output_dir}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()