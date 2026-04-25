# Voice Interface — Web Speech API vs OpenAI Realtime vs ElevenLabs

## TL;DR

**Primary: Web Speech API** (browser-native `SpeechRecognition` + `SpeechSynthesis`). Zero cost, zero accounts, ~25 lines of client code, demoable in <30 minutes. Works in Chrome and Edge — and the laptop we present from will be Chrome. **Stretch (Sunday only, if grounding stack is green): OpenAI Realtime via WebRTC** with our existing `query_health` / `query_telemetry` tools wired in for a true voice-to-voice "wow" moment that still cites the historian. **Skip ElevenLabs** for this hackathon — its strength (premium voices, telephony) doesn't move the rubric, and minute-based billing plus a separate agent console adds setup we don't have time for.

## Background — three options

| | **Web Speech API** | **OpenAI Realtime** (`gpt-realtime`) | **ElevenLabs Agents** |
|---|---|---|---|
| Transport | Browser-native ASR + TTS | WebRTC (preferred) / WebSocket / SIP | WebSocket + SDK |
| Latency | ASR streams in browser; TTS local | Sub-second voice-to-voice | ~500–800 ms voice-to-voice |
| Tool calling | N/A — we keep our `/api/chat` route | Native function calling on the realtime session | Native, plus 8k+ Zapier integrations |
| Cost | **$0** | $32 / 1M audio input tokens, $64 / 1M audio output tokens (~$0.06 / min mixed). 20 % cheaper than the old `gpt-4o-realtime-preview`. | From $0.10 / min voice + LLM pass-through |
| Setup time | <30 min, no key | 1–2 h: ephemeral-token endpoint + WebRTC SDP exchange + tool wiring | 1–2 h: agent definition in dashboard + SDK |
| Browser reach | Chrome, Edge, Safari 14.1+ partial. Firefox: disabled. (caniuse) | Any modern browser w/ WebRTC | Any modern browser |
| Demo risk | Wi-Fi flakiness, ambient noise; ASR is server-side in Chrome so we need internet | Token expiry, SDP handshake, more moving parts | Extra vendor in the loop on stage |

Reality check on Web Speech: in Chrome (and Chromium-based Edge) the constructor is still `webkitSpeechRecognition` for the legacy global; the spec'd `SpeechRecognition()` is shipping but the safe pattern is `window.SpeechRecognition || window.webkitSpeechRecognition`. Audio is shipped to Google's servers for transcription — fine for a demo, would not be fine for an HP factory floor in production (we should call this out as a future-work item: swap to on-device Whisper/`processLocally` for shop-floor privacy).

## Decision

### Primary: Web Speech API in a Next.js client component

```tsx
"use client";
import { useState, useRef } from "react";

export function VoiceCopilot() {
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const recRef = useRef<any>(null);

  const start = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "en-US"; rec.interimResults = false; rec.continuous = false;
    rec.onresult = async (e: any) => {
      const text = e.results[0][0].transcript;
      setTranscript(text);
      const r = await fetch("/api/chat", {
        method: "POST",
        body: JSON.stringify({ messages: [{ role: "user", content: text }] }),
      }).then(r => r.json());
      setReply(r.text);
      const u = new SpeechSynthesisUtterance(r.text);
      u.rate = 1.05; speechSynthesis.speak(u);
    };
    rec.start(); recRef.current = rec;
  };

  return (
    <div>
      <button onMouseDown={start}>Hold to talk</button>
      <p><b>You:</b> {transcript}</p>
      <p><b>Co-Pilot:</b> {reply}</p>
    </div>
  );
}
```

The key insight: **our existing `/api/chat` already does grounded tool-calling against the SQLite historian.** The voice layer is purely an I/O wrapper. Citations come back in `reply` text and we just speak them — "Nozzle plate 7 is at 84 % health, citing 412 cycles since last replacement, source: build_log table, latest entry 2026-04-24 18:22 UTC." TTS reads that verbatim.

### Stretch: OpenAI Realtime (Sunday afternoon, only if Phase 2 demo is green)

Sketch:

