# Recoater Blade — Archard's Wear Law

## TL;DR

Model the HP Metal Jet S100 recoater blade as a hardened tool-steel edge sliding over a metal-powder bed and lose **thickness** every tick using the linear form of Archard's law: `Δh = k_eff · P · v · dt / H`. We start the blade at **1.0 mm** of usable edge, set `k = 5·10⁻⁵`, contact pressure `P = 5·10⁴ Pa`, sliding length `s = 310 m/h`, hardness `H = 7·10⁹ Pa` (~700 HV). Humidity/contamination scales `k` multiplicatively (`k_eff = k · (1 + 1.5·C)`), Operational Load scales sliding distance (more layers per hour), and Maintenance Level both reduces `k_eff` and snaps a small amount of remaining life back at service events. Under nominal conditions the blade reaches the FAILED threshold after ~5–6 months of 24/7 operation; under contaminated, heavily loaded conditions it fails in ~6–8 weeks. Status thresholds: DEGRADED at 20 % thickness loss, CRITICAL at 40 %, FAILED at 50 %.

## Background

Archard's law (Archard 1953) is the canonical model for sliding-contact wear. The volumetric form is

```
V = k · F · s / H
```

where `V` is wear volume [m³], `k` is the dimensionless wear coefficient, `F` is normal load [N], `s` is sliding distance [m], and `H` is the hardness of the softer body in pressure units [Pa]. Reported `k` spans ~10⁻⁸ (mild adhesive) to ~10⁻² (severe abrasive) [Tribonet, Wikipedia]. For a blade of contact area `A`, dividing by `A` and noting `P = F/A` gives the **linear thickness form** we actually want for a 1-D component metric:

```
Δh = k · P · v · dt / H        with v · dt = s
```

Archard's law is strictly an *adhesive* wear model, but it is routinely used as a first-order proxy for abrasive sliding by inflating `k` and treating environmental factors as multiplicative pre-factors on `k` [MDPI 2025 review of Archard-type laws]. That is exactly the level of fidelity our hackathon simulator needs.

## Decision

**State variable:** `thickness_mm` ∈ [0, 1.0] (component physical metric).

**Constants (per blade):**

| Symbol | Value | Unit | Note |
|---|---|---|---|
| `h0` | `1.0` | mm | initial usable edge thickness |
| `k0` | `5·10⁻⁵` | – | base wear coefficient (two-body abrasion against metal powder) |
| `P0` | `5·10⁴` | Pa | nominal contact pressure (light blade line-load) |
| `s0` | `310` | m / h | nominal sliding distance per simulated hour (~360 layers/h × ~0.86 m stroke) |
| `H` | `7·10⁹` | Pa | hardness of hardened tool-steel blade (~700 HV) |
| `dt` | `1` | h = 3600 s | simulation tick |

**Driver couplings:**

- **Humidity / Contamination `C` ∈ [0, 1]**: scales `k` multiplicatively. `k_eff = k0 · (1 + α · C)` with `α = 1.5`. Reasoning: abrasive wear rate roughly doubles to triples in dust/humid environments versus clean dry sliding [ScienceDirect "humidity on abrasive wear"]. `α = 1.5` puts a fully contaminated bed (`C = 1`) at 2.5× the clean wear rate, which is realistic without saturating the model.
- **Operational Load `L` ∈ [0, 1]**: scales sliding distance (more layers per hour, longer strokes). `s_eff = s0 · (0.5 + L)`. Idle (`L=0`) still does test/purge passes; full duty (`L=1`) gives 1.5×.
- **Maintenance Level `M` ∈ [0, 1]**: blade alignment, cleanliness, lube. `k_eff` is further divided by `(1 + β · M)` with `β = 0.5`, so a perfectly maintained blade (`M=1`) wears at two-thirds the rate. Discrete maintenance *events* additionally restore `min(0.05 mm, h_lost·0.1)` (cosmetic re-honing) and reset `M` to 1.0.
- **Temperature Stress `T_stress` ∈ [0, 1]**: secondary; softens hardness as `H_eff = H · (1 − 0.1 · T_stress)`. Recoater blade rarely sees furnace temps, so the effect is small but non-zero.

**Per-tick formula:**

