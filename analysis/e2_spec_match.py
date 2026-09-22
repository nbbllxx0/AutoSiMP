"""E2: specification-match primary metric from frozen specs. No LLM path.

Configured specs are the stored retry-run specs (frozen_specs/configured_specs.json).
Nine fields are scored with compare_specs; mesh is reported beside them.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
DIAG = IMPL / "reproducibility" / "diagnostic_suite"
FROZEN = IMPL / "frozen_specs"
OUT = IMPL / "results"

sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(DIAG))

from problem_spec import ProblemSpec  # noqa: E402
from revision_experiments import compare_specs  # noqa: E402

SEM = (
    "support_semantics_match",
    "load_semantics_match",
    "passive_semantics_match",
)
MATCH = (
    "Lx_match", "Ly_match", "volfrac_match",
    "n_supports_match", "n_loads_match", "n_passive_match",
    *SEM,
)


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def main() -> None:
    sums = {}
    for line in (FROZEN / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        d, n = line.split("  ", 1)
        sums[n] = d
    ref_doc = json.loads((FROZEN / "reference_specs.json").read_text(encoding="utf-8"))
    cfg_doc = json.loads((FROZEN / "configured_specs.json").read_text(encoding="utf-8"))
    for label, doc in (("reference_specs.json", ref_doc), ("configured_specs.json", cfg_doc)):
        if hashlib.sha256(canonical_bytes(doc)).hexdigest() != sums[label]:
            raise SystemExit(f"HASH MISMATCH {label}")

    rows = []
    for name, ref in ref_doc["specs"].items():
        cfg = cfg_doc["specs"][name]
        gt = ProblemSpec.from_dict(ref["spec"])
        test = ProblemSpec.from_dict(cfg["spec"])
        cmp = compare_specs(gt, test)
        fields = {k: bool(cmp[k]) for k in MATCH}
        n_match = sum(fields.values())
        mesh_equal = (gt.nelx, gt.nely) == (test.nelx, test.nely)
        rows.append({
            "name": name,
            "configured_status": cfg["status"],
            "n_match": n_match,
            "n_fields": 9,
            "exact_9of9": n_match == 9,
            "semantic_failure": not all(fields[k] for k in SEM),
            "fields": {**fields, "mesh_equal": mesh_equal},
            "mesh_gt": f"{gt.nelx}x{gt.nely}",
            "mesh_llm": f"{test.nelx}x{test.nely}",
            "mesh_equal": mesh_equal,
            "missed_fields": [k for k, v in fields.items() if not v],
        })

    n_exact = sum(r["exact_9of9"] for r in rows)
    summary = {
        "n_cases": len(rows),
        "n_exact_9of9": n_exact,
        "n_match_total": sum(r["n_match"] for r in rows),
        "n_fields_total": 9 * len(rows),
        "n_nine_and_mesh": sum(r["exact_9of9"] and r["mesh_equal"] for r in rows),
        "n_nine_mesh_diff": sum(r["exact_9of9"] and not r["mesh_equal"] for r in rows),
        "n_mesh_diff": sum(not r["mesh_equal"] for r in rows),
        "n_semantic_failure": sum(r["semantic_failure"] for r in rows),
        "primary_headline": f"{n_exact}/{len(rows)} exact nine-field matches",
        "rows": rows,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "e2_spec_match.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary["primary_headline"], f"({summary['n_match_total']}/{summary['n_fields_total']} fields)")
    print(f"mesh differs: {summary['n_mesh_diff']}/10; nine fields and mesh: {summary['n_nine_and_mesh']}/10")
    for r in rows:
        print(f"  {r['name']:26s} {r['n_match']}/9 {r['missed_fields']} mesh {r['mesh_gt']} vs {r['mesh_llm']}")


if __name__ == "__main__":
    main()
