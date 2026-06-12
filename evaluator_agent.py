"""
evaluator_agent.py
------------------
Post-solve quality evaluator for AutoSIMP.

Takes the solver result dict and ProblemSpec, performs deterministic structural
checks, and optionally calls an LLM for qualitative assessment.

Deterministic checks (always run, no API needed):
  1. Structural connectivity — is the density field one connected piece
     from every load point to every support?
  2. Compliance reasonableness — is final compliance within expected range?
  3. Grayness — is the design sufficiently black-and-white?
  4. Volume fraction — does it respect the constraint?
  5. Convergence — did the solver actually converge or hit max_iter?

LLM check (optional, requires API key):
  - Qualitative assessment of the topology (given a text summary of metrics).
  - Suggestions for re-run (different volfrac, mesh refinement, etc.).

Return:
  EvalResult with pass/fail, per-check details, and optional re-run hints.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from problem_spec import ProblemSpec, PointLoad, DistributedLoad


# ---------------------------------------------------------------------------
# Check result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    value: float           # the measured quantity
    threshold: float       # the pass/fail boundary
    message: str = ""


@dataclass
class EvalResult:
    """Complete evaluation of a solver run."""
    passed: bool                             # overall pass/fail
    checks: list[CheckResult] = field(default_factory=list)
    summary: str = ""
    rerun_hint: Optional[dict] = None        # suggested param changes for retry
    llm_assessment: Optional[str] = None     # qualitative LLM feedback


# ---------------------------------------------------------------------------
# 1. Structural connectivity (flood fill on binarized density)
# ---------------------------------------------------------------------------

def _check_connectivity_2d(
    rho: np.ndarray,
    nelx: int, nely: int,
    spec: ProblemSpec,
    threshold: float = 0.3,
) -> CheckResult:
    """
    Flood-fill on the binarized density field.  Check that every load node
    can reach every support node through connected solid elements.
    """
    # Binarize
    R = (rho.reshape(nelx, nely) >= threshold).astype(np.int32)

    hx = spec.Lx / nelx
    hy = spec.Ly / nely

    def coord_to_elem(x, y):
        """Map (x,y) → nearest element index (i,j)."""
        i = int(min(max(round(x / hx - 0.5), 0), nelx - 1))
        j = int(min(max(round(y / hy - 0.5), 0), nely - 1))
        return i, j

    # Collect seed elements from supports
    support_elems = set()
    for sup in spec.supports:
        if hasattr(sup, "edge"):
            # Edge support: sample elements along the edge
            edge = sup.edge
            if edge == "left":
                for j in range(nely):
                    support_elems.add((0, j))
            elif edge == "right":
                for j in range(nely):
                    support_elems.add((nelx - 1, j))
            elif edge == "bottom":
                for i in range(nelx):
                    support_elems.add((i, 0))
            elif edge == "top":
                for i in range(nelx):
                    support_elems.add((i, nely - 1))
        else:
            support_elems.add(coord_to_elem(sup.x, sup.y))

    # Collect load elements
    load_elems = set()
    for ld in spec.loads:
        if isinstance(ld, PointLoad):
            load_elems.add(coord_to_elem(ld.x, ld.y))
        elif isinstance(ld, DistributedLoad):
            edge = ld.edge
            if edge == "top":
                for i in range(nelx):
                    load_elems.add((i, nely - 1))
            elif edge == "bottom":
                for i in range(nelx):
                    load_elems.add((i, 0))
            elif edge == "left":
                for j in range(nely):
                    load_elems.add((0, j))
            elif edge == "right":
                for j in range(nely):
                    load_elems.add((nelx - 1, j))

    if not support_elems or not load_elems:
        return CheckResult(
            name="connectivity", passed=False, value=0.0, threshold=1.0,
            message="Could not identify support or load elements.")

    # Flood fill from support elements
    visited = np.zeros((nelx, nely), dtype=bool)
    stack = []
    for (si, sj) in support_elems:
        # Allow flood to start even if support element is void
        # (support is a node BC, not element density)
        if not visited[si, sj]:
            visited[si, sj] = True
            stack.append((si, sj))

    while stack:
        ci, cj = stack.pop()
        for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ni, nj = ci + di, cj + dj
            if 0 <= ni < nelx and 0 <= nj < nely:
                if not visited[ni, nj] and R[ni, nj]:
                    visited[ni, nj] = True
                    stack.append((ni, nj))

    # Check reachability from loads
    reachable = 0
    for (li, lj) in load_elems:
        # Check neighborhood (load node might be between elements)
        found = False
        for di in range(-1, 2):
            for dj in range(-1, 2):
                ni, nj = li + di, lj + dj
                if 0 <= ni < nelx and 0 <= nj < nely and visited[ni, nj]:
                    found = True
                    break
            if found:
                break
        if found:
            reachable += 1

    ratio = reachable / max(len(load_elems), 1)
    return CheckResult(
        name="connectivity", passed=(ratio >= 0.99),
        value=ratio, threshold=0.99,
        message=f"{reachable}/{len(load_elems)} load points connected to supports.")


def _check_connectivity_3d(
    rho: np.ndarray,
    nelx: int, nely: int, nelz: int,
    spec: ProblemSpec,
    threshold: float = 0.3,
) -> CheckResult:
    """
    3D flood-fill connectivity: 6-neighbor (face-adjacent) on the binarized
    density field.  Check that every load element can reach a support element.
    """
    R = (rho.reshape(nelx, nely, nelz) >= threshold).astype(np.int32)
    hx, hy, hz = spec.Lx / nelx, spec.Ly / nely, spec.Lz / nelz

    def coord_to_elem(x, y, z):
        i = int(min(max(round(x / hx - 0.5), 0), nelx - 1))
        j = int(min(max(round(y / hy - 0.5), 0), nely - 1))
        k = int(min(max(round(z / hz - 0.5), 0), nelz - 1))
        return i, j, k

    # Collect support seed elements
    support_elems = set()
    for sup in spec.supports:
        if hasattr(sup, "edge"):
            edge = sup.edge
            if edge == "left":
                for j in range(nely):
                    for k in range(nelz):
                        support_elems.add((0, j, k))
            elif edge == "right":
                for j in range(nely):
                    for k in range(nelz):
                        support_elems.add((nelx - 1, j, k))
            elif edge == "bottom":
                for i in range(nelx):
                    for k in range(nelz):
                        support_elems.add((i, 0, k))
            elif edge == "top":
                for i in range(nelx):
                    for k in range(nelz):
                        support_elems.add((i, nely - 1, k))
            elif edge == "front":
                for i in range(nelx):
                    for j in range(nely):
                        support_elems.add((i, j, 0))
            elif edge == "back":
                for i in range(nelx):
                    for j in range(nely):
                        support_elems.add((i, j, nelz - 1))
        else:
            support_elems.add(coord_to_elem(sup.x, sup.y, getattr(sup, 'z', 0.0)))

    # Collect load elements
    load_elems = set()
    for ld in spec.loads:
        if isinstance(ld, PointLoad):
            load_elems.add(coord_to_elem(ld.x, ld.y, ld.z))
        elif isinstance(ld, DistributedLoad):
            edge = ld.edge
            if edge == "top":
                for i in range(nelx):
                    for k in range(nelz):
                        load_elems.add((i, nely - 1, k))
            elif edge == "bottom":
                for i in range(nelx):
                    for k in range(nelz):
                        load_elems.add((i, 0, k))
            elif edge == "left":
                for j in range(nely):
                    for k in range(nelz):
                        load_elems.add((0, j, k))
            elif edge == "right":
                for j in range(nely):
                    for k in range(nelz):
                        load_elems.add((nelx - 1, j, k))
            elif edge == "front":
                for i in range(nelx):
                    for j in range(nely):
                        load_elems.add((i, j, 0))
            elif edge == "back":
                for i in range(nelx):
                    for j in range(nely):
                        load_elems.add((i, j, nelz - 1))

    if not support_elems or not load_elems:
        return CheckResult(
            name="connectivity", passed=False, value=0.0, threshold=1.0,
            message="Could not identify 3D support or load elements.")

    # 6-neighbor flood fill from supports
    visited = np.zeros((nelx, nely, nelz), dtype=bool)
    stack = []
    for seed in support_elems:
        si, sj, sk = seed
        if not visited[si, sj, sk]:
            visited[si, sj, sk] = True
            stack.append(seed)

    nbrs = [(-1,0,0),(1,0,0),(0,-1,0),(0,1,0),(0,0,-1),(0,0,1)]
    while stack:
        ci, cj, ck = stack.pop()
        for di, dj, dk in nbrs:
            ni, nj, nk = ci + di, cj + dj, ck + dk
            if (0 <= ni < nelx and 0 <= nj < nely and 0 <= nk < nelz
                    and not visited[ni, nj, nk] and R[ni, nj, nk]):
                visited[ni, nj, nk] = True
                stack.append((ni, nj, nk))

    # Check reachability
    reachable = 0
    for elem in load_elems:
        li, lj, lk = elem
        found = False
        for di in range(-1, 2):
            for dj in range(-1, 2):
                for dk in range(-1, 2):
                    ni, nj, nk = li + di, lj + dj, lk + dk
                    if (0 <= ni < nelx and 0 <= nj < nely and
                            0 <= nk < nelz and visited[ni, nj, nk]):
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            reachable += 1

    ratio = reachable / max(len(load_elems), 1)
    return CheckResult(
        name="connectivity", passed=(ratio >= 0.99),
        value=ratio, threshold=0.99,
        message=f"3D: {reachable}/{len(load_elems)} load regions connected to supports.")


# ---------------------------------------------------------------------------
# 1b. Thin-member detection (one-element-wide connections)
# ---------------------------------------------------------------------------

def _check_thin_members_2d(
    rho: np.ndarray,
    nelx: int, nely: int,
    threshold: float = 0.3,
    max_thin_fraction: float = 0.10,
) -> CheckResult:
    """
    Count elements that form one-element-wide connections (structurally fragile,
    often manufacturing-incompatible).

    An element is "thin" if it is solid but has ≤1 solid face-neighbor in
    at least one axis.  This catches horizontal/vertical one-pixel bars and
    diagonal one-pixel connections.
    """
    R = (rho.reshape(nelx, nely) >= threshold).astype(np.int32)
    n_solid = int(R.sum())
    if n_solid == 0:
        return CheckResult(
            name="thin_members", passed=True, value=0.0,
            threshold=max_thin_fraction,
            message="No solid elements.")

    # For each solid element, count face-adjacent solid neighbors
    thin_count = 0
    for i in range(nelx):
        for j in range(nely):
            if R[i, j] == 0:
                continue
            # Count x-neighbors and y-neighbors separately
            nx = 0
            if i > 0 and R[i-1, j]:
                nx += 1
            if i < nelx-1 and R[i+1, j]:
                nx += 1
            ny = 0
            if j > 0 and R[i, j-1]:
                ny += 1
            if j < nely-1 and R[i, j+1]:
                ny += 1
            # Thin = isolated in at least one axis direction
            if nx == 0 or ny == 0:
                thin_count += 1

    thin_frac = thin_count / n_solid
    return CheckResult(
        name="thin_members", passed=(thin_frac <= max_thin_fraction),
        value=round(thin_frac, 4), threshold=max_thin_fraction,
        message=f"{thin_count}/{n_solid} solid elements are thin-members "
                f"({thin_frac:.1%})")


# ---------------------------------------------------------------------------
# 1c. Checkerboard artifact detection
# ---------------------------------------------------------------------------

def _check_checkerboard(
    rho: np.ndarray,
    nelx: int, nely: int,
    max_checker: float = 0.10,
) -> CheckResult:
    """
    Detect checkerboard artifacts: 2×2 blocks where diagonal elements are
    similar but face-adjacent elements differ.  High values indicate the
    filter radius was too small or the Heaviside projection failed.
    """
    R = rho.reshape(nelx, nely)
    if nelx < 2 or nely < 2:
        return CheckResult(
            name="checkerboard", passed=True, value=0.0,
            threshold=max_checker, message="Mesh too small to check.")

    # Compute local checkerboard metric on 2×2 blocks:
    # checker_score = |R[i,j] + R[i+1,j+1] - R[i+1,j] - R[i,j+1]| / 2
    # This is 0 for smooth fields, 1 for perfect checkerboard
    d = np.abs(R[:-1, :-1] + R[1:, 1:] - R[1:, :-1] - R[:-1, 1:]) / 2.0
    mean_checker = float(np.mean(d))

    return CheckResult(
        name="checkerboard", passed=(mean_checker <= max_checker),
        value=round(mean_checker, 4), threshold=max_checker,
        message=f"Mean checkerboard index = {mean_checker:.4f} "
                + ("(clean)" if mean_checker <= max_checker else "(artifacts present)"))


# ---------------------------------------------------------------------------
# 1d. Load path efficiency (shortest-path vs structural-path ratio)
# ---------------------------------------------------------------------------

def _check_load_path_efficiency(
    rho: np.ndarray,
    nelx: int, nely: int,
    spec: ProblemSpec,
    threshold_bin: float = 0.3,
    min_efficiency: float = 0.15,
) -> CheckResult:
    """
    Measure how efficiently the structure connects loads to supports.

    Efficiency = (Euclidean distance from load to nearest support) /
                 (shortest path through solid elements from load to support).

    A value of 1.0 = straight line.  Values < 0.15 indicate tortuous,
    inefficient load paths that likely result from local minima.

    Uses BFS on the binarized grid to find shortest solid-element path.
    """
    R = (rho.reshape(nelx, nely) >= threshold_bin).astype(np.int32)
    hx = spec.Lx / nelx
    hy = spec.Ly / nely

    def coord_to_elem(x, y):
        i = int(min(max(round(x / hx - 0.5), 0), nelx - 1))
        j = int(min(max(round(y / hy - 0.5), 0), nely - 1))
        return i, j

    # Collect support elements
    support_elems = set()
    for sup in spec.supports:
        if hasattr(sup, "edge"):
            edge = sup.edge
            if edge == "left":
                for j in range(nely):
                    support_elems.add((0, j))
            elif edge == "right":
                for j in range(nely):
                    support_elems.add((nelx-1, j))
            elif edge == "bottom":
                for i in range(nelx):
                    support_elems.add((i, 0))
            elif edge == "top":
                for i in range(nelx):
                    support_elems.add((i, nely-1))
        else:
            support_elems.add(coord_to_elem(sup.x, sup.y))

    # Collect load elements
    load_points = []
    for ld in spec.loads:
        if isinstance(ld, PointLoad):
            load_points.append((ld.x, ld.y, coord_to_elem(ld.x, ld.y)))

    if not load_points or not support_elems:
        return CheckResult(
            name="load_path_efficiency", passed=True, value=1.0,
            threshold=min_efficiency,
            message="Skipped (no point loads or supports to measure).")

    # BFS from all supports simultaneously (distance map)
    from collections import deque
    dist = np.full((nelx, nely), -1, dtype=np.int32)
    queue = deque()
    for (si, sj) in support_elems:
        dist[si, sj] = 0
        queue.append((si, sj))

    while queue:
        ci, cj = queue.popleft()
        for di, dj in [(-1,0),(1,0),(0,-1),(0,1)]:
            ni, nj = ci + di, cj + dj
            if (0 <= ni < nelx and 0 <= nj < nely
                    and dist[ni, nj] < 0 and R[ni, nj]):
                dist[ni, nj] = dist[ci, cj] + 1
                queue.append((ni, nj))

    # Compute efficiency for each load point
    efficiencies = []
    for (lx, ly, (li, lj)) in load_points:
        # Find nearest support (Euclidean)
        min_euclid = float("inf")
        for sup in spec.supports:
            if hasattr(sup, "edge"):
                # Approximate: distance to nearest point on edge
                if sup.edge == "left":
                    d = lx
                elif sup.edge == "right":
                    d = spec.Lx - lx
                elif sup.edge == "bottom":
                    d = ly
                elif sup.edge == "top":
                    d = spec.Ly - ly
                else:
                    d = float("inf")
            else:
                d = ((lx - sup.x)**2 + (ly - sup.y)**2)**0.5
            min_euclid = min(min_euclid, d)

        # BFS path length (in element units, convert to physical distance)
        # Check neighborhood of load point
        bfs_dist = -1
        for di in range(-1, 2):
            for dj in range(-1, 2):
                ni, nj = li + di, lj + dj
                if 0 <= ni < nelx and 0 <= nj < nely and dist[ni, nj] >= 0:
                    if bfs_dist < 0 or dist[ni, nj] < bfs_dist:
                        bfs_dist = dist[ni, nj]

        if bfs_dist < 0 or min_euclid < 1e-10:
            continue  # unreachable or on support

        physical_path = bfs_dist * ((hx**2 + hy**2)**0.5 / 2 + (hx + hy) / 4)
        # More accurate: BFS on grid counts steps, each step ≈ max(hx, hy)
        physical_path = bfs_dist * max(hx, hy)
        eff = min_euclid / max(physical_path, 1e-10)
        efficiencies.append(min(eff, 1.0))

    if not efficiencies:
        return CheckResult(
            name="load_path_efficiency", passed=True, value=1.0,
            threshold=min_efficiency,
            message="No measurable load paths.")

    mean_eff = float(np.mean(efficiencies))
    return CheckResult(
        name="load_path_efficiency", passed=(mean_eff >= min_efficiency),
        value=round(mean_eff, 4), threshold=min_efficiency,
        message=f"Mean load-path efficiency = {mean_eff:.3f} "
                + ("(direct)" if mean_eff >= 0.5 else
                   "(OK)" if mean_eff >= min_efficiency else
                   "(tortuous — possible local minimum)"))


# ---------------------------------------------------------------------------
# 2. Compliance reasonableness
# ---------------------------------------------------------------------------

def _check_compliance(result: dict) -> CheckResult:
    """
    Check that final compliance is finite, positive, and not absurdly high.
    Also check that it's not much worse than the best found during optimization.
    """
    final_c = result.get("final_compliance", float("inf"))
    best_c = result.get("best_compliance", float("inf"))

    if not np.isfinite(final_c) or final_c <= 0:
        return CheckResult(
            name="compliance", passed=False,
            value=final_c, threshold=0.0,
            message="Final compliance is non-finite or non-positive.")

    # Final should not be more than 100% worse than best
    if best_c > 0 and np.isfinite(best_c):
        ratio = final_c / best_c
        passed = ratio < 2.0
        return CheckResult(
            name="compliance", passed=passed,
            value=ratio, threshold=2.0,
            message=f"Final/best ratio = {ratio:.3f} "
                    + ("(OK)" if passed else "(degraded — tail may have hurt)"))
    else:
        return CheckResult(
            name="compliance", passed=True,
            value=final_c, threshold=float("inf"),
            message=f"Final compliance = {final_c:.4f} (no valid best to compare).")


# ---------------------------------------------------------------------------
# 3. Grayness check
# ---------------------------------------------------------------------------

def _check_grayness(result: dict, threshold: float = 0.15) -> CheckResult:
    """Measure how binary the final design is.  4*mean(rho*(1-rho))."""
    rho = result.get("rho_final", np.array([]))
    if rho.size == 0:
        return CheckResult(
            name="grayness", passed=False, value=1.0, threshold=threshold,
            message="No density field available.")
    gray = float(4.0 * np.mean(rho * (1.0 - rho)))
    return CheckResult(
        name="grayness", passed=(gray <= threshold),
        value=gray, threshold=threshold,
        message=f"Grayness = {gray:.4f} " +
                ("(crisp)" if gray <= threshold else "(too gray — needs more sharpening)"))


# ---------------------------------------------------------------------------
# 4. Volume fraction check
# ---------------------------------------------------------------------------

def _check_volume(result: dict, target_vf: float,
                   tolerance: float = 0.02) -> CheckResult:
    """Check that the final volume fraction matches the target."""
    rho = result.get("rho_final", np.array([]))
    if rho.size == 0:
        return CheckResult(
            name="volume_fraction", passed=False, value=0.0,
            threshold=target_vf, message="No density field.")
    actual = float(np.mean(rho))
    diff = abs(actual - target_vf)
    return CheckResult(
        name="volume_fraction", passed=(diff <= tolerance),
        value=actual, threshold=target_vf,
        message=f"Actual vf={actual:.4f} vs target={target_vf:.4f} "
                f"(diff={diff:.4f})")


# ---------------------------------------------------------------------------
# 5. Convergence check
# ---------------------------------------------------------------------------

def _check_convergence(result: dict, max_iter: int) -> CheckResult:
    """
    Did the solver converge?

    Three ways to pass:
      1. Solver exited early (n_iter < effective_max)
      2. Compliance was stable over the final 20% of iterations
         (common with Heaviside at high β: design is converged but
         the OC move limit keeps `change` above tol)
      3. Grayness < 0.01 AND compliance ratio final/best < 1.05
         (the design is crisp and good — functional convergence)
    """
    n_iter = result.get("n_iter", max_iter)
    tail_cfg = result.get("tail_config", {})
    tail_iters = tail_cfg.get("tail_iters", 0) if tail_cfg.get("enabled") else 0
    effective_max = max_iter + tail_iters

    # Check 1: early exit
    if n_iter < effective_max:
        return CheckResult(
            name="convergence", passed=True,
            value=float(n_iter), threshold=float(effective_max),
            message=f"Solver converged at iter {n_iter}.")

    # Check 2: compliance stability in final 20%
    hist = result.get("compliance_history", [])
    if len(hist) >= 10:
        tail_window = hist[int(len(hist) * 0.8):]
        if len(tail_window) >= 5:
            rel_range = ((max(tail_window) - min(tail_window))
                         / max(abs(min(tail_window)), 1e-10))
            if rel_range < 0.005:
                return CheckResult(
                    name="convergence", passed=True,
                    value=float(n_iter), threshold=float(effective_max),
                    message=f"Compliance stable (rel_range={rel_range:.5f}) "
                            f"over final {len(tail_window)} iters.")

    # Check 3: functionally converged (crisp + good compliance)
    final_gray = result.get("final_grayness", 1.0)
    final_c = result.get("final_compliance", float("inf"))
    best_c = result.get("best_compliance", float("inf"))
    if (final_gray < 0.01 and best_c > 0 and
            np.isfinite(final_c) and final_c / best_c < 1.05):
        return CheckResult(
            name="convergence", passed=True,
            value=float(n_iter), threshold=float(effective_max),
            message=f"Functionally converged: crisp (gray={final_gray:.4f}) "
                    f"and near-best compliance.")

    return CheckResult(
        name="convergence", passed=False,
        value=float(n_iter), threshold=float(effective_max),
        message=f"Solver ran {n_iter} iters (hit limit {effective_max})")


# ---------------------------------------------------------------------------
# Optional LLM qualitative assessment
# ---------------------------------------------------------------------------

_EVAL_SYSTEM_PROMPT = """\
You are a topology optimization quality reviewer.  Given metrics from a solved
problem, provide a brief assessment (2-3 sentences) and, if the result is poor,
suggest ONE specific parameter change for a re-run.

