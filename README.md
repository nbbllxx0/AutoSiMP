# AutoSiMP

AutoSiMP is an inspectable workflow for configuring SIMP topology optimization problems from natural language. It drafts an editable `ProblemSpec`, converts the specification into solver-ready boundary conditions and passive-region masks, runs a three-field SIMP solver, and reports deterministic numerical checks.

The code is intended for research reproduction and inspection. It does not certify engineering designs; users should review generated specifications, units, loads, materials, and acceptance criteria before relying on any result.

## Repository Contents

- `problem_spec.py` - JSON-serializable problem schema and validation.
- `configurator_agent.py` - Gemini-backed natural-language to `ProblemSpec` configurator with deterministic safety rails.
- `bc_generator.py` - boundary-condition, force-vector, and passive-mask generation.
- `pub_simp_solver.py` - three-field SIMP solver.
- `pub_llm_agent.py` and `pub_baseline_controller.py` - adaptive and deterministic continuation controllers.
- `evaluator_agent.py` - connectivity, compliance, grayness, volume, convergence, thin-member, checkerboard, and load-path checks.
- `auto_simp.py` - Python API and command-line orchestrator.
- `run_experiments.py` and `generate_figures.py` - benchmark and figure utilities.
- `server.py` - Flask backend for the browser demo.
- `autosimp-demo/autosimp-demo/` - full React/Vite browser demo source.
- `web_demo/` - minimal React/Vite smoke demo source.
- `reproducibility/` - canonical prompt/spec index, deterministic diagnostics,
  raw and parsed model outputs, aggregate benchmark tables, retry records,
  normalized-bracket results, and bounded 3-D backend evidence.

## Install

### Conda

```powershell
conda env create -f environment.yml
conda activate autosimp
```

### venv + pip

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional Gemini-backed parsing/control uses the environment variable below. Leave it unset for deterministic preset/spec workflows.

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

Do not commit API keys, `.env` files, or local output folders.

## Quick Start

Run built-in presets without an API key:

```powershell
python auto_simp.py --preset cantilever --controller schedule --max-iter 80 -v
python auto_simp.py --preset mbb --controller schedule --max-iter 80 -v
python auto_simp.py --preset cantilever_with_hole --controller schedule --max-iter 80 -v
```

Run from a JSON specification:

```powershell
python auto_simp.py --spec examples\cantilever_with_hole.json --controller schedule -v
```

Run from natural language with Gemini configured:

```powershell
python auto_simp.py "cantilever beam, left edge fixed, downward point load at the middle of the right edge, 50% volume fraction" --controller schedule -v
```

By default, outputs are written to `autosimp_output/`.

## Python API

```python
from auto_simp import auto_simp, PRESETS

report = auto_simp(
    spec=PRESETS["cantilever"],
    controller="schedule",
    max_iter=80,
    verbose=True,
)

print(report["evaluation"]["passed"])
```

## Experiments

List benchmark cases and controllers:

```powershell
python run_experiments.py --list-problems
python run_experiments.py --list-controllers
python run_experiments.py --list-pipeline-cases
```

Representative paper-facing runs:

```powershell
python run_experiments.py --pipeline --controllers llm --max-iter 300 --output-dir results_pipeline_v2
python run_experiments.py --controllers llm schedule expert three_field tail_only fixed --max-iter 300 --output-dir results_controllers_v2
python run_experiments.py --retry-experiment --controllers schedule --max-iter 300 --output-dir results_retry
```

Generate figures:

```powershell
python generate_figures.py --table 1 --output-dir paper_figures
python generate_figures.py --table 2 --output-dir paper_figures
python generate_figures.py --table 3d --output-dir paper_figures
python generate_figures.py --table convergence --output-dir paper_figures
```

Full benchmark runs can take hours depending on mesh size, controller choice, and whether LLM calls are enabled.

## Validation Scope

The associated manuscript evaluates AutoSiMP as a bounded, inspectable
problem-specification and solver-orchestration workflow. The code release
supports reproduction of the solver, controller, boundary-condition generator,
evaluator, and browser inspection workflow. The `reproducibility/` directory
contains the manuscript-side diagnostic harnesses, canonical prompt/reference
index, row-level CSV/JSON outputs, raw and parsed Gemini artifacts, result
summaries, retry records, normalized-bracket data, and bounded 3-D backend
evidence. See `reproducibility/README.md` and its SHA-256 manifest.

