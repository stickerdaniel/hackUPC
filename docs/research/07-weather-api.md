# Live Weather API — Open-Meteo vs OpenWeather

## TL;DR

**Pick Open-Meteo Historical Weather API.** It is free, requires **no API key** for non-commercial / hackathon use, returns **6 months of hourly `temperature_2m` + `relative_humidity_2m` in a single GET**, and ships JSON in the column-oriented shape we already want for our driver stream. OpenWeather One Call 3.0 needs a key, a credit card on file, and — crucially — **one HTTP request per hourly timestamp** for historical data, which means ~4 380 calls per city for our 6-month window. That alone disqualifies it for a 36-hour build.

## Background — the two options

| | **Open-Meteo Archive API** | **OpenWeather One Call 3.0 `timemachine`** |
|---|---|---|
| Auth | None for non-commercial | API key (`appid`) required, card-on-file for the 1k/day free allowance |
| Free-tier limit | 600 calls/min, 5 000/h, 10 000/day | 1 000 calls/day on "One Call by Call" plan |
| History depth | 1940 → ~5 days ago (ERA5 reanalysis; 9 km from 2017) | 1979-01-01 → +4 days |
| Hourly resolution | Yes, native | Yes, but **one timestamp per request** |
| 6 months hourly (one city) | **1 request** (~4 380 rows in one JSON) | **~4 380 requests** |
| Bulk historical export | Native via `start_date` / `end_date` | Not supported on One Call; needs the separate paid History Bulk product |
| Wirable in <30 min? | Yes — `requests.get(url).json()` | No — need key signup, retry/throttle loop, billing setup |

## Decision

**Endpoint template** (single GET, returns the whole window):

```
https://archive-api.open-meteo.com/v1/archive
  ?latitude={lat}
  &longitude={lon}
  &start_date={YYYY-MM-DD}
  &end_date={YYYY-MM-DD}
  &hourly=temperature_2m,relative_humidity_2m
  &timezone=UTC
```

**Sample URL — Barcelona, 6 months ending today (2026-04-25):**

```
https://archive-api.open-meteo.com/v1/archive?latitude=41.39&longitude=2.16&start_date=2025-10-25&end_date=2026-04-20&hourly=temperature_2m,relative_humidity_2m&timezone=UTC
```

**Sample URL — Phoenix, AZ (same window):**

```
https://archive-api.open-meteo.com/v1/archive?latitude=33.45&longitude=-112.07&start_date=2025-10-25&end_date=2026-04-20&hourly=temperature_2m,relative_humidity_2m&timezone=UTC
```

(Note: archive lags real time by ~5 days; we end the window on 2026-04-20 to be safe. Forward-extend with the regular Forecast API on `https://api.open-meteo.com/v1/forecast` if we ever need "now".)

**JSON response shape (relevant fields only):**

```jsonc
{
  "latitude": 41.4,
  "longitude": 2.16,
  "timezone": "UTC",
  "hourly_units": { "temperature_2m": "°C", "relative_humidity_2m": "%" },
  "hourly": {
    "time":               ["2025-10-25T00:00", "2025-10-25T01:00", ...],
    "temperature_2m":     [16.4, 16.1, 15.9, ...],
    "relative_humidity_2m":[78,   80,   81,   ...]
  }
}
```

The arrays are aligned by index — exactly the layout pandas wants (`pd.DataFrame(resp["hourly"])`).

**Mapping to our 4-driver contract** (per [`TRACK-CONTEXT.md`](../../TRACK-CONTEXT.md) §3.1):

| API column | Driver | Transform |
|---|---|---|
| `temperature_2m` (°C) | **Temperature Stress** ∈ [0,1] | `T_stress = clip(|T - 22| / 20, 0, 1)` — deviation from 22 °C optimal, saturating at ±20 °C |
| `relative_humidity_2m` (%) | **Humidity / Contamination** ∈ [0,1] | `C = clip((RH - 30) / 60, 0, 1)` — dry-room baseline 30 % RH, fully "contaminated" at 90 % |
| (synthesised) | **Operational Load** | from a duty-cycle profile, *not* weather |
| (synthesised) | **Maintenance Level** | from the maintenance event stream, *not* weather |

