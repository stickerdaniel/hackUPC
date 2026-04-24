# AGENTS.md

**Proactively update this file** whenever the human tells you how to do something differently that is related to all future chats and work in this project. Capture the rule, a short **Why**, and **How to apply**. Do not wait to be asked — edit `AGENTS.md` in the same turn the guidance is given.

## Project

HackUPC hackathon project.

**Read [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md) first** — it holds the full challenge context (vision, three stages, constraints, team, open questions). Keep it updated as new information comes in.

## Conventions

- Keep changes minimal and focused.
- Prefer editing existing files over creating new ones.
- Use package manager commands to add dependencies (no manual edits to `package.json` / `pyproject.toml`).

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

## Commands

To be filled in once the stack is chosen (dev server, tests, lint).
