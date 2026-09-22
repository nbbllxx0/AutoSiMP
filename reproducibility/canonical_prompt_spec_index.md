# Canonical Prompt/Specification Index

## Purpose
This file makes the configuration-accuracy reference reproducible for the
10 canonical pipeline prompts. It records the natural-language prompt, the
author-defined canonical `ProblemSpec`, the reported LLM-configured outcome, field-level
comparison status, and whether alternate interpretations are plausible.

## Current nine-field scores
The outcome columns below predate scoring of the stored configured
specifications. The current nine-field scores are in
`results/e2_spec_match.json`, computed from `frozen_specs/configured_specs.json`
(the specs stored by the archived retry run): 7 of 10 exact. Bridge misses
support count and location; dual-load and L-bracket miss load location. MBB,
simply-supported, dual-load, and high-aspect use a different mesh.

## Reference-Specification Authorship
- Source: author-defined canonical `ProblemSpec` objects in
  `diagnostic_suite/revision_experiments.py`, `PIPELINE_TEST_CASES`.
- Basis: standard SIMP benchmark conventions, explicit prompt constraints,
  and rule-based canonical references used by the local experiment harness.
- Field categories: geometry, mesh, volume fraction, supports, loads, passive
  regions.
- Comparison evidence: the AEI manuscript, Table `tab:pipeline`, and
  `diagnostic_suite/rule_only_ablation.csv`.
- Classification labels:
  - `semantically equivalent`: same intended configuration at field level.
  - `physically plausible but different`: feasible configuration but different
    problem semantics.
  - `valid but unintended`: solver-ready and plausible, but not the intended
    author-defined reference interpretation.
  - `ambiguous / requires confirmation`: prompt admits multiple reasonable
    interpretations and must be previewed by a human.
  - `invalid`: not solver-ready or violates pre-solve checks.

## Canonical Prompt/Spec Pairs

