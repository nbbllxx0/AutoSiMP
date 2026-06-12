# AutoSiMP

AutoSiMP is a human-verifiable workflow for configuring SIMP topology optimization problems from natural language. It drafts an editable `ProblemSpec`, converts the specification into solver-ready boundary conditions and passive-region masks, runs a three-field SIMP solver, and reports deterministic numerical checks.

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
- Generated benchmark outputs and local manuscript/revision files are intentionally not part of the code release.

## License

This repository is released under the BSD 3-Clause License. See `LICENSE`.

## Citation

If you use this code, cite the associated AutoSiMP manuscript and the related LLM-controller paper:

- AutoSiMP: Human-Verifiable Natural-Language Configuration for SIMP Topology Optimization.
- Large Language Models as Optimization Controllers: Adaptive Continuation for SIMP Topology Optimization, arXiv:2603.25099.
