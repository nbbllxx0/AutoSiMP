"""E11: preview-surfacing four-cell from P0 prompts + keyword ambiguity gate.

P0 did not store configurator warnings. The plan states the ambiguity gate is
keyword-based (AMBIGUITY_TERMS). Flags are therefore recomputed from the same
prompt texts P0 scored. Semantic correctness is n_match==9 on the P0 majority
row. No significance claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

IMPL = Path(__file__).resolve().parents[1]
DIAG = IMPL / "reproducibility" / "diagnostic_suite"
sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(DIAG))

from revision_experiments import (  # noqa: E402
    PIPELINE_TEST_CASES,
    RULE_CHALLENGE_CASES,
    ambiguity_flags,
    expanded_prompt_generalization_cases,
)

P0 = IMPL / "results" / "headtohead_results.json"
OUT = IMPL / "results"


def cases_by_name() -> dict[str, dict]:
    out = {}
    for case in list(PIPELINE_TEST_CASES) + list(RULE_CHALLENGE_CASES) + list(
        expanded_prompt_generalization_cases()
    ):
        out[case["name"]] = case
    return out


def main() -> None:
    bundle = json.loads(P0.read_text(encoding="utf-8"))
    catalog = cases_by_name()
    rows = []
    for set_name in ("canonical", "challenge", "heldout"):
        for p in bundle["llm"][set_name]["per_prompt"]:
            case = catalog[p["name"]]
            flags = ambiguity_flags(case["prompt"])
            flagged = bool(flags)
            scored = bool(p.get("scored"))
            n_match = p.get("n_match")
            imperfect = (not scored) or (n_match is None) or (int(n_match) < 9)
            if imperfect and flagged:
                cell = "detection"
            elif imperfect and not flagged:
                cell = "silent_miss"
            elif (not imperfect) and flagged:
                cell = "false_alarm"
            else:
                cell = "correct_pass"
            rows.append(
                {
                    "set": set_name,
                    "name": p["name"],
                    "n_match": n_match,
                    "scored": scored,
                    "imperfect": imperfect,
                    "flagged": flagged,
                    "flags": flags,
                    "cell": cell,
                    "prompt": case["prompt"],
                }
            )

    counts = {k: sum(1 for r in rows if r["cell"] == k) for k in
              ("detection", "silent_miss", "false_alarm", "correct_pass")}
    n = len(rows)
    silent = [r for r in rows if r["cell"] == "silent_miss"]
    summary = {
        "n_prompts": n,
        "counts": counts,
        "n_imperfect": sum(1 for r in rows if r["imperfect"]),
        "n_flagged": sum(1 for r in rows if r["flagged"]),
        "detection_given_imperfect": (
            counts["detection"] / max(sum(1 for r in rows if r["imperfect"]), 1)
        ),
        "false_alarm_given_correct": (
            counts["false_alarm"] / max(sum(1 for r in rows if not r["imperfect"]), 1)
        ),
        "mechanism": (
            "The ambiguity gate is keyword-based (AMBIGUITY_TERMS in "
            "revision_experiments.py). It detects linguistic hedges such as "
            "near/around/roughly/mid-right, not semantic error. A confidently "
            "worded prompt that the model misreads is a silent miss."
        ),
        "silent_miss_names": [r["name"] for r in silent],
        "silent_miss_detail": [
            {
                "name": r["name"],
                "set": r["set"],
                "n_match": r["n_match"],
                "prompt": r["prompt"],
            }
            for r in silent
        ],
        "no_significance_claim": True,
    }
    (OUT / "e11_surfacing.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8"
    )
    lines = ["# E11 preview-surfacing", "", f"- n = {n} P0 prompts (10+10+100)", ""]
    lines.append("| | preview flagged | preview silent |")
    lines.append("|---|---:|---:|")
    lines.append(f"| specification imperfect | {counts['detection']} detection | {counts['silent_miss']} silent miss |")
    lines.append(f"| specification exact (9/9) | {counts['false_alarm']} false alarm | {counts['correct_pass']} correct pass |")
    lines.append("")
    lines.append(summary["mechanism"])
    lines.append("")
    lines.append("## Silent misses (named)")
    lines.append("")
    for r in silent:
        lines.append(f"- `{r['name']}` ({r['set']}, {r['n_match']}/9): {r['prompt']}")
    (OUT / "e11_surfacing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["counts"] | {"n": n, "n_silent": len(silent)}, indent=2))
    print("silent", len(silent))


if __name__ == "__main__":
    main()