The weather driver only feeds `T_stress` and `C`; the other two stay scenario-controlled. This is what makes the Barcelona-vs-Phoenix what-if clean: same printer, same duty cycle, same maintenance schedule, **only the two weather-derived drivers change**, and the recoater blade / nozzle plate / heater models diverge accordingly.

## Why this fits our case

- **Single-shot fetch.** One GET per city at demo start, cache the JSON to disk, and the rest of Phase 2 is offline. No live rate-limit risk during the judge demo.
- **Deterministic.** Archive data is reanalysis — re-fetching the same `(lat, lon, start, end)` returns byte-identical numbers, so the simulator stays deterministic per the contract.
- **Same shape, two cities.** Swapping `latitude`/`longitude` is the entire diff between the Barcelona run and the Phoenix run. Phoenix in summer routinely runs ~38 °C / 15 % RH; Barcelona ~24 °C / 75 % RH — opposite corners of our (T_stress, C) plane, which lights up *different* failure modes (Phoenix → heater electrical aging dominant; Barcelona → blade abrasion + nozzle clog dominant). Demo-perfect.
- **Missing values.** Open-Meteo returns `null` for any hour it can't fill. Handle with `pd.Series.ffill(limit=3).bfill(limit=3)` then drop any tick where either driver is still NaN. Long gaps haven't appeared in spot checks of either city in the 2025-10 → 2026-04 window.
- **Rate-limit fallback.** Even if we hit the 600/min cap (we won't with two requests total), Open-Meteo replies `429` with `Retry-After`. Keep a 30-line `requests` wrapper with exponential backoff; total complexity ≈ a coffee break. As a belt-and-braces fallback, ship the two cached JSONs in the repo so the demo runs offline.

## References

- Open-Meteo Historical Weather API — <https://open-meteo.com/en/docs/historical-weather-api>
- Open-Meteo Terms (rate limits, non-commercial use) — <https://open-meteo.com/en/terms>
- Open-Meteo Forecast API (for "now" extension) — <https://open-meteo.com/en/docs>
- OpenWeather One Call 3.0 — <https://openweathermap.org/api/one-call-3>
- OpenWeather History API by timestamp (the per-hour endpoint) — <https://openweathermap.org/api/history-api-timestamp>
- ECMWF ERA5 reanalysis (the data Open-Meteo's archive is built on) — <https://www.ecmwf.int/en/forecasts/dataset/ecmwf-reanalysis-v5>

## Open questions

- **Optimal-temperature setpoint for `T_stress`.** 22 °C is a generic clean-room number; HP's S100 datasheet may specify a tighter window. Worth a 5-minute scan of the technical whitepaper before locking it in.
- **Humidity → contamination scaling.** RH is a proxy for powder moisture absorption, not a direct contamination measurement. Linear mapping is fine for the demo; a sigmoid that knees around 60 % RH would be more physically honest if we have time.
- **Time-zone alignment.** We pull both cities in UTC; the simulator needs to decide whether "9am Barcelona local" and "9am Phoenix local" run in parallel (visual story) or whether we sync on UTC wall clock (physically honest). Probably the former for the demo.
- **Covering the last 5 days.** Archive lags ~5 days behind real time. If we want a continuous Oct → today stream we should stitch the Forecast API's `past_days=5` onto the tail. Optional polish.
- **Phoenix coordinate.** `33.45, -112.07` is downtown Phoenix. If we want a more extreme dry-heat reading, Sky Harbor Airport (`33.43, -112.01`) or a desert site like Buckeye (`33.37, -112.58`) shifts the RH another 5–10 points lower.
