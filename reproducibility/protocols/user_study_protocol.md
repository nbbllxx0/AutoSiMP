# Controlled Configuration/User Study Protocol

## Objective
Measure whether AutoSiMP reduces configuration errors and setup time compared
with existing structured workflows for standard and ambiguous SIMP topology
optimization setup tasks.

## Participants
- Target: 8-12 participants minimum for a revision pilot.
- Strata: topology optimization/FEA novices and experienced TO/FEA users.
- Use anonymized participant IDs only. Do not record names, emails, or other
  direct identifiers in the analysis CSV.

## Conditions
- `autosimp`: natural-language prompt through AutoSiMP, with required preview
  and edit opportunity before solving.
- `template`: structured ProblemSpec/JSON template editing.
- `external_gui`: selected external GUI/app or notebook/template workflow.

If an external GUI is unavailable, run `template` first and report
`external_gui` as not executed rather than substituting claims.

## Design
- Within-subject design when feasible: every participant completes all
  conditions on different task variants.
- Counterbalance condition order using Latin-square ordering:
  - A: autosimp, template, external_gui
  - B: template, external_gui, autosimp
  - C: external_gui, autosimp, template
- Time limit: 12 minutes per task-condition pair.
- Participants may ask tool-operation questions, but not modeling-answer
  questions.

## Tasks
Use `task_packet.md`, `scoring_rubric.md`, and
`participant_survey_form.md`. Minimum pilot:
- T1 cantilever.
- T2 MBB beam.
- T3 cantilever with passive hole.
- T4 ambiguous L-bracket.
- T5 normalized multi-load bracket.

## Metrics
- `time_seconds`: from task reveal to submitted specification.
- `valid_configuration`: pre-solve checks have no blocking errors.
- `field_accuracy`: fraction of required fields matching the adjudicated reference specification.
- `bc_error_count`: incorrect or missing support/load fields.
- `manual_correction_count`: participant edits after preview or validation.
- `preview_warning_count`: warnings shown before solving.
- `solved`: whether a solver run was completed.
- `evaluator_passed`: whether all evaluator checks passed if solved.
- `workload_mental`, `workload_effort`, `workload_frustration`: 1-7 short-form
  workload ratings.
- `confidence`: 1-7 user confidence in submitted configuration.

## Analysis Plan
Primary outcomes:
- Median time to valid configuration by condition.
- Valid-configuration rate by condition.
- Field accuracy by condition and task.

Secondary outcomes:
- BC error count.
- Manual correction count.
- Workload ratings.
- Confidence versus actual correctness.

Use paired comparisons only for participants who completed both compared
conditions. Report medians and interquartile ranges; avoid broad claims from a
small pilot.

## Data Collection Instruments
- Use `study_raw_results_template.csv` for analysis-ready rows.
- Use `participant_survey_form.md` after each task to collect workload,
  confidence, and short free-response notes.
- Use `scoring_rubric.md` immediately after each submitted configuration to
  score field accuracy, BC errors, correction counts, and ambiguity handling.

## Reporting Boundary
The study measures configuration assistance. It does not certify engineering
validity, structural safety, or real-world design suitability.