Respond ONLY with JSON:
{
  "assessment": "<2-3 sentence quality summary>",
  "quality": "good"|"acceptable"|"poor"|"failed",
  "rerun_suggestion": null | {"reason": "<why>", "change": {"volfrac": <float>} | {"max_iter": <int>} | {"rmin": <float>} | null}
}
"""


def _llm_evaluate(
    metrics: dict,
    model: str = "gemini-3.1-flash-lite-preview",
    api_key: Optional[str] = None,
) -> tuple[Optional[str], Optional[dict]]:
    """Optional LLM quality assessment. Returns (assessment_text, rerun_dict)."""
    key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None, None

    model_path = model if model.startswith("models/") else f"models/{model}"
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"{model_path}:generateContent?key={key}")

    prompt = json.dumps(metrics, indent=2)
    payload = {
        "system_instruction": {"parts": [{"text": _EVAL_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 400,
            "responseMimeType": "application/json",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        raw = resp_json["candidates"][0]["content"]["parts"][0]["text"]
        text = raw.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        assessment = parsed.get("assessment", "")
        rerun = parsed.get("rerun_suggestion")
        return assessment, rerun
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    result: dict,
    spec: ProblemSpec,
    max_iter: int = 300,
    use_llm: bool = True,
    model: str = "gemini-3.1-flash-lite-preview",
    api_key: Optional[str] = None,
    verbose: bool = False,
) -> EvalResult:
    """
    Run all quality checks on a completed solver result.

    Parameters
    ----------
    result : dict
        Output of run_simp().
    spec : ProblemSpec
        The problem specification (needed for connectivity check).
    max_iter : int
        The max_iter used for the solve (for convergence check).
    use_llm : bool
        Whether to call LLM for qualitative assessment.
    model, api_key : Gemini config.
    verbose : bool
        Print check results.

    Returns
    -------
    EvalResult
    """
    checks: list[CheckResult] = []

    # 1. Connectivity
    nelx = result.get("nelx", spec.nelx)
    nely = result.get("nely", spec.nely)
    nelz = result.get("nelz", spec.nelz)
    is_3d = result.get("is_3d", spec.is_3d)
    rho_final = result.get("rho_final", np.array([]))

    if not is_3d and rho_final.size == nelx * nely:
        checks.append(_check_connectivity_2d(rho_final, nelx, nely, spec))
    elif is_3d and rho_final.size == nelx * nely * nelz:
        checks.append(_check_connectivity_3d(rho_final, nelx, nely, nelz, spec))
    else:
        checks.append(CheckResult(
            name="connectivity", passed=True, value=1.0, threshold=1.0,
            message="Skipped (size mismatch)."))

    # 2. Compliance
    checks.append(_check_compliance(result))

    # 3. Grayness
    checks.append(_check_grayness(result))

    # 4. Volume fraction
    checks.append(_check_volume(result, spec.volfrac))

    # 5. Convergence
    checks.append(_check_convergence(result, max_iter))

    # 6. Thin-member detection (2D only, informational — doesn't gate pass/fail)
    if not is_3d and rho_final.size == nelx * nely:
        checks.append(_check_thin_members_2d(rho_final, nelx, nely))

    # 7. Checkerboard artifacts (2D only)
    if not is_3d and rho_final.size == nelx * nely:
        checks.append(_check_checkerboard(rho_final, nelx, nely))

    # 8. Load-path efficiency (2D only, informational)
    if not is_3d and rho_final.size == nelx * nely:
        checks.append(_check_load_path_efficiency(rho_final, nelx, nely, spec))

    # Overall pass (only first 5 core checks gate pass/fail;
    # checks 6-8 are quality metrics reported but don't block)
    core_checks = checks[:5]
    all_passed = all(c.passed for c in core_checks)

    if verbose:
        for c in checks:
            status = "PASS" if c.passed else "FAIL"
            print(f"  [{status}] {c.name}: {c.message}")

    # Summary
    n_fail = sum(1 for c in checks if not c.passed)
    summary = (f"{len(checks)} checks: {len(checks) - n_fail} passed, "
               f"{n_fail} failed.")

    # Build re-run hint from deterministic checks
    rerun_hint = None
    if not all_passed:
        hint: dict = {}
        for c in checks:
            if not c.passed:
                if c.name == "grayness":
                    hint["reason"] = "High grayness — increase max_iter or check beta schedule."
                    hint["max_iter"] = int(max_iter * 1.5)
                elif c.name == "connectivity":
                    hint["reason"] = "Disconnected structure — try lower volume fraction or check BCs."
                    hint["volfrac"] = max(0.2, spec.volfrac - 0.1)
                elif c.name == "compliance":
                    hint["reason"] = "Compliance degraded — increase max_iter for better convergence."
                    hint["max_iter"] = int(max_iter * 1.5)
                elif c.name == "convergence":
                    hint["reason"] = "Did not converge — increase max_iter."
                    hint["max_iter"] = int(max_iter * 1.5)
        if hint:
            rerun_hint = hint

    # Optional LLM assessment
    llm_text = None
    if use_llm:
        metrics = {
            "final_compliance": result.get("final_compliance"),
            "best_compliance": result.get("best_compliance"),
            "final_grayness": result.get("final_grayness"),
            "best_grayness": result.get("best_grayness"),
            "n_iter": result.get("n_iter"),
            "max_iter": max_iter,
            "volfrac_target": spec.volfrac,
            "volfrac_actual": float(np.mean(rho_final)) if rho_final.size else None,
            "nelx": nelx, "nely": nely,
            "connectivity_passed": checks[0].passed,
            "checks_passed": all_passed,
        }
        assessment, llm_rerun = _llm_evaluate(metrics, model, api_key)
        if assessment:
            llm_text = assessment
        if llm_rerun and not rerun_hint:
            # Use LLM suggestion only if deterministic checks didn't produce one
            rerun_hint = llm_rerun

    return EvalResult(
        passed=all_passed,
        checks=checks,
        summary=summary,
        rerun_hint=rerun_hint,
        llm_assessment=llm_text,
    )


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Synthetic test with a fake result
    from problem_spec import EdgeSupport, PointLoad

    spec = ProblemSpec(
        Lx=2.0, Ly=1.0, nelx=60, nely=30, volfrac=0.5,
        supports=[EdgeSupport(edge="left", constraint="fixed")],
        loads=[PointLoad(x=2.0, y=0.5, fy=-1.0)],
    )

    # Simulate a "good" result
    rho_good = np.random.rand(60 * 30)
    rho_good[rho_good > 0.5] = 1.0
    rho_good[rho_good <= 0.5] = 0.001
    # Make a connected path
    rho_2d = rho_good.reshape(60, 30)
    rho_2d[0:60, 13:17] = 1.0   # horizontal bar
    rho_good = rho_2d.ravel()

    fake_result = {
        "compliance_history": [100, 80, 60, 50, 45, 42, 41, 40.5],
        "rho_final": rho_good,
        "best_rho": rho_good,
        "best_compliance": 40.0,
        "best_iteration": 80,
        "final_compliance": 40.5,
        "final_grayness": float(4 * np.mean(rho_good * (1 - rho_good))),
        "best_grayness": 0.05,
        "best_is_valid": True,
        "n_iter": 120,
        "is_3d": False, "nelx": 60, "nely": 30,
        "tail_config": {"enabled": True, "tail_iters": 40},
    }

    print("=== Evaluating synthetic 'good' result ===")
    ev = evaluate(fake_result, spec, max_iter=100, use_llm=False, verbose=True)
    print(f"\nOverall: {'PASS' if ev.passed else 'FAIL'}")
    print(f"Summary: {ev.summary}")
    if ev.rerun_hint:
        print(f"Re-run hint: {ev.rerun_hint}")
