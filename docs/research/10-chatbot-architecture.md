# 10 — Chatbot Architecture: Pattern, Tool Design, Citation Enforcement, Severity Tagging

> Phase 3 strategic bet: a grounded co-pilot that **never hallucinates**, cites every claim against historian rows, tags severity deterministically, and reasons across multiple tool calls. We commit to **Pattern C (Agentic Diagnosis)** with B and A as graceful fallbacks built into the same code path.

## TL;DR

- **Target Pattern C (Agentic ReAct loop)** with `stopWhen: stepCountIs(8)`. B and A are emergent fallbacks — same tools, just shorter loops. The final user-facing message is produced via Vercel AI SDK 6's unified `generateText` + structured-output finisher.
- **Five tools, all read-only, all returning evidence-shaped rows.** `query_health`, `get_failure_events`, `compare_runs`, `current_status`, `recommend_action`. Every row has `(run_id, ts, component, metric, value)` so the model has nothing else to cite *with*.
- **Citation enforcement = A + B (defense in depth).** The final answer is constrained by a Zod schema where every assertion is `{claim, severity, evidence: [{run_id, ts, component, metric, value}]}` (≥ 1 evidence row required). A post-processing validator rejects any evidence row not present in the conversation's tool-result transcript and re-prompts with "evidence X not in transcript, retry".
- **Severity is computed in the tool layer**, never by the LLM. Mapping is locked to the existing status thresholds from doc 04: `health > 0.75 → INFO`, `> 0.40 → INFO`, `> 0.15 → WARNING`, `≤ 0.15 → CRITICAL`. `FAILED` events always upgrade to `CRITICAL`. The LLM only relays the tag.
- **System prompt is ~180 words**, contract-style, listing the tools, the citation rule, the severity rule, and the "I don't know" escape hatch.

## Background — three patterns recap

The brief defines a reasoning ladder over the historian:

| Pattern | Mechanism | Handles |
| :-- | :-- | :-- |
| **A. Simple Context Injection** | Latest snapshot stuffed into system prompt | "What is the status now?" |
| **B. Contextual RAG** | Question → SQL → rows → answer | "What happened at 14:00 yesterday?" |
| **C. Agentic Diagnosis** | ReAct loop over tools | "Why did run-7 fail earlier than run-3?" |

C subsumes B subsumes A: a one-step ReAct loop that calls `current_status()` *is* pattern A. We implement C and let the loop be short when the question is shallow. This collapses three patterns into one code path and lets us demo all three from the same chatbot.

## Decision

### 1. Architecture: ReAct loop on Vercel AI SDK 6

```
user → systemPrompt + tools[] → generateText({ stopWhen: stepCountIs(8) })
       ↳ LLM picks tool → tool runs SQL → result rows ↩ loop
       ↳ stop condition: model emits final structured answer
       ↳ validator: every cited evidence row must appear in tool transcript
```

`generateText` with multiple steps is the AI SDK 6 idiom; `onStepFinish` lets us stream "thinking → tool call → observation" to the UI for the wow factor.

### 2. Tool schemas (locked)

All tools are pure read functions over the SQLite historian. Inputs and outputs are JSON-schema-validated (Zod).

```ts
// 1. time-series fetch
query_health({
  component: 'recoater_blade' | 'nozzle_plate' | 'heating_element',
  time_range: { start: ISO8601, end: ISO8601 },
  run_id?: string,
}) → Array<{ run_id, ts, component, health: number, status, metric_name, metric_value, severity }>

// 2. discrete events
get_failure_events({
  run_id?: string,
  severity?: 'INFO' | 'WARNING' | 'CRITICAL',
  component?: ComponentId,
}) → Array<{ run_id, ts, component, kind: 'DEGRADED'|'CRITICAL'|'FAILED', health, severity }>

// 3. cross-run comparison
compare_runs({
  run_a: string,
  run_b: string,
  component?: ComponentId,
}) → {
  run_a: { final_health, failure_count, time_to_first_critical_s | null },
  run_b: { final_health, failure_count, time_to_first_critical_s | null },
  delta: { final_health, failure_count, time_to_first_critical_s },
  evidence: Array<{ run_id, ts, component, metric, value }>,
}

// 4. latest snapshot (Pattern A in one call)
current_status({ component?: ComponentId })
  → Array<{ run_id, ts, component, health, status, severity, drivers }>

// 5. policy lookup (deterministic table, not LLM)
recommend_action({ component: ComponentId })
  → { component, recommended_action: string, priority: 'P0'|'P1'|'P2', source: 'policy_table_v1' }
```

