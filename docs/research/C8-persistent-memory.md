# C8 — Persistent Memory: Per-Session Conversation History

**Pillar:** AUTONOMY bonus
**Status:** Decision required — skip or include

---

## TL;DR

Include it. Use a server-side `Map<sessionId, Message[]>` keyed by a browser-generated UUID stored in `localStorage`. Roll the last 10 turns into every system prompt. Zero new dependencies, ~30 lines of code, visible payoff in the demo ("you mentioned the blade earlier").

---

## Background

Phase 3 is a grounded chatbot over the historian. By default, each request is stateless: the LLM sees no prior conversation turns. Adding per-session memory lets the co-pilot reference earlier questions ("the nozzle clog you asked about two turns ago is now CRITICAL") without querying the DB again, which sharpens the "autonomous collaborator" evaluation pillar.

---

## Options Considered

### 1. Skip (baseline)

Each request is fully self-contained. Operator must re-state context every turn. Zero implementation cost.

Rejected because the demo impact of cross-turn awareness is disproportionately large for a ~30-line addition.

### 2. In-memory Map on the API server (recommended)

Server process holds `const sessions = new Map<string, Message[]>()`. Browser generates a UUID on first load (`crypto.randomUUID()`), stores it in `localStorage`, and sends it as `X-Session-Id` with every request. The API route appends each user+assistant turn to the slice, then injects the last N turns into the system prompt before calling the LLM. No external service needed.

Limitation: memory is lost on server restart. For a 24-hour hackathon demo, this is irrelevant.

### 3. Persistent DB (SQLite / Redis)

True durability across restarts. Adds schema, migrations, and a Redis sidecar or extra SQLite table. Overkill for 24 h; the historian SQLite already owns persistence for the simulation data.

Rejected on time budget.

### 4. Framework memory (mem0, LangChain ConversationBufferWindowMemory, Anthropic memory tool)

Mem0 benchmarks well (91% lower latency vs full-context) but requires an API key and an external service. LangChain `ConversationBufferWindowMemory` matches the in-memory Map semantics with more abstraction and an extra dependency. Anthropic's memory tool is still experimental.

All rejected: each adds a dependency or API key for functionality we can implement inline in 30 lines.

---

## Recommendation — Include (in-memory Map)

**Implementation sketch (Next.js API route):**

```ts
// lib/sessions.ts
export const sessions = new Map<string, CoreMessage[]>();

// In the route handler:
const sid = req.headers.get("x-session-id") ?? "default";
const history = sessions.get(sid) ?? [];
const windowedHistory = history.slice(-20); // last 10 turns = 20 messages

const messages: CoreMessage[] = [
  { role: "system", content: SYSTEM_PROMPT },
  ...windowedHistory,
  { role: "user", content: userMessage },
];

const result = await streamText({ model, messages });

// After streaming, persist both turns:
sessions.set(sid, [
  ...history,
  { role: "user", content: userMessage },
  { role: "assistant", content: await result.text },
].slice(-40)); // hard cap at 40 messages (~20 turns) to bound context
```

**Client UUID generation (once, on mount):**

```ts
const sid = localStorage.getItem("sessionId") ?? crypto.randomUUID();
localStorage.setItem("sessionId", sid);
// attach as header in useChat: headers: { "x-session-id": sid }
```

**Context bounding:** keep last 10 turns (20 messages). At ~200 tokens/turn, that is ~2 000 tokens of history — well within model context limits and leaving headroom for RAG-injected historian rows.

---

## Open Questions

- Should the session UUID reset when the user clicks "New Session"? Yes — clear `localStorage` key and let the server naturally start a fresh slice.
- Does serverless deployment (Vercel) kill the in-memory Map between requests? Yes, each cold start loses state. Run on a long-lived Node process (Railway, Fly.io) or accept the loss for demo purposes — for a 24 h hack, either is fine.
- Should we summarize older turns instead of truncating? Nice-to-have if time permits (one extra LLM call to produce a running summary), but truncation at 10 turns is sufficient.

---

## References

- [Guidance on persisting messages — vercel/ai Discussion #4845](https://github.com/vercel/ai/discussions/4845)
- [Working With Message Histories In Vercel's AI SDK — aihero.dev](https://www.aihero.dev/vercel-ai-sdk-messages-array)
- [Vercel AI SDK useChat in Production — DEV Community](https://dev.to/whoffagents/vercel-ai-sdk-usechat-in-production-lessons-from-30-days-of-real-traffic-4gbo)
- [Saving AI SDK v5 Chat Messages in Redis — Upstash Blog](https://upstash.com/blog/ai-sdk-chat-history)
- [Conversation Buffer Window Memory in LangChain — GeeksforGeeks](https://www.geeksforgeeks.org/artificial-intelligence/conversation-buffer-window-memory-in-langchain/)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory — arXiv](https://arxiv.org/html/2504.19413v1)
- [AI Memory Systems Benchmark: Mem0 vs OpenAI vs LangMem 2025](https://guptadeepak.com/the-ai-memory-wars-why-one-system-crushed-the-competition-and-its-not-openai/)
