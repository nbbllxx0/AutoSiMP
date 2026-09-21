"""P0 matched head-to-head: rule-only vs LLM configurator.

Pinned:
  LLM: AutoSiMP_full_implementation/configurator_agent.py configure()
  model: gemini-3.1-flash-lite (NOT the function default preview endpoint)
  scorer: compare_specs, nine keys ending in _match
  rule-only: rule_only_parse (gt_spec discarded inside that function)

Any row with llm_used == False is api_failure and is never scored.
>10% api_failure in any prompt set invalidates that set.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PINNED_PYTHON_NOTE = r"C:\Users\YSL0\AppData\Local\Programs\Python\Python312\python.exe"
IMPL = Path(r"E:\AI\AUTO\AutoSiMP_full_implementation")
DIAG = IMPL / "reproducibility" / "diagnostic_suite"
MODEL = "gemini-3.1-flash-lite"
N_LLM_REPEATS = 3
API_FAIL_LIMIT = 0.10

sys.path.insert(0, str(IMPL))
sys.path.insert(0, str(DIAG))

from configurator_agent import configure  # noqa: E402
from revision_experiments import (  # noqa: E402
    PIPELINE_TEST_CASES,
    RULE_CHALLENGE_CASES,
    compare_specs,
    expanded_prompt_generalization_cases,
    rule_only_parse,
)

OUT = Path(__file__).resolve().parent
# Paid-tier Gemini Developer API prices, 2026-09-20:
# https://ai.google.dev/gemini-api/docs/pricing  (gemini-3.1-flash-lite)
PRICE_INPUT_USD_PER_M = 0.25
PRICE_OUTPUT_USD_PER_M = 1.50
_LAST_USAGE: dict = {}
MATCH_KEYS = (
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


def install_usage_hook() -> None:
    """Capture Gemini usageMetadata from REST responses without changing configure()."""
    orig = urllib.request.urlopen

    class _Tee:
        def __init__(self, raw, body: bytes):
            self._raw = raw
            self._buf = io.BytesIO(body)

        def read(self, *args, **kwargs):
            return self._buf.read(*args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            try:
                self._raw.close()
            except Exception:
                pass
            return False

        def __getattr__(self, name):
            return getattr(self._raw, name)

    def wrapped(req, *args, **kwargs):
        resp = orig(req, *args, **kwargs)
        body = resp.read()
        global _LAST_USAGE
        try:
            data = json.loads(body.decode("utf-8"))
            um = data.get("usageMetadata") or {}
            _LAST_USAGE = {
                "prompt_token_count": um.get("promptTokenCount"),
                "candidates_token_count": um.get("candidatesTokenCount"),
                "total_token_count": um.get("totalTokenCount"),
            }
        except Exception:
            _LAST_USAGE = {}
        return _Tee(resp, body)

    urllib.request.urlopen = wrapped  # type: ignore[assignment]


def usd_cost(prompt_tokens: int, output_tokens: int) -> float:
    return (prompt_tokens / 1e6) * PRICE_INPUT_USD_PER_M + (
        output_tokens / 1e6
    ) * PRICE_OUTPUT_USD_PER_M


def transient_api_error(error: str | None) -> bool:
    s = str(error or "")
    return ("HTTP 429" in s) or ("HTTP 503" in s) or ("RESOURCE_EXHAUSTED" in s)


def load_scored_rows() -> dict[tuple[str, int], dict]:
    path = OUT / "llm_calls.jsonl"
    out: dict[tuple[str, int], dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (row["name"], int(row["repeat"]))
        prev = out.get(key)
        if row.get("scored") and row.get("llm_used"):
            out[key] = row
        elif prev is None or not prev.get("scored"):
            out[key] = row
    return out


def configure_with_retry(prompt: str, api_key: str):
    last = None
    for attempt in range(9):
        last = configure(
            prompt,
            model=MODEL,
            api_key=api_key,
            temperature=0.0,
            verbose=False,
        )
        if last.llm_used:
            return last
        if transient_api_error(last.error) and attempt < 8:
            wait = min(60, 2**attempt)
            print(f"    transient HTTP retry in {wait}s (attempt {attempt + 1})", flush=True)
            time.sleep(wait)
            continue
        return last
    return last


def score_spec(gt, test) -> dict:
    cmp = compare_specs(gt, test)
    n_fields = sum(1 for k in cmp if k.endswith("_match"))
    n_match = sum(1 for k, v in cmp.items() if k.endswith("_match") and v)
    if n_fields != 9:
        raise RuntimeError(f"expected 9 _match keys, got {n_fields}: {list(cmp)}")
    extra = [k for k in MATCH_KEYS if k not in cmp]
    if extra:
        raise RuntimeError(f"missing keys {extra}")
    return {
        "n_fields": n_fields,
        "n_match": n_match,
        "mesh_reasonable": cmp.get("mesh_reasonable"),
        "fields": {k: bool(cmp[k]) for k in MATCH_KEYS},
    }


def majority_fields(field_dicts: list[dict]) -> dict:
    """Field-wise majority across successful repeats. Ties (1-1) count as False."""
    out = {}
    n = len(field_dicts)
    for k in MATCH_KEYS:
        votes = sum(1 for d in field_dicts if d[k])
        out[k] = votes * 2 > n
    return out


def run_rule_only(cases: list[dict]) -> dict:
    rows = []
    n_match = 0
    n_fields = 0
    by_cat = {}
    for case in cases:
        spec = rule_only_parse(case["prompt"], case["spec"])
        sc = score_spec(case["spec"], spec)
        cat = case.get("category", "n/a")
        rows.append(
            {
                "name": case["name"],
                "category": cat,
                "n_match": sc["n_match"],
                "n_fields": sc["n_fields"],
                "fields": sc["fields"],
            }
        )
        n_match += sc["n_match"]
        n_fields += sc["n_fields"]
        slot = by_cat.setdefault(cat, {"n_match": 0, "n_fields": 0, "n": 0})
        slot["n_match"] += sc["n_match"]
        slot["n_fields"] += sc["n_fields"]
        slot["n"] += 1
    return {
        "parser": "rule_only",
        "n_prompts": len(cases),
        "n_match": n_match,
        "n_fields": n_fields,
        "by_category": by_cat,
        "rows": rows,
    }


def run_llm(cases: list[dict], api_key: str) -> dict:
    raw_rows = []
    api_failures = 0
    n_calls = 0
    latencies = []
    per_prompt = []
    prompt_tokens = 0
    output_tokens = 0
    total_tokens = 0

    for i, case in enumerate(cases, 1):
        print(f"  {case['name']} ({i}/{len(cases)})", flush=True)
        success_fields = []
        prompt_failures = 0
        prompt_lat = []
        prior = load_scored_rows()
        for rep in range(N_LLM_REPEATS):
            n_calls += 1
            cached = prior.get((case["name"], rep))
            if cached and cached.get("scored") and cached.get("llm_used"):
                row = cached
                latencies.append(float(row.get("latency_s") or 0.0))
                prompt_lat.append(float(row.get("latency_s") or 0.0))
                pt = int(row.get("prompt_token_count") or 0)
                ot = int(row.get("candidates_token_count") or 0)
                tt = int(row.get("total_token_count") or (pt + ot))
                prompt_tokens += pt
                output_tokens += ot
                total_tokens += tt
                success_fields.append(row["fields"])
                raw_rows.append(row)
                print("    resume scored", flush=True)
                continue
            t0 = time.perf_counter()
            result = configure_with_retry(case["prompt"], api_key)
            dt = time.perf_counter() - t0
            latencies.append(dt)
            prompt_lat.append(dt)
            used = bool(result.llm_used)
            usage = dict(_LAST_USAGE)
            pt = int(usage.get("prompt_token_count") or 0)
            ot = int(usage.get("candidates_token_count") or 0)
            tt = int(usage.get("total_token_count") or (pt + ot))
            prompt_tokens += pt
            output_tokens += ot
            total_tokens += tt
            row = {
                "name": case["name"],
                "category": case.get("category", "n/a"),
                "repeat": rep,
                "llm_used": used,
                "error": result.error,
                "latency_s": dt,
                "api_failure": not used,
                "prompt_token_count": usage.get("prompt_token_count"),
                "candidates_token_count": usage.get("candidates_token_count"),
                "total_token_count": usage.get("total_token_count"),
            }
            if not used:
                api_failures += 1
                prompt_failures += 1
                row["n_match"] = None
                row["n_fields"] = None
                row["fields"] = None
                row["scored"] = False
            else:
                sc = score_spec(case["spec"], result.spec)
                row["n_match"] = sc["n_match"]
                row["n_fields"] = sc["n_fields"]
                row["fields"] = sc["fields"]
                row["scored"] = True
                success_fields.append(sc["fields"])
            raw_rows.append(row)
            with (OUT / "llm_calls.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            time.sleep(1.0)

        if success_fields:
            maj = majority_fields(success_fields)
            n_m = sum(1 for v in maj.values() if v)
            per_prompt.append(
                {
                    "name": case["name"],
                    "category": case.get("category", "n/a"),
                    "n_success_repeats": len(success_fields),
                    "n_api_failure_repeats": prompt_failures,
                    "n_match": n_m,
                    "n_fields": 9,
                    "fields": maj,
                    "mean_latency_s": sum(prompt_lat) / len(prompt_lat),
                    "scored": True,
                }
            )
        else:
            per_prompt.append(
                {
                    "name": case["name"],
                    "category": case.get("category", "n/a"),
                    "n_success_repeats": 0,
                    "n_api_failure_repeats": prompt_failures,
                    "n_match": None,
                    "n_fields": 9,
                    "fields": None,
                    "mean_latency_s": sum(prompt_lat) / len(prompt_lat),
                    "scored": False,
                }
            )

    n_possible = len(cases) * N_LLM_REPEATS
    fail_rate = api_failures / n_possible if n_possible else 1.0
    invalid = fail_rate > API_FAIL_LIMIT

    n_match = 0
    n_fields = 0
    by_cat = {}
    if not invalid:
        for p in per_prompt:
            if not p["scored"]:
                # Unscored prompt inside a still-valid set: count as 0/9, not a silent skip.
                n_fields += 9
                continue
            n_match += p["n_match"]
            n_fields += p["n_fields"]
            cat = p["category"]
            slot = by_cat.setdefault(cat, {"n_match": 0, "n_fields": 0, "n": 0})
            slot["n_match"] += p["n_match"]
            slot["n_fields"] += p["n_fields"]
            slot["n"] += 1

    return {
        "parser": "llm",
        "model": MODEL,
        "n_prompts": len(cases),
        "n_repeats": N_LLM_REPEATS,
        "n_calls": n_calls,
        "api_failure_rows": api_failures,
        "api_failure_rate": fail_rate,
        "invalid": invalid,
        "invalid_reason": (
            f"api_failure {fail_rate:.3f} > {API_FAIL_LIMIT}" if invalid else None
        ),
        "n_match": None if invalid else n_match,
        "n_fields": n_fields if not invalid else len(cases) * 9,
        "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None,
        "prompt_token_count": prompt_tokens,
        "candidates_token_count": output_tokens,
        "total_token_count": total_tokens,
        "usd_paid_tier": usd_cost(prompt_tokens, output_tokens),
        "by_category": None if invalid else by_cat,
        "per_prompt": per_prompt,
        "raw_rows": raw_rows,
    }


def cell(result: dict | None) -> str:
    if not result:
        return "not run"
    if result.get("invalid"):
        return f"INVALID — API unavailable ({result['api_failure_rows']} failures)"
    if result.get("n_match") is None:
        return "unscored"
    return f"{result['n_match']}/{result['n_fields']}"


def write_summary(bundle: dict, path: Path) -> None:
    lines = []
    lines.append("# P0 head-to-head summary")
    lines.append("")
    lines.append(f"- UTC: {bundle['started_utc']}")
    lines.append(f"- Model: `{MODEL}` (explicit; not the retired preview default)")
    lines.append("- Scorer: `compare_specs`, nine `_match` keys; `mesh_reasonable` excluded")
    lines.append("- LLM repeats: 3 per prompt at temperature 0; field-wise majority")
    lines.append("- Rows with `llm_used == False` are `api_failure` and are never scored")
    lines.append("")
    lines.append("## Six-cell table")
    lines.append("")
    lines.append("| Parser | Canonical (10) | Challenge (10) | Held-out (100) |")
    lines.append("|---|---|---|---|")
    r = bundle["rule_only"]
    l = bundle["llm"]
    lines.append(
        f"| Rule-only | {cell(r.get('canonical'))} | {cell(r.get('challenge'))} | {cell(r.get('heldout'))} |"
    )
    lines.append(
        f"| LLM | {cell(l.get('canonical'))} | {cell(l.get('challenge'))} | {cell(l.get('heldout'))} |"
    )
    lines.append("")
    lines.append("## api_failure counts (LLM rows, not scored)")
    lines.append("")
    lines.append("| Set | Failures / calls | Rate | Status |")
    lines.append("|---|---|---:|---|")
    for name in ("canonical", "challenge", "heldout"):
        d = l.get(name)
        if not d:
            lines.append(f"| {name} | n/a | n/a | not run |")
            continue
        status = "INVALID" if d.get("invalid") else "ok"
        lines.append(
            f"| {name} | {d['api_failure_rows']}/{d['n_calls']} | "
            f"{d['api_failure_rate']:.3f} | {status} |"
        )
    lines.append("")
    if (l.get("heldout") or {}).get("by_category"):
        lines.append("## Held-out by category")
        lines.append("")
        lines.append("| Category | Rule-only | LLM |")
        lines.append("|---|---|---|")
        cats = sorted(r["heldout"]["by_category"])
        for cat in cats:
            rc = r["heldout"]["by_category"][cat]
            lc = l["heldout"]["by_category"].get(cat, {"n_match": 0, "n_fields": 0})
            lines.append(
                f"| {cat} | {rc['n_match']}/{rc['n_fields']} | {lc['n_match']}/{lc['n_fields']} |"
            )
        lines.append("")

    # Branch
    def ok(d):
        return not d.get("invalid") and d.get("n_match") is not None

    branch = "UNDECIDED"
    reason = ""
    if not (ok(l.get("challenge") or {}) and ok(l.get("heldout") or {})):
        branch = "INVALID-RUN"
        reason = "LLM set invalid or unscored; do not choose P0-A/B/C from this run."
    else:
        llm_c, rule_c = l["challenge"]["n_match"], r["challenge"]["n_match"]
        llm_h, rule_h = l["heldout"]["n_match"], r["heldout"]["n_match"]
        if llm_c > rule_c and llm_h > rule_h:
            branch = "P0-A"
            reason = "LLM higher field accuracy on both challenge and held-out, same denominators."
        elif llm_c < rule_c and llm_h < rule_h:
            branch = "P0-C"
            reason = "LLM loses both challenge and held-out. Escalate before any identity writing."
        else:
            branch = "P0-B"
            reason = "No clear win on both sets. Rule-first; LLM optional repair where it wins."
    lines.append(f"## Branch: **{branch}**")
    lines.append("")
    lines.append(reason)
    lines.append("")
    lines.append(
        "Definition of an LLM win (plan): higher field accuracy than rule-only "
        "on **both** the challenge set and the held-out set, at the same denominator."
    )
    lines.append("")
    lines.append("## E9 configurator cost")
    lines.append("")
    lines.append(
        f"Prices: Gemini Developer API paid tier for `{MODEL}`, "
        f"${PRICE_INPUT_USD_PER_M}/1M input and ${PRICE_OUTPUT_USD_PER_M}/1M output "
        "(https://ai.google.dev/gemini-api/docs/pricing, checked 2026-09-20). "
        "Free-tier usage would be $0; the paid-tier equivalent is reported so the "
        "figure does not depend on the account's quota class."
    )
    lines.append("")
    lines.append("| Set | Calls | Mean latency (s) | Input tokens | Output tokens | Paid-tier USD |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    tot_calls = tot_pt = tot_ot = 0
    tot_usd = 0.0
    lat_all = []
    for name in ("canonical", "challenge", "heldout"):
        d = l.get(name) or {}
        if not d:
            continue
        n = int(d.get("n_calls") or 0)
        pt = int(d.get("prompt_token_count") or 0)
        ot = int(d.get("candidates_token_count") or 0)
        usd = float(d.get("usd_paid_tier") or 0.0)
        mean_lat = d.get("mean_latency_s")
        tot_calls += n
        tot_pt += pt
        tot_ot += ot
        tot_usd += usd
        if mean_lat is not None:
            lat_all.extend([mean_lat] * n)
        mean_s = f"{mean_lat:.3f}" if mean_lat is not None else "n/a"
        lines.append(f"| {name} | {n} | {mean_s} | {pt} | {ot} | {usd:.4f} |")
    per_prompt_lat = (sum(lat_all) / len(lat_all)) if lat_all else None
    per_prompt_usd = tot_usd / tot_calls if tot_calls else 0.0
    mean_s = f"{per_prompt_lat:.3f}" if per_prompt_lat is not None else "n/a"
    lines.append(
        f"| **all** | {tot_calls} | {mean_s} | {tot_pt} | {tot_ot} | {tot_usd:.4f} |"
    )
    lines.append("")
    lines.append(
        f"Per-call paid-tier equivalent: ${per_prompt_usd:.5f}. "
        f"Mean wall-clock per call: {mean_s} s."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    bundle["branch"] = branch
    bundle["branch_reason"] = reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rule-only",
        action="store_true",
        help="Score the rule-only parser only (no API).",
    )
    parser.add_argument(
        "--sets",
        default="canonical,challenge,heldout",
        help="Comma subset of canonical,challenge,heldout",
    )
    args = parser.parse_args()

    wanted = {s.strip() for s in args.sets.split(",") if s.strip()}
    cases = {
        "canonical": PIPELINE_TEST_CASES,
        "challenge": RULE_CHALLENGE_CASES,
        "heldout": expanded_prompt_generalization_cases(),
    }

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bundle = {
        "started_utc": started,
        "model": MODEL,
        "scored_keys": list(MATCH_KEYS),
        "rule_only": {},
        "llm": {},
    }

    for name in ("canonical", "challenge", "heldout"):
        if name not in wanted:
            continue
        bundle["rule_only"][name] = run_rule_only(cases[name])
        print(
            f"rule_only {name}: "
            f"{bundle['rule_only'][name]['n_match']}/{bundle['rule_only'][name]['n_fields']}"
        )

    if args.rule_only:
        (OUT / "rule_only_results.json").write_text(
            json.dumps(bundle, indent=2), encoding="utf-8"
        )
        # Minimal summary for the rule-only half
        lines = ["# P0 rule-only half (LLM not run)", ""]
        for name in ("canonical", "challenge", "heldout"):
            if name in bundle["rule_only"]:
                d = bundle["rule_only"][name]
                lines.append(f"- {name}: {d['n_match']}/{d['n_fields']}")
        (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("wrote rule-only results; LLM skipped")
        return

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        msg = (
            "GEMINI_API_KEY is not set. P0 LLM path aborted. "
            "Never score the silent cantilever fallback."
        )
        print(msg, file=sys.stderr)
        bundle["llm_abort"] = msg
        (OUT / "headtohead_results.json").write_text(
            json.dumps(bundle, indent=2), encoding="utf-8"
        )
        (OUT / "summary.md").write_text(
            "# P0 BLOCKED\n\n" + msg + "\n", encoding="utf-8"
        )
        sys.exit(2)

    install_usage_hook()
    n_resume = sum(1 for r in load_scored_rows().values() if r.get("scored"))
    print(f"resume cache: {n_resume} scored LLM rows", flush=True)

    for name in ("canonical", "challenge", "heldout"):
        if name not in wanted:
            continue
        print(f"LLM {name}: {len(cases[name])} prompts x {N_LLM_REPEATS} ...")
        bundle["llm"][name] = run_llm(cases[name], key)
        print(
            f"LLM {name}: {cell(bundle['llm'][name])} "
            f"api_failure={bundle['llm'][name]['api_failure_rows']}"
        )
        if bundle["llm"][name].get("invalid"):
            print("INVALID — API unavailable; stopping remaining sets.")
            break
        (OUT / "headtohead_results.json").write_text(
            json.dumps(bundle, indent=2), encoding="utf-8"
        )

    (OUT / "headtohead_results.json").write_text(
        json.dumps(bundle, indent=2), encoding="utf-8"
    )
    write_summary(bundle, OUT / "summary.md")
    (OUT / "headtohead_results.json").write_text(
        json.dumps(bundle, indent=2), encoding="utf-8"
    )
    print("branch:", bundle.get("branch"))


if __name__ == "__main__":
    main()
