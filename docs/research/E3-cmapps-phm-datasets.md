# E3: C-MAPSS and PHM Society Datasets as Shape Priors

**Purpose:** Visual shape priors only. We do not train on these datasets; we mimic the look of realistic degradation curves.

---

## TL;DR

C-MAPSS and related datasets share a consistent two-phase degradation shape: a long, noisy but roughly flat plateau during healthy operation followed by a steeper monotonic drift toward failure. Bearings (FEMTO/PHM 2012) are more abrupt — near-constant RMS then an exponential spike in the last fraction of life. Both patterns apply well as priors for synthetic Metal Jet S100 component curves.

---

## Dataset Overviews

### C-MAPSS (NASA, 2008)

Commercial Modular Aero-Propulsion System Simulation. Four sub-datasets (FD001–FD004) covering 1–6 operating conditions and 1–2 fault modes. Each unit is a multivariate run-to-failure time series of 21 sensor channels (temperature, pressure, speed, flow ratios). 100–260 training trajectories per sub-dataset. Trajectories range roughly 130–350 cycles. The canonical reference is Saxena et al. 2008 (NASA TM-2008-215608).

Key signal facts: only 14 of 21 sensors carry degradation information; the rest are constant or near-constant. Monotonic sensors (e.g., exhaust gas temperature, HPC outlet temperature and pressure) drift clearly toward failure. Early cycles show stable baseline; RUL is capped at ~125–130 cycles to reflect the no-visible-degradation plateau.

### PHM Society 2008 Challenge

Uses the same C-MAPSS-generated turbofan data. Over 200 multivariate time series. Task was RUL prediction. Curves exhibit the same piecewise shape as C-MAPSS.

### PHM Society / IEEE 2012 (FEMTO / PRONOSTIA Bearing Dataset)

Accelerated degradation of deep-groove ball bearings under three load/speed conditions (1500–1800 rpm, 4–5 kN). Bearing lifetimes span 28 minutes to 7 hours — high variability. Signal: horizontal and vertical vibration sampled at 25.6 kHz, summarised as RMS per 0.1-second window.

Degradation shape: long stationary phase (Stage I) with low-amplitude Gaussian noise, then a fault-initiation elbow, then near-exponential RMS growth (Stage II/III) up to the 20 g amplitude limit. Some bearings skip Stage II entirely — failure is almost step-like. High inter-unit variability even under identical conditions.

### N-CMAPSS (NASA, 2021 — Arias Chao et al.)

Next-generation simulator using real flight-condition profiles. Engine fleet of 80+ units, each with 14 sensor channels plus flight descriptors. Degradation is modelled at the component level (fan, HPC, HPT, LPC, LPT) with a nonlinear health index that reaches 0 at failure. Operating history determines degradation onset, so the plateau length varies across units. Health index is approximately convex: slow decay at first, accelerating near end of life.

---

## Visual Rules of Thumb

These are the four rules our synthetic data generator should satisfy.

1. **Long healthy plateau, short degradation tail.** Across all datasets, healthy operation occupies 60–80% of total life. Visible drift begins in the final 20–40%. Clip synthetic RUL labels at a fixed "no-degradation" ceiling (analogous to the 125-cycle cap) to reflect this.

2. **Monotonic drift with superimposed cycle-to-cycle noise.** Degrading sensors do not oscillate back to healthy levels. The trend is monotone (rising or falling depending on the sensor), but each individual reading is noisy. In C-MAPSS, z-score noise on informative sensors is approximately 1–3% of the full-scale range in healthy state and grows slightly near failure. Simulate this as a low-amplitude white or AR(1) noise layer on top of the trend.

3. **Accelerating slope near end-of-life (convex profile).** The degradation rate is not constant. The slope of the health index (or surrogate sensor) increases as the unit approaches failure — a convex curve, not a straight line. For bearings the acceleration is especially abrupt (exponential RMS rise over the last 5–15% of life). For turbofans the acceleration is gentler but still convex. Use a power-law or Weibull-like decay function rather than a linear ramp.

4. **High inter-unit variability in plateau length, low variability in curve shape.** FEMTO bearings span 28 minutes to 7 hours total life under identical loads. C-MAPSS engines vary by ±30–50 cycles in total life. The characteristic shape (plateau → accelerating drop) is preserved across units, but the absolute duration scales widely. Synthetic units should sample total lifetime from a broad distribution while keeping the shape template fixed.

---

## Risks of Mimicry Without Training

- **Distribution mismatch:** Turbofan and bearing physics differ fundamentally from Metal Jet print-head, recoater, and nozzle degradation. The shape prior is borrowed; any amplitude or timescale numbers from these datasets are meaningless for HP hardware.
- **Spurious realism:** Overly faithful reproduction of C-MAPSS noise statistics (e.g., exact SNR) may fool reviewers into thinking the data is validated, when it is purely cosmetic.
- **Plateau-length anchoring:** C-MAPSS uses a 125-cycle plateau cap as a modelling convenience, not a physical law. Importing this threshold into Metal Jet synthetic curves without justification would be wrong.
- **Bearing abruptness:** FEMTO bearings fail very suddenly; using a bearing-like shape prior for a slow wear component (e.g., recoater blade) would understate warning time and mislead the maintenance agent.

---

## References

- Saxena, A., Goebel, K., Simon, D., Eklund, N. (2008). *Damage propagation modeling for aircraft engine run-to-failure simulation.* ICES 2008. NASA/TM-2008-215608. <https://c3.ndc.nasa.gov/dashlink/resources/139/>
- NASA Open Data Portal — CMAPSS Jet Engine Simulated Data. <https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data>
- NASA Open Data Portal — PHM 2008 Challenge. <https://data.nasa.gov/dataset/phm-2008-challenge>
- Arias Chao, M., Kulkarni, C., Goebel, K., Fink, O. (2021). *Aircraft Engine Run-to-Failure Dataset under Real Flight Conditions for Prognostics and Diagnostics.* Data, 6(1), 5. <https://www.mdpi.com/2306-5729/6/1/5>
- Nectoux, P. et al. (2012). *PRONOSTIA: An Experimental Platform for Bearings Accelerated Degradation Tests.* IEEE PHM 2012 Data Challenge. <https://github.com/wkzs111/phm-ieee-2012-data-challenge-dataset>
- PHM Society Data Repository (NASA mirror). <https://data.phmsociety.org/nasa/>
- Mauthe, F., Steinmann, L., Zeiler, P. (2025). *Overview of publicly available degradation data sets for PHM.* arXiv:2403.13694. <https://arxiv.org/abs/2403.13694>
- Remaining Useful Life Estimation with Change-Point Detection, MDPI Applied Sciences, 2023. <https://www.mdpi.com/2076-3417/13/21/11893>
