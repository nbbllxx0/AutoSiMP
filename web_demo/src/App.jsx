import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_AUTOSIMP_API || "http://localhost:5555";

const PRESETS = {
  cantilever: {
    label: "Cantilever",
    prompt: "Cantilever beam, left edge fixed, downward point load at mid-right edge, 50% volume fraction",
    spec: {
      Lx: 2,
      Ly: 1,
      nelx: 60,
      nely: 30,
      volfrac: 0.5,
      supports: [{ type: "edge", edge: "left", constraint: "fixed" }],
      loads: [{ type: "point", x: 2, y: 0.5, fx: 0, fy: -1, fz: 0 }],
      passive_regions: [],
    },
  },
  mbb: {
    label: "MBB Beam",
    prompt: "MBB beam, symmetry on the left edge, roller at bottom-right, downward load at top-left, 50% volume",
    spec: {
      Lx: 3,
      Ly: 1,
      nelx: 90,
      nely: 30,
      volfrac: 0.5,
      supports: [
        { type: "edge", edge: "left", constraint: "pin_x" },
        { type: "point", x: 3, y: 0, constraint: "pin_y" },
      ],
      loads: [{ type: "point", x: 0, y: 1, fx: 0, fy: -1, fz: 0 }],
      passive_regions: [],
    },
  },
  bridge: {
    label: "Bridge",
    prompt: "Bridge, pinned supports at both bottom corners, distributed downward load on top, 30% volume fraction",
    spec: {
      Lx: 4,
      Ly: 1,
      nelx: 120,
      nely: 30,
      volfrac: 0.3,
      supports: [
        { type: "point", x: 0, y: 0, constraint: "fixed" },
        { type: "point", x: 4, y: 0, constraint: "pin_y" },
      ],
      loads: [{ type: "distributed", edge: "top", magnitude: -1 }],
      passive_regions: [],
    },
  },
  hole: {
    label: "Cantilever + Hole",
    prompt: "Cantilever beam, left edge fixed, downward load at mid-right, circular hole at center, 40% volume",
    spec: {
      Lx: 2,
      Ly: 1,
      nelx: 80,
      nely: 40,
      volfrac: 0.4,
      supports: [{ type: "edge", edge: "left", constraint: "fixed" }],
      loads: [{ type: "point", x: 2, y: 0.5, fx: 0, fy: -1, fz: 0 }],
      passive_regions: [{ type: "circle", cx: 1, cy: 0.5, radius: 0.15, kind: "void" }],
    },
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function fallbackSpec(prompt) {
  const lower = prompt.toLowerCase();
  if (lower.includes("mbb")) return clone(PRESETS.mbb.spec);
  if (lower.includes("bridge")) return clone(PRESETS.bridge.spec);
  if (lower.includes("hole") || lower.includes("pipe")) return clone(PRESETS.hole.spec);
  return clone(PRESETS.cantilever.spec);
}

function ensureSpec(spec) {
  const next = clone(spec);
  next.Lx = Math.max(0.5, Number(next.Lx || 2));
  next.Ly = Math.max(0.5, Number(next.Ly || 1));
  next.nelx = Math.max(10, Math.min(160, Number(next.nelx || 60)));
  next.nely = Math.max(10, Math.min(100, Number(next.nely || 30)));
  next.volfrac = Math.max(0.1, Math.min(0.9, Number(next.volfrac || 0.5)));
  next.supports = Array.isArray(next.supports) && next.supports.length
    ? next.supports
    : [{ type: "edge", edge: "left", constraint: "fixed" }];
  next.loads = Array.isArray(next.loads) && next.loads.length
    ? next.loads
    : [{ type: "point", x: next.Lx, y: next.Ly / 2, fx: 0, fy: -1, fz: 0 }];
  next.passive_regions = Array.isArray(next.passive_regions) ? next.passive_regions : [];
  return next;
}

function DomainCanvas({ spec, onMoveLoad }) {
  const ref = useRef(null);
  const [drag, setDrag] = useState(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !spec) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = 760;
    const h = 310;
    const pad = 42;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = "100%";
    canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const sx = (x) => pad + (x / spec.Lx) * (w - 2 * pad);
    const sy = (y) => h - pad - (y / spec.Ly) * (h - 2 * pad);

    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1;
    ctx.strokeRect(sx(0), sy(spec.Ly), sx(spec.Lx) - sx(0), sy(0) - sy(spec.Ly));

    ctx.strokeStyle = "#1e293b";
    const gx = Math.max(1, Math.ceil(spec.nelx / 30));
    const gy = Math.max(1, Math.ceil(spec.nely / 15));
    for (let i = 0; i <= spec.nelx; i += gx) {
      const x = sx((i / spec.nelx) * spec.Lx);
      ctx.beginPath();
      ctx.moveTo(x, sy(0));
      ctx.lineTo(x, sy(spec.Ly));
      ctx.stroke();
    }
    for (let j = 0; j <= spec.nely; j += gy) {
      const y = sy((j / spec.nely) * spec.Ly);
      ctx.beginPath();
      ctx.moveTo(sx(0), y);
      ctx.lineTo(sx(spec.Lx), y);
      ctx.stroke();
    }

    ctx.fillStyle = "rgba(124,58,237,0.35)";
    ctx.strokeStyle = "#a78bfa";
    for (const region of spec.passive_regions) {
      if (region.type === "circle") {
        ctx.beginPath();
        ctx.arc(sx(region.cx), sy(region.cy), (region.radius / spec.Lx) * (w - 2 * pad), 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }

    ctx.fillStyle = "#22d3ee";
    ctx.strokeStyle = "#22d3ee";
    ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    for (const support of spec.supports) {
      if (support.type === "edge") {
        const x = support.edge === "left" ? sx(0) : support.edge === "right" ? sx(spec.Lx) : null;
        const y = support.edge === "bottom" ? sy(0) : support.edge === "top" ? sy(spec.Ly) : null;
        if (x !== null) {
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(x, sy(0));
          ctx.lineTo(x, sy(spec.Ly));
          ctx.stroke();
        }
        if (y !== null) {
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(sx(0), y);
          ctx.lineTo(sx(spec.Lx), y);
          ctx.stroke();
        }
      } else {
        ctx.beginPath();
        ctx.arc(sx(support.x), sy(support.y), 7, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    spec.loads.forEach((load, index) => {
      if (load.type !== "point") return;
      const x = sx(load.x);
      const y = sy(load.y);
      ctx.fillStyle = "#ef4444";
      ctx.strokeStyle = "#f87171";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fill();
      const fx = Number(load.fx || 0);
      const fy = Number(load.fy || 0);
      const mag = Math.hypot(fx, fy) || 1;
      const dx = (fx / mag) * 42;
      const dy = (-fy / mag) * 42;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + dx, y + dy);
      ctx.stroke();
      ctx.fillText(`load ${index + 1}`, x + 10, y - 10);
    });
  }, [spec]);

  function eventToDomain(event) {
    const rect = ref.current.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width;
    const py = (event.clientY - rect.top) / rect.height;
    return {
      x: Math.max(0, Math.min(spec.Lx, px * spec.Lx)),
      y: Math.max(0, Math.min(spec.Ly, (1 - py) * spec.Ly)),
    };
  }

  function findPointLoad(event) {
    const p = eventToDomain(event);
    let best = null;
    let bestD = Infinity;
    spec.loads.forEach((load, index) => {
      if (load.type !== "point") return;
      const d = Math.hypot(load.x - p.x, load.y - p.y);
      if (d < bestD) {
        best = index;
        bestD = d;
      }
    });
    return bestD <= spec.Lx * 0.08 ? best : null;
  }

  return (
    <canvas
      ref={ref}
      className="domain-canvas"
      onMouseDown={(event) => setDrag(findPointLoad(event))}
      onMouseMove={(event) => {
        if (drag === null) return;
        const p = eventToDomain(event);
        onMoveLoad(drag, p.x, p.y);
      }}
      onMouseUp={() => setDrag(null)}
      onMouseLeave={() => setDrag(null)}
    />
  );
}

function DensityCanvas({ rho, nelx, nely }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !rho) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = 760;
    const h = 310;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = "100%";
    canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, w, h);

    const flat = Array.isArray(rho[0]) ? rho.flat() : rho;
    const cellW = w / nelx;
    const cellH = h / nely;
    for (let i = 0; i < nelx; i += 1) {
      for (let j = 0; j < nely; j += 1) {
        const v = Number(flat[i * nely + j] || 0);
        const g = Math.round((1 - v) * 245);
        ctx.fillStyle = `rgb(${g},${g},${g})`;
        ctx.fillRect(i * cellW, h - (j + 1) * cellH, Math.ceil(cellW), Math.ceil(cellH));
      }
    }
  }, [rho, nelx, nely]);

  return <canvas ref={ref} className="density-canvas" />;
}

