# OrderKoi Frontend

The seller dashboard, public order form, and tracking pages for OrderKoi —
React 19 + Vite, plain JavaScript, custom CSS design system ("koi vermilion on
warm paper"). Talks to the FastAPI backend (default `http://localhost:8000`).

Full guide: **[../docs/FRONTEND_GUIDE.md](../docs/FRONTEND_GUIDE.md)** — setup,
routes, testing, project layout, troubleshooting. Running the whole stack
with Docker: **[../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md)**.

## Quick start

```bash
npm install     # once
npm run dev     # http://localhost:5173 — backend must be running on :8000
```

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Production build → `dist/` (what gets deployed) |
| `npm run preview` | Serve the build locally |
| `npm run lint` | Oxlint |
| `npx playwright test` | E2E suite (18 tests; dev servers must be running) |

## Notes for this project

- **API base is baked at build time** (`VITE_API_URL` build arg → `src/api/client.js`) — dev uses the Vite proxy.
- **Business config is live, not baked**: prices, free-plan allowance, bKash details, and support email are fetched from `GET /public/stores/pricing` at runtime via `src/utils/proPricing.js`. Changing an offer = backend `.env` edit + restart; no frontend rebuild.
- E2E runs single-worker (`workers: 1`) — the dev backend rate-limits by IP. Run the full suite with the backend started as `RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8000`, otherwise the suite's own logins trip the 10/min bucket. Details in `docs/FRONTEND_GUIDE.md`.
- Design tokens, components, and all styles live in `src/index.css`.
