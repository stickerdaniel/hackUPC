# C6 — Proactive Alerting

**TL;DR:** Use a Next.js App Router SSE route handler (`GET /api/alerts/stream`)
that polls SQLite every 5 seconds and pushes `CRITICAL`/`FAILED` events to the
browser. No third-party pub/sub, no Vercel Cron, no WebSocket. One route file
+ one React hook = done.

---

## Background

The AUTONOMY bonus pillar requires the system to warn the operator
*before* they ask. The historian already contains `status` per component per
tick (see B4-historian-schema). The triggering condition is any component whose
`status` is `CRITICAL` or `FAILED` at the latest recorded tick. The delivery
path needs to be push (not pull-on-demand) to feel proactive.

Stack constraint: Next.js 15 App Router on Vercel (serverless). The Python sim
writes to SQLite continuously on the same host (or the DB is shared via a
mounted volume / Turso / libSQL over HTTP).

---

## Options Considered

### Option 1 — WebSocket

WebSocket requires a persistent, stateful TCP connection. Vercel serverless
functions are stateless and ephemeral; they cannot act as a WebSocket server.
Vercel's own KB confirms this explicitly and recommends third-party services
(Pusher, Ably). Even with Fluid Compute (2025), streaming responses work but
bidirectional WebSocket connections do not.

Verdict: eliminated — needs an extra paid service.

### Option 2 — Vercel Cron

Vercel Cron invokes a serverless function on a schedule (minimum 1-minute
interval on Pro; no sub-minute). It could write alerts to a queue that the
client polls. That requires a persistence layer (Redis, DB table) just to relay
the event, adds latency of up to 60 s, and is over-engineered for a hackathon
demo.

Verdict: eliminated — 1-minute floor is too coarse; extra complexity.

### Option 3 — Client-side polling (React Query `refetchInterval`)

The browser calls `GET /api/alerts` every N seconds; the route handler does a
single synchronous SQLite read and returns JSON. Dead-simple, no streaming API,
works everywhere. Downside: the client drives the interval (battery, tab focus),
and every poll is a new cold HTTP request. Fine for 5–10 s intervals; alert
latency equals the interval.

Verdict: valid fallback, but SSE is barely harder and gives true push semantics.

### Option 4 — SSE from a Next.js route handler (chosen)

The browser opens one long-lived `EventSource` connection. The route handler
returns a `ReadableStream` with `Content-Type: text/event-stream`. Inside the
stream, a `setInterval` polls SQLite every 5 s, checks for CRITICAL/FAILED
status at the latest tick, and enqueues an event if found. When the client
disconnects, `request.signal` fires `abort` and the interval is cleared.

Works on Vercel because SSE is unidirectional streaming — no persistent socket
state is needed; Vercel's fluid-compute model keeps the function alive while the
response stream is open. `export const dynamic = 'force-dynamic'` prevents
caching of the endpoint.

---

## Recommendation

### Route handler skeleton

```ts
// app/api/alerts/stream/route.ts
import Database from "better-sqlite3";

export const dynamic = "force-dynamic";

const POLL_MS = 5_000;
const CRITICAL_STATUSES = new Set(["CRITICAL", "FAILED"]);

function queryCritical(db: ReturnType<typeof Database>) {
  return db
    .prepare(
      `SELECT component, status, health_index, ts
       FROM component_ticks
       WHERE ts = (SELECT MAX(ts) FROM component_ticks)
         AND status IN ('CRITICAL','FAILED')`
    )
    .all() as Array<{
    component: string;
    status: string;
    health_index: number;
    ts: number;
  }>;
}

export async function GET(request: Request) {
  const db = new Database(process.env.HISTORIAN_DB_PATH!);

  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();

      const send = (event: string, data: unknown) => {
        controller.enqueue(
          enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };

      // Initial heartbeat so the client knows the connection is live
      send("ping", { ts: Date.now() });

      const interval = setInterval(() => {
        try {
          const rows = queryCritical(db);
          if (rows.length > 0) {
            send("critical-alert", { alerts: rows, ts: Date.now() });
          } else {
            send("ping", { ts: Date.now() });
          }
        } catch (err) {
          // DB not ready yet; swallow and retry next tick
        }
      }, POLL_MS);

      request.signal.addEventListener("abort", () => {
        clearInterval(interval);
        db.close();
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

### Client hook skeleton

```ts
// hooks/useAlertStream.ts
import { useEffect, useState } from "react";

export type Alert = {
  component: string;
  status: string;
  health_index: number;
  ts: number;
};

export function useAlertStream() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    const es = new EventSource("/api/alerts/stream");

    es.addEventListener("critical-alert", (e) => {
      const { alerts } = JSON.parse(e.data) as { alerts: Alert[] };
      setAlerts(alerts);
    });

    es.onerror = () => es.close(); // reconnect handled by browser automatically

    return () => es.close();
  }, []);

  return alerts;
}
```

Usage: `const alerts = useAlertStream()` in any component; render a toast or
banner when `alerts.length > 0`. The browser auto-reconnects `EventSource` on
drop with exponential backoff by spec.

---

## Open Questions

1. **SQLite access on Vercel:** if the sim runs as a separate process on the
   same Vercel machine, a shared file path works. If deployed separately, swap
   `better-sqlite3` for `@libsql/client` (Turso) or expose the DB via an HTTP
   endpoint from the sim process.
2. **Alert deduplication:** the client will receive repeated `critical-alert`
   events every 5 s while the component stays CRITICAL. Use a `lastAlertedTs`
   ref in the hook to suppress re-toasts for the same component within a
   cooldown window (e.g. 60 s).
3. **WARNING threshold:** current query only surfaces CRITICAL/FAILED. Consider
   also streaming DEGRADED components at a lower priority (separate event name
   `degraded-alert`) — see C5-severity-tagging open question 1.
4. **Vercel function timeout:** Vercel Pro allows up to 300 s max duration for
   streaming functions; Hobby is 60 s. For demo purposes this is fine. For
   production, add a client-side reconnect timer.

---

## References

- Next.js App Router route handlers:
  https://nextjs.org/docs/app/building-your-application/routing/route-handlers
- Vercel WebSocket KB (no WebSocket server support on serverless):
  https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections
- Vercel Cron Jobs docs (1-minute minimum):
  https://vercel.com/docs/cron-jobs/usage-and-pricing
- SSE in Next.js discussion thread:
  https://github.com/vercel/next.js/discussions/48427
- TanStack Query polling docs (client polling fallback reference):
  https://tanstack.com/query/latest/docs/framework/react/guides/polling
- Vercel realtime options overview:
  https://vercel.com/kb/guide/publish-and-subscribe-to-realtime-data-on-vercel
- C5-severity-tagging.md — severity mapping from status enum
- B4-historian-schema.md — historian DDL (`component_ticks` table)
