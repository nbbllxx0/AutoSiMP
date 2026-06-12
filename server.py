"""
server.py — REST API + SSE streaming for AutoSiMP browser demo.

Endpoints:
    POST /solve         — Run optimization, return final result
    POST /solve_stream  — SSE: stream per-iteration progress + final result
    GET  /health        — Health check

Usage:
    pip install flask flask-cors
    python server.py
"""

from __future__ import annotations

import json
import time
import traceback
import threading
import queue
import numpy as np

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from problem_spec import ProblemSpec
from bc_generator import generate_bc, spec_to_simp_params
from auto_simp import (
    _build_controller, ControllerWrapper,
    install_passive_patch, uninstall_passive_patch,
)
from evaluator_agent import evaluate
from configurator_agent import configure

try:
    from pub_simp_solver import SIMPParams, run_simp
except ImportError:
    SIMPParams = None
    run_simp = None

app = Flask(__name__)
CORS(app)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "solver": "AutoSiMP", "version": "0.2.0"})


@app.route("/configure", methods=["POST"])
def configure_prompt():
    """Convert a natural-language prompt into a validated ProblemSpec."""
    try:
        data = request.get_json() or {}
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            return jsonify({"success": False, "error": "Missing prompt"}), 400

        result = configure(
            prompt,
            model=data.get("model", "gemini-3.1-flash-lite-preview"),
            temperature=float(data.get("temperature", 0.0)),
            verbose=bool(data.get("verbose", False)),
        )
        return jsonify({
            "success": True,
            "spec": result.spec.to_dict(),
            "raw_dict": result.raw_dict,
            "warnings": result.warnings,
            "llm_used": result.llm_used,
            "error": result.error,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


def _run_solve(spec, controller_name, max_iter, progress_queue=None):
    """Run SIMP solver, optionally pushing per-iteration progress to a queue."""
    bc = generate_bc(spec)
    kw = spec_to_simp_params(spec)
    kw["max_iter"] = max_iter
    params = SIMPParams(**kw)

    inner = _build_controller(controller_name, max_iter, verbose=True)
    controller = ControllerWrapper(inner)

    if bc.passive_mask is not None:
        install_passive_patch(bc.passive_mask)

    # Wrap callback to capture progress
    orig_call = controller.__call__
    iter_count = [0]

    def callback_with_progress(state, rho):
        iter_count[0] += 1
        action = orig_call(state, rho)

        if progress_queue is not None and iter_count[0] % 2 == 0:
            nelx = spec.nelx
            nely = spec.nely
            nelz = spec.nelz or 0
            is_3d = spec.is_3d
            n_elem = len(rho)

            # Send full density for small meshes, None for large
            rho_list = None
            if n_elem <= 5000:
                if is_3d and nelz > 0:
                    rho_list = rho.reshape(nelx, nely, nelz).tolist()
                else:
                    rho_list = rho.reshape(nelx, nely).tolist()

            progress_queue.put({
                "type": "progress",
                "iter": int(state.iteration),
                "max_iter": max_iter,
                "compliance": float(state.compliance),
                "change": float(state.change) if hasattr(state, 'change') else 0,
                "penal": float(state.penal),
                "beta": float(state.beta) if hasattr(state, 'beta') else 1.0,
                "rho": rho_list,
                "nelx": nelx, "nely": nely, "nelz": nelz,
                "is_3d": is_3d,
            })
        return action

    controller.__call__ = callback_with_progress

    try:
        result = run_simp(params, callback=controller, verbose=True, bc_override=bc.bc_override)
    finally:
        if bc.passive_mask is not None:
            uninstall_passive_patch()

    return result, bc


@app.route("/solve", methods=["POST"])
def solve():
    """Blocking solve — returns final result."""
    try:
        data = request.get_json()
        spec = ProblemSpec.from_dict(data["spec"])
        errors = spec.validate()
        if errors:
            return jsonify({"success": False, "error": "; ".join(errors)}), 400

        controller = data.get("controller", "schedule")
        max_iter = data.get("max_iter", 150)

        print(f"[Server] Solving: {spec.nelx}x{spec.nely}"
              + (f"x{spec.nelz}" if spec.is_3d else "")
              + f"  vf={spec.volfrac}  max_iter={max_iter}")

        t0 = time.time()
        result, bc = _run_solve(spec, controller, max_iter)
        wall_time = time.time() - t0

        rho = result.get("rho_final")
        if rho is None:
            return jsonify({"success": False, "error": "No density field"}), 500

        nelx, nely = spec.nelx, spec.nely
        nelz = spec.nelz or 0
        is_3d = spec.is_3d

        rho_shaped = (rho.reshape(nelx, nely, nelz).tolist() if is_3d and nelz > 0
                      else rho.reshape(nelx, nely).tolist())

        eval_result = evaluate(result, spec, max_iter=max_iter, use_llm=False, verbose=False)

        return jsonify({
            "success": True, "rho": rho_shaped,
            "nelx": nelx, "nely": nely, "nelz": nelz, "is_3d": is_3d,
            "compliance": result.get("final_compliance", 0),
            "best_compliance": result.get("best_compliance", 0),
            "grayness": float(4 * np.mean(rho * (1 - rho))),
            "n_iter": result.get("n_iter", 0),
            "volfrac_actual": float(np.mean(rho)),
            "wall_time": round(wall_time, 2),
            "evaluation": {
                "passed": eval_result.passed, "summary": eval_result.summary,
                "checks": [{"name": c.name, "passed": c.passed, "value": c.value,
                            "threshold": c.threshold, "message": c.message}
                           for c in eval_result.checks],
            },
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/solve_stream", methods=["POST"])
def solve_stream():
    """SSE streaming solve — per-iteration progress + final result."""
    data = request.get_json()
    spec = ProblemSpec.from_dict(data["spec"])
    errors = spec.validate()
    if errors:
        return jsonify({"success": False, "error": "; ".join(errors)}), 400

    controller = data.get("controller", "schedule")
    max_iter = data.get("max_iter", 150)

    print(f"[Server/SSE] Streaming solve: {spec.nelx}x{spec.nely}"
          + (f"x{spec.nelz}" if spec.is_3d else "")
          + f"  vf={spec.volfrac}  max_iter={max_iter}")

    progress_q = queue.Queue()

    def run_in_thread():
        try:
            t0 = time.time()
            result, bc = _run_solve(spec, controller, max_iter, progress_q)
            wall_time = time.time() - t0

            rho = result.get("rho_final")
            nelx, nely = spec.nelx, spec.nely
            nelz = spec.nelz or 0
            is_3d = spec.is_3d

            rho_shaped = (rho.reshape(nelx, nely, nelz).tolist() if is_3d and nelz > 0
                          else rho.reshape(nelx, nely).tolist())

            eval_result = evaluate(result, spec, max_iter=max_iter, use_llm=False, verbose=False)

            progress_q.put({
                "type": "done", "success": True, "rho": rho_shaped,
                "nelx": nelx, "nely": nely, "nelz": nelz, "is_3d": is_3d,
                "compliance": result.get("final_compliance", 0),
                "best_compliance": result.get("best_compliance", 0),
                "grayness": float(4 * np.mean(rho * (1 - rho))),
                "n_iter": result.get("n_iter", 0),
                "volfrac_actual": float(np.mean(rho)),
                "wall_time": round(wall_time, 2),
                "evaluation": {
                    "passed": eval_result.passed, "summary": eval_result.summary,
                    "checks": [{"name": c.name, "passed": c.passed, "value": c.value,
                                "threshold": c.threshold, "message": c.message}
                               for c in eval_result.checks],
                },
            })
        except Exception as e:
            traceback.print_exc()
            progress_q.put({"type": "error", "error": str(e)})

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    def generate():
        while True:
            try:
                msg = progress_q.get(timeout=300)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Timeout'})}\n\n"
                break
            yield f"data: {json.dumps(msg, default=lambda x: float(x) if hasattr(x, '__float__') else None)}\n\n"
            if msg.get("type") in ("done", "error"):
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    print("=" * 60)
    print("  AutoSiMP Backend Server v0.2")
    print("  POST /solve        — Blocking solve")
    print("  POST /solve_stream — SSE streaming solve")
    print("  GET  /health       — Health check")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5555, debug=False, threaded=True)
