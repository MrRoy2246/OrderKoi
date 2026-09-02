# ⚛️ Frontend Guide — React

The OrderKoi seller dashboard & tracking pages. React + Vite.

## Requirements

- Node.js 18+ installed (`node --version`)
- If not installed: download LTS from https://nodejs.org/

## First-time setup

Open a terminal in `OrderKoi/frontend/` and run:

```bash
npm install
```

This downloads all dependencies into `node_modules/` (takes a few minutes on first run — normal).

> ⚠️ The **backend must be running** (`localhost:8000`) for the frontend to load real data. Start it first.

## Running the dev server

```bash
npm run dev
```

- App URL: `http://localhost:5173`
- Auto-reloads when code changes — keep it running while developing

## Key pages

| Route | What | Who |
|---|---|---|
| `/` | Landing page | Everyone |
| `/login`, `/signup` | Auth | Sellers |
| `/dashboard` | Order management | Sellers (login required) |
| `/dashboard/orders/:id` | Order detail | Sellers (login required) |
| `/dashboard/settings` | Store settings | Sellers (login required) |
| `/track/:code` | **Public tracking page** | Customers — no login |

## Production build

```bash
npm run build     # outputs optimized files to dist/
npm run preview   # serves the build locally to verify it
```

The `dist/` folder is what gets deployed to your domain (Phase 8).

## Testing it yourself

- **Browser dev tools (F12) are your friend:**
  - *Console* tab → red errors mean something broke
  - *Network* tab → check API calls to `localhost:8000` (status 200 = good, 4xx/5xx = problem)
- **Test mobile view:** F12 → toggle device toolbar (Ctrl+Shift+M) → pick a phone
- **Reset login state:** F12 → Application → Local Storage → clear the token key

## Project layout

```
frontend/
├── src/
│   ├── main.jsx           # App bootstrap
│   ├── App.jsx            # Router setup
│   ├── api/client.js      # Axios/fetch wrapper → talks to backend
│   ├── pages/             # One file per page
│   ├── components/        # Reusable UI pieces (tables, badges, forms)
│   └── styles/            # CSS
├── package.json
├── vite.config.js         # Dev proxy → backend
└── index.html
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `npm` not found | Install Node.js LTS, reopen terminal |
| Blank page + console errors | Check backend is running on port 8000 |
| Login "network error" | Backend down, or CORS issue — restart backend |
| Port 5173 busy | Vite auto-picks 5174 — check terminal output |
| Weird stale behavior | Stop server, delete `node_modules/.vite`, `npm run dev` again |
