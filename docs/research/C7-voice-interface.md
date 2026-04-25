# C7 - Voice Interface: Evaluation and Decision

## TL;DR

Primary: **Web Speech API** (SpeechRecognition + SpeechSynthesis) — zero cost, zero
setup, works in Chrome/Edge (the demo browser), ships in ~30 min.
Fallback: **OpenAI Realtime API** (gpt-4o-mini-realtime) if a full hour is free near
the end — pure WebSocket, single round-trip, genuine "wow" factor.
Skip ElevenLabs Conversational AI for this hackathon: proprietary SDK, per-minute
billing from the first call, and more moving parts than the value justifies.

---

## Background

The HP Metal Jet S100 co-pilot chatbot needs a voice layer so operators can ask
questions hands-free near the printer. The interface must: capture speech, send text
to the existing chatbot API, and read the reply aloud. Tool-calling (to query live
printer data) is a secondary concern — the chatbot backend already handles it over
HTTP; the voice layer only needs to shuttle text.

---

## Options Considered

| Criterion | Web Speech API | OpenAI Realtime API | ElevenLabs Conversational AI |
|---|---|---|---|
| **Cost** | Free (browser-native) | ~$0.06/min in + $0.24/min out (mini: ~$0.02/$0.08) | $0.10/min (paid); ~15 min free/month |
| **Latency** | STT: ~500 ms (Google servers); TTS: instant | End-to-end ~300-500 ms (single WS round-trip) | ~400-600 ms; similar to Realtime |
| **Tool calling** | N/A (text out only; backend handles tools) | Yes, native function calling in session config | Yes, built-in; requires ElevenLabs agent setup |
| **Browser support** | Chrome/Edge only; Firefox no; Safari partial | Any browser (WebSocket) | Any browser (JS SDK) |
| **Setup time (est.)** | 30 min | 90-120 min | 2-3 h (agent config, API key, webhook) |
| **Hackathon risk** | Low — well-documented, no API key | Medium — streaming WS, token billing | High — billing from first call, complex SDK |
| **npm / API surface** | `window.SpeechRecognition`, `SpeechSynthesis` | `openai` npm, `gpt-4o-mini-realtime-preview` | `@11labs/client` npm |

---

## Recommendation

### Primary: Web Speech API

Demo will run in Chrome — the only browser that matters in a 60-second live demo.

**Code skeleton (React hook pattern):**

```ts
// useSpeechPipeline.ts
export function useSpeechPipeline(onTranscript: (text: string) => Promise<string>) {
  const startListening = () => {
    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onresult = async (e) => {
      const transcript = e.results[0][0].transcript;
      const reply = await onTranscript(transcript);   // POST to chatbot API
      const utt = new SpeechSynthesisUtterance(reply);
      utt.rate = 1.1;
      speechSynthesis.speak(utt);
    };
    rec.onerror = (e) => console.error("STT error", e.error);
    rec.start();
  };
  return { startListening };
}
```

UI: single mic button toggles `startListening`. No API key, no npm package, no
billing. Works offline for TTS; STT requires internet (routes through Google's
servers behind the scenes).

### Fallback: OpenAI Realtime API (if 60+ min remain before demo)

Use `gpt-4o-mini-realtime-preview` over a WebSocket. The model handles STT + LLM +
TTS in one streaming round-trip. Function/tool calling is declared in the session
config (`tools: [...]`). Estimated cost for a 5-min demo: under $0.05 on the mini
model. Risk: WebSocket lifecycle management, session token expiry, and audio encoding
(PCM16 / base64) add complexity.

### Decision rule

Start with Web Speech API. If it is working and 60 min remain: attempt Realtime. If
Realtime is not stable 20 min before the demo, revert to Web Speech.

---

## Demo Risks

- **Web Speech STT** sends audio to Google servers — requires a live internet
  connection at the venue. Test on venue Wi-Fi early.
- **SpeechSynthesis voices** vary by OS. Pre-select a voice on the demo machine
  (`speechSynthesis.getVoices()`).
- **Mic permissions** prompt on first use — click "Allow" before the demo starts.
- **Background noise** at a hackathon can cause false triggers. Add a push-to-talk
  button rather than always-on VAD.
- **Realtime WebSocket** may be blocked by corporate/venue firewalls (wss://). Test
  connectivity if attempting this path.

---

## Open Questions

1. Does the demo machine run Chrome or Edge? (Confirm before the event — no Web Speech
   on Firefox.)
2. Is there a venue Wi-Fi SSID with low latency, or should a hotspot be the backup?
3. Does the chatbot backend return plain text or streamed chunks? (SpeechSynthesis
   works best with complete sentences, not token streams.)
4. Is a bilingual (English + Spanish) demo required? Web Speech supports `rec.lang =
   "es-ES"` trivially; Realtime also supports multilingual.

---

## References

- [OpenAI Realtime API pricing (per-minute breakdown)](https://tokenmix.ai/blog/gpt-4o-realtime-audio-api-guide-2026)
- [OpenAI API pricing page](https://openai.com/api/pricing/)
- [OpenAI Realtime cost guide](https://developers.openai.com/api/docs/guides/realtime-costs)
- [ElevenLabs Conversational AI overview](https://elevenlabs.io/conversational-ai)
- [ElevenLabs pricing (2026)](https://elevenlabs.io/pricing)
- [ElevenLabs Conversational AI pricing cut announcement](https://elevenlabs.io/blog/we-cut-our-pricing-for-conversational-ai)
- [MDN: Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [MDN: SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [Can I Use: SpeechRecognition](https://caniuse.com/speech-recognition)
- [AssemblyAI: Web Speech API guide](https://www.assemblyai.com/blog/speech-recognition-javascript-web-speech-api)
