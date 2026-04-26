<div align="center">
  <h1>A digital twin for the HP Metal Jet S100.</h1>

  <p>
    A deterministic, coupled simulation of six components across three subsystems, with per-component sensor models, an AI maintenance agent, live weather data, a stochastic chaos layer, and an ML surrogate for the heater.
  </p>

  <p>
    <a href="https://www.python.org/"><img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=000000"></a>
    <img alt="HackUPC 2026" src="https://img.shields.io/badge/HackUPC-2026-FF4F00?style=for-the-badge">
  </p>
</div>

---

## Cloning

The repo is plain git except for two oversized HP brand assets (one PowerPoint playbook, one Photoshop source) that exceed GitHub's 100 MB per-file hard limit and live in Git LFS. Install `git-lfs` first (`brew install git-lfs && git lfs install`, or your distro's equivalent), then clone normally:

```bash
git clone https://github.com/stickerdaniel/hackUPC.git
cd hackUPC
```

If you don't need the two LFS files (most contributors don't — everything else is regular git), skip the LFS payload:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/stickerdaniel/hackUPC.git
```

You'll still get every other brand asset, all simulation code, and the docs. Pull individual LFS files later with `git lfs pull --include="<path>"`.

If you already cloned and the working tree contains ~130-byte text files where the binaries should be, run `git lfs install && git lfs pull` from the repo root.

---

## What we are building

A coupled digital twin where **every failure tells a story** — and where the operator's perception of the machine is itself a failable signal, not ground truth.

```
                ┌──────────────────────┐
input drivers ─▶│  Phase 1 — Logic     │──▶ next PrinterState (TRUE)
(temp, humidity,│  Engine.step()       │    + ObservedPrinterState
 load, maint.)  │  builds CouplingCtx, │      via per-component
 + live weather │  updates 6 components│      sensor models (§3.4)
 + prev state   │  from same prev      │
                │  snapshot, double-   │
                │  buffered            │
                └──────────────────────┘
                          ▲ │
                          │ │ deterministic, seeded, monotone
                          │ ▼
                ┌──────────────────────┐
                │  Phase 2 — Clock +   │  ──▶  Historian (SQLite WAL)
                │  Driver Generator +  │       runs · drivers ·
                │  Chaos Layer +       │       component_state · metrics ·
                │  Operator Loop       │       observed_component_state ·
                │                      │       observed_metrics · events
                └──────────────────────┘
                          ▲ │
                 modifies │ │ reads ObservedPrinterState (NOT true!)
                          │ ▼
                ┌──────────────────────┐
                │  AI Maintenance Agent│  emits TROUBLESHOOT / FIX / REPLACE
                │  (heuristic primary, │  per (component, action_kind)
                │   LLM-as-policy A/B) │  and writes rationale to events
                └──────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │  Streamlit Dashboard │  ──▶  judges + operators
                │  Time-series viz +   │       Phase 2 deliverable.
                │  true-vs-observed    │       Shows the §3.4 split
                │  toggle + scenarios  │       live.
                └──────────────────────┘
```
