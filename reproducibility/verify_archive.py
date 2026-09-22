"""Validate integrity, portability, and headline values in this archive."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def read_csv(relative: str) -> list[dict[str, str]]:
    path = ROOT / relative
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        fail(f"empty CSV: {relative}")
    return rows


def assert_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        fail(f"{label}: expected {expected!r}, found {actual!r}")


def assert_close(label: str, actual: float, expected: float, tolerance: float = 0.005) -> None:
    if not math.isclose(actual, expected, abs_tol=tolerance):
        fail(f"{label}: expected approximately {expected}, found {actual}")


def validate_json_and_csv() -> tuple[int, int]:
    json_count = 0
    csv_count = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".json":
                json.loads(path.read_text(encoding="utf-8"))
                json_count += 1
            elif path.suffix.lower() == ".csv":
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    reader = csv.reader(handle)
                    header = next(reader, None)
                    if not header:
                        fail(f"missing CSV header: {path.relative_to(ROOT)}")
                    list(reader)
                csv_count += 1
        except Exception as exc:  # verification should report every malformed file
            fail(f"cannot parse {path.relative_to(ROOT)}: {exc}")
    return json_count, csv_count


def validate_model_references() -> int:
    checked = 0
    for path in sorted((ROOT / "model_checks").glob("live_model_runs_*.csv")):
        for row in read_csv(path.relative_to(ROOT).as_posix()):
            for column in ("raw_output_file", "parsed_spec_file"):
                value = row.get(column, "").strip()
                if not value:
                    continue
                target = ROOT / Path(value.replace("\\", "/"))
                checked += 1
                if not target.is_file():
                    fail(f"broken {column} reference in {path.name}: {value}")
    return checked


def validate_headlines() -> None:
    ambiguity = read_csv("diagnostic_suite/ambiguity_benchmark.csv")
    assert_equal("ambiguity rows", len(ambiguity), 30)
    assert_equal("ambiguity correct", sum(row["correct"].lower() == "true" for row in ambiguity), 30)

    pre_solve = read_csv("diagnostic_suite/pre_solve_benchmark.csv")
    assert_equal("pre-solve issue sets", len(pre_solve), 8)
    assert_equal("pre-solve passes", sum(row["passed"].lower() == "true" for row in pre_solve), 8)

    rails = read_csv("diagnostic_suite/safety_rail_ablation.csv")
    assert_equal("safety-rail rows", len(rails), 8)
    assert_equal("caught with rails", sum(row["with_safety_blocks_or_flags"].lower() == "true" for row in rails), 8)
    assert_equal("caught without rails", sum(row["without_safety_blocks_or_flags"].lower() == "true" for row in rails), 0)

    for relative, expected_matches, expected_total in (
        ("diagnostic_suite/rule_only_ablation.csv", 89, 90),
        ("diagnostic_suite/rule_only_challenge_ablation.csv", 67, 90),
        ("diagnostic_suite/expanded_prompt_generalization.csv", 652, 900),
    ):
        rows = read_csv(relative)
        assert_equal(relative + " field matches", sum(int(row["field_matches"]) for row in rows), expected_matches)
        assert_equal(relative + " field total", sum(int(row["field_total"]) for row in rows), expected_total)

    template = read_csv("diagnostic_suite/template_workflow_baseline.csv")
    assert_equal("template proxy rows", len(template), 121)
    assert_close(
        "template mean manual fields",
        sum(float(row["manual_completion_fields"]) for row in template) / len(template),
        4.09,
    )

    for relative, expected_rows, expected_mean in (
        ("model_checks/live_model_runs_repeated_20260612.csv", 150, 0.794),
        ("model_checks/live_model_runs_repeated_t03_20260612.csv", 150, 0.790),
    ):
        rows = read_csv(relative)
        assert_equal(relative + " rows", len(rows), expected_rows)
        assert_equal(relative + " parseable", sum(row["parse_success"].lower() == "true" for row in rows), expected_rows)
        scored = [float(row["field_accuracy"]) for row in rows if row["field_accuracy"].strip()]
        assert_close(relative + " mean accuracy", sum(scored) / len(scored), expected_mean)

    cross = read_csv("model_checks/live_model_runs_cross_family_20260612c.csv")
    assert_equal("cross-family rows", len(cross), 60)
    assert_equal("cross-family parseable", sum(row["parse_success"].lower() == "true" for row in cross), 33)

    retry = read_csv("post_solve_retry/post_solve_retry_recovery.csv")
    by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in retry:
        by_case[row["case"]].append(row)
    assert_equal("retry cases", len(by_case), 12)
    assert_equal(
        "retry recovered cases",
        sum(any(row["passed"].lower() == "true" for row in rows) for rows in by_case.values()),
        12,
    )

    mesh = json.loads((ROOT / "diagnostic_suite/mesh_sensitivity/normalized_bracket_mesh_sensitivity.json").read_text(encoding="utf-8"))
    mesh_rows = mesh.get("cases", mesh.get("rows", []))
    assert_equal("normalized-bracket mesh cases", len(mesh_rows), 3)
    assert_equal("normalized-bracket mesh passes", sum(bool(row.get("evaluation_passed")) for row in mesh_rows), 3)

    stable = json.loads((ROOT / "stable_configurator/configurator_results.json").read_text(encoding="utf-8"))
    assert_equal("stable configurator cases", stable.get("n_tested"), 15)
    assert_equal("stable configurator all-pass rate", stable.get("all_pass_rate"), 1.0)
    assert_equal("stable configurator schema-valid rate", stable.get("spec_valid_rate"), 1.0)

    suite_3d = json.loads((ROOT / "backend_3d/results_3d_suite/suite_summary.json").read_text(encoding="utf-8"))
    rows_3d = suite_3d.get("rows", [])
    assert_equal("bounded 3-D rows", len(rows_3d), 5)
    assert_equal("bounded 3-D passing rows", sum(row.get("status") == "pass" for row in rows_3d), 5)
    assert_equal("bounded 3-D portable root", suite_3d.get("revision_root"), "reproducibility")


def validate_portability_and_secrets() -> None:
    private_path = re.compile(r"(?i)(?:[A-Z]:\\(?:Users|AI\\AUTO)\\|[A-Z]:\\\\(?:Users|AI\\\\AUTO)\\\\)")
    secret_patterns = (
        re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
        re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
        re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    )
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".npy", ".pdf"}:
            continue
        if path.name in {"portableize_archive.py", "verify_archive.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if private_path.search(text):
            fail(f"private absolute path remains in {path.relative_to(ROOT)}")
        if "<redacted-local-path>" in text:
            fail(f"unresolved redacted path placeholder remains in {path.relative_to(ROOT)}")
        if "multi_model_protocol\\live_outputs_" in text or "multi_model_protocol/live_outputs_" in text:
            fail(f"stale model-output path remains in {path.relative_to(ROOT)}")
        for pattern in secret_patterns:
            if pattern.search(text):
                fail(f"possible credential in {path.relative_to(ROOT)}")


def validate_manifest() -> int:
    manifest = ROOT / "SHA256SUMS.csv"
    if not manifest.exists():
        fail("SHA256SUMS.csv is missing")
        return 0
    rows = read_csv("SHA256SUMS.csv")
    expected_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path.name != manifest.name
        and "__pycache__" not in path.parts
    }
    listed_files = {row["path"] for row in rows}
    if listed_files != expected_files:
        fail(
            f"manifest file set differs: missing={sorted(expected_files - listed_files)}, "
            f"extra={sorted(listed_files - expected_files)}"
        )
    for row in rows:
        path = ROOT / Path(row["path"])
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            fail(f"hash mismatch: {row['path']}")
    return len(rows)


def main() -> int:
    json_count, csv_count = validate_json_and_csv()
    reference_count = validate_model_references()
    validate_headlines()
    validate_portability_and_secrets()
    manifest_count = validate_manifest()
    report = {
        "status": "pass" if not ERRORS else "fail",
        "json_files_parsed": json_count,
        "csv_files_parsed": csv_count,
        "model_file_references_checked": reference_count,
        "manifest_entries_checked": manifest_count,
        "errors": ERRORS,
    }
    print(json.dumps(report, indent=2))
    return 0 if not ERRORS else 1


if __name__ == "__main__":
    sys.exit(main())
