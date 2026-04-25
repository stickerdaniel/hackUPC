# D2 - UI / Chatbot Stack

## TL;DR

Use Next.js 16 (App Router), Vercel AI SDK v5, shadcn/ui charts (Recharts v3 wrapper)
for time-series, and a focused set of shadcn/ui primitives. This is the lowest-friction
path: one Tailwind-native design system, one charting dependency, one streaming hook.

## Background

The HP Metal Jet S100 co-pilot needs a telemetry dashboard (time-series line/area charts)
plus a grounded chatbot panel. Both must be shippable in ~24 h by two engineers. Stack
choices therefore skew toward convention over configuration.

## Options Considered

### Recharts (standalone)

Composable, React-native, SVG-based, powered by D3 under the hood. Simple declarative
API: `<LineChart>`, `<AreaChart>`, `<Tooltip>`, etc. ~500 kB gzipped with D3 internals,
but tree-shakeable. Best for teams that need robust charts fast with minimal boilerplate.
Large community, well-maintained. Downside: limited deep customization without reaching
into D3 directly.

### visx (Airbnb)

Low-level primitives (Axis, Scale, Shape, Brush) that compose like D3 but render as
React. Maximum flexibility and performance (good for many simultaneous charts). Tradeoff:
no out-of-the-box chart types; you wire up every axis, scale, and tooltip yourself.
Unsuitable for a 24 h sprint unless you already know the library.

### Tremor

Opinionated dashboard kit built on Recharts + Radix + Tailwind. Ships ready-made KPI
cards, AreaChart, BarChart, etc. Very fast initial setup. However, it sits above
Recharts' component API and blocks access to lower-level customization. As of early 2025
it uses a copy-paste model similar to shadcn/ui and is still actively maintained
(v3.18+), but it introduces a second design-system layer that conflicts with shadcn/ui
primitives already pulled in for the chatbot UI.

### shadcn/ui charts (Recharts wrapper) - CHOSEN

shadcn/ui added a Chart component in 2024 that wraps Recharts v3 with a thin,
themeable API (`ChartContainer`, `ChartTooltip`, `ChartLegend`). It is installed like
any other shadcn/ui component and integrates directly with the project's existing
Tailwind CSS variables and design tokens. No second design system, no extra peer dep
beyond Recharts itself.

## Recommendation

### Framework

Next.js 16 (App Router, React 19). Scaffold with:

```bash
npx create-next-app@latest --typescript --tailwind --eslint --app
```

### Chatbot streaming

Vercel AI SDK v5 (`ai` + `@ai-sdk/openai`). Core hook: `useChat`. API route uses
`streamText` and returns a streaming response via Server-Sent Events.

```bash
npm install ai @ai-sdk/openai
```

### Component + chart library

```bash
npx shadcn@latest init
npx shadcn@latest add button card badge scroll-area chart sonner
```

This pulls in Recharts v3 as a peer dependency for `chart`. `sonner` provides toast
notifications (e.g. alert thresholds). `scroll-area` handles the chat message list.

### Initial component set

| Component    | Use                                    |
| ------------ | -------------------------------------- |
| `card`       | Dashboard metric tiles                 |
| `chart`      | Line/area chart for telemetry streams  |
| `badge`      | Severity labels on alerts              |
| `scroll-area`| Chat message history pane              |
| `sonner`     | Toast notifications for threshold hits |
| `button`     | Send message, refresh data actions     |

### Tailwind

Tailwind v4 is included by default in Next.js 16 scaffolds. shadcn/ui v2+ targets
Tailwind v4 with CSS variable tokens; no extra config file required beyond the
`globals.css` shadcn init writes.

## Open Questions

- AI SDK v5 renamed some APIs (UIMessage vs ModelMessage); verify `useChat` signature
  against the v5 docs before wiring the chat route.
- Recharts v3 (used by shadcn chart) changed some prop names from v2; check if any
  community snippets you copy are v2-era.
- Next.js 16 has a known security advisory on React Server Components; apply latest
  patch version on init.

## References

- [shadcn/ui Chart docs](https://ui.shadcn.com/docs/components/chart)
- [shadcn/ui CLI docs](https://ui.shadcn.com/docs/cli)
- [shadcn/ui Installation (Next.js)](https://ui.shadcn.com/docs/installation/next)
- [AI SDK v5 announcement - Vercel](https://vercel.com/blog/ai-sdk-5)
- [AI SDK useChat reference](https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat)
- [Next.js 15.5 release](https://nextjs.org/blog/next-15-5)
- [Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16)
- [LogRocket: Best React chart libraries 2025](https://blog.logrocket.com/best-react-chart-libraries-2025/)
- [Tremor](https://www.tremor.so/)
