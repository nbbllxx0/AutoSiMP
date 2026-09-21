from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
REVISION_ROOT = HERE.parent
WORKSPACE_ROOT = REVISION_ROOT.parent
WRAPPER = HERE / "run_topogpu_with_temp_patch.py"


EXECUTION_CASES = [
    {
        "case_id": "cantilever_z_24x12x6_vf30",
        "name": "cantilever_3d",
        "nel": [24, 12, 6],
        "volfrac": 0.30,
        "filter_radius": 1.5,
        "support": "xmin",
        "load": "tip_patch_z",
        "iters": 5,
        "backend": "cupy",
    },
    {
        "case_id": "cantilever_y_24x12x6_vf30",
        "name": "cantilever_3d",
        "nel": [24, 12, 6],
        "volfrac": 0.30,
        "filter_radius": 1.5,
        "support": "xmin",
        "load": "tip_point_y",
        "iters": 5,
        "backend": "cupy",
    },
]


VERIFY_CASES = [
    {"case": "tool_long_cantilever_vf16", "dims": "6x4x4"},
    {"case": "tool_asymmetric_bracket_vf14", "dims": "6x4x4"},
    {"case": "tool_portal_bridge_vf18", "dims": "8x4x4"},
]


def write_yaml(path: Path, case: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"name: {case['name']}",
        "nel: [" + ", ".join(str(v) for v in case["nel"]) + "]",
        f"volfrac: {case['volfrac']:.2f}",
        f"filter_radius: {case['filter_radius']}",
        f"support: {case['support']}",
        f"load: {case['load']}",
        "role: autosimp_3d_upgrade",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    log_stem: Path,
    force: bool,
) -> dict:
    stdout_path = log_stem.with_suffix(".stdout.txt")
    stderr_path = log_stem.with_suffix(".stderr.txt")
    marker_path = log_stem.with_suffix(".status.json")
    if marker_path.exists() and not force:
        status = json.loads(marker_path.read_text(encoding="utf-8"))
        status["skipped"] = True
        return status

    log_stem.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
        wall_s = time.perf_counter() - t0
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        status = {
            "returncode": proc.returncode,
            "timeout": False,
            "wall_s": wall_s,
            "stdout": str(stdout_path.relative_to(REVISION_ROOT)),
            "stderr": str(stderr_path.relative_to(REVISION_ROOT)),
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired as exc:
        wall_s = time.perf_counter() - t0
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        status = {
            "returncode": None,
            "timeout": True,
            "wall_s": wall_s,
            "stdout": str(stdout_path.relative_to(REVISION_ROOT)),
            "stderr": str(stderr_path.relative_to(REVISION_ROOT)),
            "cmd": cmd,
        }
    marker_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_execution(case: dict, out_dir: Path, command_status: dict, render_status: dict) -> dict:
    row = {
        "kind": "execution",
        "case_id": case["case_id"],
        "status": "pass" if command_status.get("returncode") == 0 else "fail",
        "backend_requested": case["backend"],
        "mesh": "x".join(str(v) for v in case["nel"]),
        "n_elem": int(case["nel"][0]) * int(case["nel"][1]) * int(case["nel"][2]),
        "volfrac": case["volfrac"],
        "load": case["load"],
        "iterations_requested": case["iters"],
        "command_wall_s": command_status.get("wall_s", ""),
        "render_status": "pass" if render_status.get("returncode") == 0 else "fail",
        "out_dir": str(out_dir.relative_to(REVISION_ROOT)),
    }
    summary_path = out_dir / "summary.json"
    if summary_path.exists():
        summary = read_json(summary_path)
        final = summary.get("final", {})
        problem = summary.get("problem", {})
        row.update(
            {
                "backend_reported": summary.get("backend", ""),
                "linear_solver": summary.get("linear_solver", ""),
                "iterations_reported": summary.get("n_iter", ""),
                "reported_total_wall_s": summary.get("total_wall_s", ""),
                "final_compliance": final.get("compliance", summary.get("final_compliance", "")),
                "final_grayness": final.get("grayness", summary.get("final_grayness", "")),
                "final_iter_wall_s": final.get("wall_s", ""),
                "outer_iters": final.get("outer_iters", ""),
                "rho_mean": final.get("rho_mean", ""),
                "rho_min": final.get("rho_min", ""),
                "rho_max": final.get("rho_max", ""),
                "problem_name": problem.get("name", ""),
            }
        )
    return row


def summarize_verify(item: dict, out_dir: Path, command_status: dict) -> dict:
    row = {
        "kind": "verification",
        "case_id": item["case"],
        "status": "pass" if command_status.get("returncode") == 0 else "fail",
        "mesh": item["dims"],
        "command_wall_s": command_status.get("wall_s", ""),
        "out_dir": str(out_dir.relative_to(REVISION_ROOT)),
    }
    summary_path = out_dir / "verification_summary.json"
    if summary_path.exists():
        summary = read_json(summary_path)
        row.update(
            {
                "all_pass": summary.get("all_pass", ""),
                "operator_rows": summary.get("operator_rows", ""),
                "sensitivity_rows": summary.get("sensitivity_rows", ""),
                "filter_rows": summary.get("filter_rows", ""),
                "sensitivity_max_rel_error": summary.get("sensitivity_max_rel_error", ""),
                "filter_max_value": summary.get("filter_max_value", ""),
            }
        )
    return row


def write_csv_rows(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python",
        default=os.environ.get("TOPOGPU_PYTHON", sys.executable),
        help="Python interpreter for the TopoGPU environment. Defaults to TOPOGPU_PYTHON or the current interpreter.",
    )
    parser.add_argument("--out", default=str(HERE / "results_3d_suite"))
    parser.add_argument("--timeout-s", type=int, default=600)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-execution", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    py = Path(args.python)
    if not py.exists():
        raise SystemExit(f"TopoGPU Python not found: {py}")
    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = (Path.cwd() / out_root).resolve()
    case_dir = HERE / "cases"
    log_dir = out_root / "logs"

    rows: list[dict] = []

    if not args.skip_verify:
        for item in VERIFY_CASES:
            verify_out = out_root / "verify" / item["case"]
            cmd = [
                str(py),
                str(WRAPPER),
                "--topogpu",
                "verify",
                "--case",
                item["case"],
                "--dims",
                item["dims"],
                "--out",
                str(verify_out),
            ]
            status = run_command(
                cmd,
                cwd=WORKSPACE_ROOT,
                timeout_s=args.timeout_s,
                log_stem=log_dir / f"verify_{item['case']}",
                force=args.force,
            )
            rows.append(summarize_verify(item, verify_out, status))

    if not args.skip_execution:
        for case in EXECUTION_CASES:
            yaml_path = case_dir / f"{case['case_id']}.yaml"
            write_yaml(yaml_path, case)
            run_out = out_root / "runs" / case["case_id"]
            run_cmd = [
                str(py),
                str(WRAPPER),
                "--topogpu",
                "run",
                str(yaml_path),
                "--backend",
                case["backend"],
                "--iters",
                str(case["iters"]),
                "--out",
                str(run_out),
            ]
            run_status = run_command(
                run_cmd,
                cwd=WORKSPACE_ROOT,
                timeout_s=args.timeout_s,
                log_stem=log_dir / f"run_{case['case_id']}",
                force=args.force,
            )
            render_cmd = [
                str(py),
                str(WRAPPER),
                "--topogpu",
                "render",
                str(run_out),
            ]
            render_status = run_command(
                render_cmd,
                cwd=WORKSPACE_ROOT,
                timeout_s=max(120, args.timeout_s // 3),
                log_stem=log_dir / f"render_{case['case_id']}",
                force=args.force,
            )
            rows.append(summarize_execution(case, run_out, run_status, render_status))

    summary = {
        "revision_root": str(REVISION_ROOT),
        "topogpu_python": str(py),
        "wrapper": str(WRAPPER.relative_to(REVISION_ROOT)),
        "timeout_s": args.timeout_s,
        "rows": rows,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "suite_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv_rows(out_root / "suite_summary.csv", rows)
    print(json.dumps({"out": str(out_root), "rows": len(rows)}, indent=2))
    return 0 if all(row.get("status") == "pass" for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
