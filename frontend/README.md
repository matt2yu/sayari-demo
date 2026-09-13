# Frontend

React + TypeScript + Vite. Deliberately minimal — one page, no design system, no
router. The only interactive element that earns its place is the persona switch,
because switching buyer *is* the argument the deliverable makes.

```bash
npm install
npm run dev          # http://localhost:5173
```

Expects the API at `http://localhost:8000`:

```bash
uv run --directory ../backend uvicorn app.main:app --reload
```

The API falls back to the committed `sample.snapshot.json`, so the UI is fully
reviewable without Sayari credentials.

## Structure

| File | Role |
|---|---|
| `App.tsx` | Layout, data fetch, persona state, caveat footer |
| `components/PersonaSwitch.tsx` | Consumer / Enterprise / Federal Contractor / DoD |
| `components/ProductGrid.tsx` | 25 cards, re-sorted and re-coloured per persona |
| `components/DetailPanel.tsx` | Verdict matrix, ownership chains, flags, adjudication |
| `types.ts` | Mirrors the snapshot schema |

## What the UI is careful about

These are constraints, not styling choices — the repo's `AGENTS.md` explains why.

- **Seed and network flags are shown in separate blocks.** A flag derived by
  traversing the graph describes a relationship, never a property of the brand.
- **Every flag renders Sayari's own description**, hedges intact. No flag appears
  as a bare scary string.
- **Coverage gaps are shown, not hidden.** A brand with no shipment records gets a
  warning, not a clean chip — Ring looks clean only because Amazon imports for it.
- **Rejected candidates and excluded flags are published** in the detail panel. The
  adjudication is part of the deliverable.
- **No ethical language anywhere.** Every verdict names a statute and the population
  it binds.
