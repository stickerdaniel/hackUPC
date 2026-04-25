# C1 — Pattern Choice: A vs B vs C for Phase 3

**Item:** Confirm primary interaction pattern for the grounded chatbot (Phase 3).
**Status:** Decided.

---

## TL;DR

Use **Pattern C (Agentic Diagnosis)** as primary: a tool-calling ReAct loop where the LLM
decides which historian queries to run across multiple steps. Fall back to **Pattern B
(Contextual RAG)** automatically when tool calls fail or exhaust the step budget. Pattern A
(Simple Context Injection) is a free baseline that requires no extra work — it is the
degenerate case of B when N=1 and the query is always "latest row".

---

## Background

The TRACK-CONTEXT.md Phase 3 reasoning ladder defines three tiers:

- **A** — inject current snapshot into system prompt; answers "what is status now?"
- **B** — translate question to DB query, retrieve relevant rows, answer; handles
  "what happened at 2pm?"
- **C** — tool-calling ReAct loop; AI searches, compares, concludes across multi-step
  investigations

Tool-calling (function calling) matured across all target SDKs in 2025. The 2025–2026
consensus is that hybrid agentic + RAG architectures — where the agent treats retrieval as
one of several tools — outperform vanilla RAG on multi-step diagnostic queries by wide
margins while remaining buildable with minimal glue code.

---

## Options Considered

### A — Simple Context Injection

- **How:** Latest snapshot embedded in system prompt at request time.
- **Pros:** Trivially implemented; zero query logic; zero latency overhead.
- **Cons:** Cannot answer historical or comparative questions; context window fills fast
  if snapshot is large.
- **Hackathon verdict:** We get this for free. Any chatbot that reads the DB at all
  achieves A. Not a differentiator.

### B — Contextual RAG

- **How:** Translate user question to a parameterised SQL/filter query, execute once,
  embed top-N result rows in the prompt.
- **Pros:** Handles point-in-time and range queries; predictable latency (one DB round
  trip); easy to audit (single query, single citation block).
- **Cons:** One-shot — cannot refine the query if first results are insufficient; cannot
  chain across subsystems without manual orchestration.
- **Hackathon verdict:** Solid fallback. Implement as a single `query_historian` tool
  callable from the C loop; this gives B for free as a degenerate one-step agent run.

### C — Agentic Diagnosis (primary target)

- **How:** LLM drives a ReAct loop (reason → act → observe → repeat). Tools expose
  historian slices: `get_component_history`, `get_event_window`, `compare_runs`,
  `get_latest_snapshot`, `predict_time_to_failure`. LLM chains calls until it can
  formulate a grounded answer.
- **Pros:** Handles compound questions ("why did nozzle clog correlate with humidity
  spike on run 3?"); produces richer evidence trails; directly scores on Reasoning
  Depth and Autonomy pillars.
- **Cons:** More failure modes (tool error, runaway loop, token bloat); requires
  `maxSteps` cap and error handling.
- **Hackathon verdict:** Feasible in 24 h. All three target SDKs support this natively
  with minimal glue (see SDK Confirmation below).

---

## Recommendation

### Primary: Pattern C

Implement a `generateText` / `Messages` call with 4–5 registered tools and `maxSteps`
capped at 8–10. Each tool is a typed function wrapping a parameterised SQLite query.
The LLM selects and sequences them; each result is added to the conversation and becomes
evidence for the final answer. The final response must include an Evidence Citation block
and a Severity Indicator, enforced by the system prompt.

### Fallback to B (automatic degradation)

If any tool call raises an exception or the step budget is exhausted before a final text
response, the error handler executes a single best-effort `query_historian` call with the
original user query parsed into a time range and component filter, embeds the result rows
directly in a follow-up prompt, and returns a B-style answer. The response is flagged with
`[DEGRADED: single-pass retrieval]` so the UI can surface it.

Concretely: last-N rows = 50 rows (configurable), covering the most recent simulation
window, to stay well under context limits while giving the model enough signal for most
status questions.

### Baseline A (free)

`get_latest_snapshot` (the first of the five tools) already implements A. Zero extra work.

### SDK Confirmation

| SDK | Tool Calling | Notes |
|-----|-------------|-------|
| Vercel AI SDK 6 | `tool()` + `maxSteps` param on `generateText`/`streamText` | Unified API over Claude + OpenAI; strict mode per tool; tool errors scoped to single tool, not full request |
| Anthropic SDK (Claude) | `tools` array + `tool_use` / `tool_result` message cycle | Native ReAct loop; programmatic tool calling beta reduces round trips |
| OpenAI SDK | `tools` array in Chat Completions / Responses API | Responses API is agentic-by-default; 40–80% cache improvement in multi-tool runs |

Five tools is well within tested production limits for all three; no custom orchestration
framework (LangChain, LangGraph) is needed.

---

## Open Questions

1. **SQLite vs in-memory?** If historian is a flat CSV, do we need an ORM or is raw SQL
   fine? Impacts tool implementation time. (Likely raw SQL is faster to ship.)
2. **Streaming vs batch for tool results?** AI SDK 6 streams tool call inputs by default;
   decide whether the chatbot UI renders partial tool responses or waits for final text.
3. **Proactive alerting:** The "background monitor that fires before the operator asks"
   bonus fits naturally as a scheduled C-pattern call. Scope for 24 h?
4. **Token budget per run:** With 8–10 maxSteps and 50-row fallback window, estimate
   peak token usage per query to ensure we stay within model context limits.

---

## References

- [Agentic RAG Explained (2026)](https://freeacademy.ai/blog/agentic-rag-ai-agents-supercharge-retrieval-2026)
- [RAG vs Agentic RAG: Key Differences for 2026 — Kanerika](https://kanerika.com/blogs/rag-vs-agentic-rag/)
- [What Is Agentic RAG? — Weaviate](https://weaviate.io/blog/what-is-agentic-rag)
- [Agentic RAG survey — arXiv 2501.09136](https://arxiv.org/abs/2501.09136)
- [AI SDK 6 — Vercel](https://vercel.com/blog/ai-sdk-6)
- [AI SDK Core: Tool Calling](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling)
- [Tool Use with Claude — Anthropic Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Agentic RAG Failure Modes — Towards Data Science](https://towardsdatascience.com/agentic-rag-failure-modes-retrieval-thrash-tool-storms-and-context-bloat-and-how-to-spot-them-early/)
- [Building Production-Ready Agentic RAG — Adaline Labs](https://labs.adaline.ai/p/building-production-ready-agentic)
