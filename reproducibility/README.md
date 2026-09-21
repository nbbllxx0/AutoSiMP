# AutoSiMP Reproducibility Materials

This directory contains the prompt sets, reference specifications, diagnostic
harnesses, raw and parsed model outputs, aggregate benchmark tables, retry
records, normalized-bracket results, and bounded 3-D backend data used by the
AutoSiMP manuscript.

The materials support the manuscript's reported results. They do not contain
recruited-participant data, external GUI timing, independent engineering
certification, private data, or API credentials.

## Directory map

- `canonical_prompt_spec_index.md`: the 10 canonical natural-language prompts,
  author-defined reference `ProblemSpec` objects, reported outcomes, and
  alternate-interpretation notes.
- `diagnostic_suite/`: deterministic ambiguity, malformed-specification,
  safety-rail, rule-only parser, 100-prompt held-out, template-field, and
  normalized-bracket diagnostics, including `revision_experiments.py` and its
  CSV/JSON outputs.
- `model_checks/`: prompt protocol, aggregation scripts, row-level model-run
  ledgers, raw response JSON, parsed `ProblemSpec` JSON, and summaries for the
  repeated Flash-Lite and six-model Gemini-family checks.
- `stable_configurator/`: the current stable-endpoint 15-case configurator
  rerun used for the submission-time reproducibility check.
- `benchmark_results/`: aggregate pipeline, controller, retry, and coarse 3-D
  tables produced by the main experiment runner.
- `post_solve_retry/`: injected first-attempt failure/recovery harness and
  row-level outputs.
- `normalized_bracket/`: normalized multi-feature bracket solver and
  mesh-sensitivity outputs.
- `backend_3d/`: bounded optimized-backend scripts, operator/filter/sensitivity
  verification tables, execution summaries, histories, and retained density
  fields.
- `protocols/`: prepared but unexecuted user/operator and independent
  engineering-review protocols. These files document future-work procedures;
  they are not reported results.
- `workflow_evidence_proxy.md`: six-task mapping used to interpret the
  field-completion proxy without making productivity claims.
- `verify_archive.py`: offline integrity, portability, reference, and headline
  value checks.
- `LICENSE` and `CITATION.cff`: reuse and citation metadata for the archive.

## Headline checks

The supplied outputs record the following manuscript values:

- ambiguity detection: 30/30;
- malformed-specification issue sets: 8/8;
- safety-rail ablation: 8/8 caught with rails, 0/8 without;
- rule-only parser: 89/90 canonical fields, 67/90 challenge fields, and
  652/900 fields on the 100-prompt held-out suite;
- template-style field-completion proxy: 4.09/9 mean manual fields across
  121 cases;
- repeated Flash-Lite checks: 150/150 parseable in each temperature condition
  (300/300 combined), with mean scored field accuracy 0.794 and 0.790;
- Gemini-family stress test: 33/60 parseable rows;
- current stable configurator rerun: 15/15 schema-valid and all checks passed;
- injected post-solve retry: 12/12 recovered after the forced first-attempt
  failure;
- normalized bracket mesh check: all three reported meshes pass the evaluator.

## Reproduction

From the repository root, create the documented environment and run:

python reproducibility\verify_archive.py
```powershell
python reproducibility\diagnostic_suite\revision_experiments.py --output-dir reproduced_diagnostics
python reproducibility\post_solve_retry\post_solve_retry_recovery.py --output-dir reproduced_retry --initial-iter 10 --retry-iter 80 --max-attempts 3 --inject-first-failure
python reproducibility\normalized_bracket\normalized_bracket_case_solve.py
python reproducibility\normalized_bracket\normalized_bracket_mesh_sensitivity.py
```

Live model calls require a user-supplied `GEMINI_API_KEY`; archived outputs do
not. Model behavior can change after provider endpoint updates, so the archived
model identifiers, temperatures, timestamps, raw outputs, and parsed outputs
are retained as evidence of the reported run conditions.

The optimized 3-D backend check has additional dependencies and hardware
requirements documented by the scripts in `backend_3d/`. Its outputs are
included as bounded compatibility evidence, not as application-scale 3-D
engineering validation.

## Integrity and scope

`SHA256SUMS.csv` records every file in this directory except the manifest
itself. Relative paths are used throughout the public copy. The archive does
not include credentials or private local machine paths.

The manuscript and these materials use "author-defined canonical reference
specification" rather than implying a unique or independently certified
engineering reference.
