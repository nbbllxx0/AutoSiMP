"""E12: bounded NL→3-D configuration track.

Own 10-field denominator (nine 2-D _match keys + Lz_match).
Never merge counts into the 90/900 2-D totals.
Does not patch revision_experiments.compare_specs.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

IMPL = Path(__file__).resolve().parents[1]
DIAG = IMPL / "reproducibility" / "diagnostic_suite"
OUT = IMPL / "results"
FIG = OUT
MODEL = "gemini-3.1-flash-lite"
N_REPEATS = 3

sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(DIAG))

from configurator_agent import configure  # noqa: E402
from problem_spec import (  # noqa: E402
    DistributedLoad,
    EdgeSupport,
    PointLoad,
    PointSupport,
    ProblemSpec,
)
from revision_experiments import compare_specs  # noqa: E402

MATCH_KEYS_2D = (
    "Lx_match",
    "Ly_match",
    "volfrac_match",
    "n_supports_match",
    "n_loads_match",
    "n_passive_match",
    "support_semantics_match",
    "load_semantics_match",
    "passive_semantics_match",
)
MATCH_KEYS_3D = MATCH_KEYS_2D + ("Lz_match",)


def load_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def compare_specs_3d(gt: ProblemSpec, test: ProblemSpec) -> dict:
    """Ten scored fields. Z enters Lz_match and the 3-D-aware signatures.

    The 2-D compare_specs load/support signatures drop z; using them here would
    false-pass a z-mismatch. This wrapper does not modify that function.
    """
    base = compare_specs(gt, test)

    def support_sig(s):
        if isinstance(s, EdgeSupport):
            return ("edge", s.edge, s.constraint)
        return ("point", round(s.x, 2), round(s.y, 2), round(s.z, 2), s.constraint)

    def load_sig(load):
        if isinstance(load, DistributedLoad):
            return ("distributed", load.edge, round(load.magnitude, 2))
        return (
            "point",
            round(load.x, 2),
            round(load.y, 2),
            round(load.z, 2),
            math.copysign(1, load.fx) if abs(load.fx) > 1e-9 else 0,
            math.copysign(1, load.fy) if abs(load.fy) > 1e-9 else 0,
            math.copysign(1, load.fz) if abs(load.fz) > 1e-9 else 0,
        )

    gt_s = sorted(support_sig(s) for s in gt.supports)
    te_s = sorted(support_sig(s) for s in test.supports)
    gt_l = sorted(load_sig(load) for load in gt.loads)
    te_l = sorted(load_sig(load) for load in test.loads)
    out = {k: base[k] for k in MATCH_KEYS_2D}
    out["support_semantics_match"] = gt_s == te_s
    out["load_semantics_match"] = gt_l == te_l
    out["Lz_match"] = abs(gt.Lz - test.Lz) < 0.05
    out["nelz_reasonable"] = (
        gt.nelz > 0 and 0.5 <= test.nelz / max(gt.nelz, 1) <= 2.0
    )
    n_fields = sum(1 for k in out if k.endswith("_match"))
    if n_fields != 10:
        raise RuntimeError(f"expected 10 _match keys, got {n_fields}: {list(out)}")
    out["n_match"] = sum(1 for k in MATCH_KEYS_3D if out[k])
    out["n_fields"] = 10
    return out


def spec_to_jsonable(spec: ProblemSpec) -> dict:
    return spec.to_dict()


CASES = [
    {
        "name": "cantilever_3d",
        "prompt": (
            "Three-dimensional cantilever, 2 units long, 1 unit tall, 0.5 units thick. "
            "The left face is fully fixed. Apply a downward point load at the midpoint "
            "of the right face. Use 40% material."
        ),
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, Lz=0.5, nelx=30, nely=15, nelz=8, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, z=0.25, fy=-1.0)],
        ),
    },
    {
        "name": "cantilever_3d_zload",
        "prompt": (
            "A 3-D rectangular cantilever 2 by 1 by 0.5. Clamp the entire left face. "
            "Apply a point load in the negative z direction at the free-end midpoint "
            "(x=2, y=0.5, z=0.25). Volume fraction 0.30."
        ),
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, Lz=0.5, nelx=30, nely=15, nelz=8, volfrac=0.3,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, z=0.25, fz=-1.0)],
        ),
    },
    {
        "name": "mbb_3d",
        "prompt": (
            "Three-dimensional MBB beam, 3 units long, 1 unit tall, 0.5 units thick. "
            "Left face is a symmetry pin in x. Roller pin_y at the bottom-right corner "
            "at mid-thickness. Downward load at the top-left corner, mid-thickness. "
            "Half material."
        ),
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, Lz=0.5, nelx=45, nely=15, nelz=8, volfrac=0.5,
            supports=[
                EdgeSupport(edge="left", constraint="pin_x"),
                PointSupport(x=3.0, y=0.0, z=0.25, constraint="pin_y"),
            ],
            loads=[PointLoad(x=0.0, y=1.0, z=0.25, fy=-1.0)],
        ),
    },
    {
        "name": "bridge_3d",
        "prompt": (
            "A 3-D bridge box 4 meters long, 1 meter tall, 0.5 meters thick. "
            "The bottom face is supported vertically (pin_y). Uniform downward "
            "pressure on the top face. Use 30 percent material."
        ),
        "spec": ProblemSpec(
            Lx=4.0, Ly=1.0, Lz=0.5, nelx=60, nely=15, nelz=8, volfrac=0.3,
            supports=[EdgeSupport(edge="bottom", constraint="pin_y")],
            loads=[DistributedLoad(edge="top", magnitude=-1.0)],
        ),
    },
    {
        "name": "deep_cantilever_3d",
        "prompt": (
            "Short deep 3-D cantilever: 1 unit long, 2 units tall, 0.5 units thick. "
            "Left face clamped. Downward point load at the midpoint of the right face. "
            "50 percent material."
        ),
        "spec": ProblemSpec(
            Lx=1.0, Ly=2.0, Lz=0.5, nelx=15, nely=30, nelz=8, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=1.0, y=1.0, z=0.25, fy=-1.0)],
        ),
    },
    {
        "name": "slender_cantilever_3d",
        "prompt": (
            "Slender three-dimensional cantilever, 6 units long, 1 unit tall, "
            "0.5 units thick. West face fully fixed. Downward free-end load at "
            "mid-height and mid-thickness. Volume fraction 0.4."
        ),
        "spec": ProblemSpec(
            Lx=6.0, Ly=1.0, Lz=0.5, nelx=90, nely=15, nelz=8, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=6.0, y=0.5, z=0.25, fy=-1.0)],
        ),
    },
    {
        "name": "simply_supported_3d",
        "prompt": (
            "A 3-D simply supported box 3 by 1 by 0.5. Vertical pin supports at both "
            "bottom corners at mid-thickness. Downward point load at the top-center, "
            "mid-thickness. Use 40% material."
        ),
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, Lz=0.5, nelx=45, nely=15, nelz=8, volfrac=0.4,
            supports=[
                PointSupport(x=0.0, y=0.0, z=0.25, constraint="pin_y"),
                PointSupport(x=3.0, y=0.0, z=0.25, constraint="pin_y"),
            ],
            loads=[PointLoad(x=1.5, y=1.0, z=0.25, fy=-1.0)],
        ),
    },
    {
        "name": "dual_load_3d",
        "prompt": (
            "Three-dimensional left-clamped box 2 by 1 by 0.5. Two downward point "
            "loads on the right face, one at the upper-right mid-thickness and one "
            "at the lower-right mid-thickness. Volume fraction 0.5."
        ),
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, Lz=0.5, nelx=30, nely=15, nelz=8, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[
                PointLoad(x=2.0, y=1.0, z=0.25, fy=-1.0),
                PointLoad(x=2.0, y=0.0, z=0.25, fy=-1.0),
            ],
        ),
    },
]


def majority_fields(rows: list[dict]) -> dict:
    out = {}
    for k in MATCH_KEYS_3D:
        votes = [bool(r["cmp"][k]) for r in rows if r.get("cmp")]
        out[k] = (sum(votes) >= (len(votes) / 2.0)) if votes else False
    out["n_match"] = sum(1 for k in MATCH_KEYS_3D if out[k])
    out["n_fields"] = 10
    return out


def solve_configured(spec: ProblemSpec, tag: str) -> dict:
    from dataclasses import replace

    from auto_simp import run_optimization
    from bc_generator import generate_bc
    from matplotlib import pyplot as plt

    spec = replace(spec, nelx=30, nely=15, nelz=8)
    bc = generate_bc(spec)
    result = run_optimization(
        spec, bc, controller_name="schedule", max_iter=80, verbose=False
    )
    rho = np.asarray(result.get("rho_final", result.get("best_rho")), dtype=float)
    if rho.size == spec.nelx * spec.nely * spec.nelz:
        rho3 = rho.reshape((spec.nelx, spec.nely, spec.nelz), order="F")
    else:
        rho3 = rho.reshape((spec.nelx, spec.nely, spec.nelz))
    npy_path = OUT / f"e12_{tag}_rho.npy"
    np.save(npy_path, rho3)
    mid = rho3[:, :, spec.nelz // 2]
    fig, ax = plt.subplots(figsize=(5.2, 2.6), dpi=200)
    ax.imshow(mid.T, origin="lower", cmap="binary_r", vmin=0, vmax=1, aspect="equal")
    ax.set_title(
        f"{tag} mid-z slice, 30×15×8, schedule, 80 iter, C={result.get('final_compliance')}"
    )
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    png = FIG / f"fig_e12_{tag}_midz.png"
    pdf = FIG / f"fig_e12_{tag}_midz.pdf"
    fig.savefig(png, dpi=600)
    fig.savefig(pdf)
    plt.close(fig)
    return {
        "tag": tag,
        "nel": [spec.nelx, spec.nely, spec.nelz],
        "n_elem": int(spec.nelx * spec.nely * spec.nelz),
        "final_compliance": result.get("final_compliance"),
        "best_compliance": result.get("best_compliance"),
        "n_iter": result.get("n_iter"),
        "npy": str(npy_path),
        "figure_png": str(png),
        "figure_pdf": str(pdf),
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    cases_json = []
    for c in CASES:
        cases_json.append(
            {
                "name": c["name"],
                "prompt": c["prompt"],
                "reference_spec": spec_to_jsonable(c["spec"]),
            }
        )
    (OUT / "e12_cases.json").write_text(
        json.dumps(cases_json, indent=2), encoding="utf-8"
    )

    key = load_key()
    if not key:
        raise SystemExit("E12 aborted: no API key (env or correct-key file).")
    os.environ["GEMINI_API_KEY"] = key

    per_case = []
    n_api_fail = 0
    n_calls = 0
    for c in CASES:
        gt = c["spec"]
        repeats = []
        for r in range(N_REPEATS):
            n_calls += 1
            cr = configure(c["prompt"], api_key=key, model=MODEL)
            row = {
                "repeat": r,
                "llm_used": bool(getattr(cr, "llm_used", False)),
                "error": getattr(cr, "error", None),
            }
            spec = getattr(cr, "spec", None)
            if not row["llm_used"] or spec is None:
                n_api_fail += 1
                row["cmp"] = None
                row["n_match"] = None
            else:
                cmp = compare_specs_3d(gt, spec)
                row["cmp"] = {k: bool(cmp[k]) for k in list(MATCH_KEYS_3D) + ["nelz_reasonable"]}
                row["n_match"] = cmp["n_match"]
                row["configured"] = spec.to_dict()
            repeats.append(row)
            print(c["name"], r, row["n_match"], flush=True)
        scored = [x for x in repeats if x.get("cmp")]
        if not scored:
            maj = None
            n_match = None
        else:
            maj = majority_fields(scored)
            n_match = maj["n_match"]
        per_case.append(
            {
                "name": c["name"],
                "prompt": c["prompt"],
                "n_match": n_match,
                "n_fields": 10,
                "majority": maj,
                "repeats": repeats,
            }
        )

    valid = [p for p in per_case if p["n_match"] is not None]
    total_match = sum(p["n_match"] for p in valid)
    total_fields = 10 * len(valid)
    summary = {
        "started_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL,
        "n_prompts": len(CASES),
        "n_repeats": N_REPEATS,
        "n_calls": n_calls,
        "api_failure": n_api_fail,
        "scored_keys": list(MATCH_KEYS_3D),
        "denominator": f"{total_match}/{total_fields}" if valid else None,
        "n_exact_10of10": sum(1 for p in valid if p["n_match"] == 10),
        "per_case": [{"name": p["name"], "n_match": p["n_match"]} for p in per_case],
        "note": "Own 10-field denominator. Never merged with 90/900 2-D totals.",
        "rectangular_domain_limit": True,
    }
    (OUT / "e12_results.json").write_text(
        json.dumps({"summary": summary, "cases": per_case}, indent=2, default=str),
        encoding="utf-8",
    )
    print("checkpoint", summary["denominator"], flush=True)

    solve_info = None
    pick = next(
        (p for p in per_case if p["name"] == "cantilever_3d" and p.get("n_match") is not None),
        None,
    )
    if pick is not None:
        cfg = None
        for r in pick["repeats"]:
            if r.get("configured"):
                cfg = ProblemSpec.from_dict(r["configured"])
                break
        if cfg is not None and cfg.is_3d:
            try:
                solve_info = solve_configured(cfg, "cantilever_3d")
            except Exception as exc:
                solve_info = {"error": str(exc)}
    summary["solve"] = solve_info

    bundle = {"summary": summary, "cases": per_case}
    (OUT / "e12_results.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    lines = [
        "# E12 NL→3-D configuration",
        "",
        f"- model: `{MODEL}` temperature 0, {N_REPEATS} repeats, field-wise majority",
        f"- denominator: {summary['denominator']} (10 fields × {len(valid)} scored prompts)",
        f"- exact 10/10: {summary['n_exact_10of10']}/{len(valid)}",
        f"- api_failure: {n_api_fail}/{n_calls}",
        "- not merged with 90/900 2-D totals",
        "- a 3-D box remains a rectangular domain",
        "",
        "| case | majority |",
        "|---|---|",
    ]
    for p in per_case:
        cell = "api_failure" if p["n_match"] is None else f"{p['n_match']}/10"
        lines.append(f"| `{p['name']}` | {cell} |")
    if solve_info:
        lines += ["", "## Configured solve", json.dumps(solve_info, indent=2, default=str)]
    (OUT / "e12_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("E12", summary["denominator"], "exact", summary["n_exact_10of10"], flush=True)


if __name__ == "__main__":
    main()
