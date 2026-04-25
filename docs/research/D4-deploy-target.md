# D4 — Deploy Target: Vercel vs Local

## TL;DR

Run everything locally on the demo laptop. No Vercel deploy required for
the live demo. Pre-record a fallback video. If time allows after the core
build is complete, push a submit-ready URL to Vercel, but treat it as
optional.

## Background

The Digital Co-Pilot is a web app (React or similar front-end) backed by a
Python simulation core. Demo is in-person at HackUPC 2026 (Barcelona).
Two-person team, ~24 h. The key question is whether the simulation must run
remotely (Vercel) or can run locally with the laptop on stage.

## Options Considered

### Option A — Local only (recommended)

The web app and Python sim both run on the demo laptop. A local dev server
(e.g. `npm run dev` + `uvicorn`) serves everything. No internet dependency
during the live slot.

- Zero cold-start or serverless timeout risk.
- Simulation can hold arbitrarily long state in memory (no 800 s cap).
- No account/quota setup time.
- Wi-Fi failure has zero impact.

Risk: hardware failure on stage. Mitigation: pre-recorded video fallback
(see below).

### Option B — Vercel Functions (Python runtime)

Vercel supports Python via the `@vercel/python` runtime (ASGI/WSGI, Flask,
FastAPI). Python 3.12/3.13/3.14 available. With Fluid Compute enabled,
max execution duration is up to 800 s on Pro/Enterprise.

Constraints that hurt the sim use-case:
- Serverless: no persistent in-memory state between requests; each invocation
  is cold or warm but not a long-running process.
- Bundle size cap: 500 MB uncompressed.
- Fluid Compute (longer durations) requires Pro plan ($20/month credit);
  Hobby hard-caps functions at much shorter durations.
- Deploy-debug cycle eats hackathon hours.

### Option C — Vercel Sandbox

Vercel Sandbox is a Firecracker microVM (Amazon Linux 2023, python3.13
image) launched on-demand via SDK or CLI. Generally available; billed at
$0.128/CPU-hour on Pro (Hobby gets a monthly free allotment, then paused).
Automatic persistence is in beta (filesystem snapshot; running-process memory
is not preserved across stops).

Constraints:
- Currently only available in the `iad1` region (US East); latency from
  Barcelona stage Wi-Fi adds uncertainty.
- Requires Pro plan for reliable unthrottled access.
- SDK/orchestration adds integration surface; debugging under time pressure
  is costly.
- Persistent state is filesystem-level only; an in-memory sim must
  checkpoint to disk on every step.

### Option D — localhost + ngrok tunnel

Expose the local server via `ngrok http 8000` to get a public HTTPS URL.
Useful if judges want to try the app on their own devices. Free tier gives
one static domain per account. Works well as a supplement to Option A but
adds a single point of failure (ngrok relay + internet).

## Recommendation

**Primary: Option A (local only).** Stand up the full stack on the demo
laptop before the event. No network dependency on stage. Keep `ngrok` ready
as a one-command fallback if judges want a shareable URL, but do not rely on
it.

Risk-mitigation checklist:
1. **Pre-recorded video** — 60-90 s screen capture of a complete demo run,
   exported to MP4 on the laptop desktop. If the app crashes on stage, play
   the video.
2. **Offline mode** — ensure the front-end and sim have no hard dependencies
   on external APIs during the demo flow (mock or cache any external calls).
3. **No-network demo script** — rehearse the exact click-through with Wi-Fi
   disabled to confirm nothing breaks.
4. **Submit URL** — if ~2 h remain after the core build is stable, do a
   Vercel deploy of the front-end (static or Next.js) pointing at a mocked
   or simplified API. This is cosmetic for the submission form, not the live
   demo.

## Open Questions

- Does the simulation need to stream real-time updates to the UI? If yes,
  confirm WebSocket or SSE works cleanly with the chosen local server before
  the event.
- Will the venue provide a wired Ethernet port at the demo table? If yes,
  ngrok reliability improves significantly.
- Is a Vercel Pro account already available on the team? If not, skip
  Sandbox entirely — Hobby quota will throttle mid-demo.

## References

- [Vercel Sandbox pricing and limits](https://vercel.com/docs/vercel-sandbox/pricing)
- [Vercel Sandbox concepts](https://vercel.com/docs/vercel-sandbox/concepts)
- [Automatic persistence beta on Vercel Sandbox](https://vercel.com/changelog/vercel-sandbox-persistent-sandboxes-beta)
- [Vercel Functions — Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Vercel Python SDK beta](https://vercel.com/changelog/vercel-python-sdk-in-beta)
- [Configuring max duration for Vercel Functions](https://vercel.com/docs/functions/configuring-functions/duration)
- [Higher defaults with Fluid Compute](https://vercel.com/changelog/higher-defaults-and-limits-for-vercel-functions-running-fluid-compute)
- [How to demo localhost app using ngrok](https://dev.to/clarifai/how-to-demo-your-localhost-app-using-ngrok)
- [Deploy hackathon site with ngrok](https://medium.com/@tilakpat/deploy-your-hackathon-site-server-in-less-than-a-minute-4cbc866a257f)
