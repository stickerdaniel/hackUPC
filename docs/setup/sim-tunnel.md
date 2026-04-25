# Sim service tunnel — local Docker → cloud Convex

The Convex cloud deployment cannot reach `localhost`, so we expose the
local Docker sim service via a Cloudflared quick tunnel and point
Convex at that HTTPS URL.

## Prereqs

- Docker daemon running.
- `cloudflared` installed (`brew install cloudflare/cloudflare/cloudflared`).
- Convex cloud deployment authenticated (`bunx convex login` once).

## One-time

1. Copy the env template and fill in matching secrets on both sides:
   ```sh
   cp .env.sim.example .env.sim
   # edit: set SIM_API_KEY and SIM_INGEST_SECRET to fresh random values
   ```

2. Make sure `CONVEX_INGEST_URL` in `.env.sim` ends in `/sim-ingest`.
   On a cloud deployment it looks like
   `https://<deployment>.convex.site/sim-ingest`.

## Each demo session

```sh
# 1. start the sim container
make sim-docker          # docker compose up --build sim

# 2. expose it to the public internet (in a second terminal)
make sim-tunnel          # cloudflared tunnel --url http://localhost:8000
# → copy the printed https://*.trycloudflare.com URL

# 3. point cloud Convex at that URL + set the matching secrets
cd web
bun convex env set PYTHON_SIM_BASE_URL  https://<random>.trycloudflare.com
bun convex env set PYTHON_SIM_API_KEY   <same as SIM_API_KEY in .env.sim>
bun convex env set SIM_INGEST_SECRET    <same as SIM_INGEST_SECRET in .env.sim>

# 4. trigger a run end-to-end (you must be authenticated)
# Via the dashboard once /app/runs/+page.svelte is wired, or via CLI:
bun convex run sim/actions:runScenario '{"scenario":"barcelona-baseline","horizonTicks":260}'
```

Watch the sim container log show `[stub]`-style POSTs and the Convex
dashboard fill `simRuns` / `simTicks` reactively. The dashboard at
`/en/app/runs/<runId>` should animate playback.

## Troubleshooting

- `401 unauthorized` on `/sim-ingest` → secrets out of sync between
  `.env.sim` and `bun convex env`. Re-set both sides.
- `502 Bad Gateway` from the tunnel → Docker container died; check
  `docker compose logs sim`.
- Convex action error `Sim service not configured` → you forgot
  `bun convex env set PYTHON_SIM_BASE_URL`.
