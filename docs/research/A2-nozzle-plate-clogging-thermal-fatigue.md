# A2 — Nozzle Plate: Clogging + Thermal Fatigue

## TL;DR

Model the nozzle plate with **two parallel sub-models** that are composed into one health value:

1. **Thermal fatigue** — Coffin-Manson low-cycle fatigue: cumulative damage fraction D_f rises
   each tick proportional to (|delta_T| / delta_T_ref)^(1/|c|). Failure when D_f >= 1.
2. **Clogging** — non-homogeneous Poisson process (NHPP): per-tick clog probability
   lambda(t) = lambda_0 * exp(alpha * |temp_stress - T_opt| + beta_c * contamination).
   Clogs accumulate as a fraction of total nozzles (clog_pct).

Combined health: `H = (1 - D_f) * (1 - clog_pct)`, clamped to [0, 1].

---

## Background

The HP Metal Jet S100 printhead carries two columns of 5,280 thermal-inkjet nozzles per
printhead firing binder agent onto metal powder beds. Two independent damage mechanisms
threaten the nozzle plate:

**Thermal fatigue (Coffin-Manson)**
Each print cycle heats and cools the nozzle plate; the resulting cyclic plastic strain drives
low-cycle fatigue crack growth. The Coffin-Manson relation (Coffin 1954, Manson 1953) states:

```
delta_epsilon_p / 2 = epsilon_f_prime * (2 * N_f)^c
```

Rearranged for N_f (cycles to failure):

```
N_f = 0.5 * (delta_epsilon_p / (2 * epsilon_f_prime))^(1/c)
```

where:
- `delta_epsilon_p` = plastic strain range per cycle (proportional to |delta_T| via CTE)
- `epsilon_f_prime` = fatigue ductility coefficient (typically ~0.35 for stainless / hard metals)
- `c` = fatigue ductility exponent, range -0.5 to -0.7; canonical default **c = -0.6**

