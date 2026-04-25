# 11 — Vercel AI SDK v6 + AI Gateway (vs. raw Anthropic SDK)

> Phase 3 stack decision: chatbot, tool-calling over the SQLite historian, streaming UI in a Next.js App Router app.

## TL;DR

- **Use Vercel AI SDK v6 + AI Gateway.** One key, hundreds of models, automatic provider failover, streaming-first, native `useChat` for the React side, and `tool()` ergonomics that make the historian queries one-liners. The raw Anthropic SDK gives us none of that for our 36-hour budget.
- **Models:** primary `anthropic/claude-sonnet-4.6` for tool-calling (fast, reliable, cheap), bumped to `anthropic/claude-opus-4.6` for the live demo if latency allows. Fallback chain through Gateway: `anthropic → openai/gpt-5.4 → google/gemini-3.1-pro` so a provider blip doesn't kill the demo.
- **One env var:** `AI_GATEWAY_API_KEY` (Vercel dashboard → AI Gateway → API Keys → `vercel env pull` to local). On Vercel, OIDC tokens work instead of a key.
- **Cost ceiling for a 60-second demo:** under $0.15 (see math below). A non-issue.
- **Avoid v5-era patterns:** `maxSteps`, `parameters`, `toDataStreamResponse`, `handleSubmit/input` from `useChat`. All renamed/removed in v6.

## Background — what AI SDK v6 + Gateway gives us

**AI SDK v6** (released late 2025) is the agent-first rewrite of Vercel's TypeScript LLM toolkit. The bits we care about for Phase 3:

- `streamText` / `generateText` with a `tools: { ... }` map — each tool defined via `tool({ description, inputSchema, execute })`. Zod schema in, typed args in `execute`, JSON result back to the model.
- `stopWhen: stepCountIs(N)` for the multi-step ReAct loop. v6 default is 20 steps; we'll cap at 5–8 for a hackathon demo.
- `Agent` / `ToolLoopAgent` class for reusable agent definitions and end-to-end type-safe `useChat` via `InferAgentUIMessage<typeof agent>`.
- `useChat` from `@ai-sdk/react` — transport-based, returns `{ messages, sendMessage, status }`. **You manage `input` with `useState` yourself** (changed in v5+).
- `result.toUIMessageStreamResponse()` from a Route Handler to stream UI-message parts (text + tool calls + tool results) to the client.

**AI Gateway** is a unified `https://ai-gateway.vercel.sh/v1` endpoint that:

- Routes `model: 'anthropic/claude-sonnet-4.6'` to Anthropic, `'openai/gpt-5.4'` to OpenAI, etc., with one key.
- Falls back to other providers automatically on outage / rate-limit, configured via `providerOptions.gateway.order` and `only`.
- Reports usage and spend per model in the Vercel dashboard — useful at the demo to show judges actual token counts.
- Zero markup on tokens; Anthropic spend is identical to going direct.

## Decision — chosen stack + canonical Phase 3 skeleton

```ts
// app/api/chat/route.ts
import { streamText, tool, stepCountIs, convertToModelMessages } from 'ai';
import { z } from 'zod';
import { queryHealth } from '@/lib/historian';

export async function POST(req: Request) {
  const { messages } = await req.json();
  const result = streamText({
    model: 'anthropic/claude-sonnet-4.6',
    system: 'You are the S100 co-pilot. Cite every claim with a historian row.',
    messages: convertToModelMessages(messages),
    tools: {
      query_health: tool({
        description: 'Read component health from the historian for a time range.',
        inputSchema: z.object({
          component: z.enum(['blade', 'nozzle', 'heater']),
          from: z.string().describe('ISO timestamp'),
          to: z.string().describe('ISO timestamp'),
        }),
        execute: async ({ component, from, to }) =>
          queryHealth(component, from, to), // returns rows[] with run_id + tick_id
      }),
    },
    stopWhen: stepCountIs(6),
    providerOptions: {
      gateway: { order: ['anthropic', 'openai', 'google'] },
    },
  });
  return result.toUIMessageStreamResponse();
}
```

Client side: `const { messages, sendMessage } = useChat();` with our own `useState('')` for the input box and `sendMessage({ text: input })` on submit.

## Why this fits our case

- **Phase 3 needs tool-calling, not chat-only.** Pattern C (Agentic Diagnosis) is the highest-rated rung of the reasoning ladder and is exactly what `streamText` + `tools` + `stopWhen` does out of the box. With the raw Anthropic SDK we'd hand-roll the loop, message accumulation, and JSON-schema plumbing — minimum half a day we don't have.
- **Grounding protocol falls out of tool design.** Each tool returns rows with `run_id` and `timestamp`; the system prompt forces the model to cite them. No prose-only paths exist for the model to hallucinate down.
- **Streaming is the demo.** `useChat` + `toUIMessageStreamResponse` gives us token-by-token UI for free, including the visible "calling tool…" → "got rows…" transitions, which sells the agentic pillar to judges.
- **Provider failover is the venue insurance policy.** Hackathon Wi-Fi + a single Anthropic outage = dead demo. Gateway's `order: [...]` makes that a one-line guard.
- **Multi-provider for the voice add-on later.** Phase 3 bonus is voice; Whisper / TTS providers also live behind the same Gateway key.

