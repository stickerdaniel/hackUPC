# 14 — Stack & Topology Decisions

> Research note: lock the language split, UI stack, cross-language data bridge,
> deploy target, and repo skeleton for the HackUPC 2026 Digital Co-Pilot.
> Status: **decisions locked, build can start**.

## TL;DR

- **Sim = Python** (uv + numpy/pandas/simpy/sklearn). **Web = Next.js 15 App
  Router + Vercel AI SDK v6 + AI Gateway + shadcn/ui + Recharts + bun**.
- **Bridge = single SQLite file** at `data/historian.sqlite`. Python writer,
  Next.js reader via **`better-sqlite3`** in **WAL mode**. No FastAPI shim.
- **Deploy:** Web on **Vercel**; sim runs **locally** during the demo and writes
  to a local file. **Commit a fallback `historian.sqlite` to the repo** so
  Vercel and a clean clone both have something to read even if the sim never
  runs. No Vercel Functions strictly required for Phase 3 baseline; we add one
  cron Function only if we ship the proactive-alert bonus.
- **Bootstrap:** `make dev` (top-level) → spins up `sim/` (uv-managed Python
  loop) and `web/` (bun + `next dev`) in parallel via a tiny Procfile-style
  runner.
- **Critical gotcha confirmed:** SQLite cannot be **written** from a Vercel
  Function (ephemeral FS). It can be **read** from a file committed to the repo
  — that is exactly our pattern.

## Background

We have three phases (model → simulate → chat) and two builders (Chris on
sim, Daniel on UI/agent). Two contention points need a decision before code:

1. **Language split.** Chris is fluent in Python and the math library
   ecosystem (numpy, pandas, simpy, sklearn for the ML-degradation bonus) is
   far stronger than the JS/TS equivalent. Forcing TS for the sim costs us the
   sklearn / Weibull / Arrhenius shortcut and slows Chris down. The only TS-side
   win — one repo, one runtime — is not worth that.
2. **How does the chatbot read sim output?** Either Python exposes an HTTP API
   (FastAPI) or both processes share a file. A shared SQLite file is one fewer
   process to keep alive on stage; `better-sqlite3` is a synchronous,
   battle-tested Node binding; WAL mode makes a Python writer + Node reader
   safe.

## Decision

### Stack table

| Layer | Choice | Why |
| --- | --- | --- |
| Sim language | **Python 3.12** | numpy/pandas/simpy/sklearn; Chris owns it. |
| Python tooling | **uv** + **Ruff** + **Black** | uv is the fastest installer and resolves locks deterministically; Ruff replaces flake8/isort. |
| Sim libs | numpy, pandas, simpy, scikit-learn, pydantic | Phase 1 formulas + the ML degradation bonus + typed driver/state schemas. |
| Historian | **SQLite (WAL mode)** at `data/historian.sqlite` | Single file, embeddable, queryable, commits cleanly to git for fallback. |
| Web framework | **Next.js 15 App Router** | Server Components let us run `better-sqlite3` server-side cleanly. |
| Package manager | **bun** | Faster local installs than pnpm; Vercel supports it natively. |
| UI components | **shadcn/ui** + **Tailwind v4** | Hackathon-fast, owns its source, easy to theme. |
| Charts | **Recharts** | Most familiar, ships in 5 min; visx is too low-level for 36h, Tremor is overkill. |
| AI layer | **Vercel AI SDK v6** + **AI Gateway** → **Anthropic Claude (Sonnet)** | One SDK, streaming, tool-calling, fallback providers, $5/team free credit. |
| DB binding (web) | **`better-sqlite3`** | Synchronous, fastest, opens read-only easily; native module — only a problem if we tried to *write* on Vercel, we don't. |
| Deploy (web) | **Vercel** | Single click, public demo URL. |
| Deploy (sim) | **Local laptop** during demo + committed `historian.sqlite` fallback | Sim is the show; Vercel Functions can't host a long-running clock loop anyway. |

### Repo skeleton (locked)

```
.
├── Makefile             # `make dev`, `make sim`, `make web`, `make seed`
├── sim/                 # Python — owns the historian writer
│   ├── pyproject.toml   # uv-managed
│   ├── engine/          # Phase 1: pure formulas + ML hook (no I/O)
│   ├── loop/            # Phase 2: clock + driver source + writer
│   ├── scenarios/       # YAML driver profiles (hot-shop, cold-shop, chaos)
│   └── tests/
├── web/                 # Next.js 15 App Router
│   ├── app/             # routes incl. /api/chat (AI SDK v6)
│   ├── components/      # shadcn + chart wrappers
│   ├── lib/
│   │   ├── db.ts        # better-sqlite3, opened readonly + WAL
│   │   └── tools/       # AI SDK tool-calling helpers (query historian)
│   └── package.json
├── data/                # historian.sqlite (committed fallback) + scenario configs
├── docs/                # briefing/, research/, report/
└── scripts/             # one-shots: run scenario, export CSV, seed historian
```