Every row carries a `severity` field, so the LLM literally cannot "decide" severity — it can only quote the tool. `recommend_action` is a fixed lookup so the model can't invent maintenance procedures.

### 3. Citation enforcement — A + B (structured output + validator)

The final assistant turn is constrained to:

```ts
const AnswerSchema = z.object({
  summary: z.string(),                   // human prose
  overall_severity: Severity,            // max() of assertions
  assertions: z.array(z.object({
    claim: z.string(),
    severity: Severity,
    evidence: z.array(z.object({
      run_id: z.string(),
      ts: z.string(),                    // ISO8601, must match a tool result
      component: ComponentId,
      metric: z.string(),
      value: z.number(),
    })).min(1),                          // ≥ 1 evidence row per claim
  })).min(1),
  follow_up_suggestions: z.array(z.string()).max(3),
});
```

**Why both layers**: Zod alone catches "no evidence" but not "fabricated evidence". The validator (`assertEvidenceInTranscript`) hashes every `(run_id, ts, component, metric)` tuple from tool returns into a Set, then rejects any cited tuple not in the Set. On rejection, we re-prompt: *"Evidence row X is not in the tool transcript. Cite only rows you have observed."* Up to 2 retries, then we fall through to "I don't have enough data to answer." This is the zero-tolerance grounding the brief explicitly rewards.

### 4. Severity tagging — deterministic, in the tool layer

| Health (`H`) | Status (doc 04) | Severity tag |
| :-- | :-- | :-- |
| `H > 0.75` | FUNCTIONAL | **INFO** |
| `0.40 < H ≤ 0.75` | DEGRADED | **INFO** |
| `0.15 < H ≤ 0.40` | DEGRADED (deep) | **WARNING** |
| `H ≤ 0.15` | CRITICAL or FAILED | **CRITICAL** |

`FAILED` events upgrade to **CRITICAL** regardless of health snapshot. The function lives once in `lib/severity.ts` and is called by every tool before returning. A response's `overall_severity = max(assertions[*].severity)` so the UI can colour the answer bubble red/yellow/grey without parsing prose.

### 5. System prompt skeleton (~180 words)

```
You are the Metal Jet S100 Co-Pilot. You answer questions about a single 3D
printer's health using ONLY the tools below. You have no prior knowledge of
this printer.

Tools (read-only, deterministic):
- current_status(component?) — latest snapshot
- query_health(component, time_range, run_id?) — time-series rows
- get_failure_events(run_id?, severity?, component?) — events
- compare_runs(run_a, run_b, component?) — cross-run delta
- recommend_action(component) — policy lookup

Rules:
1. NEVER state a fact about the printer that is not backed by a row returned
   from a tool in THIS conversation. No training-data claims about HP printers.
2. Every assertion in your final answer MUST cite ≥ 1 evidence row with
   {run_id, ts, component, metric, value}. Quote values verbatim.
3. Severity tags (INFO/WARNING/CRITICAL) come from the tool output. Do not
   re-classify them.
4. If tool results are insufficient, say "I don't have enough data" and
   propose which tool would help. Never guess.
5. Prefer 2–4 tool calls for diagnostic questions; chain them
   (status → events → compare) before answering.

Output format: structured JSON matching AnswerSchema.
```

## Why this fits our case

