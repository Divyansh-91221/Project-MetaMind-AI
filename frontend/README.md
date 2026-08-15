# Enterprise Metadata Copilot - Frontend

React + TypeScript + Vite UI for the metadata catalog, lineage explorer, impact analysis,
governance, glossary and the Copilot chat.

## Structure

```
src/
├── app/           App shell, routing, providers
├── components/
│   ├── common/    Layout, cards, badges, spinner, search bar, empty/error states
│   ├── metadata/  Asset list, asset header, column table
│   ├── lineage/   Layered lineage graph, legend
│   ├── governance/Owner and classification views
│   ├── glossary/  Business term cards
│   └── copilot/   Chat window, message bubbles, evidence panel
├── pages/         One component per route
├── services/      Typed API clients (one per backend domain)
├── hooks/         useApi, useDebounce
├── types/         Shared API types mirroring the backend Pydantic schemas
├── utils/         Formatting helpers
└── styles/        Global stylesheet and design tokens
```

## Design decisions

* **No component library.** Styling uses plain CSS with custom properties, so the shell stays
  dependency-light and any design system can be adopted later.
* **No data-fetching library.** A small `useApi` hook wraps `fetch` with loading/error state,
  which is enough for this surface area. Swap in TanStack Query when caching or optimistic
  updates are needed.
* **Lineage is rendered as layered SVG** grouped by traversal depth rather than with a graph
  library, keeping the bundle small while still showing direction, confidence and inferred
  edges. A canvas library (React Flow / Cytoscape) is the natural next step for large graphs.
* **AI-inferred lineage is always visually distinct** (dashed edge, warning badge) so a user
  can never mistake a suggestion for a verified fact.

## Commands

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run test
npm run typecheck
```

The dev server proxies `/api` to `http://localhost:8000`; override with
`VITE_API_PROXY_TARGET`. When calling the API directly, set `VITE_API_BASE_URL`.
