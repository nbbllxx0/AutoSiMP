"""Re-solve the configured 3-D cantilever (3-D track, majority 10/10) at the
mesh the configurator drafted (80x40x20), with the same protocol as the coarse
Fig. 7 solve in analysis/run_e12.py (schedule controller, max_iter=80), and
evaluate it with the five gates.

Usage: python run_fig7_fine.py [nelx nely nelz]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

IMPL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IMPL))

from auto_simp import auto_simp  # noqa: E402
from problem_spec import ProblemSpec  # noqa: E402

EV = IMPL / "results"
res = json.loads((EV / "e12_results.json").read_text(encoding="utf-8"))
case = next(c for c in res["cases"] if c["name"] == "cantilever_3d")
spec_d = dict(case["repeats"][0]["configured"])
assert all(r["configured"] == case["repeats"][0]["configured"] for r in case["repeats"]), "repeats differ"
if len(sys.argv) == 4:
    spec_d["nelx"], spec_d["nely"], spec_d["nelz"] = map(int, sys.argv[1:])
spec = ProblemSpec.from_dict(spec_d)
tag = f"{spec.nelx}x{spec.nely}x{spec.nelz}"
out = EV / f"fig7_configured_3d_{tag}"
out.mkdir(exist_ok=True)
print("solving configured cantilever_3d at", tag, flush=True)
t0 = time.time()
report = auto_simp(spec=spec, controller="schedule", max_iter=80, max_retries=0,
                   output_dir=str(out), use_llm_eval=False, verbose=True)
elapsed = time.time() - t0
ss, ev = report["solver_summary"], report["evaluation"]
summary = {
    "spec": spec_d, "mesh": tag, "n_elem": spec.nelx * spec.nely * spec.nelz,
    "controller": "schedule", "max_iter": 80,
    "final_compliance": ss["final_compliance"], "final_grayness": ss.get("final_grayness"),
    "n_iter": ss.get("n_iter"), "evaluation_passed": ev["passed"],
    "failed_checks": [c["name"] for c in ev.get("checks", []) if not c["passed"]],
    "wall_time_s": round(elapsed, 1), "density_npy": report.get("density_npy"),
}
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "spec"}, indent=2))
