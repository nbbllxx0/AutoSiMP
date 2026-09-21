"""Convert copied experiment paths to portable archive-relative paths.

This script is intentionally limited to files under ``reproducibility``. It
does not change scientific values; it only rewrites path-bearing strings in
CSV, JSON, and retained text logs.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s\",]+")


def portable_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    lower = normalized.lower()

    if normalized.startswith("multi_model_protocol/live_outputs_"):
        return "model_checks/raw_outputs/" + normalized.removeprefix(
            "multi_model_protocol/"
        )

    markers = (
        ("/results_3d_large/", "backend_3d/results_3d_large/"),
        ("/results_3d_suite/", "backend_3d/results_3d_suite/"),
        ("/mesh_sensitivity/", "diagnostic_suite/mesh_sensitivity/"),
        ("/normalized_bracket_solve/", "diagnostic_suite/normalized_bracket_solve/"),
    )
    if re.match(r"^[A-Za-z]:/", normalized):
        for marker, replacement in markers:
            if marker in normalized:
                return replacement + normalized.split(marker, 1)[1]
        if lower.endswith("python.exe"):
            return "python"
        if "topogpu_tmp_open" in lower:
            return "<temporary-directory>"
        return "<redacted-local-path>"

    if normalized.startswith("experiments_3d_upgrade/results_3d_suite/"):
        return normalized.replace(
            "experiments_3d_upgrade/results_3d_suite/",
            "backend_3d/results_3d_suite/",
            1,
        )
    if normalized == "experiments_3d_upgrade/run_topogpu_with_temp_patch.py":
        return "backend_3d/run_topogpu_with_temp_patch.py"
    if normalized == "experiment_results_major_overhaul/normalized_bracket_case.csv":
        return "diagnostic_suite/normalized_bracket_case.csv"
    return value


def transform_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: transform_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [transform_json(item) for item in value]
    if isinstance(value, str):
        return portable_path(value)
    return value


def rewrite_json(path: Path) -> bool:
    original = json.loads(path.read_text(encoding="utf-8"))
    transformed = transform_json(original)
    if transformed == original:
        return False
    path.write_text(json.dumps(transformed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def rewrite_csv(path: Path) -> bool:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames:
        return False
    transformed = [
        {key: portable_path(value) if isinstance(value, str) else value for key, value in row.items()}
        for row in rows
    ]
    if transformed == rows:
        return False
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(transformed)
    return True


def rewrite_text(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    transformed = WINDOWS_PATH.sub(lambda match: portable_path(match.group(0)), original)
    if transformed == original:
        return False
    path.write_text(transformed, encoding="utf-8")
    return True


def main() -> int:
    changed: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == Path(__file__).name:
            continue
        try:
            if path.suffix.lower() == ".json":
                did_change = rewrite_json(path)
            elif path.suffix.lower() == ".csv":
                did_change = rewrite_csv(path)
            elif path.suffix.lower() in {".txt", ".md", ".yaml", ".yml"}:
                did_change = rewrite_text(path)
            else:
                continue
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if did_change:
            changed.append(path.relative_to(ROOT).as_posix())
    print(json.dumps({"changed_files": changed, "count": len(changed)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
