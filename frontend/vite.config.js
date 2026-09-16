import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The one .env for the whole repository, one directory up from here —
// the same file the backend and docker-compose.yml read. Vite defaults
// to `frontend/`, which would mean a second file to keep in sync.
const envDir = fileURLToPath(new URL('..', import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  // VITE_API_URL is compiled into the JS bundle, so it cannot be
  // corrected after the fact: a bundle built without it ships pointing
  // at localhost:8000, the site loads fine, and then every single
  // action fails with an opaque network error. Refuse to build.
  //
  // `vite build` only — `npm run dev` in src/api/client.js falls back
  // to the local API, so development still works with no .env at all
  // (a fresh clone that has not been configured yet).
  const env = loadEnv(mode, envDir, 'VITE_')
  if (command === 'build' && !env.VITE_API_URL) {
    throw new Error(
      'VITE_API_URL is not set. It is baked into the bundle at build time, so ' +
        'this cannot be fixed after the build — set it in the repo-root .env ' +
        '(compose passes it as a build arg) to the public API origin, e.g. ' +
        'https://api.orderkoi.example.com'
    )
  }

  return {
    plugins: [react()],
    // Where `import.meta.env.VITE_*` is read from at dev/build time —
    // src/api/client.js reads VITE_API_URL this way.
    envDir,
  }
})