Linear damage accumulation (Miner's rule): each tick adds D_tick = 1 / N_f(delta_T_tick)
to a running sum D_f. At D_f = 1 the plate has reached end-of-life from fatigue alone.

**Nozzle clogging (NHPP / hazard rate)**
Clogging arises from binder agent drying, powder particle ingestion, and contamination
buildup — all accelerated by thermal stress deviating from the optimal operating point and
by ambient contamination. A non-homogeneous Poisson process with intensity (hazard rate)
lambda(t) models the count of clog events per unit time. The NHPP framework is standard
for repairable systems where the event rate varies with operating conditions (NIST
Engineering Statistics Handbook, section 8.1.7.2). The proportional-ROCOF form multiplies
a baseline rate by an exponential covariate factor — exactly analogous to the proportional
hazards model used in A4.

**Does clog probability rise with |temp_stress - T_opt|?**
Yes. Thermal excursions accelerate binder viscosity changes (too hot: solvent flash-dries;
too cold: viscosity spikes) and particle agglomeration at the nozzle exit — both are
established mechanisms in inkjet clogging literature (ACS Ind. Eng. Chem. Res. 2013,
XTPL 2023). The exponential covariate exp(alpha * |temp_stress - T_opt|) captures this
symmetrically around the optimum.

---

## Options Considered

| Approach | Pro | Con |
|---|---|---|
| Single Weibull (from A4) | Consistent with rest of model | Conflates two physically distinct failure modes; can't separately track clog count vs crack growth |
| Coffin-Manson only | Well-grounded; cracks are deterministic | Ignores stochastic clogging; no per-nozzle resolution |
| Poisson clogging only | Captures randomness; easy to tune lambda | No fatigue damage accumulation; misses thermal crack growth |
| **Coffin-Manson + NHPP composed** | Each mode is physically grounded; separable outputs (D_f, clog_pct); composed health in [0,1] | Two sub-models to calibrate; slightly more code |

**Decision:** Coffin-Manson + NHPP composed multiplicatively. Both sub-models emit their own
metric (damage fraction and clog percentage), which are inspectable independently and
combined for the scalar health value the chatbot surfaces.

---

## Recommendation

### Numeric defaults (paste-ready)

```python
# --- Coffin-Manson thermal fatigue ---
EPSILON_F_PRIME  = 0.35      # fatigue ductility coefficient (dimensionless)
C_EXPONENT       = -0.6      # fatigue ductility exponent (canonical, ductile metals)
CTE              = 17e-6     # coefficient of thermal expansion [1/K], stainless steel
DELTA_T_REF      = 50.0      # reference temperature swing [K] at nominal stress
# Plastic strain per tick: delta_ep = CTE * |delta_T|
# Cycles to failure:       N_f = 0.5 * (delta_ep / (2 * EPSILON_F_PRIME))**(1/C_EXPONENT)
# Damage increment:        D_tick = 1.0 / N_f

# --- NHPP clogging ---
LAMBDA_0         = 5e-5      # baseline clog rate [clogs/nozzle/tick] at nominal conditions
ALPHA_TEMP       = 0.08      # sensitivity to |temp_stress - T_opt| [1/K]
BETA_CONTAM      = 1.5       # sensitivity to normalised contamination [0..1]
T_OPT            = 0.0       # optimal temp_stress (normalised driver, dimensionless)
TOTAL_NOZZLES    = 5280      # per printhead column (HP Metal Jet S100 spec)

# Per tick:
# lambda_t = LAMBDA_0 * exp(ALPHA_TEMP * abs(temp_stress - T_OPT)
#                          + BETA_CONTAM * contamination)
# expected_new_clogs = lambda_t * (TOTAL_NOZZLES - current_clogs)
# clog_pct = current_clogs / TOTAL_NOZZLES

# --- Composite health ---
# H = (1 - D_f) * (1 - clog_pct)    # both factors in [0, 1]
```

**Key design choice:** `expected_new_clogs` draws from Poisson(lambda_t * remaining_nozzles)
each tick, giving stochastic runs. In deterministic mode, use the expected value directly.

**Composition rationale:** multiplicative because total functional capacity is the product
of structural integrity (1 - D_f) and nozzle availability (1 - clog_pct). If either reaches
0, the plate is fully failed regardless of the other.

---

## Open Questions

1. Should `temp_stress` be a raw temperature (K) or a normalised driver in [-1..1]?
   The ALPHA_TEMP default above assumes normalised; if raw K is used, scale alpha down ~50x.
2. Miner's rule is linear — does not capture load-sequence effects. Acceptable for a
   24-hour hackathon simulator; flag in comments.
3. Clog recovery: maintenance events should reset some fraction of `current_clogs`
   (e.g., purge cycle recovers ~80% of clogs). Tie to `maintenance_level` driver.
4. HP's optical drop detector fires post-print to flag failed nozzles — consider using
   this as the "observed clog_pct" in the chatbot narrative.
5. If B6 stochastic mode is enabled, use `numpy.random.poisson(lambda_t * remaining)`
   per tick; otherwise use expected value for reproducible runs.

---

## References

- [Low-cycle fatigue — Wikipedia](https://en.wikipedia.org/wiki/Low-cycle_fatigue)
- [Low Cycle Fatigue: Metal Fatigue Life Prediction — fatigue-life.com](https://fatigue-life.com/low-cycle-fatigue/)
- [NASA TM-87225: Low-Cycle Thermal Fatigue](https://ntrs.nasa.gov/api/citations/19860017179/downloads/19860017179.pdf)
- [Modeling Thermal Fatigue in CPV Cell Assemblies — NREL](https://docs.nrel.gov/docs/fy11osti/50685.pdf)
- [Modified Coffin-Manson equation for mechanical-thermal coupling — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1005030223003377)
- [NHPP Power Law — NIST Engineering Statistics Handbook 8.1.7.2](https://www.itl.nist.gov/div898/handbook/apr/section1/apr172.htm)
- [NHPP with covariates — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0951832016305270)
- [Optimization of Experimental Parameters to Suppress Nozzle Clogging in Inkjet Printing — ACS Ind. Eng. Chem. Res.](https://pubs.acs.org/doi/10.1021/ie301403g)
- [XTPL: Inkjet Nozzle Clogging Mechanisms](https://xtpl.com/inkjet-printing-of-conductive-structures-how-do-you-solve-nozzle-clogging/)
- [HP Metal Jet S100 Technical Whitepaper](https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-3333ENW)
- [Failure mechanisms in thermal inkjet printhead — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0026271404005165)
- [Homogeneous and NHPP for repairable systems — Accendo Reliability](https://accendoreliability.com/homogeneous-and-nonhomogeneous-poisson-process-hpp-and-nhpp-for-repairable-systems/)
