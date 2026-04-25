# B2 - Live Weather API: Open-Meteo vs OpenWeather

## TL;DR

Use Open-Meteo. It is completely free, requires no API key, no account, no credit
card. It provides 80+ years of hourly historical data via a single GET request.
Cache results to a local JSON file at demo start so the demo survives an offline
venue.

---

## Background

The "Barcelona vs. Phoenix" what-if compares how ambient temperature and humidity
drive component degradation differently across climates. Real historical data
(past year of hourly readings) adds credibility; a live call at demo time would
be a nice-to-have bonus, but reliability matters more than novelty.

---

## Options Considered

| Criterion | Open-Meteo | OpenWeather |
|---|---|---|
| Auth required | None | API key (account required) |
| Credit card required | No | Yes (One Call 3.0, even for free tier) |
| Free daily limit | 10,000 req/day | 1,000 req/day |
| Rate limit (per minute) | Not published; generous in practice | 60 req/min |
| Historical data available free | Yes, 1940-present | One Call 3.0 historical is pay-as-you-go (first 1,000 calls/day free but card on file required); bulk archive is paid-only |
| Historical depth | 80+ years, hourly, 10 km resolution | 47+ years via paid bulk; per-point historical via One Call 3.0 (card required) |
| Python client (official) | `openmeteo-requests` on PyPI | `pyowm` on PyPI |
| Open source / self-hostable | Yes (MIT) | No |
| Demo risk | Minimal (no auth to expire or rate-spike) | Medium (key must be present; card must be on file) |

---

## Recommendation

**Use Open-Meteo** (`archive-api.open-meteo.com/v1/archive`).

### Sample request URL

```
https://archive-api.open-meteo.com/v1/archive
  ?latitude=41.39&longitude=2.17
  &start_date=2025-04-25&end_date=2026-04-25
  &hourly=temperature_2m,relative_humidity_2m
  &timezone=Europe%2FMadrid
```

Swap in `latitude=33.45&longitude=-112.07&timezone=America%2FPhoenix` for Phoenix.

### Python snippet

```python
import json, pathlib, requests

CACHE_DIR = pathlib.Path("data/weather_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LOCATIONS = {
    "barcelona": {"latitude": 41.39, "longitude": 2.17,  "timezone": "Europe/Madrid"},
    "phoenix":   {"latitude": 33.45, "longitude": -112.07, "timezone": "America/Phoenix"},
}

def fetch_hourly(city: str, start: str, end: str) -> dict:
    """Return hourly temp+humidity dict, from cache if available."""
    cache_file = CACHE_DIR / f"{city}_{start}_{end}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    loc = LOCATIONS[city]
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            **loc,
            "start_date": start,
            "end_date": end,
            "hourly": "temperature_2m,relative_humidity_2m",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data))
    return data

# Example: one year of hourly data
barcelona = fetch_hourly("barcelona", "2025-04-25", "2026-04-25")
phoenix   = fetch_hourly("phoenix",   "2025-04-25", "2026-04-25")
```

### Cache strategy

Run `fetch_hourly` once before the demo (takes ~1 s per city). The cache JSON
files sit in `data/weather_cache/`. If the network is down at demo time, the
simulator falls back to the cached files silently. A hard-coded static fallback
(annual average temp/humidity per city) is a last-resort default if the cache
file is also missing.

---

## Open Questions

- Decide on the exact date range to cache (past 12 months is enough for the
  demo; a full year covers all seasons).
- Confirm whether the simulator consumes hourly vectors or just annual averages;
  hourly data can always be averaged down.
- Open-Meteo's free tier is rate-limited at 10,000 req/day; repeated CI runs
  that hit the live API could burn through this. Add the cache layer before
  wiring into tests.

---

## References

- [Open-Meteo Pricing](https://open-meteo.com/en/pricing)
- [Open-Meteo Historical Weather API docs](https://open-meteo.com/en/docs/historical-weather-api)
- [openmeteo-requests on PyPI](https://pypi.org/project/openmeteo-requests/)
- [open-meteo/python-requests on GitHub](https://github.com/open-meteo/python-requests)
- [OpenWeather One Call API 3.0](https://openweathermap.org/api/one-call-3)
- [OpenWeather Detailed Pricing](https://openweathermap.org/full-price)
- [OpenWeather Historical Weather API](https://openweathermap.org/api/history)
- [Top weather APIs in 2026 - Xweather comparison](https://www.xweather.com/blog/article/top-weather-apis-for-production-2026)
