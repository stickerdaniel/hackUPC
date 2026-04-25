# C2 — Tool Design: LLM Tool Schema for the Historian

**TL;DR:** Define five typed tools that the LLM calls against the SQLite historian via
a ReAct loop. Every tool returns a bounded JSON object (max 20 rows) that includes
`run_id` and `ts` on every row, enforcing grounding by structure. `recommend_action`
is a pure lookup table — no model generation for the recommendation itself. The LLM
is required by system prompt to cite `run_id` and `ts` from tool results in every
factual claim.

---

## Background

Phase 3 implements Pattern C (Agentic Diagnosis): a tool-calling ReAct loop where the
LLM decides which historian queries to run, reads the results, and chains calls until
it can form a grounded answer. The historian is a SQLite table `telemetry` with columns
`(id, run_id, ts, component, health, status, metric_name, metric_value, driver_temp,
driver_humidity, driver_load, driver_maint)`. Full schema is in B4.

Two SDKs are in scope:

- **Vercel AI SDK 6** (TypeScript, for the Next.js chat layer): uses `tool()` helper
  with `inputSchema` (Zod) and an `execute` async function; tools are passed to
  `generateText` / `streamText` alongside a `maxSteps` cap.
- **Anthropic Claude API** (direct, fallback / Python layer): uses a `tools` array
  where each tool has `name`, `description`, and `input_schema` (JSON Schema object);
  the loop manually alternates `tool_use` and `tool_result` messages.

Both converge on the same underlying JSON Schema, so the schemas below are written once
and translated mechanically.

---

## Options Considered

### Raw SQL passthrough

Give the LLM a single `execute_sql(query: string)` tool. Maximum flexibility, zero
maintenance per new query type.

**Rejected:** opens SQL injection risk; the LLM routinely writes subtly wrong SQL on
multi-table or window-function queries; no row cap means unbounded context growth;
impossible to enforce run_id citation because the tool does not know what was queried.

### Five named typed tools (chosen)

Each tool wraps one parameterised SQLite query. The tool layer owns the SQL; the LLM
only provides validated enum values and identifiers. Return shapes are fixed and bounded.
Row cap (20) is enforced inside `execute`, never by the LLM.

### Lookup-table `recommend_action`

