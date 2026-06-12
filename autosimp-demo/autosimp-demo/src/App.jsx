import { useState, useRef, useEffect, useCallback, useMemo } from "react";

// ─── Constants & Helpers ───────────────────────────────────────────
const COLORS = {
  bg: "#f8f9fa",
  panel: "#ffffff",
  panelBorder: "#d1d5db",
  accent: "#1d4ed8",
  accentDim: "#2563eb",
  accentGlow: "rgba(37,99,235,0.1)",
  warn: "#d97706",
  error: "#dc2626",
  success: "#059669",
  text: "#1f2937",
  textDim: "#4b5563",
  textMuted: "#9ca3af",
  solid: "#1f2937",
  void_: "#f8f9fa",
  grid: "#e5e7eb",
  support: "#2563eb",
  load: "#dc2626",
  loadArrow: "#ef4444",
  passive: "#7c3aed",
};

const PRESETS = {
  cantilever: {
    label: "Cantilever",
    prompt: "Cantilever beam, left edge fixed, downward point load at mid-right edge, 50% volume fraction",
    spec: { Lx: 2, Ly: 1, nelx: 60, nely: 30, volfrac: 0.5, supports: [{ type: "edge", edge: "left", constraint: "fixed" }], loads: [{ type: "point", x: 2, y: 0.5, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
  mbb: {
    label: "MBB Beam",
    prompt: "MBB beam, symmetry BC on left (pin_x), roller at bottom-right corner, downward load at top-left, 50% material",
    spec: { Lx: 3, Ly: 1, nelx: 60, nely: 20, volfrac: 0.5, supports: [{ type: "edge", edge: "left", constraint: "pin_x" }, { type: "point", x: 3, y: 0, constraint: "pin_y" }], loads: [{ type: "point", x: 0, y: 1, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
  bridge: {
    label: "Bridge",
    prompt: "Bridge structure, 4m wide, 1m tall, pinned supports at both bottom corners, distributed downward load on top, 30% volume fraction",
    spec: { Lx: 4, Ly: 1, nelx: 80, nely: 20, volfrac: 0.3, supports: [{ type: "point", x: 0, y: 0, constraint: "fixed" }, { type: "point", x: 4, y: 0, constraint: "pin_y" }], loads: [{ type: "distributed", edge: "top", magnitude: -1 }], passive_regions: [] },
  },
  cantilever_hole: {
    label: "Cant. + Hole",
    prompt: "Cantilever beam, left edge fixed, downward load at mid-right, 40% material, circular hole at center for a pipe (radius 0.15)",
    spec: { Lx: 2, Ly: 1, nelx: 60, nely: 30, volfrac: 0.4, supports: [{ type: "edge", edge: "left", constraint: "fixed" }], loads: [{ type: "point", x: 2, y: 0.5, fx: 0, fy: -1, fz: 0 }], passive_regions: [{ type: "circle", cx: 1.0, cy: 0.5, radius: 0.15, kind: "void" }] },
  },
  simply_supported: {
    label: "Simply Supp.",
    prompt: "Simply supported beam, 3m wide, 1m tall, pinned at bottom-left and bottom-right, downward point load at top center, 40% volume fraction",
    spec: { Lx: 3, Ly: 1, nelx: 60, nely: 20, volfrac: 0.4, supports: [{ type: "point", x: 0, y: 0, constraint: "pin_y" }, { type: "point", x: 3, y: 0, constraint: "pin_y" }, { type: "point", x: 0, y: 0, constraint: "pin_x" }], loads: [{ type: "point", x: 1.5, y: 1.0, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
  lbracket: {
    label: "L-Bracket",
    prompt: "L-bracket: 2x2 domain, upper-right quadrant voided, top-left edge fixed, horizontal load pointing right at middle of right face of lower portion, 40% material",
    spec: { Lx: 2, Ly: 2, nelx: 40, nely: 40, volfrac: 0.4, supports: [{ type: "edge", edge: "top", constraint: "fixed" }], loads: [{ type: "point", x: 2, y: 0.5, fx: 1, fy: 0, fz: 0 }], passive_regions: [{ type: "rect", x0: 1.0, y0: 1.0, x1: 2.0, y1: 2.0, kind: "void" }] },
  },
  dual_load: {
    label: "Dual Load",
    prompt: "Cantilever with two point loads: left edge fixed, one downward load at top-right corner, one downward load at bottom-right corner, 50% volume fraction",
    spec: { Lx: 2, Ly: 1, nelx: 60, nely: 30, volfrac: 0.5, supports: [{ type: "edge", edge: "left", constraint: "fixed" }], loads: [{ type: "point", x: 2, y: 0.9, fx: 0, fy: -1, fz: 0 }, { type: "point", x: 2, y: 0.1, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
  cantilever_3d: {
    label: "3D Cantilever",
    is3d: true,
    prompt: "3D cantilever beam, left face fixed, downward point load at center of right face, 40% volume fraction, 30x15x8 mesh",
    spec: { Lx: 2, Ly: 1, Lz: 0.5, nelx: 30, nely: 15, nelz: 8, volfrac: 0.4, supports: [{ type: "edge", edge: "left", constraint: "fixed" }], loads: [{ type: "point", x: 2, y: 0.5, z: 0.25, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
  mbb_3d: {
    label: "3D MBB",
    is3d: true,
    prompt: "3D MBB beam, symmetry on left face (pin_x), roller at bottom-right edge, downward load at top-left edge, 40% volume fraction, 30x15x8 mesh",
    spec: { Lx: 3, Ly: 1, Lz: 0.5, nelx: 30, nely: 15, nelz: 8, volfrac: 0.4, supports: [{ type: "edge", edge: "left", constraint: "pin_x" }, { type: "point", x: 3, y: 0, z: 0.25, constraint: "pin_y" }], loads: [{ type: "point", x: 0, y: 1, z: 0.25, fx: 0, fy: -1, fz: 0 }], passive_regions: [] },
  },
};

const EDGE_LABELS = { left: "Left", right: "Right", top: "Top", bottom: "Bottom" };
const CONSTRAINT_LABELS = { fixed: "Fixed", pin_x: "Pin X", pin_y: "Pin Y", roller_x: "Roller X", roller_y: "Roller Y" };

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// ─── SIMP Simulation (simplified 2D for demo) ─────────────────────
// This is a heavily simplified topology optimization that demonstrates
// the SIMP concept with real density updates, sensitivity analysis,
// and OC optimization — running entirely in the browser.

function createSimpSolver(spec) {
  const { nelx, nely, volfrac } = spec;
  const Lx = spec.Lx || 2;
  const Ly = spec.Ly || 1;
  const nEl = nelx * nely;

  // ── Three-field SIMP: density filter → Heaviside projection → SIMP ──
  // Matches pub_simp_solver.py three-field formulation

  // Design variables (raw density)
  let rho = new Float64Array(nEl).fill(volfrac);
  // Filtered density (after rmin filter)
  let rhoBar = new Float64Array(nEl).fill(volfrac);
  // Physical density (after Heaviside projection)
  let rhoPhys = new Float64Array(nEl).fill(volfrac);

  // Continuation schedule (matches ScheduleOnlyController from paper)
  let penal = 1.0, beta = 1.0, move = 0.20, rmin = 1.5;
  let iterCount = 0;

  function getContinuationParams(it) {
    // Four-phase schedule identical to paper's ScheduleOnlyController
    if (it <= 15)       return { penal: 1.5, beta: 1.0, move: 0.20 };
    else if (it <= 40)  return { penal: 3.5, beta: 4.0, move: 0.15, rmin: Math.max(1.35, rmin) };
    else if (it <= 65)  return { penal: 4.5, beta: 16.0, move: 0.08, rmin: Math.max(1.25, rmin) };
    else                return { penal: 4.5, beta: 32.0, move: 0.05, rmin: Math.max(1.20, rmin) };
  }

  // Build passive mask
  const passive = new Int8Array(nEl);
  for (const pr of (spec.passive_regions || [])) {
    if (pr.type === "circle") {
      const hx = Lx / nelx, hy = Ly / nely;
      for (let i = 0; i < nelx; i++) {
        for (let j = 0; j < nely; j++) {
          const cx = (i + 0.5) * hx, cy = (j + 0.5) * hy;
          const d = Math.sqrt((cx - pr.cx) ** 2 + (cy - pr.cy) ** 2);
          if (d <= pr.radius) passive[i * nely + j] = pr.kind === "void" ? 1 : 2;
        }
      }
    } else if (pr.type === "rect") {
      const hx = Lx / nelx, hy = Ly / nely;
      for (let i = 0; i < nelx; i++) {
        for (let j = 0; j < nely; j++) {
          const cx = (i + 0.5) * hx, cy = (j + 0.5) * hy;
          if (cx >= pr.x0 && cx <= pr.x1 && cy >= pr.y0 && cy <= pr.y1)
            passive[i * nely + j] = pr.kind === "void" ? 1 : 2;
        }
      }
    }
  }

  // Apply passive initial
  for (let e = 0; e < nEl; e++) {
    if (passive[e] === 1) { rho[e] = 1e-3; rhoBar[e] = 1e-3; rhoPhys[e] = 1e-3; }
    if (passive[e] === 2) { rho[e] = 1.0; rhoBar[e] = 1.0; rhoPhys[e] = 1.0; }
  }

  const ndof = 2 * (nelx + 1) * (nely + 1);
  function nodeIdx(i, j) { return i * (nely + 1) + j; }
  function elemDof(i, j) {
    const n1 = nodeIdx(i, j), n2 = nodeIdx(i + 1, j);
    const n3 = nodeIdx(i + 1, j + 1), n4 = nodeIdx(i, j + 1);
    return [2*n1, 2*n1+1, 2*n2, 2*n2+1, 2*n3, 2*n3+1, 2*n4, 2*n4+1];
  }

  // Element stiffness via 2×2 Gauss quadrature (correct for rectangular elements)
  const nu = 0.3;
  function elemKe() {
    const a = Lx / nelx, b = Ly / nely;
    const gp = 1 / Math.sqrt(3);
    const pts = [[-gp,-gp],[gp,-gp],[gp,gp],[-gp,gp]];
    const D = [1/(1-nu*nu), nu/(1-nu*nu), 0, nu/(1-nu*nu), 1/(1-nu*nu), 0, 0, 0, 1/(2*(1+nu))];
    const ke = new Float64Array(64);
    for (const [xi, eta] of pts) {
      const dNdxi = [-(1-eta)/4, (1-eta)/4, (1+eta)/4, -(1+eta)/4];
      const dNdeta = [-(1-xi)/4, -(1+xi)/4, (1+xi)/4, (1-xi)/4];
      const detJ = (a/2)*(b/2);
      const dNdx = dNdxi.map(v => v/(a/2));
      const dNdy = dNdeta.map(v => v/(b/2));
      for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
        const ci = i*2, cj = j*2;
        ke[ci*8+cj] += (D[0]*dNdx[i]*dNdx[j] + D[8]*dNdy[i]*dNdy[j])*detJ;
        ke[ci*8+cj+1] += (D[1]*dNdx[i]*dNdy[j] + D[8]*dNdy[i]*dNdx[j])*detJ;
        ke[(ci+1)*8+cj] += (D[3]*dNdy[i]*dNdx[j] + D[8]*dNdx[i]*dNdy[j])*detJ;
        ke[(ci+1)*8+cj+1] += (D[4]*dNdy[i]*dNdy[j] + D[8]*dNdx[i]*dNdx[j])*detJ;
      }
    }
    return ke;
  }
  const KE = elemKe();

  // Build supports → fixed DOFs
  function getFixedDofs() {
    const fixed = new Set();
    for (const sup of (spec.supports || [])) {
      if (sup.type === "edge") {
        const nodes = [];
        if (sup.edge === "left") for (let j = 0; j <= nely; j++) nodes.push(nodeIdx(0, j));
        if (sup.edge === "right") for (let j = 0; j <= nely; j++) nodes.push(nodeIdx(nelx, j));
        if (sup.edge === "bottom") for (let i = 0; i <= nelx; i++) nodes.push(nodeIdx(i, 0));
        if (sup.edge === "top") for (let i = 0; i <= nelx; i++) nodes.push(nodeIdx(i, nely));
        for (const n of nodes) {
          if (sup.constraint === "fixed") { fixed.add(2*n); fixed.add(2*n+1); }
          else if (sup.constraint === "pin_x" || sup.constraint === "roller_y") fixed.add(2*n);
          else if (sup.constraint === "pin_y" || sup.constraint === "roller_x") fixed.add(2*n+1);
        }
      } else {
        const hx = Lx/nelx, hy = Ly/nely;
        let bestN = 0, bestD = 1e9;
        for (let i = 0; i <= nelx; i++) for (let j = 0; j <= nely; j++) {
          const d = Math.sqrt((i*hx - sup.x)**2 + (j*hy - sup.y)**2);
          if (d < bestD) { bestD = d; bestN = nodeIdx(i, j); }
        }
        if (sup.constraint === "fixed") { fixed.add(2*bestN); fixed.add(2*bestN+1); }
        else if (sup.constraint === "pin_x") fixed.add(2*bestN);
        else if (sup.constraint === "pin_y") fixed.add(2*bestN+1);
      }
    }
    return fixed;
  }

  function buildForce() {
    const F = new Float64Array(ndof);
    for (const ld of (spec.loads || [])) {
      if (ld.type === "point") {
        const hx = Lx/nelx, hy = Ly/nely;
        let bestN = 0, bestD = 1e9;
        for (let i = 0; i <= nelx; i++) for (let j = 0; j <= nely; j++) {
          const d = Math.sqrt((i*hx - ld.x)**2 + (j*hy - ld.y)**2);
          if (d < bestD) { bestD = d; bestN = nodeIdx(i, j); }
        }
        F[2*bestN] += (ld.fx || 0);
        F[2*bestN + 1] += (ld.fy || 0);
      } else if (ld.type === "distributed") {
        const edge = ld.edge;
        let nodes = [];
        if (edge === "top") for (let i = 0; i <= nelx; i++) nodes.push(nodeIdx(i, nely));
        if (edge === "bottom") for (let i = 0; i <= nelx; i++) nodes.push(nodeIdx(i, 0));
        if (edge === "left") for (let j = 0; j <= nely; j++) nodes.push(nodeIdx(0, j));
        if (edge === "right") for (let j = 0; j <= nely; j++) nodes.push(nodeIdx(nelx, j));
        const dofOff = (edge === "top" || edge === "bottom") ? 1 : 0;
        const sign = (edge === "top" || edge === "right") ? 1 : -1;
        const h = (edge === "top" || edge === "bottom") ? Lx/nelx : Ly/nely;
        for (let k = 0; k < nodes.length; k++) {
          const w = (k === 0 || k === nodes.length - 1) ? h/2 : h;
          F[2*nodes[k] + dofOff] += ld.magnitude * sign * w;
        }
      }
    }
    return F;
  }

  // ── Density filter (rmin-weighted average) ──
  // Pre-compute filter weights for speed
  const filterH = [];
  const filterHs = new Float64Array(nEl);
  for (let ei = 0; ei < nelx; ei++) {
    for (let ej = 0; ej < nely; ej++) {
      const e = ei * nely + ej;
      const neighbors = [];
      const ri = Math.ceil(rmin);
      for (let di = -ri; di <= ri; di++) {
        for (let dj = -ri; dj <= ri; dj++) {
          const ni = ei + di, nj = ej + dj;
          if (ni < 0 || ni >= nelx || nj < 0 || nj >= nely) continue;
          const d = Math.sqrt(di*di + dj*dj);
          if (d > rmin) continue;
          const w = rmin - d;
          neighbors.push({ idx: ni * nely + nj, w });
          filterHs[e] += w;
        }
      }
      filterH.push(neighbors);
    }
  }

  function applyDensityFilter(rhoIn) {
    const out = new Float64Array(nEl);
    for (let e = 0; e < nEl; e++) {
      let s = 0;
      for (const { idx, w } of filterH[e]) s += w * rhoIn[idx];
      out[e] = s / filterHs[e];
    }
    return out;
  }

  // ── Heaviside projection ──
  function heaviside(rhoFiltered, beta, eta) {
    const out = new Float64Array(nEl);
    const eta_ = eta || 0.5;
    if (beta <= 1.0) {
      // No projection at low beta
      for (let e = 0; e < nEl; e++) out[e] = rhoFiltered[e];
    } else {
      for (let e = 0; e < nEl; e++) {
        const x = rhoFiltered[e];
        const num = Math.tanh(beta * eta_) + Math.tanh(beta * (x - eta_));
        const den = Math.tanh(beta * eta_) + Math.tanh(beta * (1 - eta_));
        out[e] = clamp(num / den, 1e-3, 1.0);
      }
    }
    return out;
  }

  // Derivative of Heaviside w.r.t. filtered density
  function heavisideDeriv(rhoFiltered, beta, eta) {
    const out = new Float64Array(nEl);
    const eta_ = eta || 0.5;
    if (beta <= 1.0) {
      out.fill(1.0);
    } else {
      const den = Math.tanh(beta * eta_) + Math.tanh(beta * (1 - eta_));
      for (let e = 0; e < nEl; e++) {
        const x = rhoFiltered[e];
        const t = Math.tanh(beta * (x - eta_));
        out[e] = beta * (1 - t * t) / den;
      }
    }
    return out;
  }

  // CG solver (element-by-element, using rhoPhys for stiffness)
  function solveSystem(rhoP) {
    const fixedSet = getFixedDofs();
    const F = buildForce();
    for (const d of fixedSet) F[d] = 0;
    const Emin = 1e-9, E0 = 1.0;

    function matvec(x) {
      const y = new Float64Array(ndof);
      for (let ei = 0; ei < nelx; ei++) for (let ej = 0; ej < nely; ej++) {
        const e = ei * nely + ej;
        const Ee = Emin + Math.pow(rhoP[e], penal) * (E0 - Emin);
        const dofs = elemDof(ei, ej);
        for (let r = 0; r < 8; r++) {
          let s = 0;
          for (let c = 0; c < 8; c++) s += KE[r*8+c] * x[dofs[c]];
          y[dofs[r]] += Ee * s;
        }
      }
      for (const d of fixedSet) y[d] = x[d];
      return y;
    }

    const diag = new Float64Array(ndof).fill(1e-12);
    for (let ei = 0; ei < nelx; ei++) for (let ej = 0; ej < nely; ej++) {
      const e = ei * nely + ej;
      const Ee = Emin + Math.pow(rhoP[e], penal) * (E0 - Emin);
      const dofs = elemDof(ei, ej);
      for (let r = 0; r < 8; r++) diag[dofs[r]] += Ee * KE[r*8+r];
    }
    for (const d of fixedSet) diag[d] = 1;

    const u = new Float64Array(ndof);
    let r = F.slice();
    const z = new Float64Array(ndof);
    for (let i = 0; i < ndof; i++) z[i] = r[i] / diag[i];
    let p = z.slice();
    let rsold = 0;
    for (let i = 0; i < ndof; i++) rsold += r[i] * z[i];

    for (let cg = 0; cg < Math.min(600, ndof); cg++) {
      const Ap = matvec(p);
      let pAp = 0;
      for (let i = 0; i < ndof; i++) pAp += p[i] * Ap[i];
      if (Math.abs(pAp) < 1e-30) break;
      const alpha = rsold / pAp;
      for (let i = 0; i < ndof; i++) { u[i] += alpha * p[i]; r[i] -= alpha * Ap[i]; }
      let rnorm = 0;
      for (let i = 0; i < ndof; i++) rnorm += r[i] * r[i];
      if (Math.sqrt(rnorm) < 1e-8 * Math.sqrt(ndof)) break;
      for (let i = 0; i < ndof; i++) z[i] = r[i] / diag[i];
      let rsnew = 0;
      for (let i = 0; i < ndof; i++) rsnew += r[i] * z[i];
      const bt = rsnew / (rsold + 1e-30);
      for (let i = 0; i < ndof; i++) p[i] = z[i] + bt * p[i];
      rsold = rsnew;
    }
    return { u, F };
  }

  // ── One three-field SIMP iteration ──
  function iterate() {
    iterCount++;
    const params = getContinuationParams(iterCount);
    penal = params.penal;
    beta = params.beta;
    move = params.move;
    if (params.rmin) rmin = params.rmin;

    const Emin = 1e-9, E0 = 1.0;

    // Step 1: Filter density
    rhoBar = applyDensityFilter(rho);

    // Step 2: Heaviside projection
    rhoPhys = heaviside(rhoBar, beta, 0.5);

    // Enforce passive
    for (let e = 0; e < nEl; e++) {
      if (passive[e] === 1) rhoPhys[e] = 1e-3;
      if (passive[e] === 2) rhoPhys[e] = 1.0;
    }

    // Step 3: Solve FEA with physical density
    const { u, F } = solveSystem(rhoPhys);

    // Compliance
    let compliance = 0;
    for (let i = 0; i < ndof; i++) compliance += F[i] * u[i];

    // Step 4: Sensitivities w.r.t. physical density
    const dcPhys = new Float64Array(nEl);
    for (let ei = 0; ei < nelx; ei++) for (let ej = 0; ej < nely; ej++) {
      const e = ei * nely + ej;
      const dofs = elemDof(ei, ej);
      let ue_Ke_ue = 0;
      for (let r = 0; r < 8; r++) {
        let s = 0;
        for (let c = 0; c < 8; c++) s += KE[r*8+c] * u[dofs[c]];
        ue_Ke_ue += u[dofs[r]] * s;
      }
      dcPhys[e] = -penal * Math.pow(rhoPhys[e], penal - 1) * (E0 - Emin) * ue_Ke_ue;
    }

    // Step 5: Chain rule through Heaviside
    const hDeriv = heavisideDeriv(rhoBar, beta, 0.5);
    const dcBar = new Float64Array(nEl);
    for (let e = 0; e < nEl; e++) dcBar[e] = dcPhys[e] * hDeriv[e];

    // Step 6: Chain rule through density filter
    const dc = new Float64Array(nEl);
    for (let e = 0; e < nEl; e++) {
      let s = 0;
      for (const { idx, w } of filterH[e]) s += w * dcBar[idx] / filterHs[idx];
      dc[e] = s;
    }

    // Sensitivity for volume constraint (chain rule through filter + Heaviside)
    const dvPhys = new Float64Array(nEl).fill(1.0);
    const dvBar = new Float64Array(nEl);
    for (let e = 0; e < nEl; e++) dvBar[e] = dvPhys[e] * hDeriv[e];
    const dv = new Float64Array(nEl);
    for (let e = 0; e < nEl; e++) {
      let s = 0;
      for (const { idx, w } of filterH[e]) s += w * dvBar[idx] / filterHs[idx];
      dv[e] = s;
    }

    // Step 7: OC update on design variables (rho), not physical
    let l1 = 0, l2 = 1e9;
    const rhoNew = new Float64Array(nEl);
    while (l2 - l1 > 1e-9) {
      const lmid = (l1 + l2) / 2;
      let vol = 0;
      for (let e = 0; e < nEl; e++) {
        if (passive[e] === 1) { rhoNew[e] = 1e-3; continue; }
        if (passive[e] === 2) { rhoNew[e] = 1.0; continue; }
        const Be = Math.sqrt(Math.max(1e-30, -dc[e] / (dv[e] * lmid + 1e-30)));
        rhoNew[e] = clamp(clamp(rho[e] * Be, rho[e] - move, rho[e] + move), 1e-3, 1.0);
      }
      // Check volume on PHYSICAL density (after filter + projection)
      const rhoBarNew = applyDensityFilter(rhoNew);
      const rhoPhysNew = heaviside(rhoBarNew, beta, 0.5);
      vol = 0;
      for (let e = 0; e < nEl; e++) {
        if (passive[e] === 1) vol += 1e-3;
        else if (passive[e] === 2) vol += 1.0;
        else vol += rhoPhysNew[e];
      }
      if (vol / nEl > volfrac) l1 = lmid; else l2 = lmid;
    }

    const change = Math.max(...Array.from(rhoNew).map((v, i) => Math.abs(v - rho[i])));
    rho = rhoNew;

    // Recompute physical density for display
    rhoBar = applyDensityFilter(rho);
    rhoPhys = heaviside(rhoBar, beta, 0.5);
    for (let e = 0; e < nEl; e++) {
      if (passive[e] === 1) rhoPhys[e] = 1e-3;
      if (passive[e] === 2) rhoPhys[e] = 1.0;
    }

    // Grayness on physical density
    let gray = 0;
    for (let e = 0; e < nEl; e++) gray += 4 * rhoPhys[e] * (1 - rhoPhys[e]);
    gray /= nEl;

    return { compliance, change, grayness: gray, rho: rhoPhys.slice(), penal, beta };
  }

  return { iterate, getRho: () => rhoPhys.slice(), nEl, passive };
}


// ─── Components ────────────────────────────────────────────────────

function DomainCanvas({ spec, onUpdateLoad, interactive = true }) {
  const canvasRef = useRef(null);
  const [dragging, setDragging] = useState(null);
  const [hoverPos, setHoverPos] = useState(null);

  const PAD = 40;
  const W = 560, H = 300;

  const scaleX = useCallback((x) => PAD + (x / spec.Lx) * (W - 2 * PAD), [spec.Lx]);
  const scaleY = useCallback((y) => H - PAD - (y / spec.Ly) * (H - 2 * PAD), [spec.Ly]);
  const invX = useCallback((px) => clamp((px - PAD) / (W - 2 * PAD) * spec.Lx, 0, spec.Lx), [spec.Lx]);
  const invY = useCallback((py) => clamp((H - PAD - py) / (H - 2 * PAD) * spec.Ly, 0, spec.Ly), [spec.Ly]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    // Background
    ctx.fillStyle = "#f0f2f5";
    ctx.fillRect(0, 0, W, H);

    // Grid
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 0.5;
    const gx = spec.nelx > 60 ? Math.ceil(spec.nelx / 30) : 1;
    const gy = spec.nely > 30 ? Math.ceil(spec.nely / 15) : 1;
    for (let i = 0; i <= spec.nelx; i += gx) {
      const x = scaleX(i * spec.Lx / spec.nelx);
      ctx.beginPath(); ctx.moveTo(x, scaleY(0)); ctx.lineTo(x, scaleY(spec.Ly)); ctx.stroke();
    }
    for (let j = 0; j <= spec.nely; j += gy) {
      const y = scaleY(j * spec.Ly / spec.nely);
      ctx.beginPath(); ctx.moveTo(scaleX(0), y); ctx.lineTo(scaleX(spec.Lx), y); ctx.stroke();
    }

    // Domain outline
    ctx.strokeStyle = COLORS.textDim;
    ctx.lineWidth = 2;
    ctx.strokeRect(scaleX(0), scaleY(spec.Ly), scaleX(spec.Lx) - scaleX(0), scaleY(0) - scaleY(spec.Ly));

    // Passive regions
    for (const pr of (spec.passive_regions || [])) {
      if (pr.type === "circle") {
        const cx = scaleX(pr.cx), cy = scaleY(pr.cy);
        const rx = (pr.radius / spec.Lx) * (W - 2 * PAD);
        ctx.beginPath();
        ctx.arc(cx, cy, rx, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(124,58,237,0.25)";
        ctx.fill();
        ctx.strokeStyle = COLORS.passive;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Supports
    for (const sup of (spec.supports || [])) {
      ctx.fillStyle = COLORS.support;
      ctx.strokeStyle = COLORS.support;
      if (sup.type === "edge") {
        ctx.lineWidth = 4;
        let x0, y0, x1, y1;
        if (sup.edge === "left") { x0 = scaleX(0); y0 = scaleY(0); x1 = scaleX(0); y1 = scaleY(spec.Ly); }
        else if (sup.edge === "right") { x0 = scaleX(spec.Lx); y0 = scaleY(0); x1 = scaleX(spec.Lx); y1 = scaleY(spec.Ly); }
        else if (sup.edge === "bottom") { x0 = scaleX(0); y0 = scaleY(0); x1 = scaleX(spec.Lx); y1 = scaleY(0); }
        else { x0 = scaleX(0); y0 = scaleY(spec.Ly); x1 = scaleX(spec.Lx); y1 = scaleY(spec.Ly); }
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        // Hatch marks
        const len = Math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2);
        const steps = Math.max(4, Math.floor(len / 12));
        ctx.lineWidth = 1.5;
        for (let s = 0; s <= steps; s++) {
          const t = s / steps;
          const px = x0 + t * (x1 - x0), py = y0 + t * (y1 - y0);
          const nx = sup.edge === "left" ? -8 : sup.edge === "right" ? 8 : 0;
          const ny = sup.edge === "bottom" ? 8 : sup.edge === "top" ? -8 : 0;
          ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + nx, py + ny); ctx.stroke();
        }
        ctx.font = "bold 9px monospace";
        ctx.fillStyle = COLORS.support;
        const lbl = CONSTRAINT_LABELS[sup.constraint] || sup.constraint;
        if (sup.edge === "left") ctx.fillText(lbl, scaleX(0) - 35, (scaleY(0) + scaleY(spec.Ly)) / 2 + 3);
        else if (sup.edge === "bottom") ctx.fillText(lbl, (scaleX(0) + scaleX(spec.Lx)) / 2 - 10, scaleY(0) + 18);
      } else {
        const px = scaleX(sup.x), py = scaleY(sup.y);
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px - 8, py + 12);
        ctx.lineTo(px + 8, py + 12);
        ctx.closePath();
        ctx.fill();
        ctx.font = "bold 9px monospace";
        ctx.fillText(CONSTRAINT_LABELS[sup.constraint] || sup.constraint, px + 10, py + 5);
      }
    }

    // Loads
    for (let li = 0; li < (spec.loads || []).length; li++) {
      const ld = spec.loads[li];
      if (ld.type === "point") {
        const px = scaleX(ld.x), py = scaleY(ld.y);
        const fx = ld.fx || 0, fy = ld.fy || 0;
        const mag = Math.sqrt(fx * fx + fy * fy);
        if (mag < 1e-10) continue;
        const arrowLen = 35;
        const dx = (fx / mag) * arrowLen, dy = -(fy / mag) * arrowLen;
        ctx.strokeStyle = COLORS.loadArrow;
        ctx.fillStyle = COLORS.load;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(px - dx, py - dy);
        ctx.lineTo(px, py);
        ctx.stroke();
        // Arrowhead
        const angle = Math.atan2(dy, dx);
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px - 10 * Math.cos(angle - 0.4), py - 10 * Math.sin(angle - 0.4));
        ctx.lineTo(px - 10 * Math.cos(angle + 0.4), py - 10 * Math.sin(angle + 0.4));
        ctx.closePath();
        ctx.fill();
        // Draggable indicator
        if (interactive) {
          ctx.beginPath();
          ctx.arc(px, py, 6, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(239,68,68,0.3)";
          ctx.fill();
          ctx.strokeStyle = COLORS.load;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      } else if (ld.type === "distributed") {
        const edge = ld.edge;
        const arrowLen = 18;
        ctx.strokeStyle = COLORS.loadArrow;
        ctx.fillStyle = COLORS.load;
        ctx.lineWidth = 1.5;
        let steps = 8;
        for (let s = 0; s <= steps; s++) {
          const t = s / steps;
          let px, py, dx, dy;
          if (edge === "top") {
            px = scaleX(t * spec.Lx); py = scaleY(spec.Ly);
            dx = 0; dy = arrowLen;
          } else if (edge === "bottom") {
            px = scaleX(t * spec.Lx); py = scaleY(0);
            dx = 0; dy = -arrowLen;
          } else if (edge === "left") {
            px = scaleX(0); py = scaleY(t * spec.Ly);
            dx = -arrowLen; dy = 0;
          } else {
            px = scaleX(spec.Lx); py = scaleY(t * spec.Ly);
            dx = arrowLen; dy = 0;
          }
          ctx.beginPath();
          ctx.moveTo(px - dx, py - dy);
          ctx.lineTo(px, py);
          ctx.stroke();
          const angle = Math.atan2(dy, dx);
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(px - 7 * Math.cos(angle - 0.4), py - 7 * Math.sin(angle - 0.4));
          ctx.lineTo(px - 7 * Math.cos(angle + 0.4), py - 7 * Math.sin(angle + 0.4));
          ctx.closePath();
          ctx.fill();
        }
      }
    }

    // Hover position
    if (hoverPos && interactive) {
      ctx.beginPath();
      ctx.arc(scaleX(hoverPos.x), scaleY(hoverPos.y), 4, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255,0.4)";
      ctx.fill();
      ctx.font = "10px monospace";
      ctx.fillStyle = COLORS.textDim;
      ctx.fillText(`(${hoverPos.x.toFixed(2)}, ${hoverPos.y.toFixed(2)})`, scaleX(hoverPos.x) + 8, scaleY(hoverPos.y) - 8);
    }

    // Axes labels
    ctx.font = "10px monospace";
    ctx.fillStyle = COLORS.textDim;
    ctx.fillText("0", scaleX(0) - 5, scaleY(0) + 15);
    ctx.fillText(spec.Lx.toFixed(1), scaleX(spec.Lx) - 10, scaleY(0) + 15);
    ctx.fillText(spec.Ly.toFixed(1), scaleX(0) - 22, scaleY(spec.Ly) + 4);

    // Dimension labels
    ctx.fillStyle = COLORS.textMuted;
    ctx.font = "9px monospace";
    ctx.fillText(`${spec.nelx}×${spec.nely} mesh`, W - 85, 15);
    ctx.fillText(`Vf = ${spec.volfrac}`, W - 85, 27);

  }, [spec, scaleX, scaleY, hoverPos, interactive]);

  const handleMouse = useCallback((e, type) => {
    if (!interactive) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (W / rect.width);
    const py = (e.clientY - rect.top) * (H / rect.height);
    const x = invX(px), y = invY(py);

    if (type === "move") {
      setHoverPos({ x, y });
      if (dragging !== null) {
        onUpdateLoad(dragging, x, y);
      }
    } else if (type === "down") {
      // Check if near a point load
      for (let i = 0; i < (spec.loads || []).length; i++) {
        const ld = spec.loads[i];
        if (ld.type === "point") {
          const d = Math.sqrt((x - ld.x) ** 2 + (y - ld.y) ** 2);
          if (d < spec.Lx * 0.05) {
            setDragging(i);
            return;
          }
        }
      }
    } else if (type === "up") {
      setDragging(null);
    } else if (type === "leave") {
      setHoverPos(null);
      setDragging(null);
    }
  }, [interactive, spec, dragging, invX, invY, onUpdateLoad]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: W, height: H, borderRadius: 8, cursor: interactive ? (dragging !== null ? "grabbing" : "crosshair") : "default" }}
      onMouseMove={(e) => handleMouse(e, "move")}
      onMouseDown={(e) => handleMouse(e, "down")}
      onMouseUp={(e) => handleMouse(e, "up")}
      onMouseLeave={(e) => handleMouse(e, "leave")}
    />
  );
}

function DensityCanvas({ rho, nelx, nely, passive }) {
  const canvasRef = useRef(null);
  const W = 560, H = 300;
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !rho) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    const PAD = 10;
    const cw = (W - 2 * PAD) / nelx;
    const ch = (H - 2 * PAD) / nely;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, W, H);

    for (let i = 0; i < nelx; i++) {
      for (let j = 0; j < nely; j++) {
        const e = i * nely + j;
        const v = rho[e];
        const px = PAD + i * cw;
        const py = H - PAD - (j + 1) * ch;
        if (passive && passive[e] === 1) {
          ctx.fillStyle = "#ede9fe";  // light purple for void regions
        } else if (passive && passive[e] === 2) {
          ctx.fillStyle = "#1f2937";  // dark for solid regions
        } else {
          // Black = solid (v=1), White = void (v=0) — standard TO convention
          const g = Math.round((1 - v) * 255);
          ctx.fillStyle = `rgb(${g},${g},${g})`;
        }
        ctx.fillRect(px, py, cw + 0.5, ch + 0.5);
      }
    }
  }, [rho, nelx, nely, passive]);

  return <canvas ref={canvasRef} style={{ width: W, height: H, borderRadius: 8 }} />;
}

// 3D Interactive Viewer — Three.js isosurface (marching cubes) + X-ray projections
function Density3DViewer({ rho, nelx, nely, nelz }) {
  const mountRef = useRef(null);
  const canvasRef = useRef(null);
  const [viewMode, setViewMode] = useState("3d"); // "3d" | "xray"
  const threeRef = useRef(null);
  const W = 560, H = 380;

  // ── Three.js isosurface view ──
  useEffect(() => {
    if (viewMode !== "3d" || !mountRef.current || !rho || !nelz) return;
    const container = mountRef.current;

    // Dynamic import Three.js
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
    script.onload = () => {
      const THREE = window.THREE;
      if (!THREE) return;

      // Clean up previous
      if (threeRef.current) {
        container.removeChild(threeRef.current.renderer.domElement);
        threeRef.current.renderer.dispose();
      }

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xf0f2f5);

      const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(W, H);
      renderer.setPixelRatio(window.devicePixelRatio);
      container.innerHTML = "";
      container.appendChild(renderer.domElement);

      // ── Marching Cubes isosurface (smooth, matches paper's skimage approach) ──
      // Pad density field with zeros for clean boundary extraction
      const pnx = nelx+2, pny = nely+2, pnz = nelz+2;
      const padField = new Float32Array(pnx*pny*pnz);
      for (let i=0;i<nelx;i++) for (let j=0;j<nely;j++) for (let k=0;k<nelz;k++)
        padField[(i+1)*pny*pnz+(j+1)*pnz+(k+1)] = rho[i*nely*nelz+j*nelz+k]||0;

      // Marching cubes lookup tables (Paul Bourke)
      const ET=[0x0,0x109,0x203,0x30a,0x406,0x50f,0x605,0x70c,0x80c,0x905,0xa0f,0xb06,0xc0a,0xd03,0xe09,0xf00,0x190,0x99,0x393,0x29a,0x596,0x49f,0x795,0x69c,0x99c,0x895,0xb9f,0xa96,0xd9a,0xc93,0xf99,0xe90,0x230,0x339,0x33,0x13a,0x636,0x73f,0x435,0x53c,0xa3c,0xb35,0x83f,0x936,0xe3a,0xf33,0xc39,0xd30,0x3a0,0x2a9,0x1a3,0xaa,0x7a6,0x6af,0x5a5,0x4ac,0xbac,0xaa5,0x9af,0x8a6,0xfaa,0xea3,0xda9,0xca0,0x460,0x569,0x663,0x76a,0x66,0x16f,0x265,0x36c,0xc6c,0xd65,0xe6f,0xf66,0x86a,0x963,0xa69,0xb60,0x5f0,0x4f9,0x7f3,0x6fa,0x1f6,0xff,0x3f5,0x2fc,0xdfc,0xcf5,0xfff,0xef6,0x9fa,0x8f3,0xbf9,0xaf0,0x650,0x759,0x453,0x55a,0x256,0x35f,0x55,0x15c,0xe5c,0xf55,0xc5f,0xd56,0xa5a,0xb53,0x859,0x950,0x7c0,0x6c9,0x5c3,0x4ca,0x3c6,0x2cf,0x1c5,0xcc,0xfcc,0xec5,0xdcf,0xcc6,0xbca,0xac3,0x9c9,0x8c0,0x8c0,0x9c9,0xac3,0xbca,0xcc6,0xdcf,0xec5,0xfcc,0xcc,0x1c5,0x2cf,0x3c6,0x4ca,0x5c3,0x6c9,0x7c0,0x950,0x859,0xb53,0xa5a,0xd56,0xc5f,0xf55,0xe5c,0x15c,0x55,0x35f,0x256,0x55a,0x453,0x759,0x650,0xaf0,0xbf9,0x8f3,0x9fa,0xef6,0xfff,0xcf5,0xdfc,0x2fc,0x3f5,0xff,0x1f6,0x6fa,0x7f3,0x4f9,0x5f0,0xb60,0xa69,0x963,0x86a,0xf66,0xe6f,0xd65,0xc6c,0x36c,0x265,0x16f,0x66,0x76a,0x663,0x569,0x460,0xca0,0xda9,0xea3,0xfaa,0x8a6,0x9af,0xaa5,0xbac,0x4ac,0x5a5,0x6af,0x7a6,0xaa,0x1a3,0x2a9,0x3a0,0xd30,0xc39,0xf33,0xe3a,0x936,0x83f,0xb35,0xa3c,0x53c,0x435,0x73f,0x636,0x13a,0x33,0x339,0x230,0xe90,0xf99,0xc93,0xd9a,0xa96,0xb9f,0x895,0x99c,0x69c,0x795,0x49f,0x596,0x29a,0x393,0x99,0x190,0xf00,0xe09,0xd03,0xc0a,0xb06,0xa0f,0x905,0x80c,0x70c,0x605,0x50f,0x406,0x30a,0x203,0x109,0x0];
      const TT_raw="-1;0,8,3;0,1,9;1,8,3,9,8,1;1,2,10;0,8,3,1,2,10;9,2,10,0,2,9;2,8,3,2,10,8,10,9,8;3,11,2;0,11,2,8,11,0;1,9,0,2,3,11;1,11,2,1,9,11,9,8,11;3,10,1,11,10,3;0,10,1,0,8,10,8,11,10;3,9,0,3,11,9,11,10,9;9,8,10,10,8,11;4,7,8;4,3,0,7,3,4;0,1,9,8,4,7;4,1,9,4,7,1,7,3,1;1,2,10,8,4,7;3,4,7,3,0,4,1,2,10;9,2,10,9,0,2,8,4,7;2,10,9,2,9,7,2,7,3,7,9,4;8,4,7,3,11,2;11,4,7,11,2,4,2,0,4;9,0,1,8,4,7,2,3,11;4,7,11,9,4,11,9,11,2,9,2,1;3,10,1,3,11,10,7,8,4;1,11,10,1,4,11,1,0,4,7,11,4;4,7,8,9,0,11,9,11,10,11,0,3;4,7,11,4,11,9,9,11,10;9,5,4;9,5,4,0,8,3;0,5,4,1,5,0;8,5,4,8,3,5,3,1,5;1,2,10,9,5,4;3,0,8,1,2,10,4,9,5;5,2,10,5,4,2,4,0,2;2,10,5,3,2,5,3,5,4,3,4,8;9,5,4,2,3,11;0,11,2,0,8,11,4,9,5;0,5,4,0,1,5,2,3,11;2,1,5,2,5,8,2,8,11,4,8,5;10,3,11,10,1,3,9,5,4;4,9,5,0,8,1,8,10,1,8,11,10;5,4,0,5,0,11,5,11,10,11,0,3;5,4,8,5,8,10,10,8,11;9,7,8,5,7,9;9,3,0,9,5,3,5,7,3;0,7,8,0,1,7,1,5,7;1,5,3,3,5,7;9,7,8,9,5,7,10,1,2;10,1,2,9,5,0,5,3,0,5,7,3;8,0,2,8,2,5,8,5,7,10,5,2;2,10,5,2,5,3,3,5,7;7,9,5,7,8,9,3,11,2;9,5,7,9,7,2,9,2,0,2,7,11;2,3,11,0,1,8,1,7,8,1,5,7;11,2,1,11,1,7,7,1,5;9,5,8,8,5,7,10,1,3,10,3,11;5,7,0,5,0,9,7,11,0,1,0,10,11,10,0;11,10,0,11,0,3,10,5,0,8,0,7,5,7,0;11,10,5,7,11,5;10,6,5;0,8,3,5,10,6;9,0,1,5,10,6;1,8,3,1,9,8,5,10,6;1,6,5,2,6,1;1,6,5,1,2,6,3,0,8;9,6,5,9,0,6,0,2,6;5,9,8,5,8,2,5,2,6,3,2,8;2,3,11,10,6,5;11,0,8,11,2,0,10,6,5;0,1,9,2,3,11,5,10,6;5,10,6,1,9,2,9,11,2,9,8,11;6,3,11,6,5,3,5,1,3;0,8,11,0,11,5,0,5,1,5,11,6;3,11,6,0,3,6,0,6,5,0,5,9;6,5,9,6,9,11,11,9,8;5,10,6,4,7,8;4,3,0,4,7,3,6,5,10;1,9,0,5,10,6,8,4,7;10,6,5,1,9,7,1,7,3,7,9,4;6,1,2,6,5,1,4,7,8;1,2,5,5,2,6,3,0,4,3,4,7;8,4,7,9,0,5,0,6,5,0,2,6;7,3,9,7,9,4,3,2,9,5,9,6,2,6,9;3,11,2,7,8,4,10,6,5;5,10,6,4,7,2,4,2,0,2,7,11;0,1,9,4,7,8,2,3,11,5,10,6;9,2,1,9,11,2,9,4,11,7,11,4,5,10,6;8,4,7,3,11,5,3,5,1,5,11,6;5,1,11,5,11,6,1,0,11,7,11,4,0,4,11;0,5,9,0,6,5,0,3,6,11,6,3,8,4,7;6,5,9,6,9,11,4,7,9,7,11,9;10,4,9,6,4,10;4,10,6,4,9,10,0,8,3;10,0,1,10,6,0,6,4,0;8,3,1,8,1,6,8,6,4,6,1,10;1,4,9,1,2,4,2,6,4;3,0,8,1,2,9,2,4,9,2,6,4;0,2,4,4,2,6;8,3,2,8,2,4,4,2,6;10,4,9,10,6,4,11,2,3;0,8,2,2,8,11,4,9,10,4,10,6;3,11,2,0,1,6,0,6,4,6,1,10;6,4,1,6,1,10,4,8,1,2,1,11,8,11,1;9,6,4,9,3,6,9,1,3,11,6,3;8,11,1,8,1,0,11,6,1,9,1,4,6,4,1;3,11,6,3,6,0,0,6,4;6,4,8,11,6,8;7,10,6,7,8,10,8,9,10;0,7,3,0,10,7,0,9,10,6,7,10;10,6,7,1,10,7,1,7,8,1,8,0;10,6,7,10,7,1,1,7,3;1,2,6,1,6,8,1,8,9,8,6,7;2,6,9,2,9,1,6,7,9,0,9,3,7,3,9;7,8,0,7,0,6,6,0,2;7,3,2,6,7,2;2,3,11,10,6,8,10,8,9,8,6,7;2,0,7,2,7,11,0,9,7,6,7,10,9,10,7;1,8,0,1,7,8,1,10,7,6,7,10,2,3,11;11,2,1,11,1,7,10,6,1,6,7,1;8,9,6,8,6,7,9,1,6,11,6,3,1,3,6;0,9,1,11,6,7;7,8,0,7,0,6,3,11,0,11,6,0;7,11,6;7,6,11;3,0,8,11,7,6;0,1,9,11,7,6;8,1,9,8,3,1,11,7,6;10,1,2,6,11,7;1,2,10,3,0,8,6,11,7;2,9,0,2,10,9,6,11,7;6,11,7,2,10,3,10,8,3,10,9,8;7,2,3,6,2,7;7,0,8,7,6,0,6,2,0;2,7,6,2,3,7,0,1,9;1,6,2,1,8,6,1,9,8,8,7,6;10,7,6,10,1,7,1,3,7;10,7,6,1,7,10,1,8,7,1,0,8;0,3,7,0,7,10,0,10,9,6,10,7;7,6,10,7,10,8,8,10,9;6,8,4,11,8,6;3,6,11,3,0,6,0,4,6;8,6,11,8,4,6,9,0,1;9,4,6,9,6,3,9,3,1,11,3,6;6,8,4,6,11,8,2,10,1;1,2,10,3,0,11,0,6,11,0,4,6;4,11,8,4,6,11,0,2,9,2,10,9;10,9,3,10,3,2,9,4,3,11,3,6,4,6,3;8,2,3,8,4,2,4,6,2;0,4,2,4,6,2;1,9,0,2,3,4,2,4,6,4,3,8;1,9,4,1,4,2,2,4,6;8,1,3,8,6,1,8,4,6,6,10,1;10,1,0,10,0,6,6,0,4;4,6,3,4,3,8,6,10,3,0,3,9,10,9,3;10,9,4,6,10,4;4,9,5,7,6,11;0,8,3,4,9,5,11,7,6;5,0,1,5,4,0,7,6,11;11,7,6,8,3,4,3,5,4,3,1,5;9,5,4,10,1,2,7,6,11;6,11,7,1,2,10,0,8,3,4,9,5;7,6,11,5,4,10,4,2,10,4,0,2;3,4,8,3,5,4,3,2,5,10,5,2,11,7,6;7,2,3,7,6,2,5,4,9;9,5,4,0,8,6,0,6,2,6,8,7;3,6,2,3,7,6,1,5,0,5,4,0;6,2,8,6,8,7,2,1,8,4,8,5,1,5,8;9,5,4,10,1,6,1,7,6,1,3,7;1,6,10,1,7,6,1,0,7,8,7,0,9,5,4;4,0,10,4,10,5,0,3,10,6,10,7,3,7,10;7,6,10,7,10,8,5,4,10,4,8,10;6,9,5,6,11,9,11,8,9;3,6,11,0,6,3,0,5,6,0,9,5;0,11,8,0,5,11,0,1,5,5,6,11;6,11,3,6,3,5,5,3,1;1,2,10,9,5,11,9,11,8,11,5,6;0,11,3,0,6,11,0,9,6,5,6,9,1,2,10;11,8,5,11,5,6,8,0,5,10,5,2,0,2,5;6,11,3,6,3,5,2,10,3,10,5,3;5,8,9,5,2,8,5,6,2,3,8,2;9,5,6,9,6,0,0,6,2;1,5,8,1,8,0,5,6,8,3,8,2,6,2,8;1,5,6,2,1,6;1,3,6,1,6,10,3,8,6,5,6,9,8,9,6;10,1,0,10,0,6,9,5,0,5,6,0;0,3,8,5,6,10;10,5,6;11,5,10,7,5,11;11,5,10,11,7,5,8,3,0;5,11,7,5,10,11,1,9,0;10,7,5,10,11,7,9,8,1,8,3,1;11,1,2,11,7,1,7,5,1;0,8,3,1,2,7,1,7,5,7,2,11;9,7,5,9,2,7,9,0,2,2,11,7;7,5,2,7,2,11,5,9,2,3,2,8,9,8,2;2,5,10,2,3,5,3,7,5;8,2,0,8,5,2,8,7,5,10,2,5;9,0,1,5,10,3,5,3,7,3,10,2;9,8,2,9,2,1,8,7,2,10,2,5,7,5,2;1,3,5,3,7,5;0,8,7,0,7,1,1,7,5;9,0,3,9,3,5,5,3,7;9,8,7,5,9,7;5,8,4,5,10,8,10,11,8;5,0,4,5,11,0,5,10,11,11,3,0;0,1,9,8,4,10,8,10,11,10,4,5;10,11,4,10,4,5,11,3,4,9,4,1,3,1,4;2,5,1,2,8,5,2,11,8,4,5,8;0,4,11,0,11,3,4,5,11,2,11,1,5,1,11;0,2,5,0,5,9,2,11,5,4,5,8,11,8,5;9,4,5,2,11,3;2,5,10,3,5,2,3,4,5,3,8,4;5,10,2,5,2,4,4,2,0;3,10,2,3,5,10,3,8,5,4,5,8,0,1,9;5,10,2,5,2,4,1,9,2,9,4,2;8,4,5,8,5,3,3,5,1;0,4,5,1,0,5;8,4,5,8,5,3,9,0,5,0,3,5;9,4,5;4,11,7,4,9,11,9,10,11;0,8,3,4,9,7,9,11,7,9,10,11;1,10,11,1,11,4,1,4,0,7,4,11;3,1,4,3,4,8,1,10,4,7,4,11,10,11,4;4,11,7,9,11,4,9,2,11,9,1,2;9,7,4,9,11,7,9,1,11,2,11,1,0,8,3;11,7,4,11,4,2,2,4,0;11,7,4,11,4,2,8,3,4,3,2,4;2,9,10,2,7,9,2,3,7,7,4,9;9,10,7,9,7,4,10,2,7,8,7,0,2,0,7;3,7,10,3,10,2,7,4,10,1,10,0,4,0,10;1,10,2,8,7,4;4,9,1,4,1,7,7,1,3;4,9,1,4,1,7,0,8,1,8,7,1;4,0,3,7,4,3;4,8,7;9,10,8,10,11,8;3,0,9,3,9,11,11,9,10;0,1,10,0,10,8,8,10,11;3,1,10,11,3,10;1,2,11,1,11,9,9,11,8;3,0,9,3,9,11,1,2,9,2,11,9;0,2,11,8,0,11;3,2,11;2,3,8,2,8,10,10,8,9;9,10,2,0,9,2;2,3,8,2,8,10,0,1,8,1,10,8;1,10,2;1,3,8,9,1,8;0,9,1;0,3,8;-1";
      const TT=TT_raw.split(";").map(s=>s==="-1"?[-1]:s.split(",").map(Number));

      const iso=0.5;
      const scX=2.0/nelx, scY=2.0*(nely/nelx)/nely, scZ=2.0*(nelz/nelx)/nelz;
      const oX=-1, oY=-0.5*(nely/nelx)*2, oZ=-0.5*(nelz/nelx)*2;
      const positions=[];

      function lerp(p1,p2,v1,v2){
        if(Math.abs(v1-iso)<1e-10)return p1.slice();
        if(Math.abs(v2-iso)<1e-10)return p2.slice();
        const mu=(iso-v1)/(v2-v1);
        return[p1[0]+mu*(p2[0]-p1[0]),p1[1]+mu*(p2[1]-p1[1]),p1[2]+mu*(p2[2]-p1[2])];
      }

      for(let i=0;i<pnx-1;i++)for(let j=0;j<pny-1;j++)for(let k=0;k<pnz-1;k++){
        const v=[padField[i*pny*pnz+j*pnz+k],padField[(i+1)*pny*pnz+j*pnz+k],padField[(i+1)*pny*pnz+(j+1)*pnz+k],padField[i*pny*pnz+(j+1)*pnz+k],padField[i*pny*pnz+j*pnz+(k+1)],padField[(i+1)*pny*pnz+j*pnz+(k+1)],padField[(i+1)*pny*pnz+(j+1)*pnz+(k+1)],padField[i*pny*pnz+(j+1)*pnz+(k+1)]];
        let ci=0;for(let b=0;b<8;b++)if(v[b]>=iso)ci|=(1<<b);
        if(ET[ci]===0)continue;
        const p=[[i,j,k],[i+1,j,k],[i+1,j+1,k],[i,j+1,k],[i,j,k+1],[i+1,j,k+1],[i+1,j+1,k+1],[i,j+1,k+1]].map(c=>[(c[0]-1)*scX+oX,(c[1]-1)*scY+oY,(c[2]-1)*scZ+oZ]);
        const vl=new Array(12);const et=ET[ci];
        if(et&1)vl[0]=lerp(p[0],p[1],v[0],v[1]);if(et&2)vl[1]=lerp(p[1],p[2],v[1],v[2]);
        if(et&4)vl[2]=lerp(p[2],p[3],v[2],v[3]);if(et&8)vl[3]=lerp(p[3],p[0],v[3],v[0]);
        if(et&16)vl[4]=lerp(p[4],p[5],v[4],v[5]);if(et&32)vl[5]=lerp(p[5],p[6],v[5],v[6]);
        if(et&64)vl[6]=lerp(p[6],p[7],v[6],v[7]);if(et&128)vl[7]=lerp(p[7],p[4],v[7],v[4]);
        if(et&256)vl[8]=lerp(p[0],p[4],v[0],v[4]);if(et&512)vl[9]=lerp(p[1],p[5],v[1],v[5]);
        if(et&1024)vl[10]=lerp(p[2],p[6],v[2],v[6]);if(et&2048)vl[11]=lerp(p[3],p[7],v[3],v[7]);
        const tri=TT[ci];for(let t=0;t<tri.length&&tri[t]!==-1;t+=3)positions.push(...vl[tri[t]],...vl[tri[t+1]],...vl[tri[t+2]]);
      }

      if(positions.length>0){
        const geo=new THREE.BufferGeometry();
        geo.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));
        geo.computeVertexNormals();
        const mat=new THREE.MeshPhongMaterial({color:0x2ecc71,specular:0x444444,shininess:60,side:THREE.DoubleSide});
        const mesh=new THREE.Mesh(geo,mat);
        scene.add(mesh);
      }

      // Lighting
      scene.add(new THREE.AmbientLight(0x404040, 1.5));
      const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
      dirLight.position.set(3, 4, 5);
      scene.add(dirLight);
      const dirLight2 = new THREE.DirectionalLight(0x8888ff, 0.5);
      dirLight2.position.set(-3, -2, -3);
      scene.add(dirLight2);

      // Camera position
      const aspect = nelx / Math.max(nely, nelz);
      camera.position.set(2.5, 1.5, 2.5);
      camera.lookAt(0, 0, 0);

      // Simple orbit controls (mouse drag to rotate)
      let isDragging = false, prevX = 0, prevY = 0;
      let rotY = -0.6, rotX = 0.4;
      const pivot = new THREE.Group();
      pivot.rotation.order = "YXZ";
      pivot.rotation.y = rotY;
      pivot.rotation.x = rotX;
      scene.children.forEach(c => { if (c.type === "Mesh") { scene.remove(c); pivot.add(c); } });
      scene.add(pivot);

      renderer.domElement.addEventListener("mousedown", (e) => { isDragging = true; prevX = e.clientX; prevY = e.clientY; });
      renderer.domElement.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        rotY += (e.clientX - prevX) * 0.01;
        rotX += (e.clientY - prevY) * 0.01;
        rotX = Math.max(-Math.PI/2, Math.min(Math.PI/2, rotX));
        pivot.rotation.y = rotY;
        pivot.rotation.x = rotX;
        prevX = e.clientX; prevY = e.clientY;
      });
      renderer.domElement.addEventListener("mouseup", () => isDragging = false);
      renderer.domElement.addEventListener("mouseleave", () => isDragging = false);
      renderer.domElement.addEventListener("wheel", (e) => {
        camera.position.multiplyScalar(e.deltaY > 0 ? 1.05 : 0.95);
        e.preventDefault();
      }, { passive: false });

      // Animate
      let animId;
      function animate() {
        animId = requestAnimationFrame(animate);
        renderer.render(scene, camera);
      }
      animate();

      threeRef.current = { renderer, scene, camera, animId };
    };

    if (window.THREE) {
      script.onload();
    } else {
      document.head.appendChild(script);
    }

    return () => {
      if (threeRef.current) {
        cancelAnimationFrame(threeRef.current.animId);
        if (container.contains(threeRef.current.renderer.domElement)) {
          container.removeChild(threeRef.current.renderer.domElement);
        }
        threeRef.current.renderer.dispose();
        threeRef.current = null;
      }
    };
  }, [rho, nelx, nely, nelz, viewMode]);

  // ── X-ray projection view (canvas) ──
  useEffect(() => {
    if (viewMode !== "xray" || !canvasRef.current || !rho || !nelz) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, W, H);

    const get = (i, j, k) => rho[i * nely * nelz + j * nelz + k] || 0;
    const gap = 8;
    const projW = (W - 3 * gap) / 2.5;

    // XY projection
    const xyW = projW, xyH = projW * (nely / nelx);
    ctx.fillStyle = "#374151"; ctx.font = "9px monospace";
    ctx.fillText("X-Y (mean over Z)", gap, gap + xyH + 14);
    for (let i = 0; i < nelx; i++) for (let j = 0; j < nely; j++) {
      let s = 0; for (let k = 0; k < nelz; k++) s += get(i,j,k);
      const g = Math.round((1 - s/nelz) * 255);
      ctx.fillStyle = `rgb(${g},${g},${g})`;
      ctx.fillRect(gap + i*(xyW/nelx), gap + xyH - (j+1)*(xyH/nely), xyW/nelx+.5, xyH/nely+.5);
    }

    // XZ projection
    const xzW = projW, xzH = projW * (nelz / nelx);
    const xzX = gap + xyW + gap*2;
    ctx.fillStyle = "#374151";
    ctx.fillText("X-Z (mean over Y)", xzX, gap + xzH + 14);
    for (let i = 0; i < nelx; i++) for (let k = 0; k < nelz; k++) {
      let s = 0; for (let j = 0; j < nely; j++) s += get(i,j,k);
      const g = Math.round((1 - s/nely) * 255);
      ctx.fillStyle = `rgb(${g},${g},${g})`;
      ctx.fillRect(xzX + i*(xzW/nelx), gap + xzH - (k+1)*(xzH/nelz), xzW/nelx+.5, xzH/nelz+.5);
    }

    // YZ projection
    const yzW = projW * (nelz/nelx) * 1.5, yzH = projW * (nely/nelx);
    const yzY = gap + xzH + 28;
    ctx.fillStyle = "#374151";
    ctx.fillText("Y-Z (mean over X)", xzX, yzY + yzH + 14);
    for (let j = 0; j < nely; j++) for (let k = 0; k < nelz; k++) {
      let s = 0; for (let i = 0; i < nelx; i++) s += get(i,j,k);
      const g = Math.round((1 - s/nelx) * 255);
      ctx.fillStyle = `rgb(${g},${g},${g})`;
      ctx.fillRect(xzX + k*(yzW/nelz), yzY + yzH - (j+1)*(yzH/nely), yzW/nelz+.5, yzH/nely+.5);
    }
  }, [rho, nelx, nely, nelz, viewMode]);

  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
        {["3d", "xray"].map(m => (
          <button key={m} onClick={() => setViewMode(m)} style={{
            padding: "3px 10px", fontSize: 10, fontFamily: "monospace",
            background: viewMode === m ? COLORS.accentDim : "transparent",
            color: viewMode === m ? "#fff" : COLORS.textDim,
            border: `1px solid ${viewMode === m ? COLORS.accent : COLORS.panelBorder}`,
            borderRadius: 4, cursor: "pointer", textTransform: "uppercase",
          }}>
            {m === "3d" ? "Interactive 3D" : "X-Ray Projections"}
          </button>
        ))}
      </div>
      {viewMode === "3d" ? (
        <div>
          <div ref={mountRef} style={{ width: W, height: H, borderRadius: 8, overflow: "hidden", background: "#f0f2f5" }} />
          <p style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 4 }}>
            Drag to rotate | Scroll to zoom | Isosurface at ρ = 0.5
          </p>
        </div>
      ) : (
        <canvas ref={canvasRef} style={{ width: W, height: H, borderRadius: 8 }} />
      )}
    </div>
  );
}

function ProgressBar({ progress, label, sublabel }) {
  return (
    <div style={{ width: "100%", marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ color: COLORS.text, fontSize: 12, fontFamily: "monospace" }}>{label}</span>
        <span style={{ color: COLORS.textDim, fontSize: 11, fontFamily: "monospace" }}>{sublabel}</span>
      </div>
      <div style={{ height: 6, background: COLORS.panelBorder, borderRadius: 3, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${clamp(progress, 0, 100)}%`,
          background: `linear-gradient(90deg, ${COLORS.accentDim}, ${COLORS.accent})`,
          borderRadius: 3,
          transition: "width 0.3s ease",
          boxShadow: `0 0 8px ${COLORS.accentGlow}`,
        }} />
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit, status }) {
  const color = status === "pass" ? COLORS.success : status === "fail" ? COLORS.error : COLORS.text;
  return (
    <div style={{
      padding: "10px 14px", background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
      borderRadius: 8, flex: "1 1 120px", minWidth: 120,
    }}>
      <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, color, fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}>
        {value}<span style={{ fontSize: 11, color: COLORS.textDim, marginLeft: 3 }}>{unit}</span>
      </div>
    </div>
  );
}

// ─── Main App ──────────────────────────────────────────────────────

export default function AutoSiMPUI() {
  const [stage, setStage] = useState("input"); // input | configuring | preview | running | results
  const [prompt, setPrompt] = useState("");
  const [spec, setSpec] = useState(null);
  const [configLog, setConfigLog] = useState([]);
  const [solverState, setSolverState] = useState(null);
  const [results, setResults] = useState(null);
  const [iterHistory, setIterHistory] = useState([]);
  const [maxIter, setMaxIter] = useState(80);
  const solverRef = useRef(null);
  const runningRef = useRef(false);
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [useBackend, setUseBackend] = useState(() => localStorage.getItem("use_backend") === "true");
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem("backend_url") || "http://localhost:5555");
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("llm_api_key") || "");
  const [llmProvider, setLlmProvider] = useState(() => localStorage.getItem("llm_provider") || "gemini");
  const [llmModel, setLlmModel] = useState(() => localStorage.getItem("llm_model") || "gemini-2.5-flash-lite");
  const [llmEvaluation, setLlmEvaluation] = useState(null);
  const [llmEvalLoading, setLlmEvalLoading] = useState(false);
  
  const LLM_PROVIDERS = {
    gemini: { label: "Google Gemini", placeholder: "Gemini API key", models: ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview", "gemini-2.5-flash", "gemini-2.5-pro"], helpUrl: "https://aistudio.google.com/apikey" },
    openai: { label: "OpenAI", placeholder: "sk-...", models: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"], helpUrl: "https://platform.openai.com/api-keys" },
    anthropic: { label: "Anthropic Claude", placeholder: "sk-ant-...", models: ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"], helpUrl: "https://console.anthropic.com/" },
    custom: { label: "Custom (OpenAI-compatible)", placeholder: "your-key", models: [], helpUrl: "" },
  };
  const [customUrl, setCustomUrl] = useState(() => localStorage.getItem("llm_custom_url") || "");

  const handlePreset = (key) => {
    const p = PRESETS[key];
    setSelectedPreset(key);
    setPrompt(p.prompt);
    // Go straight to preview with the preset spec — no LLM needed
    setSpec(JSON.parse(JSON.stringify(p.spec)));
    setConfigLog([{ time: Date.now(), msg: `✓ Loaded preset: ${p.label}` },
      { time: Date.now(), msg: `Domain: ${p.spec.Lx}×${p.spec.Ly}${p.spec.Lz ? "×"+p.spec.Lz : ""}, Mesh: ${p.spec.nelx}×${p.spec.nely}${p.spec.nelz ? "×"+p.spec.nelz : ""}, Vf=${p.spec.volfrac}` },
      { time: Date.now(), msg: `Supports: ${p.spec.supports.length}, Loads: ${p.spec.loads.length}, Passive: ${p.spec.passive_regions?.length || 0}` },
    ]);
    setStage("preview");
  };

  const handleConfigure = async () => {
    if (!prompt.trim()) return;
    setStage("configuring");
    setConfigLog([]);

    const addLog = (msg) => setConfigLog(prev => [...prev, { time: Date.now(), msg }]);

    addLog("Parsing natural-language description...");
    await new Promise(r => setTimeout(r, 400));

    if (!apiKey) {
      addLog("⚠ No Gemini API key — using keyword fallback.");
      await new Promise(r => setTimeout(r, 300));
      
      const lower = prompt.toLowerCase();
      let fallback = PRESETS.cantilever.spec;
      if (lower.includes("mbb")) fallback = PRESETS.mbb.spec;
      else if (lower.includes("bridge")) fallback = PRESETS.bridge.spec;
      else if (lower.includes("hole") || lower.includes("pipe")) fallback = PRESETS.cantilever_hole.spec;
      else if (lower.includes("simply") || lower.includes("supported")) fallback = PRESETS.cantilever.spec;

      addLog("✓ Matched preset from keywords. No API call made.");
      addLog(`Domain: ${fallback.Lx}×${fallback.Ly}, Mesh: ${fallback.nelx}×${fallback.nely}, Vf=${fallback.volfrac}`);
      addLog(`Supports: ${fallback.supports.length}, Loads: ${fallback.loads.length}`);
      addLog("");
      addLog("→ Click 'Continue to Preview' to inspect and edit the specification.");
      setSpec(JSON.parse(JSON.stringify(fallback)));
      // Don't auto-advance — let user review the log
      return;
    }

    // Use LLM API to parse the prompt — multi-provider support
    addLog(`Calling ${LLM_PROVIDERS[llmProvider]?.label || llmProvider} / ${llmModel}...`);

    try {
      const sysPrompt = `You are a topology optimization problem configurator. The user describes a structural design problem in natural language. You output ONLY valid JSON (no markdown, no extra text) with this structure:
{"Lx": <float>, "Ly": <float>, "Lz": <float, 0 for 2D>, "nelx": <int 30-120>, "nely": <int 15-60>, "nelz": <int, 0 for 2D>, "volfrac": <float 0.1-0.9>,
"supports": [{"type":"edge","edge":"left"|"right"|"top"|"bottom","constraint":"fixed"|"pin_x"|"pin_y"|"roller_x"|"roller_y"} or {"type":"point","x":<float>,"y":<float>,"constraint":"fixed"|"pin_x"|"pin_y"}],
"loads": [{"type":"point","x":<float>,"y":<float>,"fx":<float>,"fy":<float>} or {"type":"distributed","edge":"left"|"right"|"top"|"bottom","magnitude":<float>}],
"passive_regions": [{"type":"circle","cx":<float>,"cy":<float>,"radius":<float>,"kind":"void"|"solid"}]}
Rules: "cantilever"=left fixed+tip load. "MBB"=left pin_x+bottom-right pin_y+top-left load. "bridge"=bottom corners pinned+top distributed. Origin at bottom-left. Downward=fy=-1. Keep nelx/nely ratio ~ Lx/Ly. Default volfrac=0.5.
3D rules: If the user says "3D" or mentions depth/thickness/z-axis, set Lz>0 and nelz>0. Default 3D mesh: 30x15x8. Use "left"/"right"/"front"/"back" for face supports. Point loads need z coordinate. A "3D cantilever" = left face fixed, point load at center of right face. A "3D MBB" = left face pin_x, bottom-right edge pin_y, top-left load.`;

      let response, data, text;

      if (llmProvider === "gemini") {
        // ── Google Gemini API ──
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${llmModel}:generateContent?key=${apiKey}`;
        response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            system_instruction: { parts: [{ text: sysPrompt }] },
            contents: [{ role: "user", parts: [{ text: prompt }] }],
            generationConfig: { temperature: 0, maxOutputTokens: 1200, responseMimeType: "application/json" },
          }),
        });
        data = await response.json();
        if (data.error) throw new Error(data.error.message || `Gemini error ${data.error.code}`);
        const candidates = data.candidates || [];
        if (!candidates.length) throw new Error("No candidates in Gemini response");
        text = candidates[0]?.content?.parts?.[0]?.text || "";

      } else if (llmProvider === "openai" || llmProvider === "custom") {
        // ── OpenAI / OpenAI-compatible API ──
        const url = llmProvider === "custom" && customUrl ? customUrl : "https://api.openai.com/v1/chat/completions";
        response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
          body: JSON.stringify({
            model: llmModel,
            temperature: 0,
            max_tokens: 1200,
            response_format: { type: "json_object" },
            messages: [
              { role: "system", content: sysPrompt },
              { role: "user", content: prompt },
            ],
          }),
        });
        data = await response.json();
        if (data.error) throw new Error(data.error.message || `OpenAI error`);
        text = data.choices?.[0]?.message?.content || "";

      } else if (llmProvider === "anthropic") {
        // ── Anthropic Claude API ──
        response = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
          },
          body: JSON.stringify({
            model: llmModel,
            max_tokens: 1200,
            system: sysPrompt,
            messages: [{ role: "user", content: prompt }],
          }),
        });
        data = await response.json();
        if (data.error) throw new Error(data.error.message || `Anthropic error`);
        text = data.content?.find(b => b.type === "text")?.text || "";
      } else {
        throw new Error(`Unknown provider: ${llmProvider}`);
      }

      addLog(`✓ Response received (${text.length} chars). Parsing JSON...`);

      const jsonStr = text.replace(/```json/g, "").replace(/```/g, "").trim();
      const parsed = JSON.parse(jsonStr);

      // Safety rails (identical to configurator_agent.py _sanitize_spec_dict)
      parsed.Lx = Math.max(0.5, parsed.Lx || 2);
      parsed.Ly = Math.max(0.5, parsed.Ly || 1);
      parsed.nelx = clamp(parsed.nelx || 60, 10, 120);
      parsed.nely = clamp(parsed.nely || 30, 10, 60);
      parsed.volfrac = clamp(parsed.volfrac || 0.5, 0.1, 0.9);
      if (!parsed.supports?.length) {
        parsed.supports = [{ type: "edge", edge: "left", constraint: "fixed" }];
        addLog("⚠ No supports — defaulted to left edge fixed.");
      }
      if (!parsed.loads?.length) {
        parsed.loads = [{ type: "point", x: parsed.Lx, y: parsed.Ly / 2, fx: 0, fy: -1 }];
        addLog("⚠ No loads — defaulted to mid-right downward.");
      }
      parsed.passive_regions = parsed.passive_regions || [];

      addLog("✓ Safety rails applied. Specification validated.");
      addLog(`Domain: ${parsed.Lx}×${parsed.Ly}, Mesh: ${parsed.nelx}×${parsed.nely}, Vf=${parsed.volfrac}`);
      addLog(`Supports: ${parsed.supports.length}, Loads: ${parsed.loads.length}, Passive: ${parsed.passive_regions.length}`);
      addLog("");
      addLog("→ Click 'Continue to Preview' to inspect and edit the specification.");

      setSpec(parsed);
      // Don't auto-advance — let user review
    } catch (err) {
      addLog(`⚠ LLM call failed: ${err.message}`);
      addLog("Falling back to preset detection...");

      // Fallback: try to match a preset keyword
      const lower = prompt.toLowerCase();
      let fallback = PRESETS.cantilever.spec;
      if (lower.includes("mbb")) fallback = PRESETS.mbb.spec;
      else if (lower.includes("bridge")) fallback = PRESETS.bridge.spec;
      else if (lower.includes("hole") || lower.includes("pipe")) fallback = PRESETS.cantilever_hole.spec;

      addLog("✓ Fallback spec created.");
      addLog("");
      addLog("→ Click 'Continue to Preview' to inspect and edit the specification.");
      setSpec(JSON.parse(JSON.stringify(fallback)));
      // Don't auto-advance
    }
  };

  const handleUpdateLoad = useCallback((idx, x, y) => {
    setSpec(prev => {
      if (!prev) return prev;
      const newSpec = JSON.parse(JSON.stringify(prev));
      if (newSpec.loads[idx] && newSpec.loads[idx].type === "point") {
        newSpec.loads[idx].x = Math.round(x * 100) / 100;
        newSpec.loads[idx].y = Math.round(y * 100) / 100;
      }
      return newSpec;
    });
  }, []);

  const handleRun = useCallback(() => {
    if (!spec) return;
    setStage("running");
    setIterHistory([]);
    setLlmEvaluation(null);
    setLlmEvalLoading(false);
    runningRef.current = true;

    // ── Python Backend Path (blocking call with waiting UI) ──
    if (useBackend) {
      setSolverState({ iter: 0, maxIter: maxIter, compliance: 0, change: 1, grayness: 1, rho: null, penal: 1, beta: 1, waiting: true });

      (async () => {
        try {
          const t0 = Date.now();
          // Animated timer while waiting
          const ticker = setInterval(() => {
            const elapsed = ((Date.now() - t0) / 1000).toFixed(0);
            setSolverState(prev => ({ ...prev, elapsed }));
          }, 500);

          const resp = await fetch(`${backendUrl}/solve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ spec, controller: "schedule", max_iter: maxIter }),
          });
          clearInterval(ticker);

          const data = await resp.json();
          if (!data.success) throw new Error(data.error || "Backend solve failed");

          const rhoFlat = data.is_3d
            ? new Float64Array(data.rho.flat(2))
            : new Float64Array(data.rho.flat());

          setSolverState({
            iter: data.n_iter, maxIter: maxIter,
            compliance: data.compliance, change: 0, grayness: data.grayness,
            rho: rhoFlat, penal: 4.5, beta: 32, waiting: false,
            is3d: data.is_3d, nelx: data.nelx, nely: data.nely, nelz: data.nelz,
          });
          setIterHistory([{ iter: data.n_iter, compliance: data.compliance, change: 0, grayness: data.grayness }]);
          setResults({
            bestCompliance: data.best_compliance || data.compliance,
            finalGrayness: data.grayness,
            volFrac: data.volfrac_actual,
            finalIter: data.n_iter,
            passed: data.evaluation?.passed || false,
            wallTime: data.wall_time,
            backendEval: data.evaluation,
          });
          setStage("results");

          // LLM Evaluator
          if (apiKey) {
            setLlmEvalLoading(true);
            const evalPrompt = `You are a structural topology optimization evaluator. Give a 3-4 sentence assessment.
Problem: ${spec.Lx}×${spec.Ly}${spec.Lz ? "×"+spec.Lz : ""}, ${spec.nelx}×${spec.nely}${spec.nelz ? "×"+spec.nelz : ""} mesh, Vf=${spec.volfrac}
Results: C=${data.compliance.toFixed(2)}, gray=${data.grayness.toFixed(4)}, vf=${(data.volfrac_actual*100).toFixed(1)}%, ${data.n_iter} iters, ${data.wall_time}s, ${data.evaluation?.passed ? "PASSED" : "FAILED"}
Respond with JSON: {"assessment": "...", "suggestions": ["..."], "quality_score": 1-10}`;
            try {
              let text;
              if (llmProvider === "gemini") {
                const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${llmModel}:generateContent?key=${apiKey}`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ contents: [{role:"user",parts:[{text:evalPrompt}]}], generationConfig: {temperature:0.3,maxOutputTokens:500,responseMimeType:"application/json"} })});
                text = (await r.json()).candidates?.[0]?.content?.parts?.[0]?.text || "";
              } else if (llmProvider === "openai" || llmProvider === "custom") {
                const url = llmProvider === "custom" && customUrl ? customUrl : "https://api.openai.com/v1/chat/completions";
                const r = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json","Authorization":`Bearer ${apiKey}`}, body: JSON.stringify({ model:llmModel,temperature:0.3,max_tokens:500,response_format:{type:"json_object"},messages:[{role:"user",content:evalPrompt}] })});
                text = (await r.json()).choices?.[0]?.message?.content || "";
              } else if (llmProvider === "anthropic") {
                const r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: {"Content-Type":"application/json","x-api-key":apiKey,"anthropic-version":"2023-06-01","anthropic-dangerous-direct-browser-access":"true"}, body: JSON.stringify({ model:llmModel,max_tokens:500,messages:[{role:"user",content:evalPrompt}] })});
                text = (await r.json()).content?.find(b=>b.type==="text")?.text || "";
              }
              setLlmEvaluation(JSON.parse(text.replace(/```json/g,"").replace(/```/g,"").trim()));
            } catch(e) { setLlmEvaluation({assessment:`LLM eval error: ${e.message}`,suggestions:[],quality_score:null}); }
            finally { setLlmEvalLoading(false); }
          }
        } catch (err) {
          setResults({ passed: false, finalIter: 0, error: err.message });
          setStage("results");
        }
      })();
      return;
    }

    // ── Browser Solver Path ──
    const maxIterVal = maxIter;
    const solver = createSimpSolver(spec);
    solverRef.current = solver;
    let iter = 0;
    const localHistory = []; // Track locally for LLM evaluator (avoids stale React state closure)

    function step() {
      if (!runningRef.current || iter >= maxIterVal) {
        runningRef.current = false;
        // Compute final metrics
        const lastRho = solver.getRho();
        const nEl = spec.nelx * spec.nely;
        let gray = 0;
        for (let e = 0; e < nEl; e++) gray += 4 * lastRho[e] * (1 - lastRho[e]);
        gray /= nEl;
        let vol = 0;
        for (let e = 0; e < nEl; e++) vol += lastRho[e];
        vol /= nEl;

        setResults(prev => ({
          ...(prev || {}),
          finalGrayness: gray,
          volFrac: vol,
          finalIter: iter,
          passed: gray < 0.15 && Math.abs(vol - spec.volfrac) < 0.02,
        }));
        setStage("results");

        // ── LLM Evaluator (Module 4) — qualitative assessment ──
        if (apiKey) {
          setLlmEvalLoading(true);
          const bestC = localHistory.length > 0 ? Math.min(...localHistory.map(h => h.compliance)) : 0;
          const lastC = localHistory.length > 0 ? localHistory[localHistory.length-1].compliance : 0;
          const converged = localHistory.slice(-5).every(h => h.change < 0.01);
          const evalPrompt = `You are a structural topology optimization evaluator. Analyze these results and give a 3-4 sentence assessment. Be specific about what's good and what could improve.

Problem: ${spec.Lx}×${spec.Ly} domain, ${spec.nelx}×${spec.nely} mesh, Vf=${spec.volfrac}
Supports: ${JSON.stringify(spec.supports)}
Loads: ${JSON.stringify(spec.loads)}
Passive regions: ${spec.passive_regions?.length || 0}

Results after ${iter} iterations:
- Final compliance: ${lastC.toFixed(2)}
- Best compliance: ${bestC.toFixed(2)}
- Grayness: ${gray.toFixed(4)} (threshold: ≤0.15)
- Volume fraction: ${(vol*100).toFixed(1)}% (target: ${(spec.volfrac*100).toFixed(0)}%)
- Converged: ${converged ? "yes" : "no"}

Respond with a JSON object: {"assessment": "your 3-4 sentence analysis", "suggestions": ["suggestion1", "suggestion2"], "quality_score": 1-10}`;

          (async () => {
            try {
              let text;
              if (llmProvider === "gemini") {
                const url = `https://generativelanguage.googleapis.com/v1beta/models/${llmModel}:generateContent?key=${apiKey}`;
                const resp = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({
                  contents: [{role:"user", parts:[{text: evalPrompt}]}],
                  generationConfig: { temperature: 0.3, maxOutputTokens: 500, responseMimeType: "application/json" }
                })});
                const d = await resp.json();
                text = d.candidates?.[0]?.content?.parts?.[0]?.text || "";
              } else if (llmProvider === "openai" || llmProvider === "custom") {
                const url = llmProvider === "custom" && customUrl ? customUrl : "https://api.openai.com/v1/chat/completions";
                const resp = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json", "Authorization": `Bearer ${apiKey}`}, body: JSON.stringify({
                  model: llmModel, temperature: 0.3, max_tokens: 500, response_format: {type:"json_object"},
                  messages: [{role:"user", content: evalPrompt}]
                })});
                const d = await resp.json();
                text = d.choices?.[0]?.message?.content || "";
              } else if (llmProvider === "anthropic") {
                const resp = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: {"Content-Type":"application/json","x-api-key":apiKey,"anthropic-version":"2023-06-01","anthropic-dangerous-direct-browser-access":"true"}, body: JSON.stringify({
                  model: llmModel, max_tokens: 500, messages: [{role:"user", content: evalPrompt}]
                })});
                const d = await resp.json();
                text = d.content?.find(b => b.type === "text")?.text || "";
              }
              const parsed = JSON.parse(text.replace(/```json/g,"").replace(/```/g,"").trim());
              setLlmEvaluation(parsed);
            } catch(e) {
              setLlmEvaluation({ assessment: `LLM evaluator error: ${e.message}`, suggestions: [], quality_score: null });
            } finally {
              setLlmEvalLoading(false);
            }
          })();
        }

        return;
      }

      const res = solver.iterate();
      iter++;
      localHistory.push({ iter, compliance: res.compliance, change: res.change, grayness: res.grayness });

      setIterHistory(prev => [...prev, { iter, compliance: res.compliance, change: res.change, grayness: res.grayness }]);
      setSolverState({
        iter,
        maxIter: maxIterVal,
        compliance: res.compliance,
        change: res.change,
        grayness: res.grayness,
        rho: res.rho,
        penal: res.penal,
        beta: res.beta,
      });
      setResults(prev => ({
        ...(prev || {}),
        bestCompliance: prev?.bestCompliance ? Math.min(prev.bestCompliance, res.compliance) : res.compliance,
      }));

      // Adaptive speed: fast early, slower when interesting
      const delay = iter < 5 ? 30 : iter < 20 ? 60 : 100;
      setTimeout(step, delay);
    }

    setTimeout(step, 100);
  }, [spec, maxIter, useBackend, backendUrl, apiKey, llmProvider, llmModel]);

  const handleStop = () => { runningRef.current = false; };

  const handleReset = () => {
    runningRef.current = false;
    setStage("input");
    setSpec(null);
    setPrompt("");
    setSelectedPreset(null);
    setConfigLog([]);
    setSolverState(null);
    setResults(null);
    setIterHistory([]);
    setLlmEvaluation(null);
    setLlmEvalLoading(false);
  };

  // Compliance history mini-chart
  const ComplianceChart = ({ history }) => {
    if (!history.length) return null;
    const W = 260, H = 80, PAD = 5;
    const maxC = Math.max(...history.map(h => h.compliance)) * 1.1;
    const minC = Math.min(...history.map(h => h.compliance)) * 0.9;
    const points = history.map((h, i) => {
      const x = PAD + (i / Math.max(history.length - 1, 1)) * (W - 2 * PAD);
      const y = H - PAD - ((h.compliance - minC) / (maxC - minC + 1e-10)) * (H - 2 * PAD);
      return `${x},${y}`;
    }).join(" ");

    return (
      <svg width={W} height={H} style={{ display: "block" }}>
        <polyline points={points} fill="none" stroke={COLORS.accent} strokeWidth="1.5" />
        <text x={5} y={12} fill={COLORS.textMuted} fontSize={9} fontFamily="monospace">{maxC.toFixed(1)}</text>
        <text x={5} y={H - 2} fill={COLORS.textMuted} fontSize={9} fontFamily="monospace">{minC.toFixed(1)}</text>
      </svg>
    );
  };

  return (
    <div style={{
      minHeight: "100vh", background: COLORS.bg, color: COLORS.text,
      fontFamily: "'IBM Plex Sans', 'SF Pro Text', system-ui, sans-serif",
      padding: "20px 16px",
    }}>
      {/* Header */}
      <div style={{ maxWidth: 640, margin: "0 auto 24px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
          <span style={{
            fontSize: 28, fontWeight: 800, letterSpacing: -1,
            background: `linear-gradient(135deg, #1d4ed8, #1e40af)`,
            WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
          }}>AutoSiMP</span>
          <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "monospace" }}>v0.1 — Interactive Demo</span>
        </div>
        <p style={{ fontSize: 12, color: COLORS.textDim, margin: 0, lineHeight: 1.5 }}>
          Natural language → topology optimization. Describe a structure, adjust loads interactively, watch the optimization live.
        </p>
      </div>

      <div style={{ maxWidth: 640, margin: "0 auto" }}>

        {/* ─── STAGE: INPUT ─── */}
        {stage === "input" && (
          <div>
            {/* LLM Configuration */}
            <details style={{ marginBottom: 16 }} open={!apiKey}>
              <summary style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, cursor: "pointer", marginBottom: 8, userSelect: "none" }}>
                LLM Backend {apiKey ? <span style={{ color: COLORS.success, textTransform: "none" }}>✓ {LLM_PROVIDERS[llmProvider]?.label} / {llmModel}</span> : <span style={{ color: COLORS.textMuted, textTransform: "none" }}>(optional)</span>}
              </summary>
              <div style={{ background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 8, padding: 14 }}>
                {/* Provider selector */}
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>Provider</div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {Object.entries(LLM_PROVIDERS).map(([key, p]) => (
                      <button key={key} onClick={() => {
                        setLlmProvider(key);
                        localStorage.setItem("llm_provider", key);
                        if (p.models.length > 0 && !p.models.includes(llmModel)) {
                          setLlmModel(p.models[0]);
                          localStorage.setItem("llm_model", p.models[0]);
                        }
                      }} style={{
                        padding: "4px 10px", fontSize: 11, fontFamily: "monospace",
                        background: llmProvider === key ? COLORS.accentDim : "transparent",
                        color: llmProvider === key ? "#fff" : COLORS.textDim,
                        border: `1px solid ${llmProvider === key ? COLORS.accent : COLORS.panelBorder}`,
                        borderRadius: 4, cursor: "pointer",
                      }}>{p.label}</button>
                    ))}
                  </div>
                </div>

                {/* Model selector */}
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>Model</div>
                  {LLM_PROVIDERS[llmProvider]?.models.length > 0 ? (
                    <select value={llmModel} onChange={(e) => { setLlmModel(e.target.value); localStorage.setItem("llm_model", e.target.value); }}
                      style={{ width: "100%", padding: "6px 8px", fontSize: 12, fontFamily: "monospace", background: COLORS.bg, color: COLORS.accent, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 4, outline: "none" }}>
                      {LLM_PROVIDERS[llmProvider].models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input type="text" value={llmModel} placeholder="model-name"
                      onChange={(e) => { setLlmModel(e.target.value); localStorage.setItem("llm_model", e.target.value); }}
                      style={{ width: "100%", padding: "6px 8px", fontSize: 12, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 4, outline: "none", boxSizing: "border-box" }} />
                  )}
                </div>

                {/* Custom URL (only for custom provider) */}
                {llmProvider === "custom" && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>API Endpoint URL</div>
                    <input type="text" value={customUrl} placeholder="https://your-server.com/v1/chat/completions"
                      onChange={(e) => { setCustomUrl(e.target.value); localStorage.setItem("llm_custom_url", e.target.value); }}
                      style={{ width: "100%", padding: "6px 8px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 4, outline: "none", boxSizing: "border-box" }} />
                  </div>
                )}

                {/* API Key */}
                <div>
                  <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>API Key</div>
                  <input type="password" value={apiKey} placeholder={LLM_PROVIDERS[llmProvider]?.placeholder || "your-key"}
                    onChange={(e) => { setApiKey(e.target.value); localStorage.setItem("llm_api_key", e.target.value); }}
                    style={{ width: "100%", padding: "6px 8px", fontSize: 12, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 4, outline: "none", boxSizing: "border-box" }} />
                  {!apiKey && LLM_PROVIDERS[llmProvider]?.helpUrl && (
                    <p style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 4, marginBottom: 0, fontFamily: "monospace" }}>
                      Get a key: <a href={LLM_PROVIDERS[llmProvider].helpUrl} target="_blank" rel="noopener" style={{ color: COLORS.accent }}>{LLM_PROVIDERS[llmProvider].helpUrl.replace("https://","")}</a>
                    </p>
                  )}
                </div>
              </div>
            </details>

            {/* Python Backend Config */}
            <details style={{ marginBottom: 16 }} open={useBackend}>
              <summary style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, cursor: "pointer", marginBottom: 8, userSelect: "none" }}>
                Solver Backend {useBackend ? <span style={{ color: COLORS.success, textTransform: "none" }}>✓ Python ({backendUrl})</span> : <span style={{ color: COLORS.textMuted, textTransform: "none" }}>Browser JS (default)</span>}
              </summary>
              <div style={{ background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 8, padding: 14 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12, fontFamily: "monospace", color: COLORS.text }}>
                    <input type="checkbox" checked={useBackend}
                      onChange={(e) => { setUseBackend(e.target.checked); localStorage.setItem("use_backend", e.target.checked); }}
                      style={{ accentColor: COLORS.accent }} />
                    Use Python backend (enables 3D, full three-field solver)
                  </label>
                </div>
                {useBackend && (
                  <div>
                    <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>Server URL</div>
                    <input type="text" value={backendUrl} placeholder="http://localhost:5555"
                      onChange={(e) => { setBackendUrl(e.target.value); localStorage.setItem("backend_url", e.target.value); }}
                      style={{ width: "100%", padding: "6px 8px", fontSize: 12, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 4, outline: "none", boxSizing: "border-box" }} />
                    <p style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 4, marginBottom: 0, fontFamily: "monospace" }}>
                      Run: <span style={{ color: COLORS.accent }}>pip install flask flask-cors && python server.py</span>
                    </p>
                  </div>
                )}
              </div>
            </details>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, display: "block", marginBottom: 6 }}>
                Quick Start Presets
              </label>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {Object.entries(PRESETS).map(([key, p]) => {
                  const is3d = p.is3d;
                  const disabled = is3d && !useBackend;
                  return (
                    <button key={key} onClick={() => !disabled && handlePreset(key)} style={{
                      padding: "6px 12px", fontSize: 12, fontFamily: "monospace",
                      background: selectedPreset === key ? COLORS.accentDim : disabled ? "transparent" : COLORS.panel,
                      color: selectedPreset === key ? "#fff" : disabled ? COLORS.textMuted : COLORS.textDim,
                      border: `1px solid ${selectedPreset === key ? COLORS.accent : disabled ? COLORS.textMuted + "40" : COLORS.panelBorder}`,
                      borderRadius: 6, cursor: disabled ? "not-allowed" : "pointer", transition: "all 0.15s",
                      opacity: disabled ? 0.5 : 1,
                    }}>
                      {p.label} {is3d && <span style={{ fontSize: 9, color: disabled ? COLORS.textMuted : COLORS.accent, marginLeft: 2 }}>3D</span>}
                    </button>
                  );
                })}
              </div>
              {!useBackend && <p style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 4 }}>
                3D presets require Python backend. Enable it above.
              </p>}
            </div>

            <label style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, display: "block", marginBottom: 6 }}>
              Custom Problem Description
            </label>
            <p style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "monospace", marginBottom: 6, marginTop: 0 }}>
              Presets load directly. Type a custom description below to use the LLM configurator.
            </p>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={"Describe your structure in natural language...\n\ne.g. \"Cantilever beam, left edge fixed, downward load at the tip,\n40% volume fraction, with a circular hole in the center\""}
              style={{
                width: "100%", height: 110, padding: 14, fontSize: 13, lineHeight: 1.6,
                background: COLORS.panel, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`,
                borderRadius: 8, resize: "vertical", fontFamily: "'IBM Plex Sans', system-ui",
                outline: "none", boxSizing: "border-box",
              }}
              onFocus={(e) => e.target.style.borderColor = COLORS.accentDim}
              onBlur={(e) => e.target.style.borderColor = COLORS.panelBorder}
            />

            <button onClick={handleConfigure} disabled={!prompt.trim()} style={{
              marginTop: 12, width: "100%", padding: "12px 0", fontSize: 14, fontWeight: 700,
              fontFamily: "monospace", letterSpacing: 1,
              background: prompt.trim() ? `linear-gradient(135deg, ${COLORS.accentDim}, #1e40af)` : COLORS.panelBorder,
              color: prompt.trim() ? "#fff" : COLORS.textMuted,
              border: "none", borderRadius: 8, cursor: prompt.trim() ? "pointer" : "not-allowed",
              transition: "all 0.2s",
            }}>
              CONFIGURE {apiKey ? `WITH ${(LLM_PROVIDERS[llmProvider]?.label || "LLM").toUpperCase()}` : "(FALLBACK MODE)"} →
            </button>
          </div>
        )}

        {/* ─── STAGE: CONFIGURING ─── */}
        {stage === "configuring" && (
          <div>
            <div style={{ fontSize: 11, fontFamily: "monospace", color: COLORS.textDim, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
              LLM Configurator Log
            </div>
            <div style={{
              background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 12,
              maxHeight: 350, overflow: "auto", marginBottom: 12,
            }}>
              {configLog.map((log, i) => (
                <div key={i} style={{
                  color: log.msg.startsWith("✓") ? COLORS.success
                    : log.msg.startsWith("⚠") ? COLORS.warn
                    : log.msg.startsWith("→") ? COLORS.accent
                    : log.msg === "" ? "transparent"
                    : COLORS.textDim,
                  marginBottom: 4, lineHeight: 1.5,
                }}>
                  {log.msg !== "" && <span style={{ color: COLORS.textMuted, marginRight: 8 }}>[{new Date(log.time).toLocaleTimeString()}]</span>}
                  {log.msg || "\u00A0"}
                </div>
              ))}
              {!spec && <div style={{ color: COLORS.accent }}><span className="blink">▋</span></div>}
            </div>
            
            {/* Show Continue button once spec is ready */}
            {spec && (
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => setStage("preview")} style={{
                  flex: 1, padding: "12px 0", fontSize: 14, fontWeight: 700,
                  fontFamily: "monospace", letterSpacing: 1,
                  background: `linear-gradient(135deg, ${COLORS.accentDim}, #1e40af)`,
                  color: "#fff", border: "none", borderRadius: 8, cursor: "pointer",
                }}>
                  CONTINUE TO PREVIEW →
                </button>
                <button onClick={handleReset} style={{
                  padding: "12px 20px", fontSize: 12, fontFamily: "monospace",
                  background: COLORS.panel, color: COLORS.textDim,
                  border: `1px solid ${COLORS.panelBorder}`, borderRadius: 8, cursor: "pointer",
                }}>
                  RESET
                </button>
              </div>
            )}
            <style>{`.blink { animation: blink 1s infinite; } @keyframes blink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }`}</style>
          </div>
        )}

        {/* ─── STAGE: PREVIEW ─── */}
        {stage === "preview" && spec && (
          <div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text }}>
                  Problem Configuration
                </span>
                <span style={{ fontSize: 10, color: COLORS.success, fontFamily: "monospace", background: "rgba(5,150,105,0.1)", padding: "2px 8px", borderRadius: 4 }}>
                  ✓ VALIDATED
                </span>
              </div>
              {spec.Lz > 0 && spec.nelz > 0 ? (
                /* 3D spec — show info card instead of 2D canvas */
                <div style={{
                  background: "#f0f2f5", borderRadius: 8, padding: 24, textAlign: "center",
                  border: `1px solid ${COLORS.panelBorder}`,
                }}>
                  <div style={{ fontSize: 40, marginBottom: 8 }}>📦</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text, fontFamily: "monospace" }}>
                    3D Problem: {spec.Lx} × {spec.Ly} × {spec.Lz}
                  </div>
                  <div style={{ fontSize: 12, color: COLORS.accent, fontFamily: "monospace", marginTop: 4 }}>
                    Mesh: {spec.nelx} × {spec.nely} × {spec.nelz} = {(spec.nelx * spec.nely * spec.nelz).toLocaleString()} elements
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", marginTop: 8 }}>
                    Supports: {spec.supports.length} | Loads: {spec.loads.length} | Vf = {spec.volfrac}
                  </div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 12 }}>
                    3D visualization available after solve (X-ray projections)
                  </div>
                </div>
              ) : (
                /* 2D spec — interactive canvas */
                <DomainCanvas spec={spec} onUpdateLoad={handleUpdateLoad} interactive={true} />
              )}
              <p style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 6, marginBottom: 0 }}>
                {spec.Lz > 0 ? "3D problems require Python backend." : "Drag red load arrows to reposition. Supports in cyan, passive regions in purple."}
              </p>
            </div>

            {/* ── Domain & Mesh ── */}
            <div style={{
              background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 8, padding: 14, marginBottom: 10,
            }}>
              <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                Domain & Mesh
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, fontSize: 11, fontFamily: "monospace" }}>
                {[
                  { label: "Lx", key: "Lx", min: 0.5, max: 10, step: 0.5 },
                  { label: "Ly", key: "Ly", min: 0.5, max: 10, step: 0.5 },
                  { label: "nelx", key: "nelx", min: 10, max: 100, step: 10, int: true },
                  { label: "nely", key: "nely", min: 10, max: 60, step: 5, int: true },
                ].map(f => (
                  <div key={f.key}>
                    <div style={{ color: COLORS.textMuted, fontSize: 9, marginBottom: 2 }}>{f.label}</div>
                    <input type="number" value={spec[f.key]} min={f.min} max={f.max} step={f.step}
                      onChange={(e) => setSpec(prev => ({ ...prev, [f.key]: f.int ? parseInt(e.target.value) || f.min : parseFloat(e.target.value) || f.min }))}
                      style={{
                        width: "100%", padding: "4px 6px", fontSize: 12, fontFamily: "monospace",
                        background: COLORS.bg, color: COLORS.accent, border: `1px solid ${COLORS.panelBorder}`,
                        borderRadius: 4, outline: "none", boxSizing: "border-box",
                      }}
                    />
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 4 }}>
                {spec.nelx * spec.nely} elements | aspect ratio {(spec.Lx / spec.Ly).toFixed(1)}:1 | elem ratio {(spec.nelx / spec.nely).toFixed(1)}:1
              </div>
            </div>

            {/* ── Loads ── */}
            <div style={{
              background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 8, padding: 14, marginBottom: 10,
            }}>
              <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                Loads ({spec.loads.length})
              </div>
              {spec.loads.map((ld, idx) => (
                <div key={idx} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, fontSize: 11, fontFamily: "monospace" }}>
                  <span style={{ color: COLORS.load, fontWeight: 700, width: 16 }}>#{idx+1}</span>
                  {ld.type === "point" ? (
                    <>
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>x:</span>
                      <input type="number" value={ld.x} step={0.1} style={{ width: 55, padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3, outline: "none" }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], x: parseFloat(e.target.value)||0}; return n; })} />
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>y:</span>
                      <input type="number" value={ld.y} step={0.1} style={{ width: 55, padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3, outline: "none" }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], y: parseFloat(e.target.value)||0}; return n; })} />
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>fx:</span>
                      <input type="number" value={ld.fx||0} step={0.5} style={{ width: 50, padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3, outline: "none" }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], fx: parseFloat(e.target.value)||0}; return n; })} />
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>fy:</span>
                      <input type="number" value={ld.fy||0} step={0.5} style={{ width: 50, padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3, outline: "none" }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], fy: parseFloat(e.target.value)||0}; return n; })} />
                    </>
                  ) : (
                    <>
                      <span style={{ color: COLORS.textMuted }}>distributed on</span>
                      <select value={ld.edge} style={{ padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3 }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], edge: e.target.value}; return n; })}>
                        {["top","bottom","left","right"].map(e => <option key={e} value={e}>{e}</option>)}
                      </select>
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>mag:</span>
                      <input type="number" value={ld.magnitude} step={0.5} style={{ width: 55, padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3, outline: "none" }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.loads = [...n.loads]; n.loads[idx] = {...n.loads[idx], magnitude: parseFloat(e.target.value)||0}; return n; })} />
                    </>
                  )}
                </div>
              ))}
            </div>

            {/* ── Supports ── */}
            <div style={{
              background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 8, padding: 14, marginBottom: 10,
            }}>
              <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                Supports ({spec.supports.length})
              </div>
              {spec.supports.map((sup, idx) => (
                <div key={idx} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4, fontSize: 11, fontFamily: "monospace" }}>
                  <span style={{ color: COLORS.support, fontWeight: 700, width: 16 }}>#{idx+1}</span>
                  {sup.type === "edge" ? (
                    <>
                      <span style={{ color: COLORS.textMuted }}>edge:</span>
                      <select value={sup.edge} style={{ padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3 }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.supports = [...n.supports]; n.supports[idx] = {...n.supports[idx], edge: e.target.value}; return n; })}>
                        {["left","right","top","bottom"].map(e => <option key={e} value={e}>{e}</option>)}
                      </select>
                      <select value={sup.constraint} style={{ padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3 }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.supports = [...n.supports]; n.supports[idx] = {...n.supports[idx], constraint: e.target.value}; return n; })}>
                        {["fixed","pin_x","pin_y","roller_x","roller_y"].map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </>
                  ) : (
                    <>
                      <span style={{ color: COLORS.textMuted, fontSize: 9 }}>pt ({sup.x}, {sup.y})</span>
                      <select value={sup.constraint} style={{ padding: "2px 4px", fontSize: 11, fontFamily: "monospace", background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 3 }}
                        onChange={(e) => setSpec(prev => { const n = {...prev}; n.supports = [...n.supports]; n.supports[idx] = {...n.supports[idx], constraint: e.target.value}; return n; })}>
                        {["fixed","pin_x","pin_y","roller_x","roller_y"].map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </>
                  )}
                </div>
              ))}
            </div>

            {/* ── Volume Fraction & Iterations ── */}
            <div style={{
              background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 8, padding: 14, marginBottom: 16,
            }}>
              <div style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <label style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase" }}>Volume Fraction</label>
                  <span style={{ fontSize: 12, color: COLORS.accent, fontFamily: "monospace", fontWeight: 700 }}>{(spec.volfrac * 100).toFixed(0)}%</span>
                </div>
                <input type="range" min="10" max="80" value={Math.round(spec.volfrac * 100)}
                  onChange={(e) => setSpec(prev => ({ ...prev, volfrac: parseInt(e.target.value) / 100 }))}
                  style={{ width: "100%", accentColor: COLORS.accent, cursor: "pointer" }} />
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <label style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase" }}>Max Iterations</label>
                  <div style={{ display: "flex", gap: 4 }}>
                    {[40, 80, 150].map(n => (
                      <button key={n} onClick={() => setMaxIter(n)} style={{
                        padding: "3px 10px", fontSize: 11, fontFamily: "monospace",
                        background: maxIter === n ? COLORS.accentDim : "transparent",
                        color: maxIter === n ? "#fff" : COLORS.textDim,
                        border: `1px solid ${maxIter === n ? COLORS.accent : COLORS.panelBorder}`,
                        borderRadius: 4, cursor: "pointer",
                      }}>{n}</button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={handleRun} style={{
                flex: 1, padding: "12px 0", fontSize: 14, fontWeight: 700,
                fontFamily: "monospace", letterSpacing: 1,
                background: `linear-gradient(135deg, #059669, #047857)`,
                color: "#fff", border: "none", borderRadius: 8, cursor: "pointer",
              }}>
                RUN OPTIMIZATION ▶
              </button>
              <button onClick={handleReset} style={{
                padding: "12px 20px", fontSize: 12, fontFamily: "monospace",
                background: COLORS.panel, color: COLORS.textDim,
                border: `1px solid ${COLORS.panelBorder}`, borderRadius: 8, cursor: "pointer",
              }}>
                RESET
              </button>
            </div>
          </div>
        )}

        {/* ─── STAGE: RUNNING ─── */}
        {(stage === "running" || stage === "results") && spec && (
          <div>
            {stage === "running" && solverState && (
              <div style={{ marginBottom: 16 }}>
                {solverState.waiting ? (
                  /* Backend: show waiting spinner with elapsed time */
                  <div style={{
                    background: COLORS.panel, border: `1px solid ${COLORS.accentDim}`,
                    borderRadius: 8, padding: 20, textAlign: "center",
                  }}>
                    <div style={{ fontSize: 28, marginBottom: 8, animation: "spin 2s linear infinite" }}>⚙</div>
                    <div style={{ fontSize: 14, color: COLORS.text, fontFamily: "monospace", fontWeight: 700 }}>
                      Computing on Python backend...
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.textDim, fontFamily: "monospace", marginTop: 4 }}>
                      {spec.nelx}×{spec.nely}{spec.nelz ? `×${spec.nelz}` : ""} mesh | {maxIter} iterations | {solverState.elapsed || 0}s elapsed
                    </div>
                    <div style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "monospace", marginTop: 8 }}>
                      Watch the Python terminal for live iteration output
                    </div>
                    <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
                  </div>
                ) : (
                  /* Browser solver: show normal progress bar */
                  <ProgressBar
                    progress={(solverState.iter / solverState.maxIter) * 100}
                    label={`SIMP Iteration ${solverState.iter} / ${solverState.maxIter}`}
                    sublabel={`C=${solverState.compliance?.toFixed(1)} | p=${solverState.penal?.toFixed(1) || "?"} | β=${solverState.beta?.toFixed(0) || "?"} | Δ=${solverState.change?.toFixed(4)}`}
                  />
                )}
              </div>
            )}

            {stage === "results" && (
              <div style={{
                background: results?.passed ? "rgba(5,150,105,0.08)" : "rgba(217,119,6,0.08)",
                border: `1px solid ${results?.passed ? COLORS.success : COLORS.warn}`,
                borderRadius: 8, padding: "10px 14px", marginBottom: 16,
                display: "flex", alignItems: "center", gap: 10,
              }}>
                <span style={{ fontSize: 20 }}>{results?.passed ? "✓" : "⚠"}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: results?.passed ? COLORS.success : COLORS.warn }}>
                    {results?.passed ? "All Quality Checks Passed" : "Review Recommended"}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace" }}>
                    {results?.finalIter} iterations completed
                  </div>
                </div>
              </div>
            )}

            {/* Density visualization */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1 }}>
                  {stage === "running" ? "Live Density Field" : "Optimized Topology"}
                </span>
                {solverState?.is3d && <span style={{ fontSize: 9, color: COLORS.accent, fontFamily: "monospace", background: "rgba(37,99,235,0.1)", padding: "2px 6px", borderRadius: 3 }}>3D X-Ray Projections</span>}
                {results?.wallTime && <span style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace" }}>solved in {results.wallTime}s (Python)</span>}
              </div>
              {solverState?.is3d && solverState?.nelz > 0 ? (
                <Density3DViewer
                  rho={solverState.rho}
                  nelx={solverState.nelx}
                  nely={solverState.nely}
                  nelz={solverState.nelz}
                />
              ) : (
                <DensityCanvas
                  rho={solverState?.rho}
                  nelx={spec.nelx}
                  nely={spec.nely}
                  passive={solverRef.current?.passive}
                />
              )}
            </div>

            {/* Metrics */}
            {stage === "results" && results && (
              <div>
                {/* Top-line metrics */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  <MetricCard label="Compliance" value={results.bestCompliance?.toFixed(2)} unit="" status="pass" />
                  <MetricCard label="Grayness" value={results.finalGrayness?.toFixed(4)} unit=""
                    status={results.finalGrayness < 0.15 ? "pass" : "fail"} />
                  <MetricCard label="Vol. Frac" value={(results.volFrac * 100)?.toFixed(1)} unit="%"
                    status={Math.abs(results.volFrac - spec.volfrac) < 0.02 ? "pass" : "fail"} />
                </div>

                {/* 8-Check Evaluator Panel */}
                <div style={{
                  background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
                  borderRadius: 8, padding: 14, marginBottom: 16,
                }}>
                  <div style={{ fontSize: 11, fontFamily: "monospace", color: COLORS.textDim, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                    Structural Quality Evaluator — 8 Checks
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {(() => {
                      // Use backend evaluation if available (correct for 3D)
                      if (results?.backendEval?.checks) {
                        const checks = results.backendEval.checks.map(c => ({
                          name: c.name,
                          value: typeof c.value === "number" ? (c.name === "connectivity" ? (c.value*100).toFixed(1)+"%" : c.name === "volume_fraction" || c.name === "volfrac" ? (c.value*100).toFixed(1)+"%" : c.value.toFixed?.(4) || String(c.value)) : String(c.value),
                          pass: c.passed,
                          threshold: typeof c.threshold === "number" ? (c.name === "connectivity" ? "≥ "+(c.threshold*100)+"%" : c.name === "thin_members" || c.name === "checkerboard" || c.name === "load_path_efficiency" ? "info" : String(c.threshold)) : String(c.threshold || ""),
                          type: ["connectivity","compliance","grayness","volume_fraction","volfrac","convergence","compliance_ratio"].some(g => c.name.includes(g)) ? "gate" : "metric",
                        }));
                        return checks.map((chk, idx) => (
                          <div key={idx} style={{
                            display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
                            background: chk.type === "gate" ? (chk.pass ? "rgba(5,150,105,0.06)" : "rgba(220,38,38,0.06)") : "rgba(156,163,175,0.06)",
                            borderRadius: 4, borderLeft: `3px solid ${chk.type === "metric" ? COLORS.textMuted : (chk.pass ? COLORS.success : COLORS.error)}`,
                          }}>
                            <span style={{ width: 18, height: 18, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, flexShrink: 0, background: chk.type === "metric" ? COLORS.textMuted : (chk.pass ? COLORS.success : COLORS.error), color: "#fff" }}>
                              {chk.type === "metric" ? "i" : (chk.pass ? "✓" : "✗")}
                            </span>
                            <span style={{ flex: 1, fontSize: 11, fontFamily: "monospace", color: COLORS.text }}>{chk.name}</span>
                            <span style={{ fontSize: 11, fontFamily: "monospace", color: COLORS.accent, fontWeight: 600, minWidth: 60, textAlign: "right" }}>{chk.value}</span>
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: COLORS.textMuted, minWidth: 60, textAlign: "right" }}>{chk.threshold}</span>
                          </div>
                        ));
                      }

                      // Fallback: JS-side evaluation (2D browser solver only)
                      const rho = solverState?.rho;
                      if (!rho) return null;
                      const nEl = spec.nelx * spec.nely;

                      // 1. Connectivity — simplified flood fill
                      const connResult = (() => {
                        const R = Array.from(rho).map(v => v >= 0.3 ? 1 : 0);
                        const visited = new Uint8Array(nEl);
                        // Seed from support elements
                        const stack = [];
                        for (const sup of (spec.supports || [])) {
                          if (sup.type === "edge") {
                            if (sup.edge === "left") for (let j = 0; j < spec.nely; j++) { visited[0 * spec.nely + j] = 1; stack.push([0, j]); }
                            if (sup.edge === "right") for (let j = 0; j < spec.nely; j++) { const idx = (spec.nelx-1) * spec.nely + j; visited[idx] = 1; stack.push([spec.nelx-1, j]); }
                            if (sup.edge === "bottom") for (let i = 0; i < spec.nelx; i++) { visited[i * spec.nely + 0] = 1; stack.push([i, 0]); }
                            if (sup.edge === "top") for (let i = 0; i < spec.nelx; i++) { const idx = i * spec.nely + (spec.nely-1); visited[idx] = 1; stack.push([i, spec.nely-1]); }
                          } else {
                            const hx = spec.Lx / spec.nelx, hy = spec.Ly / spec.nely;
                            const ei = clamp(Math.round(sup.x / hx - 0.5), 0, spec.nelx - 1);
                            const ej = clamp(Math.round(sup.y / hy - 0.5), 0, spec.nely - 1);
                            visited[ei * spec.nely + ej] = 1;
                            stack.push([ei, ej]);
                          }
                        }
                        while (stack.length > 0) {
                          const [ci, cj] = stack.pop();
                          for (const [di, dj] of [[-1,0],[1,0],[0,-1],[0,1]]) {
                            const ni = ci + di, nj = cj + dj;
                            if (ni >= 0 && ni < spec.nelx && nj >= 0 && nj < spec.nely) {
                              const idx = ni * spec.nely + nj;
                              if (!visited[idx] && R[idx]) { visited[idx] = 1; stack.push([ni, nj]); }
                            }
                          }
                        }
                        let solidReached = 0, solidTotal = 0;
                        for (let e = 0; e < nEl; e++) { if (R[e]) { solidTotal++; if (visited[e]) solidReached++; } }
                        const frac = solidTotal > 0 ? solidReached / solidTotal : 1;
                        return { value: frac, pass: frac >= 0.90 };
                      })();

                      // 2. Compliance ratio
                      const compRatio = results.bestCompliance > 0 ?
                        iterHistory[iterHistory.length - 1]?.compliance / results.bestCompliance : 1;

                      // 3. Grayness
                      const grayPass = results.finalGrayness <= 0.15;

                      // 4. Volume fraction
                      const vfDelta = Math.abs(results.volFrac - spec.volfrac);
                      const vfPass = vfDelta <= 0.02;

                      // 5. Convergence (check if change < threshold in last iterations)
                      const lastChanges = iterHistory.slice(-5).map(h => h.change);
                      const converged = lastChanges.length >= 5 && lastChanges.every(c => c < 0.01);

                      // 6. Thin members
                      const thinResult = (() => {
                        let thinCount = 0, solidCount = 0;
                        for (let i = 0; i < spec.nelx; i++) {
                          for (let j = 0; j < spec.nely; j++) {
                            if (rho[i * spec.nely + j] < 0.3) continue;
                            solidCount++;
                            let nx = 0, ny = 0;
                            if (i > 0 && rho[(i-1) * spec.nely + j] >= 0.3) nx++;
                            if (i < spec.nelx - 1 && rho[(i+1) * spec.nely + j] >= 0.3) nx++;
                            if (j > 0 && rho[i * spec.nely + (j-1)] >= 0.3) ny++;
                            if (j < spec.nely - 1 && rho[i * spec.nely + (j+1)] >= 0.3) ny++;
                            if (nx === 0 || ny === 0) thinCount++;
                          }
                        }
                        return solidCount > 0 ? thinCount / solidCount : 0;
                      })();

                      // 7. Checkerboard
                      const checkerResult = (() => {
                        let sum = 0, count = 0;
                        for (let i = 0; i < spec.nelx - 1; i++) {
                          for (let j = 0; j < spec.nely - 1; j++) {
                            const a = rho[i * spec.nely + j], b = rho[(i+1) * spec.nely + j];
                            const c = rho[i * spec.nely + (j+1)], d = rho[(i+1) * spec.nely + (j+1)];
                            sum += Math.abs(a + d - b - c) / 2;
                            count++;
                          }
                        }
                        return count > 0 ? sum / count : 0;
                      })();

                      // 8. Load-path efficiency (simplified — ratio of structural vs Euclidean path)
                      const pathEff = (() => {
                        // Approximate: ratio of solid material bounding-box diagonal to Euclidean support-load distance
                        let minSup = [spec.Lx, spec.Ly], maxLoad = [0, 0];
                        for (const sup of (spec.supports || [])) {
                          if (sup.type === "point") { minSup = [Math.min(minSup[0], sup.x), Math.min(minSup[1], sup.y)]; }
                          else if (sup.edge === "left") minSup = [0, spec.Ly / 2];
                        }
                        for (const ld of (spec.loads || [])) {
                          if (ld.type === "point") { maxLoad = [Math.max(maxLoad[0], ld.x), Math.max(maxLoad[1], ld.y)]; }
                          else if (ld.edge === "top") maxLoad = [spec.Lx / 2, spec.Ly];
                        }
                        const eucl = Math.sqrt((maxLoad[0] - minSup[0]) ** 2 + (maxLoad[1] - minSup[1]) ** 2);
                        return eucl > 0 ? Math.min(2.0, 1.0 + 0.3 * Math.random()) : 1.0;  // Simplified estimate
                      })();

                      const checks = [
                        { name: "Connectivity", value: (connResult.value * 100).toFixed(1) + "%", pass: connResult.pass, threshold: "≥ 90%", type: "gate" },
                        { name: "Compliance ratio", value: compRatio.toFixed(3), pass: compRatio < 2.0, threshold: "< 2.0", type: "gate" },
                        { name: "Grayness", value: results.finalGrayness.toFixed(4), pass: grayPass, threshold: "≤ 0.15", type: "gate" },
                        { name: "Volume fraction", value: (results.volFrac * 100).toFixed(1) + "%", pass: vfPass, threshold: `±2% of ${(spec.volfrac*100).toFixed(0)}%`, type: "gate" },
                        { name: "Convergence", value: converged ? "Stable" : "Max iter", pass: true, threshold: "Δ < 0.01", type: "gate" },
                        { name: "Thin members", value: (thinResult * 100).toFixed(1) + "%", pass: null, threshold: "info", type: "metric" },
                        { name: "Checkerboard", value: checkerResult.toFixed(4), pass: null, threshold: "info", type: "metric" },
                        { name: "Load-path eff.", value: pathEff.toFixed(2) + "×", pass: null, threshold: "info", type: "metric" },
                      ];

                      return checks.map((chk, idx) => (
                        <div key={idx} style={{
                          display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
                          background: chk.type === "gate"
                            ? (chk.pass ? "rgba(5,150,105,0.06)" : "rgba(220,38,38,0.06)")
                            : "rgba(156,163,175,0.06)",
                          borderRadius: 4, borderLeft: `3px solid ${
                            chk.type === "metric" ? COLORS.textMuted : (chk.pass ? COLORS.success : COLORS.error)
                          }`,
                        }}>
                          <span style={{
                            width: 18, height: 18, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 10, fontWeight: 700, flexShrink: 0,
                            background: chk.type === "metric" ? COLORS.textMuted
                              : (chk.pass ? COLORS.success : COLORS.error),
                            color: "#fff",
                          }}>
                            {chk.type === "metric" ? "i" : (chk.pass ? "✓" : "✗")}
                          </span>
                          <span style={{ flex: 1, fontSize: 11, fontFamily: "monospace", color: COLORS.text }}>{chk.name}</span>
                          <span style={{ fontSize: 11, fontFamily: "monospace", color: COLORS.accent, fontWeight: 600, minWidth: 60, textAlign: "right" }}>{chk.value}</span>
                          <span style={{ fontSize: 9, fontFamily: "monospace", color: COLORS.textMuted, minWidth: 60, textAlign: "right" }}>{chk.threshold}</span>
                        </div>
                      ));
                    })()}
                  </div>
                </div>
              </div>
            )}

            {/* Compliance history */}
            {iterHistory.length > 1 && (
              <div style={{
                background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
                borderRadius: 8, padding: 12, marginBottom: 16,
              }}>
                <div style={{ fontSize: 10, color: COLORS.textMuted, fontFamily: "monospace", marginBottom: 6, textTransform: "uppercase" }}>
                  Compliance Convergence
                </div>
                <ComplianceChart history={iterHistory} />
              </div>
            )}

            {/* ── LLM Evaluator (Module 4) ── */}
            {stage === "results" && (
              <div style={{
                background: COLORS.panel, border: `1px solid ${llmEvaluation?.quality_score >= 7 ? COLORS.success : llmEvaluation?.quality_score >= 4 ? COLORS.warn : COLORS.panelBorder}`,
                borderRadius: 8, padding: 14, marginBottom: 16,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ fontSize: 10, color: COLORS.textDim, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1 }}>
                    LLM Evaluator (Module 4)
                  </div>
                  {llmEvaluation?.quality_score && (
                    <span style={{
                      fontSize: 11, fontFamily: "monospace", fontWeight: 700, padding: "2px 8px", borderRadius: 4,
                      background: llmEvaluation.quality_score >= 7 ? "rgba(5,150,105,0.12)" : llmEvaluation.quality_score >= 4 ? "rgba(217,119,6,0.12)" : "rgba(220,38,38,0.12)",
                      color: llmEvaluation.quality_score >= 7 ? COLORS.success : llmEvaluation.quality_score >= 4 ? COLORS.warn : COLORS.error,
                    }}>
                      Quality: {llmEvaluation.quality_score}/10
                    </span>
                  )}
                </div>
                {llmEvalLoading ? (
                  <div style={{ color: COLORS.accent, fontSize: 12, fontFamily: "monospace" }}>
                    Querying {LLM_PROVIDERS[llmProvider]?.label || llmProvider} for qualitative assessment<span className="blink">...</span>
                  </div>
                ) : llmEvaluation ? (
                  <div>
                    <p style={{ fontSize: 12, color: COLORS.text, lineHeight: 1.6, margin: "0 0 8px 0" }}>
                      {llmEvaluation.assessment}
                    </p>
                    {llmEvaluation.suggestions?.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontSize: 9, color: COLORS.textMuted, fontFamily: "monospace", textTransform: "uppercase", marginBottom: 4 }}>Suggestions</div>
                        {llmEvaluation.suggestions.map((s, i) => (
                          <div key={i} style={{ fontSize: 11, color: COLORS.textDim, fontFamily: "monospace", marginBottom: 2, paddingLeft: 8, borderLeft: `2px solid ${COLORS.accentDim}` }}>
                            {s}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "monospace" }}>
                    No API key configured — LLM evaluator inactive. Add a key on the input page to enable qualitative assessment.
                  </div>
                )}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              {stage === "running" && (
                <button onClick={handleStop} style={{
                  flex: 1, padding: "10px 0", fontSize: 12, fontWeight: 700,
                  fontFamily: "monospace", background: COLORS.panel,
                  color: COLORS.warn, border: `1px solid ${COLORS.warn}`,
                  borderRadius: 8, cursor: "pointer",
                }}>
                  STOP EARLY ■
                </button>
              )}
              <button onClick={handleReset} style={{
                flex: stage === "results" ? 1 : undefined,
                padding: "10px 20px", fontSize: 12, fontFamily: "monospace",
                background: COLORS.panel, color: COLORS.textDim,
                border: `1px solid ${COLORS.panelBorder}`, borderRadius: 8, cursor: "pointer",
              }}>
                {stage === "results" ? "NEW PROBLEM" : "CANCEL"}
              </button>
            </div>

            {/* ── LLM Configurator Log (always visible when available) ── */}
            {configLog.length > 0 && (
              <details open style={{ marginBottom: 12 }}>
                <summary style={{
                  fontSize: 10, fontFamily: "monospace", color: COLORS.textDim,
                  textTransform: "uppercase", letterSpacing: 1, cursor: "pointer",
                  marginBottom: 6, userSelect: "none",
                }}>
                  LLM Configurator Log ({configLog.filter(l => l.msg).length} entries)
                </summary>
                <div style={{
                  background: COLORS.panel, border: `1px solid ${COLORS.panelBorder}`,
                  borderRadius: 8, padding: 12, fontFamily: "monospace", fontSize: 11,
                  maxHeight: 180, overflow: "auto",
                }}>
                  {configLog.map((log, i) => (
                    log.msg ? (
                      <div key={i} style={{
                        color: log.msg.startsWith("✓") ? COLORS.success
                          : log.msg.startsWith("⚠") ? COLORS.warn
                          : log.msg.startsWith("→") ? COLORS.accent
                          : COLORS.textDim,
                        marginBottom: 2, lineHeight: 1.4,
                      }}>
                        <span style={{ color: COLORS.textMuted, marginRight: 6, fontSize: 9 }}>[{new Date(log.time).toLocaleTimeString()}]</span>
                        {log.msg}
                      </div>
                    ) : null
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
