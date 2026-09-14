# Frontend

React + TypeScript + Vite. One page, no design system, no router. The only
interactive element is the buyer-profile switch, because switching buyer is the
argument the deliverable makes.

```bash
npm install
npm run dev          # http://localhost:5173
npm run lint         # oxlint
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
| `components/PersonaPicker.tsx` | Consumer / Enterprise / Federal Contractor / DoD |
| `components/ProductGrid.tsx` | 25 cards, re-sorted and re-coloured per persona |
| `components/DetailPanel.tsx` | Verdict matrix, ownership chains, flags, adjudication |
| `components/ImpactBar.tsx` | Per-persona restricted/review/clear split |
| `brands.ts` | Brand to logo domain. Presentation only, never reaches a verdict |
| `types.ts` | Mirrors the snapshot schema |

## Rendering constraints

`AGENTS.md` in the repo root states the rules and the reasoning. The four that
shape this code:

- Seed and network flags render in separate blocks.
- Every flag carries Sayari's own description, hedges intact.
- Coverage gaps render as a warning, never as a clean chip.
- Rejected candidates and excluded flags are published in the detail panel.