`recommend_action` could be LLM-generated advice ("based on the degradation curve,
consider replacing the nozzle plate"). Rejected: the LLM has no training on HP Metal Jet
S100 maintenance procedures and would hallucinate. A static decision table keyed on
`(component, status)` produces deterministic, auditable recommendations that can be
shown to HP judges as a citable source.

---

## Recommendation

### Shared types

```typescript
type Component = "recoater_blade" | "nozzle_plate" | "heating_element";
type Status    = "FUNCTIONAL" | "DEGRADED" | "CRITICAL" | "FAILED";
type Severity  = "INFO" | "WARNING" | "CRITICAL";

// Every result row carries identity fields so the LLM can cite them.
interface TelemetryRow {
  run_id:       string;
  ts:           number;   // Unix epoch seconds
  component:    Component;
  health:       number;   // 0.0–1.0
  status:       Status;
  metric_name:  string;
  metric_value: number;
}
```

---

### Tool 1 — `query_health`

Fetch time-series health for a component, optionally within a time window and/or
scoped to a single run.

```typescript
tool({
  description:
    "Retrieve health index and operational status for a specific component " +
    "over a time range, optionally filtered to one run. " +
    "Returns rows ordered by ts ascending, capped at 20 rows " +
    "(most recent if range is large). " +
    "You MUST cite run_id and ts from the returned rows in your answer.",
  inputSchema: z.object({
    component:  z.enum(["recoater_blade","nozzle_plate","heating_element"])
                  .describe("Which subsystem component to inspect"),
    run_id:     z.string().optional()
                  .describe("Historian run identifier, e.g. 'run_042'. Omit to search all runs"),
    ts_from:    z.number().optional()
                  .describe("Start of time window as Unix epoch seconds"),
    ts_to:      z.number().optional()
                  .describe("End of time window as Unix epoch seconds"),
  }),
  execute: async ({ component, run_id, ts_from, ts_to }): Promise<{
    rows: TelemetryRow[];
    total_matching: number;
    capped: boolean;
  }> => { /* parameterised SQL, LIMIT 20 */ }
})
```

**Return shape:** `{ rows: TelemetryRow[]; total_matching: number; capped: boolean }`.
`capped: true` signals the LLM that there are more rows and it should narrow the window.

**Underlying SQL:**

```sql
SELECT run_id, ts, component, health, status, metric_name, metric_value
FROM telemetry
WHERE component = :component
  AND (:run_id IS NULL OR run_id = :run_id)
  AND (:ts_from IS NULL OR ts >= :ts_from)
  AND (:ts_to   IS NULL OR ts <= :ts_to)
ORDER BY ts DESC
LIMIT 21   -- fetch 21 to detect capping; return 20
```

---

### Tool 2 — `get_failure_events`

Return only ticks where a component entered CRITICAL or FAILED, optionally for a
specific severity tier or run.

```typescript
tool({
  description:
    "List all ticks where a component reached CRITICAL or FAILED status. " +
    "Useful for root-cause and timeline investigations. " +
    "Returns up to 20 events ordered by ts ascending. " +
    "Cite run_id and ts for every event you mention.",
  inputSchema: z.object({
    run_id:    z.string().optional(),
    component: z.enum(["recoater_blade","nozzle_plate","heating_element"]).optional()
                 .describe("Filter to one component; omit for all"),
    min_severity: z.enum(["DEGRADED","CRITICAL","FAILED"]).optional()
                    .describe("Minimum status level to include; default CRITICAL"),
  }),
  execute: async ({ run_id, component, min_severity }): Promise<{
    events: TelemetryRow[];
    total_matching: number;
    capped: boolean;
  }> => { /* SQL with IN filter on status */ }
})
```

**Underlying SQL:**

```sql
SELECT run_id, ts, component, health, status, metric_name, metric_value
FROM telemetry
WHERE status IN (/* expand min_severity enum */)
  AND (:run_id    IS NULL OR run_id    = :run_id)
  AND (:component IS NULL OR component = :component)
ORDER BY ts ASC
LIMIT 21
```

---

### Tool 3 — `compare_runs`

Aggregate health statistics for one or both runs, optionally per component.

```typescript
tool({
  description:
    "Compare aggregate health metrics between two simulation runs. " +
    "Returns avg_health, min_health, and first_failure_ts per component per run. " +
    "Always cite both run_id values in your comparative statements.",
  inputSchema: z.object({
    run_a:     z.string().describe("First run identifier"),
    run_b:     z.string().describe("Second run identifier"),
    component: z.enum(["recoater_blade","nozzle_plate","heating_element"]).optional()
                 .describe("Restrict to one component; omit for all three"),
  }),
  execute: async ({ run_a, run_b, component }): Promise<{
    summary: Array<{
      run_id:          string;
      component:       Component;
      avg_health:      number;
      min_health:      number;
      first_failure_ts: number | null;  // null if no FAILED tick
    }>;
  }> => { /* GROUP BY run_id, component + subquery for first FAILED ts */ }
})
```

This tool always returns at most 6 rows (2 runs × 3 components) so no row cap needed.

---

### Tool 4 — `current_status`

Snapshot of the latest tick for all (or one) component(s) within a run.

```typescript
tool({
  description:
    "Return the most recent health, status, and metric value for each component " +
    "in a given run. This is the live snapshot. " +
    "You MUST cite the run_id and the ts of the returned snapshot in your answer.",
  inputSchema: z.object({
    run_id:    z.string().describe("Run to inspect"),
    component: z.enum(["recoater_blade","nozzle_plate","heating_element"]).optional()
                 .describe("Restrict to one component; omit for all"),
  }),
  execute: async ({ run_id, component }): Promise<{
    snapshot: TelemetryRow[];
    snapshot_ts: number;   // MAX(ts) used for this snapshot
  }> => { /* correlated subquery on MAX(ts) */ }
})
```

At most 3 rows; no cap needed.

---

### Tool 5 — `recommend_action`

Return a deterministic maintenance recommendation from a static lookup table. Does not
touch the historian; uses only component + current status derived from a prior tool call.

```typescript
const ACTION_TABLE: Record<Component, Record<Status, {
  action:   string;
  urgency:  "routine" | "soon" | "immediate" | "stop_print";
  rationale: string;
}>> = {
  recoater_blade: {
    FUNCTIONAL: { action: "No action required.",            urgency: "routine",   rationale: "Health nominal." },
    DEGRADED:   { action: "Schedule blade inspection.",     urgency: "soon",      rationale: "Abrasive wear increasing contamination risk." },
    CRITICAL:   { action: "Replace blade before next run.", urgency: "immediate", rationale: "Blade wear will cause powder layer defects." },
    FAILED:     { action: "Stop print. Replace blade now.", urgency: "stop_print",rationale: "Blade cannot form uniform powder bed." },
  },
  nozzle_plate: {
    FUNCTIONAL: { action: "No action required.",                urgency: "routine",   rationale: "Clog % within spec." },
    DEGRADED:   { action: "Run nozzle purge cycle.",            urgency: "soon",      rationale: "Partial clogging reduces binder coverage." },
    CRITICAL:   { action: "Execute full cleaning protocol.",    urgency: "immediate", rationale: "Thermal fatigue + clogging risk voiding part." },
    FAILED:     { action: "Stop print. Replace nozzle plate.", urgency: "stop_print",rationale: "Nozzle plate no longer functional." },
  },
  heating_element: {
    FUNCTIONAL: { action: "No action required.",              urgency: "routine",   rationale: "Resistance within spec." },
    DEGRADED:   { action: "Log resistance trend; next PM.",   urgency: "soon",      rationale: "Electrical degradation beginning." },
    CRITICAL:   { action: "Reduce duty cycle; plan replacement.", urgency: "immediate", rationale: "High resistance wastes energy; thermal control risk." },
    FAILED:     { action: "Stop print. Replace heating element.", urgency: "stop_print",rationale: "Thermal control lost." },
  },
};

tool({
  description:
    "Return a deterministic, lookup-table-based maintenance recommendation " +
    "for a component given its current status. " +
    "Does NOT use model reasoning — output is always identical for the same inputs. " +
    "Call current_status first to get the status, then call this tool. " +
    "Cite the run_id and ts from the current_status call when presenting this recommendation.",
  inputSchema: z.object({
    component: z.enum(["recoater_blade","nozzle_plate","heating_element"]),
    status:    z.enum(["FUNCTIONAL","DEGRADED","CRITICAL","FAILED"]),
  }),
  execute: async ({ component, status }) => ACTION_TABLE[component][status],
})
```

**Why lookup table:** Recommendations are HP-domain knowledge. An LLM would fabricate
procedures. The table is version-controlled, auditable by HP judges, and produces the
same output every time — satisfying the grounding protocol.

---

### Grounding enforcement

The system prompt appends:

```
After every tool call, you will receive rows that include run_id and ts.
You MUST reference at least one (run_id, ts) pair for every factual claim
you make. Format: [run_id=<id>, ts=<epoch>].
If retrieved rows do not support a claim, write INSUFFICIENT_DATA instead.
```

A post-processing validator (see C4) then confirms every cited `run_id` and `ts`
exists in the historian before the response is returned to the operator.

---

### Sample tool-call trace

```
User: "Why is the nozzle plate degrading faster in run_007 than run_003?"

Step 1 → compare_runs(run_a="run_007", run_b="run_003", component="nozzle_plate")
  Result: run_007 avg_health=0.61, min_health=0.31, first_failure_ts=null
          run_003 avg_health=0.79, min_health=0.58, first_failure_ts=null

Step 2 → query_health(component="nozzle_plate", run_id="run_007", ts_from=0)
  Result: rows showing health dropping steeply from ts=7200; capped=true

Step 3 → get_failure_events(run_id="run_007", component="nozzle_plate", min_severity="DEGRADED")
  Result: first DEGRADED at ts=7240, driver_humidity=0.87 at that tick

Step 4 → recommend_action(component="nozzle_plate", status="DEGRADED")
  Result: { action: "Run nozzle purge cycle.", urgency: "soon", ... }

Final answer:
"Run 007 shows faster nozzle degradation because humidity spiked to 0.87 at
ts=7240 [run_id=run_007, ts=7240], triggering accelerated clogging. Run 003
maintained humidity below 0.55 throughout. Recommended action: run nozzle purge
cycle (urgency: soon) [run_id=run_007, ts=<latest>]. Severity: WARNING."
```

---

## Open Questions

1. **Multiple metrics per tick:** If Phase 1 writes two rows per component per tick
   (e.g. nozzle: `clog_pct` and `temp_stress`), `query_health` and `current_status`
   need a `metric_name` filter or should aggregate — decide when Phase 1 schema is final.
2. **run_id enumeration:** The LLM needs to know valid run IDs. Add a `list_runs()` tool
   (trivial `SELECT DISTINCT run_id FROM telemetry`) or inject the list into the system
   prompt at session start.
3. **Streaming tool results:** Vercel AI SDK 6 `streamText` streams tool call inputs
   before execute completes. For a 60-second demo, batch mode is simpler — decide per UI.
4. **Row cap tuning:** 20 rows at ~100 tokens each = ~2 000 tokens per tool call.
   With 8 maxSteps and 4 tool calls per chain, peak retrieval is ~8 000 tokens — well
   within Claude's 200 k context. Cap can be raised to 50 if more resolution is needed.

---

## References

- [Vercel AI SDK Core: tool()](https://ai-sdk.dev/docs/reference/ai-sdk-core/tool)
- [AI SDK 6 announcement — Vercel](https://vercel.com/blog/ai-sdk-6)
- [Anthropic: Define tools (tool_use)](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use)
- [Anthropic: Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- [SQLite as MCP context saver — DEV Community](https://dev.to/richardbaxter/sqlite-as-an-mcp-context-saver-stop-cramming-raw-api-data-into-your-llm-2oj4)
- [Context bloat problems in AI agents — Agenteer](https://agenteer.com/blog/the-two-context-bloat-problems-every-ai-agent-builder-must-understand/)
- [C1-pattern-choice.md](./C1-pattern-choice.md) — ReAct loop and SDK comparison
- [C4-citation-enforcement.md](./C4-citation-enforcement.md) — post-processing validator
- [B4-historian-schema.md](./B4-historian-schema.md) — SQLite DDL and index strategy
