"""E2: specification-match primary metric from frozen specs. No LLM path."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IMPL = Path(r"E:\AI\AUTO\AutoSiMP_full_implementation")
DIAG = IMPL / "reproducibility" / "diagnostic_suite"
PIPE = IMPL / "reproducibility" / "benchmark_results" / "pipeline_results.json"
FROZEN = Path(r"E:\AI\AUTO\revision_2026-09-20_aes\frozen_specs")
OUT = Path(r"E:\AI\AUTO\revision_2026-09-20_aes\evidence")

sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(DIAG))

from problem_spec import ProblemSpec  # noqa: E402
from revision_experiments import compare_specs  # noqa: E402

SEM = (
    "support_semantics_match",
    "load_semantics_match",
    "passive_semantics_match",
)
MATCH = tuple(k for k in (
    "Lx_match", "Ly_match", "volfrac_match",
    "n_supports_match", "n_loads_match", "n_passive_match",
    *SEM,
))


def pipeline_mesh() -> dict[str, dict[str, tuple[int, int]]]:
    """Exact nelx×nely from the archived pipeline, not from frozen specs.

    Frozen configured specs for the eight recovered cases were copied from
    the reference, so they cannot see the original LLM mesh. The public
    archive can.
    """
    rows = json.loads(PIPE.read_text(encoding="utf-8"))
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for r in rows:
        src = r.get("source")
        if src not in ("ground_truth", "llm_configured"):
            continue
        out.setdefault(r["problem"], {})[src] = (int(r["nelx"]), int(r["nely"]))
    return out


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def main() -> None:
    sums = {}
    for line in (FROZEN / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        d, n = line.split("  ", 1)
        sums[n] = d
    ref_doc = json.loads((FROZEN / "reference_specs.json").read_text(encoding="utf-8"))
    cfg_doc = json.loads((FROZEN / "configured_specs.json").read_text(encoding="utf-8"))
    for label, doc in (
        ("reference_specs.json", ref_doc),
        ("configured_specs.json", cfg_doc),
    ):
        got = hashlib.sha256(canonical_bytes(doc)).hexdigest()
        if got != sums[label]:
            raise SystemExit(f"HASH MISMATCH {label}")

    rows = []
    n_exact = 0
    n_semantic_fail = 0
    n_unrecoverable = 0
    n_nine_and_mesh = 0
    n_nine_mesh_diff = 0
    meshes = pipeline_mesh()
    for name, ref in ref_doc["specs"].items():
        cfg = cfg_doc["specs"][name]
        row = {"name": name, "configured_status": cfg["status"]}
        if cfg["status"] == "UNRECOVERABLE" or cfg.get("spec") is None:
            n_unrecoverable += 1
            n_semantic_fail += 1
            row["scored"] = False
            row["n_match"] = None
            row["n_fields"] = 9
            row["exact_9of9"] = False
            row["semantic_failure"] = True
            row["reason"] = cfg["unknown_fields"]
            row["fields"] = {}
            if name == "lbracket":
                row["load_semantics_match"] = False
                row["note"] = (
                    "Generated load y is UNRECOVERABLE. Scored as a load-location "
                    "failure, not as a pass."
                )
            if name == "bridge":
                row["n_supports_match"] = False
                row["note"] = (
                    "Support identities UNRECOVERABLE (count 2 vs 1). "
                    "Not a specification match."
                )
        else:
            gt = ProblemSpec.from_dict(ref["spec"])
            test = ProblemSpec.from_dict(cfg["spec"])
            cmp = compare_specs(gt, test)
            fields = {k: bool(cmp[k]) for k in MATCH}
            n_match = sum(fields.values())
            row.update(
                {
                    "scored": True,
                    "n_match": n_match,
                    "n_fields": 9,
                    "exact_9of9": n_match == 9,
                    "semantic_failure": not all(fields[k] for k in SEM),
                    "fields": fields,
                }
            )
            if n_match == 9:
                n_exact += 1
            if row["semantic_failure"]:
                n_semantic_fail += 1
        gt_m, llm_m = meshes[name]["ground_truth"], meshes[name]["llm_configured"]
        mesh_equal = gt_m == llm_m
        row["mesh_gt"] = f"{gt_m[0]}x{gt_m[1]}"
        row["mesh_llm"] = f"{llm_m[0]}x{llm_m[1]}"
        row["mesh_equal"] = mesh_equal
        row.setdefault("fields", {})["mesh_equal"] = mesh_equal
        if row.get("exact_9of9") and mesh_equal:
            n_nine_and_mesh += 1
        if row.get("exact_9of9") and not mesh_equal:
            n_nine_mesh_diff += 1
        rows.append(row)

    lbr = next(r for r in rows if r["name"] == "lbracket")
    if lbr.get("load_semantics_match") is not False and not lbr.get("semantic_failure"):
        raise SystemExit("E2 FAIL: L-bracket must be a semantic failure")
    if n_nine_mesh_diff != 4:
        raise SystemExit(f"E2 FAIL: expected 4 nine-field matches with mesh diff, got {n_nine_mesh_diff}")

    summary = {
        "n_cases": 10,
        "n_exact_9of9": n_exact,
        "n_nine_and_mesh": n_nine_and_mesh,
        "n_nine_mesh_diff": n_nine_mesh_diff,
        "n_semantic_failure": n_semantic_fail,
        "n_unrecoverable": n_unrecoverable,
        "primary_headline": f"{n_exact}/10 exact nine-field matches",
        "mesh_disclosure": (
            f"{n_exact}/10 match on all nine scored fields; "
            f"{n_nine_mesh_diff} of those also differ in archived mesh "
            "(pipeline nelx x nely), which the nine fields do not score. "
            f"{n_nine_and_mesh}/10 match on nine fields and mesh."
        ),
        "lbracket_semantic_failure": True,
        "high_aspect_not_claimed_better": True,
        "rows": rows,
    }
    (OUT / "e2_spec_match.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary["primary_headline"])
    print(summary["mesh_disclosure"])
    print("L-bracket semantic failure:", lbr["semantic_failure"])


if __name__ == "__main__":
    main()
