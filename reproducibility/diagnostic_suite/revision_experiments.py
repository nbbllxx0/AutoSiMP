"""Major-overhaul validation experiments for the AutoSiMP manuscript.

This harness covers validation checks that can be run locally without
new API calls or human subjects:

- ambiguity detection benchmark;
- pre-solve model-validity checks on deliberately invalid specifications;
- rule-only parser ablation against the existing pipeline prompts;
- template-style configuration baseline proxy;
- normalized engineering-style bracket workflow case;
- optional bounded retry stress solves.

It writes JSON, CSV, and a compact Markdown summary into the output directory.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
REVISION_ROOT = THIS_DIR.parent
WORKSPACE_ROOT = REVISION_ROOT.parent
IMPL_ROOT = WORKSPACE_ROOT
sys.path.insert(0, str(IMPL_ROOT))

from problem_spec import (  # noqa: E402
    CircularRegion,
    DistributedLoad,
    EdgeSupport,
    PointLoad,
    PointSupport,
    ProblemSpec,
    RectangularRegion,
)


PIPELINE_TEST_CASES = [
    {
        "name": "cantilever_basic",
        "prompt": "Cantilever beam. Left edge is clamped. Downward point load at the center of the right edge. 50% volume fraction.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
        ),
    },
    {
        "name": "mbb_beam",
        "prompt": "MBB beam, 3:1 aspect ratio. Symmetry boundary condition on the left edge, roller support at the bottom right corner. Downward load at the top left corner. Half material.",
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.5,
            supports=[
                EdgeSupport(edge="left", constraint="pin_x"),
                PointSupport(x=3.0, y=0.0, constraint="pin_y"),
            ],
            loads=[PointLoad(x=0.0, y=1.0, fy=-1.0)],
        ),
    },
    {
        "name": "bridge",
        "prompt": "Bridge structure. 4 meters wide, 1 meter tall. Bottom edge supported vertically (pin_y). Uniform downward pressure on the top edge. Use 30% material.",
        "spec": ProblemSpec(
            Lx=4.0, Ly=1.0, nelx=120, nely=30, volfrac=0.3,
            supports=[EdgeSupport(edge="bottom", constraint="pin_y")],
            loads=[DistributedLoad(edge="top", magnitude=-1.0)],
        ),
    },
    {
        "name": "cantilever_with_hole",
        "prompt": "Cantilever beam, left edge fixed, tip load downward at mid-right. There's a circular hole in the center of the beam for a pipe, radius 0.15. Use 40% volume fraction.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
            passive_regions=[CircularRegion(cx=1.0, cy=0.5, radius=0.15, kind="void")],
        ),
    },
    {
        "name": "deep_beam_shear",
        "prompt": "Short deep cantilever: 1 unit wide, 2 units tall. Left edge clamped. Downward load at the midpoint of the right edge. 50 percent material.",
        "spec": ProblemSpec(
            Lx=1.0, Ly=2.0, nelx=30, nely=60, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=1.0, y=1.0, fy=-1.0)],
        ),
    },
    {
        "name": "simply_supported_center",
        "prompt": "Simply supported beam. Fixed supports at both bottom corners. Point load at the top center, going down. 50% volume fraction. 3 to 1 aspect ratio.",
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.5,
            supports=[
                PointSupport(x=0.0, y=0.0, constraint="fixed"),
                PointSupport(x=3.0, y=0.0, constraint="fixed"),
            ],
            loads=[PointLoad(x=1.5, y=1.0, fy=-1.0)],
        ),
    },
    {
        "name": "cantilever_low_vf",
        "prompt": "Lightweight cantilever beam. Left wall fixed. Load at the tip pointing down. Only 30% material allowed.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.3,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
        ),
    },
    {
        "name": "dual_load",
        "prompt": "Cantilever with two loads: one at the upper-right and one at the lower-right, both pushing down. Left edge is fixed. 50% volume fraction.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[
                PointLoad(x=2.0, y=0.75, fy=-1.0),
                PointLoad(x=2.0, y=0.25, fy=-1.0),
            ],
        ),
    },
    {
        "name": "lbracket",
        "prompt": "L-bracket: square domain 2x2. Top edge fixed to the wall. Horizontal load pointing right at the lower part of the right edge. 40% material.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=2.0, nelx=60, nely=60, volfrac=0.4,
            supports=[EdgeSupport(edge="top", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fx=1.0)],
        ),
    },
    {
        "name": "high_aspect",
        "prompt": "Very long cantilever, 6 to 1 aspect ratio. Fixed on the left. Downward tip load. 50% volume fraction.",
        "spec": ProblemSpec(
            Lx=6.0, Ly=1.0, nelx=120, nely=20, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=6.0, y=0.5, fy=-1.0)],
        ),
    },
]


def compare_specs(gt_spec: ProblemSpec, test_spec: ProblemSpec) -> dict[str, Any]:
    def support_sig(s: PointSupport | EdgeSupport) -> tuple[Any, ...]:
        if isinstance(s, EdgeSupport):
            return ("edge", s.edge, s.constraint)
        return ("point", round(s.x, 2), round(s.y, 2), s.constraint)

    def load_sig(load: PointLoad | DistributedLoad) -> tuple[Any, ...]:
        if isinstance(load, DistributedLoad):
            return ("distributed", load.edge, round(load.magnitude, 2))
        return (
            "point",
            round(load.x, 2),
            round(load.y, 2),
            math.copysign(1, load.fx) if abs(load.fx) > 1e-9 else 0,
            math.copysign(1, load.fy) if abs(load.fy) > 1e-9 else 0,
        )

    def passive_sig(region: CircularRegion | RectangularRegion) -> tuple[Any, ...]:
        if isinstance(region, CircularRegion):
            return ("circle", round(region.cx, 2), round(region.cy, 2), round(region.radius, 2), region.kind)
        return (
            "rect",
            round(region.x0, 2),
            round(region.y0, 2),
            round(region.x1, 2),
            round(region.y1, 2),
            region.kind,
        )

    gt_supports = sorted(support_sig(s) for s in gt_spec.supports)
    test_supports = sorted(support_sig(s) for s in test_spec.supports)
    gt_loads = sorted(load_sig(load) for load in gt_spec.loads)
    test_loads = sorted(load_sig(load) for load in test_spec.loads)
    gt_passive = sorted(passive_sig(region) for region in gt_spec.passive_regions)
    test_passive = sorted(passive_sig(region) for region in test_spec.passive_regions)

    return {
        "Lx_match": abs(gt_spec.Lx - test_spec.Lx) < 0.05,
        "Ly_match": abs(gt_spec.Ly - test_spec.Ly) < 0.05,
        "mesh_reasonable": (
            0.5 <= test_spec.nelx / max(gt_spec.nelx, 1) <= 2.0
            and 0.5 <= test_spec.nely / max(gt_spec.nely, 1) <= 2.0
        ),
        "volfrac_match": abs(gt_spec.volfrac - test_spec.volfrac) < 0.05,
        "n_supports_match": len(gt_spec.supports) == len(test_spec.supports),
        "n_loads_match": len(gt_spec.loads) == len(test_spec.loads),
        "n_passive_match": len(gt_spec.passive_regions) == len(test_spec.passive_regions),
        "support_semantics_match": gt_supports == test_supports,
        "load_semantics_match": gt_loads == test_loads,
        "passive_semantics_match": gt_passive == test_passive,
    }


AMBIGUITY_TERMS = {
    "near": r"\bnear\b",
    "around": r"\baround\b",
    "mid-right": r"\bmid[- ]right\b",
    "middle-ish": r"\bmiddle[- ]?ish\b",
    "roughly": r"\broughly\b",
    "approximately": r"\bapproximately\b",
    "about": r"\babout\b",
    "under the hole": r"\bunder the hole\b",
    "on the bracket arm": r"\bon the bracket arm\b",
    "tip": r"\btip\b",
    "right side": r"\bright side\b",
    "upper part": r"\bupper part\b",
    "lower part": r"\blower part\b",
    "center-ish": r"\bcenter[- ]?ish\b",
    "left-ish": r"\bleft[- ]?ish\b",
}


AMBIGUITY_CASES = [
    ("cantilever with a downward load near the right side", True),
    ("load at mid-right of the bracket arm", True),
    ("put a support around the lower-left area", True),
    ("apply force under the hole", True),
    ("load on the upper part of the right side", True),
    ("force at the tip of the L bracket", True),
    ("support somewhere near the base", True),
    ("hole approximately in the middle-ish region", True),
    ("load center-ish on the right side", True),
    ("roller near the bottom-right corner", True),
    ("force on the bracket arm, roughly horizontal", True),
    ("fix the left-ish end and load the far side", True),
    ("load at x=2.0, y=0.5, fy=-1.0", False),
    ("left edge fixed; point load at (2.0, 0.5)", False),
    ("bottom-left pin_y and bottom-right pin_y", False),
    ("distributed load on the top edge", False),
    ("circular void centered at (1.0, 0.5) with radius 0.15", False),
    ("MBB beam: pin_x on left edge, pin_y at bottom-right, load at top-left", False),
    ("domain 4 by 1, bottom edge pin_y, top distributed load magnitude -1", False),
    ("3D cantilever: left face fixed, load at (2,0.5,0.25)", False),
    ("rectangular void x0=1.0 y0=0.4 x1=1.3 y1=0.6", False),
    ("volume fraction 0.4, nelx=80, nely=40", False),
    ("fixed support at point (0,0)", False),
    ("load at top-right corner, x=2, y=1, fy=-1", False),
    ("passive solid region from x=1.8 to 2.0 and y=0.35 to 0.65", False),
    ("left edge fixed and two loads at (2,0.75), (2,0.25)", False),
    ("right edge roller_x with distributed load on top edge", False),
    ("support at bottom-left, roller at bottom-right, load at top center", False),
    ("domain 2x2 with top edge fixed and right-face load at y=0.5", False),
    ("cantilever, left edge fixed, right midpoint load", False),
]


RULE_CHALLENGE_CASES = [
    {
        "name": "western_clamped_free_tip",
        "prompt": "A beam is clamped along the western boundary and pulled downward at the free-end midpoint.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
        ),
    },
    {
        "name": "eastern_wall_left_load",
        "prompt": "Use an eastern wall clamp and apply a downward force at the midpoint of the opposite free side.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
            supports=[EdgeSupport(edge="right", constraint="fixed")],
            loads=[PointLoad(x=0.0, y=0.5, fy=-1.0)],
        ),
    },
    {
        "name": "load_rightward_midspan",
        "prompt": "Clamp the left wall and push the free end horizontally to the right at mid-height.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fx=1.0)],
        ),
    },
    {
        "name": "multi_load_mixed_direction",
        "prompt": "Left wall fixed; one downward force at the upper free corner and one upward force at the lower free corner.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=1.0, fy=-1.0), PointLoad(x=2.0, y=0.0, fy=1.0)],
        ),
    },
    {
        "name": "void_off_center",
        "prompt": "Cantilever with a pipe cutout one third from the clamp and centered vertically.",
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=3.0, y=0.5, fy=-1.0)],
            passive_regions=[CircularRegion(cx=1.0, cy=0.5, radius=0.15, kind="void")],
        ),
    },
    {
        "name": "solid_bolt_plate",
        "prompt": "Keep a solid bolt plate at the loaded end of a cantilever, centered around mid-height.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=1.0, nelx=80, nely=40, volfrac=0.5,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
            passive_regions=[RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid")],
        ),
    },
    {
        "name": "top_clamped_bracket",
        "prompt": "For an L-shaped bracket, attach the upper edge to the wall and pull the lower right side horizontally outward.",
        "spec": ProblemSpec(
            Lx=2.0, Ly=2.0, nelx=60, nely=60, volfrac=0.4,
            supports=[EdgeSupport(edge="top", constraint="fixed")],
            loads=[PointLoad(x=2.0, y=0.5, fx=1.0)],
        ),
    },
    {
        "name": "roller_language",
        "prompt": "Model a three-unit beam with a vertical restraint at each bottom corner and a downward load at top center.",
        "spec": ProblemSpec(
            Lx=3.0, Ly=1.0, nelx=90, nely=30, volfrac=0.5,
            supports=[PointSupport(x=0.0, y=0.0, constraint="pin_y"), PointSupport(x=3.0, y=0.0, constraint="pin_y")],
            loads=[PointLoad(x=1.5, y=1.0, fy=-1.0)],
        ),
    },
    {
        "name": "distributed_bottom_support",
        "prompt": "A bridge-like span with vertical support along the underside and pressure over the deck.",
        "spec": ProblemSpec(
            Lx=4.0, Ly=1.0, nelx=120, nely=30, volfrac=0.3,
            supports=[EdgeSupport(edge="bottom", constraint="pin_y")],
            loads=[DistributedLoad(edge="top", magnitude=-1.0)],
        ),
    },
    {
        "name": "fine_mesh_words",
        "prompt": "Use a high-resolution four-to-one cantilever with forty percent material.",
        "spec": ProblemSpec(
            Lx=4.0, Ly=1.0, nelx=120, nely=30, volfrac=0.4,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[PointLoad(x=4.0, y=0.5, fy=-1.0)],
        ),
    },
]


def expanded_prompt_generalization_cases() -> list[dict[str, Any]]:
    """A larger held-out prompt set for rule-only and template burden checks.

    These prompts are author-defined diagnostic cases, not participant-authored
    user-study data. They deliberately stress paraphrase, spatial language,
    multi-loads, passive regions, and ambiguous-but-supported wording.
    """

    def clone(case: dict[str, Any]) -> ProblemSpec:
        return copy.deepcopy(case["spec"])

    base = {case["name"]: case for case in PIPELINE_TEST_CASES}
    cases: list[dict[str, Any]] = []

    def add(name: str, category: str, prompt: str, spec: ProblemSpec) -> None:
        cases.append({"name": name, "category": category, "prompt": prompt, "spec": spec})

    paraphrases = [
        ("p01_cantilever_wall", "Make a rectangular cantilever; clamp the left wall and put a downward force halfway up the free right edge.", clone(base["cantilever_basic"])),
        ("p02_mbb_words", "Use the standard MBB setup with left symmetry, a vertical roller at the lower right, and a downward load at the upper left.", clone(base["mbb_beam"])),
        ("p03_bridge_deck", "Bridge-like span: support the underside vertically and apply uniform deck pressure downward; use thirty percent material.", clone(base["bridge"])),
        ("p04_pipe_cutout", "Cantilever with a central circular pipe cutout, fixed left side, and a downward right-midpoint tip load.", clone(base["cantilever_with_hole"])),
        ("p05_tall_short_beam", "A short deep beam, taller than it is wide, clamped on the left and loaded downward at the right-side midpoint.", clone(base["deep_beam_shear"])),
        ("p06_two_corner_supports", "Support the two lower corners and load the top center downward in a three-to-one beam.", clone(base["simply_supported_center"])),
        ("p07_lightweight_tip", "Only allow 30 percent material in a left-clamped cantilever with a downward load at the free tip.", clone(base["cantilever_low_vf"])),
        ("p08_two_down_forces", "Left-clamped beam with two downward forces, one high and one low on the right boundary.", clone(base["dual_load"])),
        ("p09_l_shape_outward", "L bracket, top fixed, square domain, pull the lower-right side horizontally outward.", clone(base["lbracket"])),
        ("p10_slender_beam", "Slender six-to-one cantilever, fixed on the west side, with a downward free-end load.", clone(base["high_aspect"])),
    ]
    for name, prompt, spec in paraphrases:
        add(name, "paraphrased_canonical", prompt, spec)

    spatial_specs = [
        ("s01_west_clamp", "Clamp the west boundary and push down at the east midpoint.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)])),
        ("s02_east_clamp", "Clamp the east boundary and push down at the west midpoint.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="right", constraint="fixed")], loads=[PointLoad(x=0, y=0.5, fy=-1)])),
        ("s03_south_support", "Use a southern vertical support and load the northern edge with downward pressure.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1)])),
        ("s04_north_clamp", "Attach the top edge and pull the lower-right point outward.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)])),
        ("s05_upper_corner", "Left wall fixed; apply a downward point load at the upper free corner.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=1, fy=-1)])),
        ("s06_lower_corner", "Left wall fixed; apply an upward point load at the lower free corner.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0, fy=1)])),
        ("s07_midheight_horizontal", "Left edge clamped, free side pushed to the right at mid-height.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)])),
        ("s08_bottom_corners_pin", "A three-unit beam with vertical restraints at both bottom corners and a top-center downward load.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.5, supports=[PointSupport(x=0, y=0, constraint="pin_y"), PointSupport(x=3, y=0, constraint="pin_y")], loads=[PointLoad(x=1.5, y=1, fy=-1)])),
        ("s09_right_face_pull", "Fix the top of a square bracket and pull the right face at one-quarter height.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)])),
        ("s10_free_end_tip", "A long six-by-one bar fixed at the western end, loaded downward at the free-end midpoint.", clone(base["high_aspect"])),
    ]
    for name, prompt, spec in spatial_specs:
        add(name, "spatial_language", prompt, spec)

    multi_load_specs = [
        ("m01_upper_lower_down", "Left edge fixed; downward forces at both the upper-right and lower-right points.", clone(base["dual_load"])),
        ("m02_opposed_vertical", "Left wall fixed; top-right force downward and bottom-right force upward.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=1, fy=-1), PointLoad(x=2, y=0, fy=1)])),
        ("m03_down_and_back", "Left-clamped bracket arm with a downward tip load and a smaller backward horizontal load at the same right-midpoint.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1), PointLoad(x=2, y=0.5, fx=-0.25)])),
        ("m04_pressure_plus_tip", "Bottom edge supports vertical motion; apply top pressure and an extra downward point load at midspan.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1), PointLoad(x=2, y=1, fy=-1)])),
        ("m05_three_point_loads", "Cantilever with three downward point loads equally spaced on the free right edge.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.25, fy=-1), PointLoad(x=2, y=0.5, fy=-1), PointLoad(x=2, y=0.75, fy=-1)])),
        ("m06_lbracket_two_forces", "Top-fixed square bracket with rightward pull low on the right side and a downward force at the outer corner.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1), PointLoad(x=2, y=0, fy=-1)])),
        ("m07_mbb_extra_tip", "MBB beam with the standard upper-left downward load and a second small downward load at midspan.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="pin_x"), PointSupport(x=3, y=0, constraint="pin_y")], loads=[PointLoad(x=0, y=1, fy=-1), PointLoad(x=1.5, y=1, fy=-0.5)])),
        ("m08_shear_pair", "A short deep left-clamped beam with one downward and one rightward load at the free-side midpoint.", ProblemSpec(Lx=1, Ly=2, nelx=30, nely=60, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=1, y=1, fy=-1), PointLoad(x=1, y=1, fx=0.5)])),
        ("m09_bridge_side_load", "Bridge span with vertical bottom support, deck pressure, and a small horizontal side load at the right end.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1), PointLoad(x=4, y=0.5, fx=-0.25)])),
        ("m10_split_tip_load", "Six-to-one cantilever with two downward loads bracketing the free-end midpoint.", ProblemSpec(Lx=6, Ly=1, nelx=120, nely=20, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=6, y=0.4, fy=-1), PointLoad(x=6, y=0.6, fy=-1)])),
    ]
    for name, prompt, spec in multi_load_specs:
        add(name, "multi_load", prompt, spec)

    passive_specs = [
        ("v01_center_void", "Left-clamped cantilever with a circular void at the center and a downward free-end load.", clone(base["cantilever_with_hole"])),
        ("v02_offcenter_void", "Cantilever with a circular cutout one third from the clamp, centered vertically.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=3, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1, cy=0.5, radius=0.15, kind="void")])),
        ("v03_two_bolt_holes", "Left-clamped bracket with two bolt-clearance holes near the mount and a downward right-midpoint load.", ProblemSpec(Lx=4, Ly=1.5, nelx=100, nely=38, volfrac=0.35, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=4, y=0.75, fy=-1)], passive_regions=[CircularRegion(cx=0.55, cy=0.45, radius=0.12, kind="void"), CircularRegion(cx=0.55, cy=1.05, radius=0.12, kind="void")])),
        ("v04_protected_pad", "Keep a protected solid pad at the loaded right end of a left-clamped beam.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v05_void_and_pad", "Cantilever with a central pipe void and a protected solid block at the loaded tip.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1, cy=0.5, radius=0.15, kind="void"), RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v06_rect_void", "Left-clamped beam with a rectangular window from x=0.8 to 1.1 and y=0.35 to 0.65.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[RectangularRegion(x0=0.8, y0=0.35, x1=1.1, y1=0.65, kind="void")])),
        ("v07_bridge_void", "Bridge span with a circular service opening at midspan and top pressure.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1)], passive_regions=[CircularRegion(cx=2, cy=0.5, radius=0.15, kind="void")])),
        ("v08_mbb_void", "MBB beam with a small circular void centered in the domain.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="pin_x"), PointSupport(x=3, y=0, constraint="pin_y")], loads=[PointLoad(x=0, y=1, fy=-1)], passive_regions=[CircularRegion(cx=1.5, cy=0.5, radius=0.12, kind="void")])),
        ("v09_lbracket_pad", "Top-fixed square bracket with a protected solid pad around the lower-right pull point.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)], passive_regions=[RectangularRegion(x0=1.75, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v10_slender_void", "Six-to-one cantilever with a small circular lightening hole near the root.", ProblemSpec(Lx=6, Ly=1, nelx=120, nely=20, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=6, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1.2, cy=0.5, radius=0.12, kind="void")])),
    ]
    for name, prompt, spec in passive_specs:
        add(name, "passive_region", prompt, spec)

    ambiguous_specs = [
        ("a01_near_tip", "Place the load near the free tip of a left-clamped beam.", clone(base["cantilever_basic"])),
        ("a02_under_hole", "Apply force under the pipe hole in a cantilever.", clone(base["cantilever_with_hole"])),
        ("a03_bracket_arm", "For the bracket, pull on the lower part of the right side.", clone(base["lbracket"])),
        ("a04_somewhere_base", "Support the beam somewhere near the base and load the far side.", clone(base["simply_supported_center"])),
        ("a05_high_resolution", "Use a high-resolution long cantilever with about half material.", clone(base["high_aspect"])),
        ("a06_around_mount", "Put two bolt holes around the mount and load the motor-pad side.", passive_specs[2][2]),
        ("a07_centerish_load", "Cantilever with the load center-ish on the right side.", clone(base["cantilever_basic"])),
        ("a08_upper_region", "Load the upper region of the free end and fix the left-ish side.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.75, fy=-1)])),
        ("a09_pressure_deck", "A bridge with pressure over the deck and supports along the underside.", clone(base["bridge"])),
        ("a10_tip_horizontal", "Push the tip horizontally on a top-mounted L bracket.", clone(base["lbracket"])),
    ]
    for name, prompt, spec in ambiguous_specs:
        add(name, "ambiguous_supported", prompt, spec)

    extra_paraphrases = [
        ("p11_cantilever_tip_synonym", "Design a left-wall fixed rectangular beam and press downward at the free-end midpoint.", clone(base["cantilever_basic"])),
        ("p12_mbb_support_synonym", "MBB beam: symmetry along the left edge, roller at the lower-right point, load down at the top-left point.", clone(base["mbb_beam"])),
        ("p13_bridge_uniform_deck", "Make a simply supported deck with vertical underside restraint and a uniformly downward top load.", clone(base["bridge"])),
        ("p14_cutout_cantilever", "A clamped beam with one round service opening in the middle and a vertical load at the right tip.", clone(base["cantilever_with_hole"])),
        ("p15_deep_shear_wall", "Tall short cantilever, west side fixed, downward load at the midpoint of the east side.", clone(base["deep_beam_shear"])),
        ("p16_two_end_supports", "Beam supported vertically at both lower end points with a vertical downward load at the top center.", clone(base["simply_supported_center"])),
        ("p17_low_volume_cantilever", "Use only 30% density for a left-clamped cantilever carrying a downward load at the free end.", clone(base["cantilever_low_vf"])),
        ("p18_pair_right_loads", "Clamped-left rectangle with two downward right-edge point forces, one near the top and one near the bottom.", clone(base["dual_load"])),
        ("p19_square_top_fixed_pull", "Square L-style bracket, top boundary fixed, horizontal pull at the lower part of the right boundary.", clone(base["lbracket"])),
        ("p20_long_narrow_free_load", "Long narrow cantilever fixed at the left end and loaded vertically downward at the free end.", clone(base["high_aspect"])),
    ]
    for name, prompt, spec in extra_paraphrases:
        add(name, "paraphrased_canonical", prompt, spec)

    extra_spatial_specs = [
        ("s11_left_boundary_midload", "Anchor the left boundary; apply a downward force at the middle of the opposite boundary.", clone(base["cantilever_basic"])),
        ("s12_right_boundary_midload", "Anchor the right boundary; apply a downward force at the middle of the opposite boundary.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="right", constraint="fixed")], loads=[PointLoad(x=0, y=0.5, fy=-1)])),
        ("s13_top_pressure_bottom_support", "Restrain the lower edge vertically and put a downward distributed load on the upper edge.", clone(base["bridge"])),
        ("s14_top_fixed_low_pull", "Fix the upper edge of a square bracket and pull outward at the lower-right side.", clone(base["lbracket"])),
        ("s15_upper_free_corner_down", "For a left-clamped rectangle, load the upper free corner downward.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=1, fy=-1)])),
        ("s16_lower_free_corner_up", "For a left-clamped rectangle, load the lower free corner upward.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0, fy=1)])),
        ("s17_mid_free_horizontal", "Clamp the west edge and push the east-edge midpoint horizontally outward.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)])),
        ("s18_bottom_end_rollers", "Give the two bottom ends vertical roller restraints and load the upper midpoint downward.", clone(base["simply_supported_center"])),
        ("s19_quarter_height_pull", "Top-fixed square bracket with a right-edge pull at about one quarter of the height.", clone(base["lbracket"])),
        ("s20_west_fixed_long_bar", "A six-unit bar fixed on the west side with a downward load at the east-side midpoint.", clone(base["high_aspect"])),
    ]
    for name, prompt, spec in extra_spatial_specs:
        add(name, "spatial_language", prompt, spec)

    extra_multi_load_specs = [
        ("m11_two_right_edge_down", "Left-clamped beam with downward point loads at the upper and lower right-edge locations.", clone(base["dual_load"])),
        ("m12_vertical_load_pair", "Left-fixed beam with one downward force at the upper free corner and one upward force at the lower free corner.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=1, fy=-1), PointLoad(x=2, y=0, fy=1)])),
        ("m13_same_point_two_components", "At the right midpoint of a left-clamped beam, apply a downward load and a smaller load pointing left.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1), PointLoad(x=2, y=0.5, fx=-0.25)])),
        ("m14_deck_pressure_midpoint", "Use bottom vertical support, top downward pressure, and an additional downward point force at the top-center.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1), PointLoad(x=2, y=1, fy=-1)])),
        ("m15_three_free_edge_forces", "Cantilever with three equal downward loads at quarter, half, and three-quarter height on the free side.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.25, fy=-1), PointLoad(x=2, y=0.5, fy=-1), PointLoad(x=2, y=0.75, fy=-1)])),
        ("m16_bracket_pull_and_drop", "Top-fixed bracket with a horizontal lower-right pull and a downward force at the outer corner.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1), PointLoad(x=2, y=0, fy=-1)])),
        ("m17_mbb_two_down_loads", "MBB setup with the normal upper-left load plus a smaller top-midspan downward point load.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="pin_x"), PointSupport(x=3, y=0, constraint="pin_y")], loads=[PointLoad(x=0, y=1, fy=-1), PointLoad(x=1.5, y=1, fy=-0.5)])),
        ("m18_deep_beam_two_components", "Short deep beam fixed left, with vertical downward and horizontal rightward loads at the free-side midpoint.", ProblemSpec(Lx=1, Ly=2, nelx=30, nely=60, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=1, y=1, fy=-1), PointLoad(x=1, y=1, fx=0.5)])),
        ("m19_pressure_and_side_push", "Bridge-like span with deck pressure and a small leftward push at the right side.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1), PointLoad(x=4, y=0.5, fx=-0.25)])),
        ("m20_two_tip_loads", "Long cantilever with two downward loads placed just above and below the free-end center.", ProblemSpec(Lx=6, Ly=1, nelx=120, nely=20, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=6, y=0.4, fy=-1), PointLoad(x=6, y=0.6, fy=-1)])),
    ]
    for name, prompt, spec in extra_multi_load_specs:
        add(name, "multi_load", prompt, spec)

    extra_passive_specs = [
        ("v11_round_mid_opening", "Left-fixed cantilever with one round opening at the domain center.", clone(base["cantilever_with_hole"])),
        ("v12_root_side_opening", "Three-by-one cantilever with a circular opening near the root and a downward right-end load.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=3, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1, cy=0.5, radius=0.15, kind="void")])),
        ("v13_mount_hole_pair", "Normalized bracket with two circular mounting holes near the fixed edge and a downward load at the far pad.", ProblemSpec(Lx=4, Ly=1.5, nelx=100, nely=38, volfrac=0.35, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=4, y=0.75, fy=-1)], passive_regions=[CircularRegion(cx=0.55, cy=0.45, radius=0.12, kind="void"), CircularRegion(cx=0.55, cy=1.05, radius=0.12, kind="void")])),
        ("v14_solid_tip_insert", "Left-clamped beam with a protected solid insert around the loaded free-end midpoint.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v15_opening_and_insert", "Cantilever with both a middle circular void and a protected solid load pad at the free end.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1, cy=0.5, radius=0.15, kind="void"), RectangularRegion(x0=1.8, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v16_rectangular_window", "Cantilever containing a rectangular non-design window in the center region.", ProblemSpec(Lx=2, Ly=1, nelx=80, nely=40, volfrac=0.4, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fy=-1)], passive_regions=[RectangularRegion(x0=0.8, y0=0.35, x1=1.1, y1=0.65, kind="void")])),
        ("v17_bridge_service_hole", "Bridge span with a circular service void at midspan under a distributed top load.", ProblemSpec(Lx=4, Ly=1, nelx=120, nely=30, volfrac=0.3, supports=[EdgeSupport(edge="bottom", constraint="pin_y")], loads=[DistributedLoad(edge="top", magnitude=-1)], passive_regions=[CircularRegion(cx=2, cy=0.5, radius=0.15, kind="void")])),
        ("v18_mbb_central_void", "Standard MBB beam but reserve a small circular void in the domain center.", ProblemSpec(Lx=3, Ly=1, nelx=90, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="pin_x"), PointSupport(x=3, y=0, constraint="pin_y")], loads=[PointLoad(x=0, y=1, fy=-1)], passive_regions=[CircularRegion(cx=1.5, cy=0.5, radius=0.12, kind="void")])),
        ("v19_square_bracket_pad", "Top-fixed square bracket with a rectangular protected solid pad at the lower-right pull location.", ProblemSpec(Lx=2, Ly=2, nelx=60, nely=60, volfrac=0.4, supports=[EdgeSupport(edge="top", constraint="fixed")], loads=[PointLoad(x=2, y=0.5, fx=1)], passive_regions=[RectangularRegion(x0=1.75, y0=0.35, x1=2.0, y1=0.65, kind="solid")])),
        ("v20_long_bar_root_hole", "Long left-fixed cantilever with a small circular root-side lightening hole.", ProblemSpec(Lx=6, Ly=1, nelx=120, nely=20, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=6, y=0.5, fy=-1)], passive_regions=[CircularRegion(cx=1.2, cy=0.5, radius=0.12, kind="void")])),
    ]
    for name, prompt, spec in extra_passive_specs:
        add(name, "passive_region", prompt, spec)

    extra_ambiguous_specs = [
        ("a11_close_to_tip", "Load the part close to the free tip of a cantilever.", clone(base["cantilever_basic"])),
        ("a12_below_opening", "Put the load below the circular opening in a clamped beam.", clone(base["cantilever_with_hole"])),
        ("a13_lower_bracket_side", "Pull on the lower right-side area of a top-fixed bracket.", clone(base["lbracket"])),
        ("a14_base_supports", "Support the base area and apply a force on the far side of the beam.", clone(base["simply_supported_center"])),
        ("a15_finer_long_beam", "Make the long beam fairly fine and use roughly half the material.", clone(base["high_aspect"])),
        ("a16_mount_holes_motor_side", "Add bolt holes near the mount and load the far motor side.", passive_specs[2][2]),
        ("a17_about_mid_side", "Apply the load about the middle of the free side.", clone(base["cantilever_basic"])),
        ("a18_upper_free_region", "Fix the left-ish side and load somewhere in the upper free region.", ProblemSpec(Lx=2, Ly=1, nelx=60, nely=30, volfrac=0.5, supports=[EdgeSupport(edge="left", constraint="fixed")], loads=[PointLoad(x=2, y=0.75, fy=-1)])),
        ("a19_deck_like_load", "Use deck-like loading with support along the underside.", clone(base["bridge"])),
        ("a20_horizontal_tip_push", "Push the tip sideways on an L-shaped top-mounted bracket.", clone(base["lbracket"])),
    ]
    for name, prompt, spec in extra_ambiguous_specs:
        add(name, "ambiguous_supported", prompt, spec)

    return cases


NORMALIZED_BRACKET_CASES = [
    {
        "name": "normalized_multiload_bracket",
        "prompt": (
            "Normalized mounting bracket: rectangular design envelope 4.0 by 1.5, "
            "clamped mounting edge on the left, two bolt-clearance holes near the "
            "mount, a protected solid pad at the far right, and combined downward "
            "and backward point loads at the pad. Use 35% material. Dimensions are "
            "normalized, not certified millimeter units."
        ),
        "spec": ProblemSpec(
            Lx=4.0,
            Ly=1.5,
            nelx=160,
            nely=60,
            volfrac=0.35,
            supports=[EdgeSupport(edge="left", constraint="fixed")],
            loads=[
                PointLoad(x=4.0, y=0.75, fy=-1.0),
                PointLoad(x=4.0, y=0.75, fx=-0.25),
            ],
            passive_regions=[
                CircularRegion(cx=0.55, cy=0.45, radius=0.12, kind="void"),
                CircularRegion(cx=0.55, cy=1.05, radius=0.12, kind="void"),
                RectangularRegion(x0=3.65, y0=0.55, x1=4.0, y1=0.95, kind="solid"),
            ],
        ),
        "notes": (
            "Normalized benchmark-style bracket with multiple loads, multiple passive "
            "regions, and a protected mounting pad. It is a bounded workflow case for configuration "
            "and validity checks, not an independently certified engineering design."
        ),
    }
]


def ambiguity_flags(prompt: str) -> list[str]:
    text = prompt.lower()
    return [name for name, pattern in AMBIGUITY_TERMS.items() if re.search(pattern, text)]


def run_ambiguity_benchmark() -> dict[str, Any]:
    rows = []
    for prompt, expected in AMBIGUITY_CASES:
        flags = ambiguity_flags(prompt)
        predicted = bool(flags)
        rows.append({
            "prompt": prompt,
            "expected_ambiguous": expected,
            "predicted_ambiguous": predicted,
            "flags": flags,
            "correct": predicted == expected,
        })
    tp = sum(r["expected_ambiguous"] and r["predicted_ambiguous"] for r in rows)
    fp = sum((not r["expected_ambiguous"]) and r["predicted_ambiguous"] for r in rows)
    tn = sum((not r["expected_ambiguous"]) and (not r["predicted_ambiguous"]) for r in rows)
    fn = sum(r["expected_ambiguous"] and (not r["predicted_ambiguous"]) for r in rows)
    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "accuracy": (tp + tn) / len(rows),
            "recall": tp / max(tp + fn, 1),
            "precision": tp / max(tp + fp, 1),
        },
    }


def _point_in_region(x: float, y: float, region: CircularRegion | RectangularRegion) -> bool:
    if isinstance(region, CircularRegion):
        return math.hypot(x - region.cx, y - region.cy) <= region.radius
    return min(region.x0, region.x1) <= x <= max(region.x0, region.x1) and min(region.y0, region.y1) <= y <= max(region.y0, region.y1)


def pre_solve_model_checks(spec: ProblemSpec, prompt: str = "") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    for msg in spec.validate():
        issues.append({"check": "schema_physical_plausibility", "severity": "error", "message": msg})

    fixed_x = False
    fixed_y = False
    for support in spec.supports:
        dofs = support.dof_mask(spec.ndim)
        fixed_x = fixed_x or 0 in dofs
        fixed_y = fixed_y or 1 in dofs
    if not fixed_x or not fixed_y:
        issues.append({
            "check": "rigid_body_mode",
            "severity": "error",
            "message": "Supports do not constrain both x and y rigid-body translation modes.",
        })

    for load in spec.loads:
        if not isinstance(load, PointLoad):
            continue
        for support in spec.supports:
            if isinstance(support, EdgeSupport):
                on_edge = (
                    (support.edge == "left" and abs(load.x) < 1e-9)
                    or (support.edge == "right" and abs(load.x - spec.Lx) < 1e-9)
                    or (support.edge == "bottom" and abs(load.y) < 1e-9)
                    or (support.edge == "top" and abs(load.y - spec.Ly) < 1e-9)
                )
                if on_edge and support.constraint == "fixed":
                    issues.append({
                        "check": "load_on_fixed_dof",
                        "severity": "error",
                        "message": "Point load lies on a fully fixed edge.",
                    })
            elif support.constraint == "fixed":
                h = max(spec.Lx / max(spec.nelx, 1), spec.Ly / max(spec.nely, 1))
                if math.hypot(load.x - support.x, load.y - support.y) <= 0.5 * h:
                    issues.append({
                        "check": "load_on_fixed_dof",
                        "severity": "error",
                        "message": "Point load coincides with a fully fixed support node.",
                    })

        for region in spec.passive_regions:
            if region.kind == "void" and _point_in_region(load.x, load.y, region):
                issues.append({
                    "check": "passive_load_overlap",
                    "severity": "error",
                    "message": "Point load is inside a passive void region.",
                })

    for support in spec.supports:
        points: list[tuple[float, float]] = []
        if isinstance(support, PointSupport):
            points.append((support.x, support.y))
        for x, y in points:
            for region in spec.passive_regions:
                if region.kind == "void" and _point_in_region(x, y, region):
                    issues.append({
                        "check": "passive_support_overlap",
                        "severity": "error",
                        "message": "Support lies inside a passive void region.",
                    })

    flags = ambiguity_flags(prompt)
    if flags:
        issues.append({
            "check": "boundary_ambiguity",
            "severity": "warning",
            "message": "Ambiguous spatial terms require preview confirmation: " + ", ".join(flags),
        })

    if spec.E == 1.0 and prompt and re.search(r"\bcertif|real|physical|steel|aluminum|mpa|gpa|kn|mm\b", prompt.lower()):
        issues.append({
            "check": "units_material_warning",
            "severity": "warning",
            "message": "Material/units appear underspecified or normalized; output is comparative, not certified.",
        })

    return issues


def invalid_spec_cases() -> list[dict[str, Any]]:
    return [
        {
            "name": "missing_support",
            "prompt": "cantilever with only a load",
            "spec": ProblemSpec(loads=[PointLoad(x=2, y=0.5, fy=-1)]),
            "expected": {"schema_physical_plausibility", "rigid_body_mode"},
        },
        {
            "name": "missing_load",
            "prompt": "fixed cantilever with no load",
            "spec": ProblemSpec(supports=[EdgeSupport(edge="left", constraint="fixed")]),
            "expected": {"schema_physical_plausibility"},
        },
        {
            "name": "load_on_fixed_edge",
            "prompt": "left edge fixed, load on the left edge",
            "spec": ProblemSpec(
                supports=[EdgeSupport(edge="left", constraint="fixed")],
                loads=[PointLoad(x=0, y=0.5, fy=-1)],
            ),
            "expected": {"load_on_fixed_dof"},
        },
        {
            "name": "rigid_y_unconstrained",
            "prompt": "left edge only pin_x, right edge load",
            "spec": ProblemSpec(
                supports=[EdgeSupport(edge="left", constraint="pin_x")],
                loads=[PointLoad(x=2, y=0.5, fy=-1)],
            ),
            "expected": {"rigid_body_mode"},
        },
        {
            "name": "load_inside_void",
            "prompt": "cantilever with the load inside a void",
            "spec": ProblemSpec(
                supports=[EdgeSupport(edge="left", constraint="fixed")],
                loads=[PointLoad(x=2, y=0.5, fy=-1)],
                passive_regions=[CircularRegion(cx=2, cy=0.5, radius=0.2, kind="void")],
            ),
            "expected": {"passive_load_overlap"},
        },
        {
            "name": "support_inside_void",
            "prompt": "point support inside a void",
            "spec": ProblemSpec(
                supports=[PointSupport(x=0, y=0, constraint="fixed")],
                loads=[PointLoad(x=2, y=0.5, fy=-1)],
                passive_regions=[CircularRegion(cx=0, cy=0, radius=0.2, kind="void")],
            ),
            "expected": {"passive_support_overlap"},
        },
        {
            "name": "ambiguous_load_phrase",
            "prompt": "put the load near the right side under the hole",
            "spec": ProblemSpec(
                supports=[EdgeSupport(edge="left", constraint="fixed")],
                loads=[PointLoad(x=2, y=0.5, fy=-1)],
            ),
            "expected": {"boundary_ambiguity"},
        },
        {
            "name": "real_units_warning",
            "prompt": "steel bracket in mm with 3 kN real service load",
            "spec": ProblemSpec(
                supports=[EdgeSupport(edge="left", constraint="fixed")],
                loads=[PointLoad(x=2, y=0.5, fy=-1)],
            ),
            "expected": {"units_material_warning"},
        },
    ]


def run_pre_solve_benchmark() -> dict[str, Any]:
    rows = []
    for case in invalid_spec_cases():
        issues = pre_solve_model_checks(case["spec"], case["prompt"])
        detected = {issue["check"] for issue in issues}
        expected = case["expected"]
        rows.append({
            "name": case["name"],
            "prompt": case["prompt"],
            "expected": sorted(expected),
            "detected": sorted(detected),
            "missed": sorted(expected - detected),
            "extra": sorted(detected - expected),
            "passed": expected.issubset(detected),
            "issues": issues,
        })
    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "passed": sum(r["passed"] for r in rows),
            "detection_rate": sum(r["passed"] for r in rows) / len(rows),
        },
    }


def repair_invalid_case(case: dict[str, Any]) -> tuple[ProblemSpec, str, str]:
    """Apply a minimal deterministic correction for retry-gate testing."""
    spec = copy.deepcopy(case["spec"])
    prompt = case["prompt"]
    note = ""

    if case["name"] == "missing_support":
        spec.supports = [EdgeSupport(edge="left", constraint="fixed")]
        note = "added fixed left-edge support"
    elif case["name"] == "missing_load":
        spec.loads = [PointLoad(x=spec.Lx, y=spec.Ly / 2.0, fy=-1.0)]
        note = "added downward right-edge load"
    elif case["name"] == "load_on_fixed_edge":
        spec.loads = [PointLoad(x=spec.Lx, y=spec.Ly / 2.0, fy=-1.0)]
        note = "moved load from fixed edge to free edge"
    elif case["name"] == "rigid_y_unconstrained":
        spec.supports = [EdgeSupport(edge="left", constraint="fixed")]
        note = "upgraded support from pin_x to fixed"
    elif case["name"] == "load_inside_void":
        spec.passive_regions = [
            CircularRegion(cx=0.7 * spec.Lx, cy=0.25 * spec.Ly, radius=0.12, kind="void")
        ]
        note = "moved passive void away from load point"
    elif case["name"] == "support_inside_void":
        spec.passive_regions = [
            CircularRegion(cx=0.7 * spec.Lx, cy=0.5 * spec.Ly, radius=0.12, kind="void")
        ]
        note = "moved passive void away from support"
    elif case["name"] == "ambiguous_load_phrase":
        prompt = "left edge fixed; place a downward point load at x=2.0, y=0.5"
        note = "replaced ambiguous spatial phrase with coordinates"
    elif case["name"] == "real_units_warning":
        prompt = "normalized dimensionless bracket benchmark load"
        note = "changed real-units prompt to normalized comparative benchmark"
    else:
        note = "no repair rule"

    return spec, prompt, note


def run_failure_retry_benchmark() -> dict[str, Any]:
    rows = []
    for case in invalid_spec_cases():
        before_issues = pre_solve_model_checks(case["spec"], case["prompt"])
        repaired_spec, repaired_prompt, repair_note = repair_invalid_case(case)
        after_issues = pre_solve_model_checks(repaired_spec, repaired_prompt)
        before_errors = [issue for issue in before_issues if issue["severity"] == "error"]
        after_errors = [issue for issue in after_issues if issue["severity"] == "error"]
        after_checks = {issue["check"] for issue in after_issues}
        rows.append({
            "name": case["name"],
            "repair": repair_note,
            "before_issue_count": len(before_issues),
            "before_error_count": len(before_errors),
            "after_issue_count": len(after_issues),
            "after_error_count": len(after_errors),
            "blocking_recovered": len(after_errors) == 0,
            "all_expected_cleared": not (case["expected"] & after_checks),
            "after_checks": sorted(after_checks),
        })

    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "blocking_recovered": sum(row["blocking_recovered"] for row in rows),
            "expected_cleared": sum(row["all_expected_cleared"] for row in rows),
        },
    }


def run_safety_rail_ablation() -> dict[str, Any]:
    """Compare invalid-spec handling with and without deterministic safety checks."""
    rows = []
    for case in invalid_spec_cases():
        issues = pre_solve_model_checks(case["spec"], case["prompt"])
        detected = {issue["check"] for issue in issues}
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
        rows.append({
            "name": case["name"],
            "expected": sorted(case["expected"]),
            "with_safety_detected": sorted(detected),
            "with_safety_error_count": error_count,
            "with_safety_warning_count": warning_count,
            "with_safety_blocks_or_flags": bool(case["expected"] & detected),
            "without_safety_blocks_or_flags": False,
            "ablation_failure": bool(case["expected"]),
        })

    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "with_safety_caught": sum(row["with_safety_blocks_or_flags"] for row in rows),
            "without_safety_caught": sum(row["without_safety_blocks_or_flags"] for row in rows),
            "safety_catch_delta": (
                sum(row["with_safety_blocks_or_flags"] for row in rows)
                - sum(row["without_safety_blocks_or_flags"] for row in rows)
            ),
        },
    }


def rule_only_parse(prompt: str, gt_spec: ProblemSpec) -> ProblemSpec:
    text = prompt.lower()
    spec = ProblemSpec(Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5)

    if "3 to 1" in text or "3:1" in text or "mbb" in text or "simply supported" in text:
        spec.Lx, spec.Ly, spec.nelx, spec.nely = 3.0, 1.0, 90, 30
    if "4 meters" in text or "bridge" in text:
        spec.Lx, spec.Ly, spec.nelx, spec.nely = 4.0, 1.0, 120, 30
    if "short deep" in text:
        spec.Lx, spec.Ly, spec.nelx, spec.nely = 1.0, 2.0, 30, 60
    if "square" in text or "l-bracket" in text:
        spec.Lx, spec.Ly, spec.nelx, spec.nely = 2.0, 2.0, 60, 60
    if "6 to 1" in text or "6:1" in text:
        spec.Lx, spec.Ly, spec.nelx, spec.nely = 6.0, 1.0, 120, 20
    if "80" in text and "40" in text:
        spec.nelx, spec.nely = 80, 40
    if "30%" in text or "30 percent" in text:
        spec.volfrac = 0.3
    elif "40%" in text or "40 percent" in text:
        spec.volfrac = 0.4
    elif "60%" in text or "60 percent" in text:
        spec.volfrac = 0.6

    if "mbb" in text:
        spec.supports = [
            EdgeSupport(edge="left", constraint="pin_x"),
            PointSupport(x=spec.Lx, y=0.0, constraint="pin_y"),
        ]
        spec.loads = [PointLoad(x=0.0, y=spec.Ly, fy=-1.0)]
    elif "bridge" in text:
        spec.supports = [EdgeSupport(edge="bottom", constraint="pin_y")]
        spec.loads = []
        from problem_spec import DistributedLoad
        spec.loads.append(DistributedLoad(edge="top", magnitude=-1.0))
    elif "simply supported" in text:
        spec.supports = [
            PointSupport(x=0.0, y=0.0, constraint="fixed"),
            PointSupport(x=spec.Lx, y=0.0, constraint="fixed"),
        ]
        spec.loads = [PointLoad(x=spec.Lx / 2, y=spec.Ly, fy=-1.0)]
    elif "l-bracket" in text or "bracket" in text:
        spec.supports = [EdgeSupport(edge="top" if "top edge" in text else "left", constraint="fixed")]
        fx = 1.0 if "right" in text and "pointing left" not in text else -1.0
        spec.loads = [PointLoad(x=spec.Lx, y=0.5 * spec.Ly, fx=fx)]
    else:
        spec.supports = [EdgeSupport(edge="left", constraint="fixed")]
        spec.loads = [PointLoad(x=spec.Lx, y=0.5 * spec.Ly, fy=-1.0)]

    if "two loads" in text:
        spec.loads = [
            PointLoad(x=spec.Lx, y=0.75 * spec.Ly, fy=-1.0),
            PointLoad(x=spec.Lx, y=0.25 * spec.Ly, fy=-1.0),
        ]
    if "hole" in text or "void" in text:
        spec.passive_regions = [CircularRegion(cx=spec.Lx / 2, cy=spec.Ly / 2, radius=0.15, kind="void")]

    # Avoid giving this parser access to gt_spec beyond signature consistency.
    _ = gt_spec
    return spec


def run_rule_only_ablation() -> dict[str, Any]:
    rows = []
    for case in PIPELINE_TEST_CASES:
        name = case["name"]
        gt = case["spec"]
        spec = rule_only_parse(case["prompt"], gt)
        cmp = compare_specs(gt, spec)
        n_fields = sum(1 for k in cmp if k.endswith("_match"))
        n_match = sum(1 for k, v in cmp.items() if k.endswith("_match") and v)
        rows.append({
            "problem": name,
            "prompt": case["prompt"],
            "field_matches": n_match,
            "field_total": n_fields,
            "field_accuracy": n_match / max(n_fields, 1),
            **cmp,
        })
    challenge_rows = []
    for case in RULE_CHALLENGE_CASES:
        gt = case["spec"]
        spec = rule_only_parse(case["prompt"], gt)
        cmp = compare_specs(gt, spec)
        n_fields = sum(1 for k in cmp if k.endswith("_match"))
        n_match = sum(1 for k, v in cmp.items() if k.endswith("_match") and v)
        challenge_rows.append({
            "problem": case["name"],
            "prompt": case["prompt"],
            "field_matches": n_match,
            "field_total": n_fields,
            "field_accuracy": n_match / max(n_fields, 1),
            **cmp,
        })

    total_match = sum(r["field_matches"] for r in rows)
    total_fields = sum(r["field_total"] for r in rows)
    challenge_match = sum(r["field_matches"] for r in challenge_rows)
    challenge_fields = sum(r["field_total"] for r in challenge_rows)
    return {
        "rows": rows,
        "challenge_rows": challenge_rows,
        "summary": {
            "n": len(rows),
            "field_accuracy": total_match / max(total_fields, 1),
            "total_match": total_match,
            "total_fields": total_fields,
            "challenge_n": len(challenge_rows),
            "challenge_field_accuracy": challenge_match / max(challenge_fields, 1),
            "challenge_total_match": challenge_match,
            "challenge_total_fields": challenge_fields,
        },
    }


def run_expanded_prompt_generalization() -> dict[str, Any]:
    rows = []
    for case in expanded_prompt_generalization_cases():
        gt = case["spec"]
        parsed = rule_only_parse(case["prompt"], gt)
        cmp = compare_specs(gt, parsed)
        n_fields = sum(1 for k in cmp if k.endswith("_match"))
        n_match = sum(1 for k, v in cmp.items() if k.endswith("_match") and v)
        rows.append({
            "problem": case["name"],
            "category": case["category"],
            "prompt": case["prompt"],
            "field_matches": n_match,
            "field_total": n_fields,
            "field_accuracy": n_match / max(n_fields, 1),
            "ambiguity_flags": ";".join(ambiguity_flags(case["prompt"])),
            **cmp,
        })

    total_match = sum(row["field_matches"] for row in rows)
    total_fields = sum(row["field_total"] for row in rows)
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({row["category"] for row in rows}):
        subset = [row for row in rows if row["category"] == category]
        cat_match = sum(row["field_matches"] for row in subset)
        cat_fields = sum(row["field_total"] for row in subset)
        by_category[category] = {
            "n": len(subset),
            "field_accuracy": cat_match / max(cat_fields, 1),
            "field_matches": cat_match,
            "field_total": cat_fields,
            "mean_ambiguity_flags": sum(1 for row in subset if row["ambiguity_flags"]) / len(subset),
        }

    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "field_accuracy": total_match / max(total_fields, 1),
            "total_match": total_match,
            "total_fields": total_fields,
            "by_category": by_category,
        },
    }


REQUIRED_TEMPLATE_FIELDS = [
    "domain_dimensions",
    "mesh_resolution",
    "volume_fraction",
    "support_type",
    "support_location",
    "load_type",
    "load_location",
    "load_direction",
    "passive_regions",
]


def template_field_is_explicit(prompt: str, field: str) -> bool:
    text = prompt.lower()
    has_number = bool(re.search(r"\b\d+(\.\d+)?\b", text))
    has_coordinate = bool(re.search(r"\(\s*\d+(\.\d+)?\s*,\s*\d+(\.\d+)?", text))
    if field == "domain_dimensions":
        return bool(re.search(r"\b\d+(\.\d+)?\s*(x|by|to)\s*\d+(\.\d+)?\b", text)) or "aspect ratio" in text or "3:1" in text or "6 to 1" in text
    if field == "mesh_resolution":
        return bool(re.search(r"\b(nelx|nely|mesh|resolution|high-resolution|60x|80x|90x|120x)\b", text))
    if field == "volume_fraction":
        return "%" in text or "percent" in text or "half material" in text or "material allowed" in text
    if field == "support_type":
        return any(token in text for token in ["fixed", "clamped", "pin", "roller", "restraint", "supported"])
    if field == "support_location":
        return any(token in text for token in ["left", "right", "top", "bottom", "western", "eastern", "corner", "edge", "boundary", "wall"])
    if field == "load_type":
        return any(token in text for token in ["point load", "force", "load", "pressure", "distributed", "uniform", "pulled", "push"])
    if field == "load_location":
        return has_coordinate or any(token in text for token in ["right", "left", "top", "bottom", "center", "midpoint", "corner", "free end", "tip", "motor pad"])
    if field == "load_direction":
        return any(token in text for token in ["down", "up", "right", "left", "horizontal", "vertical", "backward", "outward"])
    if field == "passive_regions":
        if not any(token in text for token in ["hole", "void", "cutout", "solid", "pad", "plate", "passive"]):
            return True
        return has_number or "center" in text or "near" in text or "pad" in text
    raise ValueError(field)


def run_template_workflow_baseline() -> dict[str, Any]:
    rows = []
    cases = [(case["name"], case["prompt"], "canonical") for case in PIPELINE_TEST_CASES]
    cases.extend((case["name"], case["prompt"], "challenge") for case in RULE_CHALLENGE_CASES)
    cases.extend((case["name"], case["prompt"], f"expanded_{case['category']}") for case in expanded_prompt_generalization_cases())
    cases.extend((case["name"], case["prompt"], "normalized_bracket") for case in NORMALIZED_BRACKET_CASES)
    for name, prompt, suite in cases:
        explicit = {field: template_field_is_explicit(prompt, field) for field in REQUIRED_TEMPLATE_FIELDS}
        explicit_count = sum(explicit.values())
        missing = [field for field, ok in explicit.items() if not ok]
        rows.append({
            "problem": name,
            "suite": suite,
            "template_fields": len(REQUIRED_TEMPLATE_FIELDS),
            "explicit_fields": explicit_count,
            "manual_completion_fields": len(missing),
            "explicit_fraction": explicit_count / len(REQUIRED_TEMPLATE_FIELDS),
            "missing_fields": ";".join(missing),
            "prompt": prompt,
        })

    summary: dict[str, Any] = {"n": len(rows)}
    for suite in sorted({row["suite"] for row in rows}):
        suite_rows = [row for row in rows if row["suite"] == suite]
        summary[f"{suite}_n"] = len(suite_rows)
        summary[f"{suite}_mean_manual_completion_fields"] = sum(row["manual_completion_fields"] for row in suite_rows) / len(suite_rows)
        summary[f"{suite}_mean_explicit_fraction"] = sum(row["explicit_fraction"] for row in suite_rows) / len(suite_rows)
    expanded_rows = [row for row in rows if row["suite"].startswith("expanded_")]
    if expanded_rows:
        summary["expanded_n"] = len(expanded_rows)
        summary["expanded_mean_manual_completion_fields"] = sum(row["manual_completion_fields"] for row in expanded_rows) / len(expanded_rows)
        summary["expanded_mean_explicit_fraction"] = sum(row["explicit_fraction"] for row in expanded_rows) / len(expanded_rows)
    summary["overall_mean_manual_completion_fields"] = sum(row["manual_completion_fields"] for row in rows) / len(rows)
    summary["overall_mean_explicit_fraction"] = sum(row["explicit_fraction"] for row in rows) / len(rows)
    return {"rows": rows, "summary": summary}


def run_normalized_bracket_case_checks() -> dict[str, Any]:
    rows = []
    for case in NORMALIZED_BRACKET_CASES:
        spec = case["spec"]
        issues = pre_solve_model_checks(spec, case["prompt"])
        errors = [issue for issue in issues if issue["severity"] == "error"]
        warnings = [issue for issue in issues if issue["severity"] == "warning"]
        rows.append({
            "name": case["name"],
            "prompt": case["prompt"],
            "notes": case["notes"],
            "supports": len(spec.supports),
            "loads": len(spec.loads),
            "passive_regions": len(spec.passive_regions),
            "elements": spec.nelx * spec.nely,
            "volfrac": spec.volfrac,
            "pre_solve_errors": len(errors),
            "pre_solve_warnings": len(warnings),
            "checks_pass": len(errors) == 0,
            "warnings": ";".join(issue["check"] for issue in warnings),
        })
    return {
        "rows": rows,
        "summary": {
            "n": len(rows),
            "passed": sum(row["checks_pass"] for row in rows),
            "max_loads": max(row["loads"] for row in rows),
            "max_passive_regions": max(row["passive_regions"] for row in rows),
            "max_elements": max(row["elements"] for row in rows),
        },
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(out_dir: Path, results: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "revision_experiment_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    _write_csv(out_dir / "ambiguity_benchmark.csv", results["ambiguity"]["rows"])
    _write_csv(out_dir / "pre_solve_benchmark.csv", results["pre_solve"]["rows"])
    _write_csv(out_dir / "failure_retry_benchmark.csv", results["failure_retry"]["rows"])
    _write_csv(out_dir / "safety_rail_ablation.csv", results["safety_rail_ablation"]["rows"])
    _write_csv(out_dir / "rule_only_ablation.csv", results["rule_only"]["rows"])
    _write_csv(out_dir / "rule_only_challenge_ablation.csv", results["rule_only"]["challenge_rows"])
    _write_csv(out_dir / "expanded_prompt_generalization.csv", results["expanded_prompt_generalization"]["rows"])
    _write_csv(out_dir / "template_workflow_baseline.csv", results["template_baseline"]["rows"])
    _write_csv(out_dir / "normalized_bracket_case.csv", results["normalized_bracket_case"]["rows"])

    lines = [
        "# Revision Experiment Summary",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Ambiguity Detection",
        f"- Cases: {results['ambiguity']['summary']['n']}",
        f"- Accuracy: {results['ambiguity']['summary']['accuracy']:.3f}",
        f"- Precision: {results['ambiguity']['summary']['precision']:.3f}",
        f"- Recall: {results['ambiguity']['summary']['recall']:.3f}",
        "",
        "## Pre-Solve Invalid-Spec Checks",
        f"- Cases: {results['pre_solve']['summary']['n']}",
        f"- Expected issue sets fully detected: {results['pre_solve']['summary']['passed']}/{results['pre_solve']['summary']['n']}",
        f"- Detection rate: {results['pre_solve']['summary']['detection_rate']:.3f}",
        "",
        "## Failure/Retry Recovery",
        f"- Cases: {results['failure_retry']['summary']['n']}",
        f"- Blocking errors cleared after repair: {results['failure_retry']['summary']['blocking_recovered']}/{results['failure_retry']['summary']['n']}",
        f"- Expected issue sets cleared after repair: {results['failure_retry']['summary']['expected_cleared']}/{results['failure_retry']['summary']['n']}",
        "",
        "## Safety-Rail Ablation",
        f"- Cases: {results['safety_rail_ablation']['summary']['n']}",
        f"- With safety rails caught: {results['safety_rail_ablation']['summary']['with_safety_caught']}/{results['safety_rail_ablation']['summary']['n']}",
        f"- Without safety rails caught: {results['safety_rail_ablation']['summary']['without_safety_caught']}/{results['safety_rail_ablation']['summary']['n']}",
        "",
        "## Rule-Only Parser Ablation",
        f"- Pipeline prompts: {results['rule_only']['summary']['n']}",
        f"- Field accuracy: {results['rule_only']['summary']['field_accuracy']:.3f} ({results['rule_only']['summary']['total_match']}/{results['rule_only']['summary']['total_fields']})",
        f"- Challenge prompts: {results['rule_only']['summary']['challenge_n']}",
        f"- Challenge field accuracy: {results['rule_only']['summary']['challenge_field_accuracy']:.3f} ({results['rule_only']['summary']['challenge_total_match']}/{results['rule_only']['summary']['challenge_total_fields']})",
        "",
        "## Expanded Prompt Generalization Suite",
        f"- Held-out prompts: {results['expanded_prompt_generalization']['summary']['n']}",
        f"- Rule-only field accuracy: {results['expanded_prompt_generalization']['summary']['field_accuracy']:.3f} ({results['expanded_prompt_generalization']['summary']['total_match']}/{results['expanded_prompt_generalization']['summary']['total_fields']})",
    ]
    for category, stats in results["expanded_prompt_generalization"]["summary"]["by_category"].items():
        lines.append(
            f"- {category}: {stats['field_accuracy']:.3f} ({stats['field_matches']}/{stats['field_total']}); "
            f"ambiguity-flag incidence {stats['mean_ambiguity_flags']:.2f}"
        )
    lines.extend([
        "",
        "## Template-Style Configuration Baseline Proxy",
        f"- Cases: {results['template_baseline']['summary']['n']}",
        f"- Mean manual-completion fields: {results['template_baseline']['summary']['overall_mean_manual_completion_fields']:.2f}/{len(REQUIRED_TEMPLATE_FIELDS)}",
        f"- Canonical mean manual-completion fields: {results['template_baseline']['summary']['canonical_mean_manual_completion_fields']:.2f}",
        f"- Challenge mean manual-completion fields: {results['template_baseline']['summary']['challenge_mean_manual_completion_fields']:.2f}",
        f"- Expanded held-out mean manual-completion fields: {results['template_baseline']['summary']['expanded_mean_manual_completion_fields']:.2f}",
        f"- Normalized bracket mean manual-completion fields: {results['template_baseline']['summary']['normalized_bracket_mean_manual_completion_fields']:.2f}",
        "",
        "## Normalized Engineering-Style Bracket Case",
        f"- Cases: {results['normalized_bracket_case']['summary']['n']}",
        f"- Passed pre-solve checks: {results['normalized_bracket_case']['summary']['passed']}/{results['normalized_bracket_case']['summary']['n']}",
        f"- Max loads/passive regions/elements: {results['normalized_bracket_case']['summary']['max_loads']}/{results['normalized_bracket_case']['summary']['max_passive_regions']}/{results['normalized_bracket_case']['summary']['max_elements']}",
        "",
        "## Empirical Items Not Covered By This Local Harness",
        "- Controlled user study: requires recruited participants and task timing.",
        "- Provider-diverse LLM comparison: requires additional API credentials and model access.",
        "- GUI timing against external tools: requires a defined participant/protocol or recorded operator runs.",
    ])
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(REVISION_ROOT / "experiment_results_major_overhaul"))
    args = parser.parse_args()

    results = {
        "ambiguity": run_ambiguity_benchmark(),
        "pre_solve": run_pre_solve_benchmark(),
        "failure_retry": run_failure_retry_benchmark(),
        "safety_rail_ablation": run_safety_rail_ablation(),
        "rule_only": run_rule_only_ablation(),
        "expanded_prompt_generalization": run_expanded_prompt_generalization(),
        "template_baseline": run_template_workflow_baseline(),
        "normalized_bracket_case": run_normalized_bracket_case_checks(),
    }
    out_dir = Path(args.output_dir)
    write_outputs(out_dir, results)
    print((out_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