### One-command bootstrap

```bash
make dev
```

Behind it (top-level `Makefile`):

```make
dev:        ## start sim + web together
	(cd sim && uv run python -m loop.main --scenario default) & \
	(cd web && bun run dev) ; \
	wait

seed:       ## regenerate the committed fallback historian
	cd sim && uv run python -m loop.main --scenario default --duration 7d \
	  --out ../data/historian.sqlite

web:        ## web only (reads committed historian)
	cd web && bun run dev

sim:        ## sim only
	cd sim && uv run python -m loop.main --scenario default
```

`make seed` is the safety net: anyone (including Vercel's build) can read a
non-empty historian without running the sim first.

### SQLite concurrency settings

On the Python side, on first connect:

```python
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA busy_timeout=5000;")
```

On the Node side (`web/lib/db.ts`):

```ts
const db = new Database(path, { readonly: true, fileMustExist: true });
db.pragma("journal_mode = WAL");
db.pragma("query_only = true");
```

WAL gives us **multiple readers + one writer concurrently** — exactly the
sim-writer / web-reader topology — without "database is locked" errors during
the demo.

## Why this fits our case

- **Sim in Python** keeps Chris on his strongest tooling (sklearn for the AI
  degradation bonus, pandas for the historian export, simpy if we want
  event-driven ticks). The TS-monorepo win is symbolic; the python-ecosystem
  win is concrete.
- **One file, two readers** is the simplest cross-language bridge that exists.
  No FastAPI process to die on stage, no port collisions, no CORS, no auth. A
  `better-sqlite3` opened readonly with WAL is microseconds-per-query, plenty
  for a chatbot.
- **Vercel + committed historian** gives us a public URL judges can open on
  their phone *even if our sim laptop dies*. The web build never depends on
  Python being installed.
- **Vercel AI SDK v6** gives us streaming, tool-calling and provider fallback
  for free, which is exactly the surface Phase 3's RAG/agentic ladder needs.
- **shadcn + Recharts + bun** is the fastest known path to a polished UI in
  36 hours. We have shipped this exact combo before; zero learning tax.

## References

- [Is SQLite supported in Vercel? — Vercel KB](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel) — confirms write-on-Vercel is unsupported, read-from-committed-file is fine.
- [Read-only sqlite — vercel/community #1181](https://github.com/vercel/community/discussions/1181) — community-confirmed pattern of committing the `.db` file and reading it from a Function.
- [SQLite WAL docs](https://www.sqlite.org/wal.html) — readers don't block writer, writer doesn't block readers; one writer at a time (we have exactly one).
- [better-sqlite3 performance docs](https://github.com/WiseLibs/better-sqlite3/blob/master/docs/performance.md) — recommends WAL for web apps.
- [AI SDK 6 — Vercel blog](https://vercel.com/blog/ai-sdk-6) — Agent abstraction, tool calling, AI Gateway integration.
- [AI Gateway — Anthropic Messages API](https://vercel.com/docs/ai-gateway/sdks-and-apis/anthropic-messages-api) — Claude routing through Gateway.
- [Vercel fails to build with dev-dep better-sqlite3 — vercel/vercel #12040](https://github.com/vercel/vercel/issues/12040) — pin Node 22, not 24, on Vercel to avoid the native-module registration bug.

## Open questions

1. **Node version on Vercel** — pin to **Node 22** in `package.json` `engines`
   to dodge the known better-sqlite3-on-Node-24 registration error. Confirm
   during first deploy.
2. **Historian size in the repo.** A 7-day scenario at 1-minute tick × 3
   components ≈ 30k rows, well under 5 MB — fine to commit. If we go to
   1-second tick we cross 100 MB; switch to git-lfs or a smaller default
   scenario.
3. **Proactive alerts (Phase 3 bonus).** Cleanest path: a Vercel Cron Function
   that opens the committed historian read-only every N minutes and pushes
   alerts to the UI via Server-Sent Events. Decision deferred until Phase 1+2
   are green.
4. **Voice (Phase 3 bonus).** Web Speech API in-browser is free and zero infra;
   only revisit if we want hands-free demo polish.

## Synthetic prompt

> Write `docs/research/14-stack-and-topology.md` for the HackUPC Metal Jet
> Co-Pilot. Lock: Python sim (uv, numpy/pandas/sklearn) writes
> `data/historian.sqlite` in WAL mode; Next.js 15 App Router on Vercel reads it
> via `better-sqlite3` (readonly) — no FastAPI. UI: shadcn + Recharts + bun;
> AI: Vercel AI SDK v6 through AI Gateway to Claude. Commit a seeded fallback
> historian for Vercel/clean-clone reads. Provide the repo tree, a top-level
> `make dev` that runs sim + web in parallel, the WAL pragmas for both sides,
> and call out the better-sqlite3-on-Node-24 Vercel build bug. Sections:
> TL;DR, Background, Decision (table + tree + commands), Why this fits,
> References, Open questions.

Generated with Claude Opus 4.7
