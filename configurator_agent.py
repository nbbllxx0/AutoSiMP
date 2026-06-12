"""
configurator_agent.py
---------------------
LLM agent that parses a natural-language topology optimization problem
description into a validated ProblemSpec JSON.

Same DNC pattern as pub_llm_agent.py:
  - Structured JSON output (responseMimeType = application/json)
  - Gemini Flash Lite via raw REST
  - Deterministic safety rails: clamp, validate, reject impossible physics
  - Graceful fallback to a default cantilever when API is unavailable
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from problem_spec import (
    ProblemSpec,
    PointSupport, EdgeSupport,
    PointLoad, DistributedLoad,
    CircularRegion, RectangularRegion,
)

# ---------------------------------------------------------------------------
# System prompt — domain knowledge for the configurator
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a topology optimization problem configurator.  The user describes a
structural design problem in natural language.  You output a JSON specification
that a SIMP solver can consume.

OUTPUT FORMAT — respond ONLY with this JSON (no markdown, no extra text):
{
  "Lx": <float>,        // domain length in x
  "Ly": <float>,        // domain height in y
  "Lz": <float>,        // depth (0 for 2D)
  "nelx": <int>,        // elements in x (30-200 typical)
  "nely": <int>,        // elements in y (15-100 typical)
  "nelz": <int>,        // elements in z (0 for 2D)
  "E": <float>,         // Young's modulus (use 1.0 unless specified)
  "nu": <float>,        // Poisson's ratio (default 0.3)
  "volfrac": <float>,   // volume fraction (0.01-0.99, default 0.5)
  "supports": [
    {"type": "edge",  "edge": "left"|"right"|"top"|"bottom"|"front"|"back",
     "constraint": "fixed"|"pin_x"|"pin_y"|"roller_x"|"roller_y"},
    {"type": "point", "x": <float>, "y": <float>, "z": <float>,
     "constraint": "fixed"|"pin_x"|"pin_y"|"roller_x"|"roller_y"}
  ],
  "loads": [
    {"type": "point", "x": <float>, "y": <float>, "z": <float>,
     "fx": <float>, "fy": <float>, "fz": <float>},
    {"type": "distributed", "edge": "left"|"right"|"top"|"bottom",
     "magnitude": <float>}
  ],
  "passive_regions": [
    {"type": "circle", "cx": <float>, "cy": <float>, "radius": <float>,
     "kind": "void"|"solid"},
    {"type": "rect", "x0": <float>, "y0": <float>, "x1": <float>,
     "y1": <float>, "kind": "void"|"solid"}
  ],
  "max_iter": <int|null>,
  "rmin": <float|null>
}

INTERPRETATION RULES:
- "cantilever" = left edge fully fixed, point load at mid-right edge, downward.
- "MBB beam" = left edge pin_x (symmetry), bottom-right point pin_y, top-left downward load.
- "bridge" = bottom-left and bottom-right supports, distributed load on top.
- "bracket" = left edge fixed, load on right side.
- "simply supported" = bottom-left pin_y + bottom-right pin_y (or roller).
- Mesh resolution: aim for aspect ratio ≈ Lx/Ly.  Default ~60×30 for 2D.
  If user says "fine mesh" use 120×60+.  If "coarse" use 40×20.
- Coordinates: origin at BOTTOM-LEFT.  x goes right, y goes up.
- Loads default to -1.0 (downward) unless specified.  Use fy=-1.0 for "downward".
- "Hole", "bolt hole", "cutout" → circular void passive region.
- "Reinforced zone", "solid insert" → solid passive region.
- If user specifies physical units (kN, mm, MPa), keep the numbers but note
  the solver normalizes E=1 internally.

PHYSICAL SANITY:
- Every problem MUST have at least one support AND one load.
- Loads should NOT be placed on fully-fixed supports.
- Domain must be positive (Lx>0, Ly>0).
- Volume fraction must be 0.01-0.99 (0.3-0.6 typical).
"""


# ---------------------------------------------------------------------------
# Gemini REST call (same pattern as pub_llm_agent.py)
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, model: str, api_key: str,
                 temperature: float = 0.0) -> tuple[Optional[dict], Optional[str]]:
    """Call Gemini, return (parsed_dict, error_string)."""
    model_path = model if model.startswith("models/") else f"models/{model}"
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"{model_path}:generateContent?key={api_key}")

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        candidates = resp_json.get("candidates", [])
        if not candidates:
            return None, f"No candidates in response: {resp_json}"
        raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        text = raw.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {body}"
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except Exception as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# Safety rails — validate and repair LLM output
# ---------------------------------------------------------------------------