Current manuscript evidence includes:

- 10 canonical configuration prompts, 10 challenge prompts, a 100-prompt held-out
  suite, and an eight-prompt rectangular 3-D configuration track.
- Stored configured-spec match: 7 of 10 nine-field exact (86/90 fields); four
  configured specs use a different mesh; Bridge, dual-load, and L-bracket are
  semantic failures that still pass the five numerical gates
  (`frozen_specs/configured_specs.json`, `results/e2_spec_match.json`).
- Matched LLM vs rule-only scores: 85/90 vs 89/90 (canonical), 71/90 vs 67/90
  (challenge), 670/900 vs 652/900 (held-out).
- Preview-surfacing (E11): 32 detections against 71 named silent misses on 120
  prompts (31% detection). The gate detects linguistic hedges, not semantic error.
- 3-D configuration track: 79/80 on an own ten-field denominator at canonical
  difficulty.
- Rule-only parser ablation: 89/90 canonical, 67/90 challenge, 652/900 held-out.
- A template-style field-completion proxy (mean 4.09 of nine fields).
- Repeated Gemini Flash-Lite-family model checks and a six-model Gemini-family
  stress test. These runs are single-provider evidence and should not be
  interpreted as provider-diverse robustness.
- A normalized multi-load bracket workflow case with solver/evaluator checks.
- Aggregate pipeline, controller, retry, and coarse 3-D result tables.

The release does not include recruited user timing, external GUI/operator
timing, independent engineering sign-off, or provider-diverse model evidence.
Do not use it to claim productivity gains, engineering certification, or broad
LLM robustness beyond the reported scope.

## Browser Demo

Start the backend:

```powershell
python server.py
```

Start the full demo in another terminal:

```powershell
cd autosimp-demo\autosimp-demo
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

The browser demo is intended for local inspection. Prefer the Python backend
with `GEMINI_API_KEY` set in the shell for LLM-backed parsing. If you use the
browser-side LLM controls, the entered key is kept in memory only and is not
persisted by the demo.

Backend endpoints:

- `GET /health`
- `POST /configure`
- `POST /solve`
- `POST /solve_stream`

## ProblemSpec Example

```json
{
  "Lx": 2.0,
  "Ly": 1.0,
  "Lz": 0.0,
  "nelx": 80,
  "nely": 40,
  "nelz": 0,
  "E": 1.0,
  "nu": 0.3,
  "volfrac": 0.4,
  "supports": [
    {"type": "edge", "edge": "left", "constraint": "fixed"}
  ],
  "loads": [
    {"type": "point", "x": 2.0, "y": 0.5, "z": 0.0, "fx": 0.0, "fy": -1.0, "fz": 0.0}
  ],
  "passive_regions": [
    {"type": "circle", "cx": 1.0, "cy": 0.5, "radius": 0.15, "kind": "void"}
  ],
  "max_iter": null,
  "rmin": null
}
```

## Notes for Readers

- Use `--controller schedule` for deterministic reproduction.
- Use `--spec` when you want to bypass LLM parsing and inspect exact inputs.
- The configurator safety rails reject or repair many invalid specifications, but generated specs should still be reviewed before solving.
- 3-D and large 2-D meshes benefit from `pyamg`.
- The browser interface is an inspection aid; the Python CLI is the most direct reproduction path.
- Manuscript-facing benchmark outputs are versioned under `reproducibility/`;
  unrelated local solver outputs and manuscript working files remain excluded.

## License

This repository is released under the BSD 3-Clause License. See `LICENSE`.

## Citation

If you use this code, cite the associated AutoSiMP manuscript and the related LLM-controller paper:

- An earlier preprint of this work is arXiv:2603.27000; its title and claims predate this revision.
- Yang, Wang, Wang, Large language models as optimization controllers: Adaptive continuation for SIMP topology optimization, Advances in Engineering Software 223, 104304, 2026, doi:10.1016/j.advengsoft.2026.104304.
