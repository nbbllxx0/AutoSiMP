from __future__ import annotations

import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNS = HERE / "results_3d_large" / "runs"
OUT_DIR = HERE / "results_3d_large"

CASES = [
    "cantilever_z_27k_vf30_i20",
    "cantilever_z_64k_vf30_i20",
    "cantilever_z_216k_vf30_i20",
]


def summarize_case(case_id: str) -> dict[str, object]:
    run_dir = RUNS / case_id
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    problem = summary["problem"]
    final = summary["final"]
    nelx = int(problem["nelx"])
    nely = int(problem["nely"])
    nelz = int(problem["nelz"])
    return {
        "case_id": case_id,
        "mesh": f"{nelx}x{nely}x{nelz}",
        "n_elem": nelx * nely * nelz,
        "volfrac": float(problem["volfrac"]),
        "filter_radius": float(problem["filter_radius"]),
        "backend": summary["backend"],
        "linear_solver": summary["linear_solver"],
        "n_iter": int(summary["n_iter"]),
        "total_wall_s": float(summary["total_wall_s"]),
        "final_iter_wall_s": float(final["wall_s"]),
        "compliance": float(final["compliance"]),
        "grayness": float(final["grayness"]),
        "outer_iters": int(final["outer_iters"]),
        "rho_mean": float(final["rho_mean"]),
        "rho_min": float(final["rho_min"]),
        "rho_max": float(final["rho_max"]),
        "run_dir": str(run_dir),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = [summarize_case(case_id) for case_id in CASES]

    csv_path = OUT_DIR / "large_suite_summary.csv"
    json_path = OUT_DIR / "large_suite_summary.json"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(csv_path)
    print(json_path)


if __name__ == "__main__":
    main()
