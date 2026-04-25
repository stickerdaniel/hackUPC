# D3 — Topology: sim/ + data/ + web/ monorepo data bridge

## TL;DR

For a local hackathon demo, use **option (a): `better-sqlite3`** in Next.js API routes.
It is synchronous, zero-latency, and requires no extra process.
If deployment to Vercel becomes necessary, swap to **option (b): `@libsql/client`**
with a single URL change — no other code changes needed.
Option (c) FastAPI is only worth adding if the Python sim already needs an HTTP interface
for other reasons (e.g., triggering sim runs from the UI).

---

## Background

The Python sim writes telemetry rows to `data/historian.sqlite` at a configurable tick
rate. The Next.js web app needs to read those rows to render dashboards and feed the
AI chatbot context. The question is which data bridge avoids the most friction in a
time-boxed hackathon setting.

---

## Options considered

### (a) `better-sqlite3` — TS-side, synchronous, local only

- Native C++ addon; ships prebuilt binaries for Node.js LTS on Linux/Mac/Win.
- Fully synchronous API: no `await`, no connection lifecycle — one import, one call.
- Works in Next.js API routes and `getServerSideProps` (Node.js runtime only, not Edge).
- **Does not work on Vercel serverless** because native bindings require a build step
  that Vercel's ephemeral lambda environment does not support reliably, and the
  filesystem is ephemeral anyway (writes are lost between invocations).
- Install: `npm install better-sqlite3` + `npm install -D @types/better-sqlite3`
- Usage: `const db = new Database('data/historian.sqlite'); db.prepare('SELECT …').all()`

### (b) `@libsql/client` — TS-side, async, local + cloud swap

- Pure-JS/WASM driver; no native bindings. Works anywhere Node.js runs, including Vercel
  serverless (Node runtime, not Edge). Edge Runtime requires a remote `libsql://` URL.
- Local mode: `createClient({ url: 'file:data/historian.sqlite' })` — reads the same
  SQLite file that Python writes; no format conversion needed.
- Production swap: change URL to `libsql://your-db.turso.io` with an auth token; all
  `db.execute()` calls remain identical.
- Slightly more boilerplate than (a) due to async/await, but negligible.
- Install: `npm install @libsql/client`
- Usage: `const db = createClient({ url: 'file:data/historian.sqlite' }); await db.execute({ sql: 'SELECT …', args: [] })`

### (c) FastAPI shim — Python HTTP bridge

- A thin `uvicorn`-served FastAPI app exposes REST endpoints that query SQLite and return
  JSON; Next.js fetches from `http://localhost:8000`.
- Adds a second process to start, a second port to manage, CORS config, and a Python
  dependency group separate from the sim.
- Useful if the UI also needs to trigger sim runs or write back to the DB, since Python
  already owns the sim loop. Cross-language HTTP is well-understood.
- Minimal install: `pip install fastapi uvicorn` (sqlite3 is stdlib).
- Minimal app: ~20 lines — `app = FastAPI()`, `@app.get('/metrics')`, `conn = sqlite3.connect(DB_PATH)`, return rows as dicts.
- For a read-only demo this is the most overhead for the least gain.

---

## Recommendation

**Primary (local demo): option (a) `better-sqlite3`.**

```bash
# web/ directory
npm install better-sqlite3
npm install -D @types/better-sqlite3
```

Create `web/lib/db.ts`:
```ts
import Database from 'better-sqlite3';
import path from 'path';

const db = new Database(path.resolve(process.cwd(), '../data/historian.sqlite'), {
  readonly: true,
  fileMustExist: true,
});

export default db;
```

Next.js API route (`web/app/api/metrics/route.ts`):
```ts
import db from '@/lib/db';
export function GET() {
  const rows = db.prepare('SELECT * FROM sensor_readings ORDER BY ts DESC LIMIT 100').all();
  return Response.json(rows);
}
```

Chatbot tools query the DB the same way: call the `/api/metrics` route (or a dedicated
`/api/tool/[name]` route) from the AI SDK tool handler, passing structured args as query
params or POST body.

**Fallback (Vercel deploy): option (b) `@libsql/client`.**
Replace `better-sqlite3` import with `@libsql/client`; change `url` from `file:…` to
`process.env.TURSO_URL`; add `authToken: process.env.TURSO_TOKEN`. No other changes.

---

## Open questions

1. Does the sim need to be triggered from the UI? If yes, add FastAPI just for that
   control plane endpoint and keep DB reads in TS.
2. Will the demo machine be the same OS/arch that `better-sqlite3` was compiled on?
   If not, run `npm rebuild better-sqlite3` after cloning.
3. Is read concurrency a concern? SQLite WAL mode (`PRAGMA journal_mode=WAL`) lets the
   Python writer and Node reader coexist safely without locking.

---

## References

- [better-sqlite3 npm](https://www.npmjs.com/package/better-sqlite3)
- [better-sqlite3 guide 2025](https://generalistprogrammer.com/tutorials/better-sqlite3-npm-package-guide)
- [@libsql/client GitHub](https://github.com/tursodatabase/libsql-client-ts)
- [Is SQLite supported in Vercel?](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel)
- [Use this instead of SQLite on Vercel](https://www.hrekov.com/blog/sqlite-vercel)
- [Next.js + Prisma 7 + SQLite with libSQL](https://revione.medium.com/next-js-prisma-7-sqlite-the-modern-way-to-use-sql-with-libsql-21e207ce2235)
- [FastAPI SQL Databases tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [Prototyping on Vercel: comparing embedded DBs](https://codenote.net/en/posts/vercel-nextjs-embedded-database-prototyping/)