export default function App() {
  const [prompt, setPrompt] = useState(PRESETS.cantilever.prompt);
  const [spec, setSpec] = useState(clone(PRESETS.cantilever.spec));
  const [controller, setController] = useState("schedule");
  const [maxIter, setMaxIter] = useState(120);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);
  const [result, setResult] = useState(null);

  const specSummary = useMemo(() => {
    if (!spec) return "";
    const dim = spec.nelz ? `${spec.nelx} x ${spec.nely} x ${spec.nelz}` : `${spec.nelx} x ${spec.nely}`;
    return `${spec.Lx} x ${spec.Ly}, mesh ${dim}, volume ${(spec.volfrac * 100).toFixed(0)}%`;
  }, [spec]);

  function push(message) {
    setLog((items) => [...items.slice(-7), `${new Date().toLocaleTimeString()}  ${message}`]);
  }

  async function configurePrompt() {
    setBusy(true);
    setResult(null);
    try {
      push("Configuring problem from prompt...");
      const response = await fetch(`${API_BASE}/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, temperature: 0 }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || `HTTP ${response.status}`);
      setSpec(ensureSpec(data.spec));
      push(data.llm_used ? "LLM configurator returned a valid spec." : "Backend fallback returned a valid spec.");
    } catch (error) {
      const fallback = ensureSpec(fallbackSpec(prompt));
      setSpec(fallback);
      push(`Backend unavailable; using deterministic fallback (${error.message}).`);
    } finally {
      setBusy(false);
    }
  }

  async function solve() {
    setBusy(true);
    setResult(null);
    try {
      push(`Solving with ${controller} controller...`);
      const response = await fetch(`${API_BASE}/solve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec, controller, max_iter: Number(maxIter) }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || `HTTP ${response.status}`);
      setResult(data);
      push(`Solve completed in ${data.wall_time}s after ${data.n_iter} iterations.`);
    } catch (error) {
      push(`Solve failed: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  function loadPreset(key) {
    setPrompt(PRESETS[key].prompt);
    setSpec(clone(PRESETS[key].spec));
    setResult(null);
    push(`Loaded ${PRESETS[key].label} preset.`);
  }

  function moveLoad(index, x, y) {
    setSpec((current) => {
      const next = clone(current);
      if (next.loads[index]?.type === "point") {
        next.loads[index].x = Number(x.toFixed(3));
        next.loads[index].y = Number(y.toFixed(3));
      }
      return next;
    });
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>AutoSiMP</h1>
            <p>Natural-language problem configuration, SIMP solving, and structural quality checks.</p>
          </div>
          <div className="status">{busy ? "Running" : "Ready"}</div>
        </header>

        <div className="layout">
          <aside className="panel controls">
            <label>
              Problem prompt
              <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={6} />
            </label>

            <div className="preset-grid">
              {Object.entries(PRESETS).map(([key, preset]) => (
                <button key={key} type="button" onClick={() => loadPreset(key)}>
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="field-row">
              <label>
                Controller
                <select value={controller} onChange={(event) => setController(event.target.value)}>
                  <option value="schedule">schedule</option>
                  <option value="llm">llm</option>
                  <option value="none">none</option>
                </select>
              </label>
              <label>
                Iterations
                <input
                  type="number"
                  min="20"
                  max="500"
                  step="10"
                  value={maxIter}
                  onChange={(event) => setMaxIter(event.target.value)}
                />
              </label>
            </div>

            <div className="button-row">
              <button className="primary" type="button" onClick={configurePrompt} disabled={busy}>
                Configure
              </button>
              <button className="primary" type="button" onClick={solve} disabled={busy || !spec}>
                Solve
              </button>
            </div>

            <div className="log">
              {log.length ? log.map((item) => <div key={item}>{item}</div>) : <div>No actions yet.</div>}
            </div>
          </aside>

          <section className="panel visual">
            <div className="section-head">
              <div>
                <h2>Problem Preview</h2>
                <p>{specSummary}</p>
              </div>
              <span>{spec.supports.length} supports / {spec.loads.length} loads</span>
            </div>
            <DomainCanvas spec={spec} onMoveLoad={moveLoad} />
            <p className="hint">Drag red point loads to adjust their coordinates before solving.</p>

            {result && (
              <div className="results">
                <div className="section-head">
                  <div>
                    <h2>Optimized Topology</h2>
                    <p>
                      Compliance {Number(result.compliance).toFixed(3)} / grayness {Number(result.grayness).toFixed(4)}
                    </p>
                  </div>
                  <span className={result.evaluation?.passed ? "pass" : "warn"}>
                    {result.evaluation?.passed ? "Passed" : "Review"}
                  </span>
                </div>
                <DensityCanvas rho={result.rho} nelx={result.nelx} nely={result.nely} />
                <div className="metric-grid">
                  <div><b>{Number(result.volfrac_actual).toFixed(3)}</b><span>volume</span></div>
                  <div><b>{result.n_iter}</b><span>iterations</span></div>
                  <div><b>{result.wall_time}s</b><span>wall time</span></div>
                </div>
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
