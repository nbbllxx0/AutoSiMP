# Data Dictionary

## Diagnostic CSV files

- `prompt`: natural-language input supplied to the deterministic or model
  configurator.
- `field_matches` / `field_total`: number of scored `ProblemSpec` fields that
  match the author-defined canonical reference.
- `field_accuracy`: `field_matches / field_total` for scorable rows.
- `ambiguity_flags`: deterministic phrases or conditions requiring review.
- `manual_repair_required`: whether a parsed output requires human correction
  before it can represent the intended reference problem.
- `pre_solve_blocking_errors`: number of conditions that block solver entry.
- `pre_solve_warnings`: non-blocking conditions exposed for confirmation.

## Model-run ledger

- `run_id`: unique model/prompt/repeat identifier.
- `model_provider`, `model_name`, `model_version`: recorded API condition.
- `run_timestamp`: UTC timestamp recorded by the live-run harness.
- `temperature`: requested sampling temperature.
- `raw_output_file`: relative path to the archived provider response.
- `parsed_spec_file`: relative path to the parsed `ProblemSpec` artifact.
- `parse_success`: whether schema-conforming JSON was recovered.

## Solver results

- `compliance`: reported compliance objective for the stated normalized load
  and material assumptions.
- `grayness`: density grayness measure used by the evaluator.
- `passed`: whether all stated blocking evaluator gates pass.
- `attempts`: number of solver attempts used by the bounded retry loop.

Compliance values are benchmark-specific and are not certified engineering
allowables. Timing fields are diagnostic wall-clock records, not productivity
or speedup claims.
