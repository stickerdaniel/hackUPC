# D1 — Sim Core Language: Python vs TypeScript

**Decision item:** Which language runs Phases 1 and 2 (degradation model + simulation loop + historian writes)?

---

## TL;DR

Use Python. The math library ecosystem is mature and directly covers every model required (Weibull, Arrhenius, Archard). The AI-in-model bonus is a one-liner with scikit-learn. The bridge to the Next.js front-end is a thin REST API, not a liability.

---

## Background

Phase 1 requires at least two formal failure models (Exponential Decay, Weibull, Arrhenius, Coffin-Manson, Archard, Paris). Phase 2 wraps Phase 1 in a time loop and writes every tick to SQLite. Both are compute-heavy and data-shaped, not UI-shaped. Phase 3 (Next.js chatbot) reads from the same SQLite historian — it does not need to share a runtime with the sim.

---

## Options Considered

### Option A — Python

**Strengths:**

- `numpy` / `scipy` cover every failure-model formula with vectorised ops and `scipy.stats.weibull_min`, `scipy.integrate`, etc. No manual implementation of special functions.
- `pandas` makes per-tick DataFrames trivial to aggregate, inspect, and dump to SQLite via `DataFrame.to_sql`.
- `sqlite3` is stdlib — zero extra dependency for the historian.
- `scikit-learn` gives a one-import path to the "AI degradation model" bonus (e.g. a `GradientBoostingRegressor` replacing one component's formula).
- `simpy` is optional but available if we want discrete-event semantics for maintenance events or shock injection.
- Fastest iteration for formula-heavy code: interactive notebooks, rich tracebacks, no compile step.

**Weaknesses:**

- Requires a separate process from Next.js; a REST layer (FastAPI, or plain `http.server`) adds ~30 min setup.
- Two runtimes mean two dev envs; teammate must have Python set up.
- Deployment: two services to start (Python sim, Node web).

### Option B — TypeScript

**Strengths:**

- Single language across entire repo; no cross-language bridge.
- `mathjs` handles symbolic math; `simple-statistics` covers basic distributions.
- Easier to deploy as a single Vercel/Railway project.

**Weaknesses:**

- No native Weibull/Arrhenius implementations; every special function is a manual port or untested micro-lib.
- No equivalent of `scikit-learn` for the AI bonus — would need a third-party ONNX runtime or skip the bonus entirely.
- `pandas`-style time-series manipulation does not exist; DataFrame operations become verbose array code.
- Higher risk of subtle numeric bugs in 24 h.

---

## Recommendation

**Python** with the following library set:

| Library | Role |
| :-- | :-- |
| `numpy` | Vectorised math, array ops |
| `scipy` | Weibull, Arrhenius, statistical distributions |
| `pandas` | Per-tick state DataFrames, CSV/SQLite export |
| `sqlite3` | Historian persistence (stdlib, no install) |
| `fastapi` + `uvicorn` | REST bridge to Next.js (Phase 3 reads) |
| `scikit-learn` | AI degradation model bonus (optional) |
| `simpy` | Discrete-event loop if needed (optional) |

**Environment tooling:** `uv` over `venv`. `uv` resolves and installs in seconds, creates a lockfile (`uv.lock`), and requires no activation ceremony — `uv run python sim.py` just works. Saves setup time in a 24 h contest.

---

## Three Risks to Monitor

1. **Cross-language friction.** The Python sim and the Next.js front-end must agree on a data contract (REST schema or direct SQLite file path). Define this contract in hour 1.
2. **Deploy story.** Two processes to start for judges. Mitigate with a single `Makefile` or `docker-compose` that boots both with one command.
3. **Dev environment parity.** Both teammates must be on the same Python version (3.11+). Pin it in `.python-version` (for `uv`) on day 0.

---

## Open Questions

- Does Chris run the sim as a long-lived process emitting SSE, or does the Next.js API route shell-out to run a batch scenario on demand?
- Should the historian be a file on disk (simple for demos) or a shared SQLite URL accessible by both processes simultaneously?
- If the AI bonus is implemented, does it live inside Phase 1 (replace one formula) or outside as a post-processing step?

---

## References

- numpy: https://numpy.org/doc/stable/
- scipy.stats (Weibull, Arrhenius): https://docs.scipy.org/doc/scipy/reference/stats.html
- pandas to_sql: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html
- scikit-learn: https://scikit-learn.org/stable/
- simpy: https://simpy.readthedocs.io/en/latest/
- uv: https://docs.astral.sh/uv/
- mathjs (TS alternative): https://mathjs.org/
- simple-statistics (TS alternative): https://simplestatistics.org/
