# External GUI/App or Template Baseline Operator Protocol

## Objective
Collect timing and error data for at least one non-AutoSiMP configuration
workflow under a repeatable operator protocol.

## Acceptable Baselines
- Existing topology optimization GUI/app.
- Educational TopOpt notebook or web app with boundary-condition controls.
- JSON/ProblemSpec template edited manually.
- Python script/template workflow.

Record the exact tool name, version or commit, URL/path, and any limitations.

## Operator Rules
- Use one trained operator for all baseline tasks if recruited participants are
  not available.
- The operator may use the target tool's documentation but may not inspect
  AutoSiMP-generated answers during the baseline run.
- Start timing when the task prompt is revealed.
- Stop timing when a complete configuration is ready for validation or solve.
- Record every correction required after validation.

## Required Evidence Per Task
- Screenshot or saved configuration file when the tool supports export.
- Raw timing in seconds.
- Final specification fields transcribed into `study_raw_results_template.csv`.
- Timestamp and evidence-file paths recorded in `operator_run_sheet.csv`.
- Field accuracy and BC errors scored with `scoring_rubric.md`.
- Notes on fields the baseline could not represent.

For lower-friction collection, use `prepare_operator_packet.py` to generate
prompt-only task sheets and blank JSON submission forms. After the run,
`score_operator_submissions.py` can score completed JSON files and merge
run-sheet timing into analysis-ready rows.

## Minimum Tasks
Use the same task IDs as `task_packet.md`.

Recommended minimum for an operator baseline:
- T1 cantilever.
- T3 passive-hole cantilever.
- T4 ambiguous L-bracket.
- T5 normalized multi-load bracket.

## Reporting Boundary
An operator baseline is weaker than a participant user study. Report it as
operator timing, not user productivity, and do not generalize to novice users.
Do not report the baseline until a collected run-sheet file passes strict
validation, for example:

```powershell
python study_protocol\validate_operator_run_sheet.py study_protocol\operator_run_sheet_collected.csv --condition external_gui --min-populated 4 --require-evidence
```

The corresponding raw-result rows must also be scored with
`scoring_rubric.md`.