## Cost — 60-second demo, back-of-envelope

Assume Sonnet 4.6 ($3 / Mtok in, $15 / Mtok out) and 4 tool-call steps per user turn:

- System prompt + history + tool definitions: ≈ 2k input tokens × 4 calls = **8k input** ≈ $0.024
- Tool result rows injected: ≈ 1k tokens × 3 = **3k input** ≈ $0.009
- Model output (text + tool calls): ≈ 1.5k output tokens total ≈ $0.023
- **One full agentic turn ≈ $0.06.** A 60-second demo with two turns ≈ **$0.12**. Even with Opus 4.6 ($15 / $75) it's ≈ $0.60. Not a constraint.

## Avoid — v5-era patterns that break in v6

- `maxSteps: 5` → use `stopWhen: stepCountIs(5)`.
- `parameters: z.object(...)` inside `tool()` → use `inputSchema:`.
- `result.toDataStreamResponse()` from a Route Handler talking to `useChat` → use `toUIMessageStreamResponse()`.
- `useChat({ api: '/api/chat', input, handleInputChange, handleSubmit })` — none of those exist; use `DefaultChatTransport` (default) and your own `useState`. Use `sendMessage({ text })` instead of `handleSubmit`.
- `generateObject` for structured output → `generateText({ output: Output.object({ schema }) })`.
- Rendering `part.type === 'tool-invocation'` in messages → render typed parts `tool-query_health` with `part.state === 'output-available'` and read `part.input` / `part.output`.
- `addToolResult` → `addToolOutput` (with `tool` + `output` keys).

If anything below v6 syntax slips in, run `npx @ai-sdk/codemod v6` once at the start of Phase 3 and it migrates us in place.

## References

1. Vercel — *AI Gateway overview*. https://vercel.com/docs/ai-gateway
2. Vercel — *AI Gateway: Text generation quickstart* (env-var setup, model strings). https://vercel.com/docs/ai-gateway/getting-started/text
3. Vercel — *AI Gateway: Provider options (routing, fallback, BYOK timeouts)*. https://vercel.com/docs/ai-gateway/models-and-providers/provider-options
4. AI SDK — *AI Gateway provider*. https://ai-sdk.dev/providers/ai-sdk-providers/ai-gateway
5. AI SDK — *Tools and tool calling*. https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling
6. AI SDK — *`streamText` reference*. https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text
7. AI SDK — *`useChat` reference (transport-based, manual input state)*. https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat
8. Vercel Blog — *AI SDK 6 release notes*. https://vercel.com/blog/ai-sdk-6
9. Anthropic — *Claude pricing*. https://www.anthropic.com/pricing

## Open questions

- **Sonnet 4.6 vs. Opus 4.6 for the demo.** Sonnet is fast enough that streaming feels live; Opus reads as more "intelligent" in long diagnoses but adds latency. Decision: build on Sonnet, swap to Opus only for the recorded walkthrough video if judges aren't watching live.
- **Should the agent run in a Vercel Workflow (DurableAgent)?** Phase 3 is short-lived (< 10 s per turn), so plain Route Handler is fine. Reconsider only if we ship the proactive-alerts background monitor — that one is naturally durable.
- **Per-tool schema strictness.** Should `query_health` accept relative times like `"last hour"` and resolve them server-side, or force ISO from the model? Bias: ISO only, with a separate `now()` tool. Less prompting, no parsing bugs.
- **Citation rendering.** Inline `[run=42, t=2026-04-25T12:00:03Z]` markers vs. a structured `evidence` field in tool output that the UI renders as chips. Bias: chips, because they survive copy-paste better and read cleaner in the demo.
- **Rate-limit posture during judging.** Add `providerTimeouts` and a request-level retry, or trust Gateway's defaults? Probably trust the defaults until we see a single failure during rehearsal.

## Synthetic prompt

> Write `docs/research/11-vercel-ai-sdk.md` recommending Vercel AI SDK v6 + AI Gateway over the raw Anthropic SDK for Phase 3. Verify v6 syntax against ai-sdk.dev and vercel.com/docs/ai-gateway. Include: TL;DR, background, decision with a <30-line canonical Route Handler skeleton (streamText + tool() + inputSchema + stopWhen + Gateway order fallback), why-it-fits, 60-second demo cost estimate, list of v5 patterns to avoid (maxSteps, parameters, toDataStreamResponse, useChat input), references, open questions.