```
k_eff   = k0 · (1 + 1.5·C) / (1 + 0.5·M)
s_eff   = s0 · (0.5 + L)
H_eff   = H  · (1 − 0.1·T_stress)
Δh      = k_eff · P0 · s_eff · dt / H_eff       # in metres
thickness_mm  ← thickness_mm − Δh · 1000
loss_frac     = 1 − thickness_mm / h0
```

**Health Index and Status:**

```
HI = clamp(1 − loss_frac / 0.5, 0, 1)           # FAILED at 50 % loss → HI = 0
status = FUNCTIONAL  if loss_frac < 0.20
       | DEGRADED    if loss_frac < 0.40
       | CRITICAL    if loss_frac < 0.50
       | FAILED      otherwise
```

Sanity check (nominal `C=0.1, L=0.6, M=0.5, T=0.1`): `Δh ≈ 1.1·10⁻⁷ m/h`. Over 4 380 h (6 months 24/7) that's ≈ 0.49 mm loss → just past FAILED. Under harsh drivers (`C=0.8, L=1.0, M=0.1`) failure arrives in ~6–8 weeks. Under pristine drivers (`C=0, L=0.3, M=1.0`) the blade lasts well over a year. That spread is exactly what we want the demo to show.

## Why this fits our case

The HP Metal Jet S100 recoater spreads thin layers of metal powder; abrasive wear of the blade edge against hard metal particles is the dominant failure mode and is explicitly contamination-accelerated, which matches the challenge brief one-to-one. Archard's law is the textbook model for this regime, named in the brief's allowed list, and gives us a single closed-form equation parameterised by all four required drivers. The linear thickness form keeps the component metric a real, plottable, physical quantity (millimetres) — easy to chart, easy for the LLM co-pilot to reason about, and easy to translate into a binary threshold for the status enum. Determinism is automatic since the formula has no stochastic terms. Cascading failure into the nozzle plate (degraded blade → uneven layer → contaminated bed → clog) becomes a clean coupling: as `loss_frac` rises, we can feed `0.5·loss_frac` back into the nozzle's `C` driver.

## References

- Archard equation, Wikipedia — <https://en.wikipedia.org/wiki/Archard_equation>
- Archard Wear Equation, Tribonet — <https://www.tribonet.org/wiki/archard-wear-equation/>
- *Archard's Law: Foundations, Extensions, and Critiques*, MDPI Encyclopedia 2025 — <https://www.mdpi.com/2673-8392/5/3/124>
- *A Contemporary Review and Data-Driven Evaluation of Archard-Type Wear Laws*, ASME AMR 2025 — <https://asmedigitalcollection.asme.org/appliedmechanicsreviews/article/77/2/022101/1214387>
- Misra & Finnie, *Influence of atmospheric humidity on abrasive wear — II. 2-body abrasion*, Wear (1975) — <https://www.sciencedirect.com/science/article/abs/pii/0043164875902008>
- Strano et al., *Recoater design for a helical motion binder jet AM 3D printer*, 2025 — <https://www.sciencedirect.com/science/article/abs/pii/S1674200125000288>
- *What's the right recoater for your metal AM process?*, 3D ADEPT MEDIA — <https://3dadept.com/whats-the-right-recoater-for-your-metal-am-process/>
- HP Metal Jet S100 Technical Whitepaper — <https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-3333ENW>

## Open questions

- **Real `k` for tool steel sliding against metal powder**: 5·10⁻⁵ is a defensible mid-range guess; if we find a published binder-jet-specific number we should swap it in.
- **Contact pressure `P`**: HP does not publish recoater preload. 50 kPa is a plausible "barely touches" estimate; sensitivity sweep recommended.
- **Discrete chipping events**: real blade failure includes sudden chips, not just smooth abrasion. We could overlay a low-rate Poisson chip event whose intensity scales with `loss_frac` — bonus stochastic realism.
- **Blade replacement vs. honing**: model assumes honing (small recovery). Full replacement should reset `thickness_mm` to `h0` and is a different maintenance event class.
- **Coupling sign for `T_stress`**: hardness softens at high temperature, but the recoater is far from the sintering furnace. The 0.1 coefficient is a rounding-error knob; could be set to 0 if we want the blade to be temperature-insensitive.
