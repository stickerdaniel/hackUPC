# C5 — Severity Tagging

**TL;DR:** Compute severity deterministically in the tool layer using a fixed
mapping from the `status` enum. The LLM never decides severity. The response
schema carries a top-level `severity` field (max across all cited components)
plus per-claim severity in the evidence array. The UI maps severity to a badge
color; each cited component gets its own inline badge.

---

## Background

Phase 3 responses must include a Severity Indicator (`INFO` / `WARNING` /
`CRITICAL`) per the grounding protocol. The `status` enum from the historian
already encodes the exact same information in categorical form: `FUNCTIONAL`,
`DEGRADED`, `CRITICAL`, `FAILED`. Asking the LLM to invent a severity label
from prose introduces non-determinism and hallucination risk with no benefit —
the ground truth is already a structured field in the database row.

---

## Options Considered

### Option A: LLM-assigned severity

The LLM reads the component narrative and chooses `INFO / WARNING / CRITICAL`
from its own judgment.

Drawbacks: non-deterministic; the same status row could yield different labels
on different runs; LLM may upgrade or downgrade severity to sound helpful;
breaks the zero-hallucination contract; impossible to unit-test.

### Option B: Tool-layer deterministic mapping (chosen)

Each tool (`current_status`, `get_failure_events`, `query_health`, etc.)
returns structured rows from the historian. Before the LLM ever sees the data,
a thin Python function maps `status` → severity and attaches it to each row.
The LLM is instructed to copy the severity field verbatim into its structured
response; it may not override it.

Benefits: fully deterministic; testable with a two-line assertion; consistent
with the historian-as-ground-truth contract; severity is computed once at the
tool boundary, not re-derived from prose.

---

## Recommendation

### Mapping Table

| `status` (historian) | Severity tag |
|----------------------|--------------|
| `FUNCTIONAL`         | `INFO`       |
| `DEGRADED`           | `WARNING`    |
| `CRITICAL`           | `CRITICAL`   |
| `FAILED`             | `CRITICAL`   |

`CRITICAL` and `FAILED` both map to `CRITICAL` because from the operator's
perspective both require immediate action; distinguishing them adds UI
complexity with no operational benefit.

### Multi-component Rule

When a single chatbot answer cites N components with different severities, two
fields are used:

- **`severity`** (top-level): the maximum severity across all cited components,
  following the ordering `INFO < WARNING < CRITICAL`. This drives the main
  response badge that the operator sees first.
- **`evidence[].severity`**: per-claim severity attached to each historian row
  cited. The UI can render inline per-component badges.

"Max-severity wins" at the response level ensures the operator is never
under-alerted when one healthy component appears alongside a failing one.

### Response Schema

```json
{
  "severity": "WARNING",
  "answer": "The nozzle plate is degraded ...",
  "evidence": [
    {
      "run_id": "run-042",
      "ts": 1714000800,
      "component": "nozzle_plate",
      "status": "DEGRADED",
      "severity": "WARNING",
      "health": 0.61,
      "metric_name": "nozzle_clog_pct",
      "metric_value": 38.2
    },
    {
      "run_id": "run-042",
      "ts": 1714000800,
      "component": "recoater_blade",
      "status": "FUNCTIONAL",
      "severity": "INFO",
      "health": 0.89,
      "metric_name": "blade_thickness_mm",
      "metric_value": 2.1
    }
  ]
}
```

The `severity` field on each evidence item is injected by the tool function
(`status_to_severity(row["status"])`) before the row reaches the LLM context.

### UI Badge Spec

| Severity   | Color token     | Hex suggestion |
|------------|-----------------|----------------|
| `INFO`     | `badge-info`    | `#3B82F6` (blue)   |
| `WARNING`  | `badge-warning` | `#F59E0B` (amber)  |
| `CRITICAL` | `badge-critical`| `#EF4444` (red)    |

Top-level badge: displayed prominently in the chat bubble header.
Per-evidence badge: small inline pill next to component name in the citation
list below the answer text.

---

## Open Questions

1. **Proactive alert threshold:** the background monitor (Phase 3 bonus) should
   fire on `WARNING` or `CRITICAL`. Decide whether a single `DEGRADED` component
   is enough to push a proactive alert or only `CRITICAL`/`FAILED`.
2. **Transition events:** should the tool layer emit severity only on the latest
   tick, or also on the tick where status *changed* (e.g. `FUNCTIONAL` →
   `DEGRADED`)? Transition severity could surface as a `WARNING` even if the
   component later recovered.
3. **Aggregated run-level severity:** `compare_runs` answers that span thousands
   of ticks — should the response severity be the max over the entire run or only
   the max at the latest tick?

---

## References

- TRACK-CONTEXT.md §3.2 — Operational Status enum definition
- TRACK-CONTEXT.md §Phase 3 — Grounding Protocol (Severity Indicator requirement)
- B4-historian-schema.md — historian DDL and tool query patterns
- General practice: deterministic severity in alerting pipelines (PagerDuty,
  Prometheus alertmanager) always derives alert level from structured metrics,
  not from text summarization.