| Case | Natural-language prompt | Author-defined canonical `ProblemSpec` summary | Reported LLM-configured outcome | Field-level comparison | Alternate interpretations |
| --- | --- | --- | --- | --- | --- |
| `cantilever_basic` | Cantilever beam. Left edge is clamped. Downward point load at the center of the right edge. 50% volume fraction. | `Lx=2.0`, `Ly=1.0`, `nelx=60`, `nely=30`, `volfrac=0.5`; support `left:fixed`; load point `(2.0,0.5)`, `fy=-1.0`; no passive regions. | Semantically equivalent; table penalty `0.0%`. | Geometry, mesh, volume, supports, loads, passive regions match. | No material alternate interpretation. |
| `mbb_beam` | MBB beam, 3:1 aspect ratio. Symmetry boundary condition on the left edge, roller support at the bottom right corner. Downward load at the top left corner. Half material. | `Lx=3.0`, `Ly=1.0`, `nelx=90`, `nely=30`, `volfrac=0.5`; supports `left:pin_x`, point `(3.0,0.0):pin_y`; load point `(0.0,1.0)`, `fy=-1.0`; no passive regions. | Semantically equivalent; table penalty `+0.6%` with LLM controller and `+0.4%` with schedule controller figure. | Geometry, mesh, volume, supports, loads, passive regions match. | Low. MBB conventions must be stated for reproducibility. |
| `bridge` | Bridge structure. 4 meters wide, 1 meter tall. Bottom edge supported vertically (pin_y). Uniform downward pressure on the top edge. Use 30% material. | `Lx=4.0`, `Ly=1.0`, `nelx=120`, `nely=30`, `volfrac=0.3`; support `bottom:pin_y`; distributed load `top`, magnitude `-1.0`; no passive regions. | Partial configuration gap and controller failure are reported in Table `tab:pipeline`; this is not counted as a clean LLM success. | Geometry, mesh, volume, supports, and passive-region count match; load-field handling is the reported mismatch/failure point. | Some bridge support/load idealizations are plausible; report as benchmark-specific canonical setup. |
| `cantilever_with_hole` | Cantilever beam, left edge fixed, tip load downward at mid-right. There's a circular hole in the center of the beam for a pipe, radius 0.15. Use 40% volume fraction. | `Lx=2.0`, `Ly=1.0`, `nelx=80`, `nely=40`, `volfrac=0.4`; support `left:fixed`; load point `(2.0,0.5)`, `fy=-1.0`; passive circular void `(cx=1.0, cy=0.5, r=0.15)`. | Semantically equivalent; table penalty `0.0%`. | Geometry, mesh, volume, supports, loads, passive regions match. | `mid-right` can be ambiguous in free-form prompts, but this canonical case fixes the pipe-hole center and radius. |
| `deep_beam_shear` | Short deep cantilever: 1 unit wide, 2 units tall. Left edge clamped. Downward load at the midpoint of the right edge. 50 percent material. | `Lx=1.0`, `Ly=2.0`, `nelx=30`, `nely=60`, `volfrac=0.5`; support `left:fixed`; load point `(1.0,1.0)`, `fy=-1.0`; no passive regions. | Semantically equivalent; table penalty `0.0%`. | Geometry, mesh, volume, supports, loads, passive regions match. | No material alternate interpretation. |
| `simply_supported_center` | Simply supported beam. Fixed supports at both bottom corners. Point load at the top center, going down. 50% volume fraction. 3 to 1 aspect ratio. | `Lx=3.0`, `Ly=1.0`, `nelx=90`, `nely=30`, `volfrac=0.5`; point supports `(0.0,0.0):fixed`, `(3.0,0.0):fixed`; load point `(1.5,1.0)`, `fy=-1.0`; no passive regions. | Semantically equivalent but produces a small compliance difference; table penalty `+7.7%` with LLM controller and `+6.8%` with schedule controller figure. | Geometry, mesh, volume, supports, loads, passive regions match at the benchmark-field level. | Some supports could be modeled as pin/roller rather than fixed; this benchmark uses the stated fixed-corner convention. |
| `cantilever_low_vf` | Lightweight cantilever beam. Left wall fixed. Load at the tip pointing down. Only 30% material allowed. | `Lx=2.0`, `Ly=1.0`, `nelx=60`, `nely=30`, `volfrac=0.3`; support `left:fixed`; load point `(2.0,0.5)`, `fy=-1.0`; no passive regions. | Semantically equivalent; table penalty `0.0%`. | Geometry, mesh, volume, supports, loads, passive regions match. | Low; "tip" is resolved by the canonical right-midpoint convention. |
| `dual_load` | Cantilever with two loads: one at the upper-right and one at the lower-right, both pushing down. Left edge is fixed. 50% volume fraction. | `Lx=2.0`, `Ly=1.0`, `nelx=80`, `nely=40`, `volfrac=0.5`; support `left:fixed`; loads `(2.0,0.75)`, `fy=-1.0` and `(2.0,0.25)`, `fy=-1.0`; no passive regions. | Semantically equivalent at field level but with modest topology/compliance variation; table penalty `+6.4%`. | Geometry, mesh, volume, supports, load count/direction, passive regions match. | Upper/lower load y-coordinates are convention choices; preview should expose them. |
| `lbracket` | L-bracket: square domain 2x2. Top edge fixed to the wall. Horizontal load pointing right at the lower part of the right edge. 40% material. | `Lx=2.0`, `Ly=2.0`, `nelx=60`, `nely=60`, `volfrac=0.4`; support `top:fixed`; load point `(2.0,0.5)`, `fx=1.0`; no passive regions. | Valid but unintended. The configurator produced a solver-ready and physically plausible load placement, but at a different y-coordinate from the author-defined reference, producing a `+119%` compliance penalty. | Geometry, mesh, volume, support semantics, load count/direction, and passive regions match; load location semantics do not match. | Yes. Classify as `ambiguous / requires confirmation` and `valid but unintended`, not simply correct. |
| `high_aspect` | Very long cantilever, 6 to 1 aspect ratio. Fixed on the left. Downward tip load. 50% volume fraction. | `Lx=6.0`, `Ly=1.0`, `nelx=120`, `nely=20`, `volfrac=0.5`; support `left:fixed`; load point `(6.0,0.5)`, `fy=-1.0`; no passive regions. | Semantically equivalent; table penalty `-0.9%`. | Geometry, mesh, volume, supports, loads, passive regions match. | Low; "tip" is resolved by the canonical right-midpoint convention. |

## Reproduction Notes
- The canonical reference objects are executable in
  `diagnostic_suite/revision_experiments.py`.
- Field comparison uses geometry, mesh reasonableness, volume fraction,
  support count/semantics, load count/semantics, and passive-region
  count/semantics. The manuscript compresses these into the six paper-level
  categories.
- The L-bracket must be reported as a semantic ambiguity/outlier. It is
  solver-ready, but the load location differs from the intended benchmark
  interpretation.