def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _sanitize_spec_dict(d: dict) -> tuple[dict, list[str]]:
    """
    Clamp values to physically meaningful ranges.
    Return (cleaned_dict, list_of_warnings).
    """
    warnings: list[str] = []

    # Domain
    d["Lx"] = max(0.1, float(d.get("Lx", 2.0)))
    d["Ly"] = max(0.1, float(d.get("Ly", 1.0)))
    d["Lz"] = max(0.0, float(d.get("Lz", 0.0)))

    # Mesh
    d["nelx"] = int(_clamp(d.get("nelx", 60), 4, 400))
    d["nely"] = int(_clamp(d.get("nely", 30), 4, 200))
    d["nelz"] = int(max(0, d.get("nelz", 0)))
    if d["Lz"] > 0 and d["nelz"] < 2:
        d["nelz"] = max(2, int(d["nelx"] * d["Lz"] / d["Lx"]))
        warnings.append(f"Auto-set nelz={d['nelz']} for 3D domain.")

    # Material
    d["E"] = max(1e-6, float(d.get("E", 1.0)))
    d["nu"] = float(_clamp(d.get("nu", 0.3), -0.99, 0.49))

    # Volume fraction
    d["volfrac"] = float(_clamp(d.get("volfrac", 0.5), 0.01, 0.99))

    # Supports: ensure at least one
    if not d.get("supports"):
        d["supports"] = [{"type": "edge", "edge": "left", "constraint": "fixed"}]
        warnings.append("No supports specified — defaulted to left edge fixed.")

    # Loads: ensure at least one
    if not d.get("loads"):
        d["loads"] = [{"type": "point", "x": d["Lx"], "y": d["Ly"] / 2,
                       "z": 0.0, "fx": 0.0, "fy": -1.0, "fz": 0.0}]
        warnings.append("No loads specified — defaulted to mid-right downward point load.")

    # Clamp load coordinates to domain
    for ld in d.get("loads", []):
        if ld.get("type") == "point":
            ld["x"] = float(_clamp(ld.get("x", 0), 0, d["Lx"]))
            ld["y"] = float(_clamp(ld.get("y", 0), 0, d["Ly"]))
            ld["z"] = float(_clamp(ld.get("z", 0), 0, max(d["Lz"], 0)))

    # Clamp support coordinates to domain
    for sup in d.get("supports", []):
        if sup.get("type") == "point":
            sup["x"] = float(_clamp(sup.get("x", 0), 0, d["Lx"]))
            sup["y"] = float(_clamp(sup.get("y", 0), 0, d["Ly"]))
            sup["z"] = float(_clamp(sup.get("z", 0), 0, max(d["Lz"], 0)))

    # Clamp passive regions to domain
    for pr in d.get("passive_regions", []):
        if pr.get("type") == "circle":
            pr["cx"] = float(_clamp(pr.get("cx", 0), 0, d["Lx"]))
            pr["cy"] = float(_clamp(pr.get("cy", 0), 0, d["Ly"]))
            pr["radius"] = max(0.01, float(pr.get("radius", 0.1)))
        elif pr.get("type") == "rect":
            pr["x0"] = float(_clamp(pr.get("x0", 0), 0, d["Lx"]))
            pr["y0"] = float(_clamp(pr.get("y0", 0), 0, d["Ly"]))
            pr["x1"] = float(_clamp(pr.get("x1", 0), 0, d["Lx"]))
            pr["y1"] = float(_clamp(pr.get("y1", 0), 0, d["Ly"]))
            if pr["x0"] >= pr["x1"]:
                pr["x0"], pr["x1"] = pr["x1"], pr["x0"] + 0.01
            if pr["y0"] >= pr["y1"]:
                pr["y0"], pr["y1"] = pr["y1"], pr["y0"] + 0.01

    # Optional solver hints
    if d.get("max_iter") is not None:
        d["max_iter"] = int(_clamp(d["max_iter"], 20, 2000))
    if d.get("rmin") is not None:
        d["rmin"] = float(_clamp(d["rmin"], 1.1, 4.0))

    return d, warnings


# ---------------------------------------------------------------------------
# Default fallback problem (no API needed)
# ---------------------------------------------------------------------------

