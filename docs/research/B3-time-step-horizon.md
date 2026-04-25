# B3 — Time Step + Horizon

## TL;DR

Use **dt = 1 simulated hour**, horizon = **6 months (4 380 ticks)**.
Stream ticks at ~73 ticks/second so the full 6-month scenario plays out in
60 seconds of demo time. All three failure modes become visible well before
the run ends.

---

## Background

Three components degrade on very different physical timescales:

| Component | Dominant failure model | Realistic wear-to-failure |
|---|---|---|
| Recoater blade (Archard wear) | Abrasive wear accumulates per print cycle | ~2–6 weeks of continuous use |
| Nozzle plate (clogging) | Stochastic + thermal fatigue, binder residue | 1–8 weeks; bursty |
| Heating element (Arrhenius / electrical degradation) | Slow resistance creep | 3–9 months |

The UI (Recharts or visx) renders smoothly up to ~5 000 points per series
and begins to lag beyond ~100 000 points (DOM node count grows linearly with
tick count). We have three series minimum, so the practical per-series cap is
~5 000 ticks for a lag-free demo.

---

## Options Considered

### dt = 1 simulated minute

- 6-month horizon -> 262 800 ticks. Far exceeds UI rendering limit.
- 3-month horizon -> 131 400 ticks. Still too large.
- Blade failure visible by ~week 3 (~30 240 ticks). No benefit over coarser dt.
- **Verdict: rejected.** Tick count unmanageable; no fidelity gain for
  part-level degradation (our formulas don't need sub-hour resolution).

### dt = 1 simulated hour

- 6-month horizon (26 weeks) -> 26 x 7 x 24 = **4 368 ticks** (round to 4 380).
- Within Recharts sweet spot. Three series = ~13 140 total data points, fine.
- Blade health index crosses DEGRADED (~0.7) around tick 500 (week 3),
  CRITICAL (~0.3) around tick 900 (week 5-6).
- Nozzle clog events fire stochastically; first incident typically tick 200-600.
- Heater resistance drifts noticeably around tick 2 000 (month 3), CRITICAL
  near tick 3 500 (month 5).
- **Verdict: selected.**

### dt = 1 simulated day

- 6-month horizon -> 182 ticks. Chart looks sparse; micro-events invisible.
- Stochastic nozzle clogs average <1 per day so they appear as isolated
  spikes rather than a degradation curve.
- **Verdict: rejected.** Too coarse; the health curves look like step
  functions, not realistic degradation arcs.

---

## Recommendation

| Parameter | Value |
|---|---|
| dt | 1 simulated hour |
| Horizon | 6 simulated months (26 weeks) |
| Total ticks | 4 380 |
| Demo duration | 60 seconds |
| Ticks per demo-second | 73 |
| Real-to-demo compression | ~1 sim-month per 10 demo-seconds |

**How demo seconds map to sim time:**

- 0–10 s (ticks 0–730): printer "new", all health near 1.0
- 10–20 s (ticks 730–1 460): blade enters DEGRADED; first nozzle event possible
- 20–35 s (ticks 1 460–2 555): blade CRITICAL; nozzle shows clog trend
- 35–50 s (ticks 2 555–3 650): heater resistance visibly drifting; blade may FAIL
- 50–60 s (ticks 3 650–4 380): heater CRITICAL; cascading failure story complete

**Implementation note:** the simulation loop runs in batch first (all 4 380
ticks computed instantly in Python), then the UI replays from the historian at
73 ticks/second via a streaming endpoint or `setInterval`. This decouples
simulation correctness from demo pacing and avoids real-time compute pressure.
A `playback_speed` multiplier lets us tune the 73 ticks/s without rerunning
the sim.

---

## Open Questions

1. Should the historian store every tick (4 380 rows) or downsample for the
   chart (e.g. every 6th tick, ~730 points)? Store everything; downsample only
   in the chart layer so Phase 3 RAG queries still see full resolution.
2. Should `playback_speed` be a runtime parameter so judges can fast-forward?
   Probably yes — expose a 1x/5x/10x slider.
3. If we add stochastic shocks (humidity spike, temperature excursion), do we
   need sub-hour dt? No — shocks can be injected at hourly boundaries.
4. Does the AI Maintenance Agent (Phase 2 bonus) run inside the sim loop or
   as a post-processing step? Needs to run inside the loop so maintenance
   events reset decay curves and appear in the historian at the correct tick.

---

## References

- Recharts performance guidance: ~5 k points per series before noticeable
  jank (community benchmarks; no official doc threshold).
- Archard wear law: wear volume proportional to sliding distance and load —
  linear accumulation per print cycle justifies hourly dt.
- Arrhenius degradation: exponential in temperature, slow enough that
  daily-or-hourly resolution is sufficient for a months-long horizon.
- HP Metal Jet S100 briefing pack (see `docs/briefing/`) for component
  failure mode definitions.
