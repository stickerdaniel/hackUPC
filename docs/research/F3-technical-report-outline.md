# F3 — Technical Report Outline

**Item:** Outline the technical report headings (mirror the slide deck, 3 phases).
**Audience:** HP AI Innovation Hub judges.
**Target length:** ~2000 words body + references appendix.

---

## TL;DR

Use plain Markdown compiled to PDF via Pandoc with a minimal LaTeX template.
Total body target: 2000-2200 words across 8 top-level sections mirroring the
Phase 1 / Phase 2 / Phase 3 deck structure. Formula derivations go inline (brief)
with the heavy math relegated to an Appendix. Four figures required (architecture
diagram, telemetry chart, chatbot screenshot, citation-trace example). APA-style
references, numbered inline as [1], collected in a final References section.

---

## Markdown Outline (full ## tree)

```
# Digital Co-Pilot for the HP Metal Jet S100
## A Hackathon Technical Report — HackUPC 2026

### Abstract
One paragraph: problem, approach, three-phase solution, key result.

## 1. Introduction
### 1.1 Challenge Statement
### 1.2 Scope and Constraints
### 1.3 Report Structure

## 2. System Architecture
### 2.1 High-Level Design
(Figure 1: architecture diagram — engine → historian → LLM interface)
### 2.2 Technology Stack

## 3. Phase 1 — Degradation Model (the Brain)
### 3.1 Subsystems and Components in Scope
### 3.2 Failure Models Applied
  3.2.1 Recoater Blade — Archard Wear
  3.2.2 Nozzle Plate — Clogging + Arrhenius Thermal Fatigue
  3.2.3 Heating Elements — Exponential Electrical Degradation
### 3.3 Environmental and Operational Drivers
### 3.4 Cascading Failure Interactions
### 3.5 Health Index and Operational Status Schema
### 3.6 Determinism and Seeding Strategy

## 4. Phase 2 — Simulation Engine (the Clock + Historian)
### 4.1 Time-Step Architecture
### 4.2 Driver Generation and Profiles
(Figure 2: sample telemetry chart — health index over time for 3 components)
### 4.3 Historian Schema (SQLite / CSV)
### 4.4 Run and Scenario Identity
### 4.5 Stochastic Mode and Chaos Injection

## 5. Phase 3 — Natural-Language Interface (the Voice)
### 5.1 Grounding Protocol and Zero-Hallucination Policy
### 5.2 Reasoning Architecture
  5.2.1 Context Injection (baseline)
  5.2.2 Contextual RAG
  5.2.3 Agentic ReAct Loop (bonus)
### 5.3 Evidence Citation and Severity Tagging
(Figure 3: chatbot screenshot with citation trace)
(Figure 4: citation format example — timestamp, component, run ID)
### 5.4 Proactive Alerting (bonus)
### 5.5 Voice Interface (bonus)

## 6. Results and Evaluation
### 6.1 Phase 1 — Model Accuracy and Sanity Checks
### 6.2 Phase 2 — Simulation Fidelity
### 6.3 Phase 3 — Grounding Accuracy and Reasoning Quality
### 6.4 Limitations

## 7. Challenges and Solutions

## 8. Conclusion and Future Work

## Appendix A — Mathematical Derivations
  A.1 Archard Wear Equation (Recoater Blade)
  A.2 Arrhenius Rate Law (Nozzle Clog Acceleration)
  A.3 Coffin-Manson Thermal Cycle Fatigue (Heating Elements)
  A.4 Composite Health Index Aggregation Formula

## References
```

---

## Per-Section Word Budget

| Section | Target words |
|:--------|------------:|
| Abstract | 80 |
| 1. Introduction | 150 |
| 2. System Architecture | 150 |
| 3. Phase 1 — Degradation Model | 500 |
| 4. Phase 2 — Simulation Engine | 300 |
| 5. Phase 3 — NL Interface | 350 |
| 6. Results and Evaluation | 250 |
| 7. Challenges and Solutions | 150 |
| 8. Conclusion | 100 |
| Appendix A (equations only, not counted in body) | — |
| References (not counted in body) | — |
| **Total body** | **~2030** |

Inline math in sections 3 and 4 is kept to one display equation per sub-section
(the result form only). Full derivations — with intermediate steps and parameter
sensitivity notes — belong in Appendix A, cited as "see Appendix A.1".

---

## Required Figures

| # | Name | What to show | Where in report |
|:--|:-----|:-------------|:----------------|
| 1 | Architecture diagram | Three-layer stack: Phase 1 engine box → Phase 2 historian box → Phase 3 LLM interface box; arrows show data flow; drivers listed on left edge | Section 2.1 |
| 2 | Sample telemetry chart | Line chart: time (x) vs health index 0-1 (y); three lines (blade, nozzle, heater); annotate a CRITICAL threshold crossing | Section 4.2 |
| 3 | Chatbot screenshot | One question-answer exchange showing severity tag (`CRITICAL`), grounded answer, and evidence citation row | Section 5.3 |
| 4 | Citation format example | Code-block or styled box showing one citation record (timestamp, component, run ID, value) as it appears in an LLM response | Section 5.3 |

Figures produced as: SVG/PNG for diagrams (draw.io or matplotlib), annotated
screenshot for Figure 3, monospaced code block for Figure 4.

---

## Tooling

**Recommended: Pandoc + Markdown to PDF.**

- Write everything in one `report.md` (or split per section and include via
  Pandoc `--include-before-body`).
- Compile: `pandoc report.md -o report.pdf --pdf-engine=xelatex -V geometry:margin=2.5cm -V fontsize=11pt`
- No Quarto needed — Quarto adds value for notebooks, not for a pure prose
  report. Use it only if the team already has `.ipynb` outputs to embed.
- Figures embedded as `![caption](path/to/fig.png){width=90%}`.
- Math blocks: `$$...$$` (Pandoc renders via KaTeX or LaTeX).
- A four-line `metadata.yaml` block at the top of `report.md` sets title,
  authors, date, and `documentclass: article`.

---

## References

Style: APA-ish, numbered `[1]`, collected at the end.

Example entries:
```
[1] Archard, J. F. (1953). Contact and rubbing of flat surfaces.
    Journal of Applied Physics, 24(8), 981-988.
[2] Arrhenius, S. (1889). Uber die Reaktionsgeschwindigkeit...
    Zeitschrift fur physikalische Chemie, 4, 226-248.
[3] HP Inc. (2024). Metal Jet S100 Product Brief. hp.com/go/metaljet.
[4] Open-Meteo.com. (2024). Free Weather API. https://open-meteo.com
[5] LangChain. (2024). LangChain documentation. https://docs.langchain.com
```

Citation placement: inline number `[1]` immediately after the claim or equation
it supports. Do not use footnotes — judges read on-screen.
