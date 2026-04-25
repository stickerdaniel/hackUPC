# A5 — Health-Index Normalisation

## TL;DR

Use **inverse min-max normalisation** (HI = 1 at baseline, 0 at failure limit) with **clamping
to [0, 1]** for every raw metric. Apply a **piecewise-linear** function (not sigmoid) for all
three components because the physics are well-understood and thresholds are physically motivated.
Composite components (Nozzle Plate) combine sub-metrics with a **weighted minimum** so no single
degraded sub-metric can be masked by a healthy one. Map the scalar HI to the four-state enum
using fixed thresholds: HI > 0.75 → FUNCTIONAL, > 0.40 → DEGRADED, > 0.10 → CRITICAL,
else FAILED.

---

## Background

PHM literature converges on the following conventions (NASA C-MAPSS, ISO 13381-1:2015):

1. A **Health Index (HI)** is a scalar in [0, 1] where 1 = new/perfect condition and 0 =
   failed/end-of-life.
2. Raw sensor values are mapped to HI through a monotone normalisation that encodes domain
   knowledge about the acceptable operating envelope.
3. The piecewise-linear (PWL) degradation model is dominant in C-MAPSS-derived literature: a
   flat "healthy plateau" followed by a linear decay to a failure threshold. This is preferable
   to a sigmoid when degradation onset is observable and approximately linear, as is the case
   for mechanical wear and resistive drift.
4. Health-stage boundaries are set so that the DEGRADED zone gives enough warning for planned
   maintenance, CRITICAL triggers urgent maintenance, and FAILED halts operation.

---

## Options Considered

### Normalisation function shape

| Option | Formula | Pros | Cons |
|---|---|---|---|
| Linear (min-max) | `(fail_limit - x) / (fail_limit - baseline)` | Interpretable, no hyperparameters | Abrupt, no gradual acceleration |
| Sigmoid | `1 / (1 + exp(k*(x - mid)))` | Smooth, models gradual onset | Extra hyperparams k, mid; hard to tie to physical limits |
| Piecewise linear | Flat plateau then linear decay | Matches C-MAPSS convention; captures healthy regime | Requires known degradation-onset point |

**Decision: piecewise linear collapsed to pure linear** for this simulator because we do not
model an explicit healthy plateau phase — degradation begins at t=0 in the simulator. The
formula reduces to `clamp((fail_limit - x) / (fail_limit - baseline), 0.0, 1.0)`.

Clamping above 1.0 handles measurements better than baseline (e.g. a blade thicker than the
nominal new value due to measurement noise). Clamping below 0.0 handles post-failure
over-degradation.

### Composite aggregation (Nozzle Plate)

Nozzle Plate has two sub-metrics: clog_pct and fatigue_cycles. Options:

- **Weighted mean**: `w1*HI_clog + w2*HI_fatigue` — a healthy metric compensates a failed one.
- **Weighted minimum** (chosen): `min(HI_clog, HI_fatigue)` — the worst sub-metric dominates.
- **Geometric mean**: intermediate, harder to explain.

The weighted minimum is the conservative choice: a fully clogged nozzle plate is non-functional
regardless of fatigue cycles remaining, and vice versa.

### Threshold cutoffs

Three-zone boundaries from condition-monitoring practice (ISO 13381-1, PHM Society surveys):

- 0.75 distinguishes normal operation from early degradation, giving ~25 % margin before action.
- 0.40 signals significant degradation; planned maintenance must be scheduled within the current
  or next maintenance window.
- 0.10 is the safety floor; continued operation risks irreversible damage or quality loss.

These are consistent with typical alarm-level structures in industrial SCADA/DCS systems (green /
amber / red / shutdown).

---

## Recommendation

### Per-metric normalisation

```python
def normalise(x, baseline, fail_limit):
    """Map raw metric x to HI in [0, 1].

    baseline   -- nominal new-part value (HI = 1.0)
    fail_limit -- end-of-life threshold (HI = 0.0)
    """
    raw = (fail_limit - x) / (fail_limit - baseline)
    return max(0.0, min(1.0, raw))
```

Metric-specific parameters:

| Component | Metric | baseline | fail_limit | Direction |
|---|---|---|---|---|
| Recoater Blade | thickness (mm) | 3.0 mm (new) | 1.5 mm (worn-out) | decreasing = worse |
| Nozzle Plate | clog_pct (%) | 0 % | 30 % | increasing = worse |
| Nozzle Plate | fatigue_cycles | 0 | 2,000,000 | increasing = worse |
| Heating Elements | resistance (Ohm) | 10 Ohm (nominal) | 14 Ohm (+40 %) | increasing = worse |

For clog_pct and fatigue_cycles the formula becomes
`clamp((x - baseline) / (fail_limit - baseline) * -1 + 1, 0, 1)` which is equivalent to
`clamp(1 - (x - baseline) / (fail_limit - baseline), 0, 1)`.

### Composite (Nozzle Plate)

```python
hi_nozzle = min(hi_clog, hi_fatigue)
```

### Enum mapping

```python
def to_health_state(hi: float) -> str:
    if hi > 0.75:
        return "FUNCTIONAL"
    elif hi > 0.40:
        return "DEGRADED"
    elif hi > 0.10:
        return "CRITICAL"
    else:
        return "FAILED"
```

### Edge cases

- **Metric beyond baseline** (e.g. blade thickness measured > 3.0 mm): clamp to HI = 1.0.
- **Metric beyond fail_limit** (post-failure over-degradation): clamp to HI = 0.0, state = FAILED.
- **divide-by-zero** if baseline == fail_limit: raise ValueError at config load time.
- **NaN / missing sensor**: propagate as HI = None and surface as a separate "sensor fault" flag;
  do not substitute 0.0 silently.

---

## Open Questions

1. Exact numerical values for blade baseline/fail_limit and heating element nominal/limit depend
   on HP Metal Jet S100 spec sheets — confirm or adjust with domain owner.
2. Should fatigue cycles use a Weibull-shaped curve (from A4) rather than linear? A4 suggests
   R(t) = exp(-(t/η)^β) which would give a nonlinear HI over cycles. Worth considering a
   hybrid: use Weibull-derived reliability as the HI for fatigue sub-metric only.
3. Weights for the nozzle composite: both sub-metrics currently have equal weight in the `min`
   aggregation. If clog is empirically more likely to cause print defects, a weighted minimum
   `min(w_c * hi_clog, w_f * hi_fatigue)` (with w_c > w_f) could be introduced.
4. Hysteresis: should the enum state require HI to rise above threshold + epsilon before
   recovering from CRITICAL to DEGRADED? Prevents chattering at boundary.

---

## References

- ISO 13381-1:2015 — Condition monitoring and diagnostics of machines: Prognostics general
  guidelines. https://www.iso.org/standard/51436.html
- NASA C-MAPSS dataset and piecewise linear RUL conventions.
  https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data
- Saxena et al., "Metrics for Offline Evaluation of Prognostic Performance," IJPHM 2010.
  https://papers.phmsociety.org/index.php/ijphm/article/view/4262
- Lei et al., "Machinery health prognostics: A systematic review," MSSP 2018.
  https://www.sciencedirect.com/science/article/abs/pii/S0888327017305988
- Composite indicator normalisation (min-max, clamp): EU Knowledge4Policy toolkit.
  https://knowledge4policy.ec.europa.eu/composite-indicators/toolkit_en/navigation-page/10-step-guide_en/step-5-normalisation_en
- Delivery Playbooks — composite metrics aggregation patterns.
  https://delivery-playbooks.rise8.us/content/plays/product/composite-metrics/
