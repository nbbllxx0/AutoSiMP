# AutoSiMP Interactive Demo

React/Vite demo for the AutoSiMP paper. It supports natural-language problem entry, preset selection, boundary-condition preview, point-load editing, in-browser 2-D SIMP solving, and result/evaluator display.

## Run

```bash
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

## Backend

The demo can call the Python backend at `http://localhost:5555` for production-grade solves:

```bash
python server.py
```

The browser-side solver is useful for instant 2-D interaction. The Python backend is the paper-aligned implementation path for the full solver, controller, evaluator, and 3-D cases.

## API Keys

For LLM configuration, prefer setting `GEMINI_API_KEY` in the Python backend
environment. If browser-side LLM controls are used, the key is kept in memory
only and is not persisted by the demo. Do not commit or share API keys.

## Files

```text
index.html
package.json
src/
  main.jsx
  App.jsx
```
