# D5 — Repo Skeleton: Folder Structure & One-Command Bootstrap

**Date:** 2026-04-25
**Item:** Lock folder structure and one-command dev bootstrap for the HP Metal Jet S100 Digital Co-Pilot monorepo.

---

## TL;DR

Use `uv` for Python (sim/), `pnpm` for Next.js (web/), and a single `Makefile` at root with a `make dev` target that installs both stacks and starts sim + web concurrently via `make -j2`. No heavyweight monorepo tooling needed for a two-day hackathon.

---

## Background

The project is a polyglot monorepo: a Python simulation engine (sim/) backed by SQLite (data/) and a Next.js chat/dashboard frontend (web/). Both must be bootstrappable in one command for demos and pair-programming handoffs. The structure must also survive the hackathon's 24-hour crunch without dependency surprises.

---

## Options Considered

### Python package manager

| Tool | Speed | 2026 status | Decision |
|------|-------|-------------|----------|
| pip + venv | baseline | ubiquitous, slow | skip |
| Poetry | moderate | stable but heavy | skip |
| **uv** | 10-100x pip | de-facto new default in 2026; replaces pip/pyenv/virtualenv in one binary | **chosen** |

uv handles `pyproject.toml`, creates `.venv`, pins via `uv.lock`, and `uv sync` is a single idempotent command. No pre-install needed beyond `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### JS package manager

| Tool | Monorepo maturity | 2026 status | Decision |
|------|-------------------|-------------|----------|
| npm | poor | baseline | skip |
| Yarn Berry | moderate | complex config | skip |
| Bun | fast installs | workspaces functional but less proven | secondary |
| **pnpm** | production-proven | 65 M weekly downloads, strict dep graph, disk-efficient | **chosen** |

pnpm workspaces are not needed here (only one JS package), but pnpm gives strict, reproducible installs. `pnpm install` + `pnpm dev` is the standard Next.js incantation.

### Monorepo orchestration

Turborepo and Nx add caching and task graphs but require significant config. For a two-day hack with two packages, a plain `Makefile` with `make -j2` for concurrency is sufficient and zero-config.

---

## Recommendation

### Full folder tree

```
hackUPC/
├── Makefile
├── .env.example
├── .gitignore
├── README.md
├── sim/
│   ├── pyproject.toml      # uv project file
│   ├── uv.lock
│   ├── src/
│   │   └── sim/
│   │       ├── __init__.py
│   │       ├── engine.py   # Phase 1 logic engine
│   │       ├── loop.py     # Phase 2 simulation loop
│   │       ├── historian.py
│   │       └── agents/
│   │           └── maintenance.py
│   └── tests/
├── web/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── next.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── app/            # Next.js App Router
│       └── components/
├── data/
│   └── .gitkeep            # historian.sqlite lives here at runtime
├── docs/
│   ├── briefing/
│   └── research/
└── scripts/
    └── seed_run.py         # convenience: run a canned scenario
```

### Makefile

```makefile
.PHONY: dev install install-sim install-web sim web

# One-command bootstrap + concurrent dev servers
dev: install
	$(MAKE) -j2 sim web

install: install-sim install-web

install-sim:
	cd sim && uv sync

install-web:
	cd web && pnpm install

sim:
	cd sim && uv run python -m sim.loop

web:
	cd web && pnpm dev

# Utility
clean:
	rm -rf sim/.venv web/node_modules data/historian.sqlite
```

`make dev` runs `uv sync` + `pnpm install` then fires both servers in parallel.

### .gitignore essentials

```
# Python
sim/.venv/
__pycache__/
*.pyc
sim/uv.lock   # keep — commit the lock file

# Node
web/node_modules/
web/.next/

# Runtime data
data/historian.sqlite

# Secrets
.env
*.env.local
```

### .env.example

```
OPENAI_API_KEY=
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1
SIM_DB_PATH=./data/historian.sqlite
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Open Questions

1. Does `make -j2` work in the hackathon environment (Windows WSL edge case)? Fallback: two terminal tabs.
2. If the AI agent (Phase 3) needs a FastAPI server, add a third `make api` target and bump to `make -j3`.
3. Should `uv.lock` be committed? Yes — determinism matters for reproducible demos.
4. pnpm version pinning: add `"packageManager": "pnpm@10"` to `web/package.json` to avoid version drift.

---

## References

- [uv docs — Astral](https://docs.astral.sh/uv/)
- [Best Python Package Managers 2026 — Scopir](https://scopir.com/posts/best-python-package-managers-2026/)
- [pnpm vs Bun 2026 — PkgPulse](https://www.pkgpulse.com/blog/pnpm-vs-bun-2026)
- [pnpm vs npm vs Yarn vs Bun — DeployHQ](https://www.deployhq.com/blog/choosing-the-right-package-manager-npm-vs-yarn-vs-pnpm-vs-bun)
- [Managing multiple languages in a monorepo — Graphite](https://graphite.com/guides/managing-multiple-languages-in-a-monorepo)
