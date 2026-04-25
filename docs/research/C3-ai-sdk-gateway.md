# C3 - AI SDK / Gateway: Vercel AI SDK v6 + AI Gateway vs Raw Anthropic SDK

## TL;DR

Use **Vercel AI SDK v6** (`ai` package) with **`@ai-sdk/gateway`** for all LLM calls.
The abstraction cost is near-zero; the payoff is automatic multi-provider fallback,
OIDC zero-credential deploys on Vercel, and a unified tool-calling API that works
across Anthropic, OpenAI, and Google without any router code of our own.

---

## Background

Phase 3 of the co-pilot is an LLM chatbot with tool-calling (querying printer state,
reading maintenance history, fetching part specs). The stack target is Next.js App
Router on Vercel. Two options were evaluated for the inference layer.

---

## Options Considered

### Option A: Vercel AI SDK v6 + AI Gateway

- **Package**: `ai` (core), `@ai-sdk/gateway` (provider), `zod` (schemas).
- **Tool API (v6)**: `tool({ description, inputSchema: z.object({...}), execute })`.
  The field is `inputSchema`, not `parameters` — renamed in v5 / v6.
- **Streaming**: `streamText({ model, messages, tools })` returns
  `result.toUIMessageStreamResponse()` — works natively with Next.js Route Handlers.
- **Gateway**: single endpoint `https://ai-gateway.vercel.sh/v1/ai`, model strings
  like `anthropic/claude-sonnet-4-5`. Failover across Anthropic direct, Bedrock, and
  Vertex AI is automatic. Latency overhead: < 20 ms per request.
- **Auth on Vercel**: OIDC token (`VERCEL_OIDC_TOKEN`) — no API key stored in secrets
  when deployed. Local dev: `AI_GATEWAY_API_KEY` from Vercel dashboard.
- **Cost**: Gateway passes through provider pricing at zero markup. Every team gets
  $5 free credits/month; BYOK is supported for the team's own Anthropic key.
- **v6 extras**: `Agent` abstraction for reusable agents, human-in-the-loop tool
  approval (`needsApproval`), MCP tool integration, DevTools panel.

### Option B: Raw `@anthropic-ai/sdk` + Custom Router

- Direct access to every Anthropic feature, no abstraction layer.
- Tool syntax: `tools: [{ name, description, input_schema: {...} }]` (JSON Schema, not
  Zod) plus a manual tool-dispatch loop.
- No built-in fallback; a custom router would need to handle provider outages.
- Streaming requires manual SSE plumbing; no `useChat` hook.
- More code, more surface area, same capability for a 24 h hackathon.

---

## Recommendation

**Chosen stack: Option A.**

DX wins and fallback resilience justify the thin abstraction for a hackathon. The
AI Gateway's automatic Anthropic -> Bedrock -> Vertex failover means a provider blip
does not demo-kill us. OIDC auth means zero secret management on the deployed URL.

### npm packages

```
npm install ai @ai-sdk/gateway zod
```

### Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `AI_GATEWAY_API_KEY` | `.env.local` | Auth for Gateway in local dev |
| `VERCEL_OIDC_TOKEN` | Auto-injected by Vercel | Auth in deployment (no secret needed) |

BYOK (optional): add own Anthropic key in Vercel Dashboard -> AI Gateway -> Credentials
so calls route directly and use team quota, not the $5 credit pool.

### Code skeleton: one tool call

```typescript
// app/api/chat/route.ts
import { streamText, tool } from "ai";
import { gateway } from "@ai-sdk/gateway";
import { z } from "zod";

const getPrinterStatus = tool({
  description: "Return current status and nozzle health for a Metal Jet S100 printer.",
  inputSchema: z.object({
    printerId: z.string().describe("Printer serial number"),
  }),
  execute: async ({ printerId }) => {
    // Replace with real historian / OPC-UA call
    return { printerId, status: "idle", nozzleHealth: 0.94 };
  },
});

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: gateway("anthropic/claude-sonnet-4-5"),
    system: "You are the HP Metal Jet S100 Digital Co-Pilot.",
    messages,
    tools: { getPrinterStatus },
    maxSteps: 5, // allow automatic tool-call roundtrips
  });

  return result.toUIMessageStreamResponse();
}
```

Client-side hook (`useChat` from `ai/react`) consumes this without changes.

---

## Open Questions

1. **Credit headroom**: $5/month of gateway credits is enough for demo traffic but
   confirm BYOK is set up before the live demo to avoid hitting the cap mid-run.
2. **`maxSteps` limit**: default is 1 step; set to 5+ for agentic loops where the
   model may call multiple tools before producing a final response.
3. **AI SDK v6 `inputSchema` bug**: GitHub issue #12020 reports empty `input_schema`
   sent to Anthropic in some v6 builds — verify with the exact `ai` version pinned
   in `package.json` before demo day.
4. **Gateway model string currency**: model IDs change; run
   `curl https://ai-gateway.vercel.sh/v1/models` at setup time to confirm
   `anthropic/claude-sonnet-4-5` is still current.

---

## References

- [AI SDK 6 launch post](https://vercel.com/blog/ai-sdk-6)
- [AI SDK Core: Tool Calling](https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling)
- [AI SDK Core: streamText reference](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text)
- [AI Gateway provider docs](https://ai-sdk.dev/providers/ai-sdk-providers/ai-gateway)
- [AI Gateway overview](https://vercel.com/docs/ai-gateway)
- [AI Gateway models & providers](https://vercel.com/docs/ai-gateway/models-and-providers)
- [AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
- [AI Gateway BYOK](https://vercel.com/docs/ai-gateway/authentication-and-byok/byok)
- [Migration Guide: v5 -> v6](https://ai-sdk.dev/docs/migration-guides/migration-guide-6-0)
- [GitHub issue #12020: empty inputSchema on Anthropic](https://github.com/vercel/ai/issues/12020)
- [Vercel AI Gateway DeepWiki](https://deepwiki.com/vercel/ai/3.11-vercel-ai-gateway)