1. **Server route `/api/realtime/session`** — `POST` to `https://api.openai.com/v1/realtime/client_secrets` with our system prompt + tool definitions, returns the `ek_…` ephemeral token. Token is short-lived; mint per session.
2. **Client** — fetch the ephemeral token, create `RTCPeerConnection`, attach mic track, create data channel for events, then `POST` the SDP offer to `https://api.openai.com/v1/realtime?model=gpt-realtime` with `Authorization: Bearer <ek>` and use the SDP answer.
3. **Tools** — pass our existing `query_health(component_id)` and `query_telemetry(metric, window)` JSON-schema definitions on the session. The model emits `response.function_call_arguments.done` events on the data channel; we run the SQL, send back `conversation.item.create` with the result, then `response.create`. Voice answer streams out of the audio track. Same grounding contract, same citations — just spoken in real time with barge-in.
4. **Fallback button** — if Realtime fails on stage, one click reverts to Web Speech. No demo death.

Don't over-engineer this on Saturday. Build it Sunday morning **only** if the historian + chat path is rock solid.

## Why this fits our case

- **Hackathon rubric Phase 3 "Versatility":** judges want to see the operator hands-free. Web Speech alone is enough to tick that box and it feels native — no headset, no app install, just a hold-to-talk button.
- **Grounding stays intact:** voice is a wrapper around `/api/chat`, so every spoken answer is still backed by the historian and cites a row. Voice does not weaken our "no hallucination" pillar — it amplifies it because the audience hears the citation.
- **Risk profile:** Web Speech has one external dependency (Chrome's ASR endpoint) and zero billing surface. OpenAI Realtime adds 4 (token endpoint, WebRTC SDP, tool round-trips, audio decoder). On a hackathon stage with shared Wi-Fi, Web Speech wins on robustness.
- **Demo script we're optimising for:** operator says "what's the status of the nozzle plate?" → mic icon pulses → on-screen transcript appears → grounded text answer renders → speech synthesis reads it including the citation ("…source: nozzle_plate_history row 1142, build job NJ-2026-04-22-A"). 12 seconds, no typing, no slides.

## References

- [Speech Recognition API support — caniuse.com](https://caniuse.com/speech-recognition)
- [Speech Synthesis API support — caniuse.com](https://caniuse.com/speech-synthesis)
- [SpeechRecognition — MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [Realtime API with WebRTC — OpenAI](https://platform.openai.com/docs/guides/realtime-webrtc)
- [Introducing gpt-realtime — OpenAI](https://openai.com/index/introducing-gpt-realtime/)
- [GPT Realtime model card](https://platform.openai.com/docs/models/gpt-realtime)
- [How OpenAI does WebRTC in the new gpt-realtime — webrtcHacks](https://webrtchacks.com/how-openai-does-webrtc-in-the-new-gpt-realtime/)
- [ElevenLabs Conversational AI / Agents](https://elevenlabs.io/conversational-ai)
- [ElevenLabs Agents pricing — help center](https://help.elevenlabs.io/hc/en-us/articles/29298065878929)

## Open questions

- **Mic permission UX on stage.** Chrome will prompt the first time. Pre-warm by clicking the button once during setup so the permission is already granted before judging.
- **Ambient noise in the venue.** Hackathon halls are loud. Test with `interimResults=true` and a confidence threshold; consider a wired headset mic for the demo run.
- **Wake word vs hold-to-talk.** Hold-to-talk is more reliable for a 36-hour build. Wake word ("Hey Jet") is a Sunday stretch only.
- **Streaming the answer.** Our `/api/chat` likely returns the full text in one shot. For Web Speech we can speak it as one utterance. For OpenAI Realtime the audio streams natively — no work needed.
- **Citations spoken aloud.** Long row IDs read awkwardly. Decide whether to render citations only on screen and have TTS say "see screen for source" or read a shortened form ("source: build log, yesterday 18:22").
- **Privacy disclaimer.** If asked by judges: yes, Chrome ASR is cloud. Production path is on-device (`processLocally`) or a self-hosted Whisper endpoint.