- **Brief alignment.** The brief lists "Reliability — Grounding Accuracy (zero hallucinations)" as the first evaluation pillar. The A+B citation stack makes hallucinated facts mechanically impossible at the response boundary, not just discouraged in prose.
- **Demo-ability.** Streaming `onStepFinish` events lets the judge *see* "thought → tool → observation → tool → answer". This is the visible "intelligence" the brief asks for.
- **Risk hedge.** If the agentic loop wobbles in the demo, the same tool set with a one-step prompt degrades cleanly to Pattern A. We never have to switch architectures.
- **Cheap to extend.** "Proactive alerting" (bonus pillar) becomes a cron that calls `current_status()` and pushes any `CRITICAL` to the UI — same severity function, no new code paths.
- **Defensible.** Severity in the tool layer means we can show judges the exact line of code that decides CRITICAL — there is no LLM judgement to defend.

## References

- [AI SDK Core: Tool Calling](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling) — `generateText` + `tools` + `stopWhen` is the canonical multi-step loop.
- [AI SDK 6 release notes](https://vercel.com/blog/ai-sdk-6) — unified `generateText` / `generateObject` finisher; `ToolLoopAgent` class.
- [How to build AI Agents with Vercel and the AI SDK](https://vercel.com/kb/guide/how-to-build-ai-agents-with-vercel-and-the-ai-sdk) — default `stopWhen: stepCountIs(20)`, `onStepFinish` callback pattern.
- [Multi-Step & Generative UI](https://vercel.com/academy/ai-sdk/multi-step-and-generative-ui) — streaming intermediate steps to the UI.
- [Anthropic — Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) — "have the model cite quotes for each claim" is the recommended guardrail.
- [arXiv 2404.08189 — Reducing hallucination in structured outputs via RAG](https://arxiv.org/html/2404.08189v1) — empirical: schema-constrained outputs + retrieval cuts hallucinations.
- [arXiv 2510.24476 — Mitigating Hallucination in LLMs (RAG, Reasoning, Agentic)](https://arxiv.org/html/2510.24476v1) — agentic systems benefit from "retrieval for factual grounding + structured reasoning for logical consistency."
- [ReAct Pattern — Prompting Guide](https://www.promptingguide.ai/techniques/react) — Reason / Act / Observe loop primer.
- [IBM — What is a ReAct Agent?](https://www.ibm.com/think/topics/react-agent) — function-calling integration with ReAct.
- [Simon Willison — Python ReAct pattern](https://til.simonwillison.net/llms/python-react-pattern) — minimal reference implementation.
- Internal: [`docs/research/04-aging-baselines-and-normalization.md`](./04-aging-baselines-and-normalization.md) — source of the 0.75 / 0.40 / 0.15 health thresholds we reuse for severity.

## Open questions

1. **Model choice.** Claude Sonnet vs. Gemini 2.x vs. GPT-5-class for the loop. Sonnet has the strongest tool-calling reliability we have direct experience with, but adds API key plumbing for the demo. Decide before kickoff.
2. **`time_range` defaults.** Should `query_health` default to "last 24h of the active run" if omitted, or force the LLM to pick? Forcing reduces ambiguity; defaulting is more forgiving in the demo.
3. **Citation row identity.** We hash `(run_id, ts, component, metric)`. If two metrics share a timestamp they collide unless we include `metric` — confirmed included. But: do we round `ts` to the tick boundary to avoid float-vs-string mismatches between SQLite `TEXT` and the model's quoted ts?
4. **Validator retry budget.** 2 retries × ~2k tokens = small but non-zero latency on stage. Fall through to "insufficient data" or hard-fail with a visible badge?
5. **Tool result size cap.** `query_health` over a long range can return thousands of rows. Cap at N=200 with a `truncated: true` flag, or pre-aggregate into buckets when range > 6h?
6. **Voice modality.** The brief lists voice as a versatility bonus. Same tools + Whisper STT + TTS, but the structured-output finisher needs to be re-rendered as prose for speech. Out of scope for v1, easy v2.
7. **`recommend_action` policy table content.** Who writes it? A trivial 3-component table is fine for the demo; flagging for the team to draft 3–5 actions per component before Saturday.