DEFAULT_CANTILEVER = {
    "Lx": 2.0, "Ly": 1.0, "Lz": 0.0,
    "nelx": 60, "nely": 30, "nelz": 0,
    "E": 1.0, "nu": 0.3, "volfrac": 0.5,
    "supports": [{"type": "edge", "edge": "left", "constraint": "fixed"}],
    "loads": [{"type": "point", "x": 2.0, "y": 0.5, "z": 0.0,
               "fx": 0.0, "fy": -1.0, "fz": 0.0}],
    "passive_regions": [],
    "max_iter": None, "rmin": None,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ConfiguratorResult:
    """Bundle returned by configure()."""
    __slots__ = ("spec", "raw_dict", "warnings", "llm_used", "error")

    def __init__(self, spec, raw_dict, warnings, llm_used, error):
        self.spec = spec
        self.raw_dict = raw_dict
        self.warnings = warnings
        self.llm_used = llm_used
        self.error = error


def configure(
    prompt: str,
    model: str = "gemini-3.1-flash-lite-preview",
    api_key: Optional[str] = None,
    temperature: float = 0.0,
    verbose: bool = False,
) -> ConfiguratorResult:
    """
    Parse a natural-language problem description into a ProblemSpec.

    Parameters
    ----------
    prompt : str
        User's problem description in natural language.
    model : str
        Gemini model name.
    api_key : str or None
        If None, reads GEMINI_API_KEY env var.
    temperature : float
        LLM temperature (0.0 = deterministic).
    verbose : bool
        Print diagnostics.

    Returns
    -------
    ConfiguratorResult with:
        .spec       : ProblemSpec (validated, ready for bc_generator)
        .raw_dict   : dict the LLM returned (after sanitization)
        .warnings   : list[str] from sanitization
        .llm_used   : bool — True if LLM was called, False if fallback
        .error      : str or None
    """
    key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()

    if not key:
        if verbose:
            print("[Configurator] No API key — using default cantilever.")
        spec = ProblemSpec.from_dict(DEFAULT_CANTILEVER)
        return ConfiguratorResult(
            spec=spec, raw_dict=DEFAULT_CANTILEVER,
            warnings=["No API key — fell back to default cantilever."],
            llm_used=False, error=None)

    # Call LLM
    parsed, err = _call_gemini(prompt, model, key, temperature)

    if err or parsed is None:
        if verbose:
            print(f"[Configurator] LLM error: {err} — using default cantilever.")
        spec = ProblemSpec.from_dict(DEFAULT_CANTILEVER)
        return ConfiguratorResult(
            spec=spec, raw_dict=DEFAULT_CANTILEVER,
            warnings=["LLM call failed — fell back to default cantilever."],
            llm_used=False, error=err)

    # Sanitize
    cleaned, warnings = _sanitize_spec_dict(parsed)
    if verbose and warnings:
        for w in warnings:
            print(f"[Configurator] WARNING: {w}")

    # Build ProblemSpec
    spec = ProblemSpec.from_dict(cleaned)

    # Validate (ProblemSpec's own physical checks)
    errors = spec.validate()
    if errors:
        if verbose:
            for e in errors:
                print(f"[Configurator] VALIDATION ERROR: {e}")
        # Try to use it anyway (sanitize should have fixed critical issues)
        # but propagate warnings
        warnings.extend(errors)

    if verbose:
        print(f"[Configurator] {spec.nelx}×{spec.nely}"
              + (f"×{spec.nelz}" if spec.is_3d else "")
              + f"  vf={spec.volfrac}"
              + f"  supports={len(spec.supports)}"
              + f"  loads={len(spec.loads)}"
              + f"  passive={len(spec.passive_regions)}")

    return ConfiguratorResult(
        spec=spec, raw_dict=cleaned, warnings=warnings,
        llm_used=True, error=None)


# ---------------------------------------------------------------------------
# CLI quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    test_prompts = [
        "A cantilever beam, 3:1 aspect ratio, left edge fixed, "
        "downward point load at the middle of the right edge. 50% volume fraction.",

        "MBB beam with fine mesh. Symmetry BC on the left, roller at bottom right, "
        "downward load at top left corner.",

        "Bridge structure, 4m wide, 1m tall. Pinned supports at both bottom corners. "
        "Uniform downward load on the top edge. Volume fraction 0.3. "
        "There's a circular hole at the center for a pipe, radius 0.15m.",

        "L-bracket: domain is 2x2, left half of the bottom edge is fixed, "
        "downward load at the tip of the right side, 40% material.",
    ]

    prompt = test_prompts[0] if len(sys.argv) < 2 else " ".join(sys.argv[1:])
    result = configure(prompt, verbose=True)
    print()
    print("=== Result ===")
    print(f"LLM used: {result.llm_used}")
    print(f"Error:    {result.error}")
    print(f"Warnings: {result.warnings}")
    print(json.dumps(result.raw_dict, indent=2))
