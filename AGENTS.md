# AGENTS.md

**Proactively update this file** whenever the human tells you how to do something differently that is related to all future chats and work in this project. Capture the rule, a short **Why**, and **How to apply**. Do not wait to be asked — edit `AGENTS.md` in the same turn the guidance is given.

## Project

HackUPC hackathon project.

**Read [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md) first** — it holds the full challenge context (vision, three stages, constraints, team, open questions). Keep it updated as new information comes in.

## Subprojects

- **`web/`** — SvelteKit + Convex web app derived from the saas-starter template. **You MUST read [`web/AGENTS.md`](./web/AGENTS.md) before editing anything in `web/`.** It covers the framework-specific stack (Svelte 5 runes, Convex, Better Auth, Tolgee, Tailwind v4), dev commands, env-var schemas, testing, and conventions that do not apply outside `web/`.
- **`sim/`** — Python simulation engine.

## Conventions

- Keep changes minimal and focused.
- Prefer editing existing files over creating new ones.
- Use package manager commands to add dependencies (no manual edits to `package.json` / `pyproject.toml`).
- **Before starting, make sure to clone all submodules.** `references/` contains vendored upstream repos (e.g. `streamlit`, `scikit-learn`, `httpx`, `pydantic`) so you can read real source instead of guessing. Figure out the right git command for the current repo state and run it before doing any non-trivial work.

## Operational hazards

- Always push to `stickerdaniel/hackUPC`. Run `git remote -v` first.
- Always re-run `git status --short` before staging — session-start snapshot can be stale.
- `git commit --allow-empty` still includes anything staged. Verify `git diff --cached` first.
- Never `stash drop` a stash you didn't create.
- Don't blanket `--no-verify`. If pre-commit conflicts on stash pop, commit/stash WIP first.
- `grep -r <file>` before deleting any config-adjacent file (e.g. `web/.gitignore` is read by `web/eslint.config.js`).
- Workers Builds status: `gh api repos/stickerdaniel/hackUPC/commits/<sha>/check-runs`. `wrangler deployments list` only shows already-deployed.

## Simulation Modeling

- Rule: Phase 1 component updates are state transitions from `t-1` to `t`, not independent per-tick formulas. Each component starts from explicit initial metric values, then updates from its own previous state, the environmental/operational drivers, and relevant previous states of other components.
  - Why: The printer should behave like a coupled system: e.g. overheating, contamination, or degradation in one subsystem can mathematically affect another subsystem on the next tick.
  - How to apply: Design `Engine.step()` so all components read from the same immutable previous `PrinterState`; compute cross-component influence terms from `tn-1`; then produce the new `PrinterState` for `tn` without letting update order affect results.

## Commit Style

### When to Commit

- After a logical unit of work, not just file saves.
- One cohesive change per commit (even if spanning multiple files).
- If you can summarize it in one sentence, commit it.

### Message Format

```
<type>(scope)[!]: <subject>

[optional body]
```

**Subject line:**
- Imperative mood: "Add" not "Added".
- Capitalize first letter, no period.
- Max 50 characters.
- `!` after type/scope = breaking change.

**Body (if needed):**
- Blank line after subject.
- Explain *what* and *why*, not *how*.
- Keep it short and concise — main changes only.
- Wrap at 72 characters.
- Include `Resolves: #123` or `See also: #456` where relevant.

### Commit Types

| Type       | Description                        |
| ---------- | ---------------------------------- |
| `feat`     | New feature                        |
| `fix`      | Bug fix                            |
| `docs`     | Documentation only                 |
| `style`    | Formatting, no logic change        |
| `refactor` | Code restructure (not fix/feature) |
| `test`     | Adding or fixing tests             |
| `chore`    | Maintenance (build, deps, etc.)    |
| `perf`     | Performance improvement            |
| `ci`       | CI/CD changes                      |

### Synthetic Prompt

Every **commit message** (after the short body) **and** every **PR description** ends with a **synthetic prompt** — a short, distilled instruction that would reproduce the diff if pasted into a fresh AI coding session. Do not copy the user's first message; condense the entire conversation into a single instruction that captures the full scope of changes. This tells reviewers what was intended, which is often more useful than reading the full diff.

Format: a Markdown blockquote under a `## Synthetic prompt` heading, followed by the model attribution.

```
<type>(scope): <subject>

<short body explaining what and why>

## Synthetic prompt

> Add `skills` and `projects` sections to `get_person_profile`, following the certifications PR pattern. Update fields, tests, docs, and manifest.

Generated with <model name and version>
```

The same `## Synthetic prompt` block (last commit's, or a combined one for the whole PR) is appended to the PR description.

## Package Manager

- **Always use `uv` for all Python actions** — running scripts, installing packages, launching tools.
  - Why: The project's `sim/` package is managed with `uv` (`pyproject.toml` + `uv.lock`). Using the system Python or pip bypasses the lockfile and gets the wrong environment.
  - How to apply: Prefix every Python command with `uv run` (e.g. `uv run streamlit run ...`, `uv run pytest`). Add dependencies with `uv add <pkg>`. Never call `python`, `pip`, or `streamlit` directly.
  - Binary is installed at `C:\Users\leoni\.local\bin\uv.exe` — use the full path if `uv` is not on PATH in the current shell.

## Commands

To be filled in once the stack is chosen (dev server, tests, lint).
