# Workflow-Evidence Proxy

## Purpose
This file provides the strongest local workflow comparison currently supported
by the revision package without fabricating participant or external-GUI timing
data. It is a proxy based on existing experiment outputs, not a controlled user
study.

## Evidence Sources
- AutoSiMP configuration outcomes: `autosimp_cad_FIX.tex`, Table
  `tab:pipeline`, and schedule-controller comparison figure notes.
- Template/manual baseline proxy:
  `diagnostic_suite/template_workflow_baseline.csv`.
- Ambiguity exposure:
  `diagnostic_suite/ambiguity_benchmark.csv`.
- User/operator protocol package for future timing: `protocols/`.

## Six-Task Workflow Proxy

| Task type requested by checklist | Case / prompt source | AutoSiMP outcome | Template/manual proxy burden | Ambiguity handling | Interpretation |
| --- | --- | --- | --- | --- | --- |
| Cantilever | `cantilever_basic` | Exact field match; `0.0%` compliance penalty in Table `tab:pipeline`. | 2/9 fields require manual completion in template proxy. | No ambiguity flag required. | AutoSiMP removes routine field entry for this canonical task. |
| MBB beam | `mbb_beam` | Exact field match; `+0.6%` penalty with LLM controller and `+0.4%` in schedule figure. | 1/9 fields require manual completion. | No ambiguity flag required; MBB convention is encoded in benchmark definition. | Template is already close because the prompt is explicit, but AutoSiMP resolves benchmark convention. |
| Passive-hole cantilever | `cantilever_with_hole` | Exact field match; `0.0%` penalty. | 2/9 fields require manual completion. | Canonical case has explicit center/radius; ambiguous variants are covered separately. | AutoSiMP correctly transfers passive-region intent into the structured spec. |
| L-bracket | `lbracket` | Solver-ready but valid-but-unintended; load y-coordinate differs, `+119%` penalty. | 1/9 fields require manual completion, but template burden alone misses semantic ambiguity. | Should be flagged/reviewed because "lower part" admits plausible alternatives. | This is the primary human-verification example; preview/confirmation is necessary. |
| Multi-load bracket/cantilever | `dual_load` | Field-level match; `+6.4%` penalty in Table `tab:pipeline`. | 2/9 fields require manual completion. | Upper/lower coordinates are convention choices that should be previewed. | AutoSiMP handles multiple loads, but visual verification remains important. |
| Ambiguous prompt | `put the load near the right side under the hole` from invalid/ambiguity suites | Solver should be blocked or warned before solve. | Not measured as a completed configuration. | Boundary ambiguity detected in local pre-solve benchmark and ambiguity suite. | Ambiguity detection is safety evidence, not a productivity result. |

## What This Does and Does Not Support
- Supports: bounded evidence that AutoSiMP reduces structured-field completion
  burden for canonical tasks and exposes ambiguity in diagnostic prompts.
- Does not support: participant productivity gains, novice/expert usability,
  external-GUI superiority, or statistically general HCI conclusions.
- Required next evidence for stronger claims: record actual participant or
  operator timing using `protocols/operator_run_sheet.csv` and analyze it
  with `protocols/aggregate_study_results.py`.
