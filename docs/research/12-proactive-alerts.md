# 12 — Proactive Alerts: Pattern + Stack

## TL;DR

For the Phase 3 **Autonomy** pillar, fire alerts the moment any component crosses into `CRITICAL` *without the operator asking*. The simplest pattern that survives a 60-second live demo: **write `events` rows at simulation tick when status transitions, then poll `GET /api/alerts?since=<ts>` from the React client every 2 s and surface new events as a Sonner toast plus a persistent banner**. Skip SSE/WebSockets. Polling SQLite over Next.js route handlers is boring, deterministic, replayable, and impossible to break on stage.

## Background

Phase 2 already runs a deterministic loop that writes per-component health to SQLite each tick. Phase 3 needs a "voice" — but for Autonomy points, the twin must speak first. That means a feedback path from sim → UI that does not depend on the user typing in the chat.

Three architectural axes:

| Axis | Options |
| :--- | :--- |
| Transport | SSE, WebSocket (Pusher/Ably), client polling |
| Threshold logic | Computed at sim tick, or recomputed on read |
| UI surface | Toast, banner, both |

Constraints: 36 hours, two devs, one demo machine, judges sitting two metres away. We don't need 10k concurrent connections; we need *one* connection to survive 60 seconds of speaking.

## Decision

### Transport — client polling, every 2 seconds

`GET /api/alerts?since=<unix_ms>` returns all `events` rows newer than `since`. Client keeps the latest seen `ts`, fires `setInterval` at 2000 ms.

Why not SSE: Next.js App Router does support SSE via `ReadableStream` in a route handler with `Cache-Control: no-cache`, `Content-Type: text/event-stream`, and `export const dynamic = "force-dynamic"`. Vercel even allows it (Fluid Compute gives 300 s on Hobby, Edge runtime needs first byte within 25 s). It works. But it adds a stream lifecycle, a heartbeat, reconnect logic, and a class of bugs ("why is the stream silent?") that we cannot afford to debug at 03:00. Polling is one `fetch` and one `setState`.

Why not Pusher/Ably: external dependency, auth, free-tier quirks, and a network round-trip we don't need when the sim runs on the same laptop as the UI.

### Threshold logic — at simulation tick (write to `events` table)

The sim already owns the previous-and-next state per tick. Detecting a `DEGRADED → CRITICAL` transition is a single comparison there. Doing it on-the-fly in the API route means re-scanning health rows on every poll and re-deriving "did it just cross?" — wasteful and harder to dedupe.

**Schema:**

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,           -- unix ms, sim time
  run_id TEXT NOT NULL,
  component TEXT NOT NULL,       -- 'recoater_blade' | 'nozzle_plate' | 'heating_element'
  severity TEXT NOT NULL,        -- 'WARNING' | 'CRITICAL' | 'FAILED'
  prev_status TEXT NOT NULL,
  new_status TEXT NOT NULL,
  health REAL NOT NULL,
  ttf_hours REAL,                -- predicted time-to-failure, NULL if not computable
  recommended_action TEXT NOT NULL,
  payload_json TEXT              -- full structured payload for the chatbot to cite
);
CREATE INDEX idx_events_ts ON events(ts);
```

Deterministic, replayable, citable from the chatbot (`see also event #42`).

### Alert payload (JSON shape returned by `/api/alerts`)

```json
{
  "alerts": [
    {
      "id": 42,
      "ts": 1714060800000,
      "run_id": "demo-2026-04-25-A",
      "component": "nozzle_plate",
      "severity": "CRITICAL",
      "transition": { "from": "DEGRADED", "to": "CRITICAL" },
      "health": 0.18,
      "metrics": { "clog_pct": 71.4, "temp_stress_c": 12.3 },
      "ttf_hours": 6.2,
      "recommended_action": "Schedule purge cycle within 6 h; reduce humidity setpoint to 35%.",
      "evidence": { "table": "health", "run_id": "demo-2026-04-25-A", "ts": 1714060800000 }
    }
  ],
  "server_ts": 1714060802137
}
```

The `evidence` block lets the chatbot quote the same row when the operator follows up. `server_ts` becomes the next `since`.

### UI — Sonner toast **plus** sticky banner

- **Sonner toast** (already in shadcn) for the moment-of-arrival hit. Severity-coloured, includes component + recommended action + a "Show me" button that routes the chatbot to the relevant timestamp.
- **Sticky banner** at the top of the dashboard while any component is currently `CRITICAL` or `FAILED`. The banner is derived from the latest `health` snapshot, not the event stream, so it stays visible after the toast dismisses.

Toasts are ephemeral (operator looks away → misses it). Banners are persistent (judges scrolling the chat → still see the warning). Both is the right answer.

## Why this fits our case

- **Demo determinism.** Sim writes events at known ticks; the demo script can hit "go" and the alert fires on a known second.
- **One process, no infra.** Sim writes SQLite, Next.js reads SQLite, no extra service to start on stage.
- **2 s latency is invisible.** Judges won't see the difference between push and 2 s polling.
- **Chatbot grounding for free.** Every alert is already a row in `events` with an `evidence` pointer — the RAG layer cites it directly.
- **Failure mode is graceful.** If polling hiccups, the next tick catches up; an SSE drop would freeze the UI silently.

## References

- [Real-Time Notifications with SSE in Next.js — Pedro Alonso](https://www.pedroalonso.net/blog/sse-nextjs-real-time-notifications/)
- [Next.js SSE Guide 2026 — nextjslaunchpad](https://nextjslaunchpad.com/article/nextjs-server-sent-events-real-time-notifications-progress-tracking-live-dashboards)
- [Fixing Slow SSE Streaming in Next.js and Vercel — Medium](https://medium.com/@oyetoketoby80/fixing-slow-sse-server-sent-events-streaming-in-next-js-and-vercel-99f42fbdb996)
- [Vercel Functions Limits](https://vercel.com/docs/functions/limitations)
- [Vercel Function Max Duration](https://vercel.com/docs/functions/configuring-functions/duration)
- [SSE Time Limits — Vercel Community](https://community.vercel.com/t/sse-time-limits/5954)
- [Sonner — shadcn/ui](https://ui.shadcn.com/docs/components/radix/sonner)

## Open questions

- **Dedup across reloads.** If the operator refreshes mid-demo, do we replay the last N alerts as toasts, or only show the banner? Lean: banner only on reload, toasts only for events arriving after mount.
- **Maintenance acknowledgement.** Should clicking "acknowledge" on a toast write back to `events` (`acknowledged_ts`) so the chatbot knows the operator saw it? Probably yes for the Collaborative Memory bonus point.
- **Predicted TTF source.** Compute from the degradation slope of the last K ticks, or extract from the failure model directly? Cheaper to slope-fit; defer model-derived TTF to a stretch goal.
- **Demo-time accelerator.** Sim `dt` will be much faster than wall-clock. Confirm `2000 ms` poll cadence still resolves transitions cleanly when one wall-second equals one sim-hour.
