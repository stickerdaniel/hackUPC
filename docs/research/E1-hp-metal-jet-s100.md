# E1 — HP Metal Jet S100: Machine Research

## TL;DR

The HP Metal Jet S100 is a production-grade binder-jetting system introduced at IMTS 2022. It is not a hobbyist or prototyping printer: it is a four-station modular production line targeting automotive, industrial, and medical manufacturers. The print engine lays down up to 630 million binder drops per second through 63,360 nozzles across two print bars. Throughput reaches 1,990 cc/hr (at 50 µm layer thickness). Sintering is done off-machine in any compatible furnace — HP does not sell one. Build volume was expanded in 2024 to 430 × 309 × 170 mm.

---

## Machine Specs (table)

| Parameter | Value |
|---|---|
| Technology | Binder Jetting (metal powder + liquid binder) |
| Configurations | S100 (mass production), S100P (production), S100D (entry-level, in-printer cure) |
| Effective build volume (S100) | 430 × 309 × 170 mm (updated 2024; original 140 mm Z) |
| Effective build volume (S100P) | 430 × 309 × 100 mm |
| Effective build volume (S100D) | 430 × 309 × 40 mm |
| Print resolution | 1,200 dpi |
| Layer thickness | 35 – 140 µm (typical 50 µm) |
| Number of printheads | 6 HP Thermal Inkjet printheads on 2 print bars |
| Total nozzles | 63,360 |
| Binder drop rate | Up to 630 million drops/second |
| Build speed | 1,990 cc/hr (at 50 µm) |
| Materials certified | SS 316L, SS 17-4PH (MIM-grade powder) |
| Density after sintering | >96% (approaching wrought) |
| Starting price | ~$550,000 USD (full system) |
| Sintering furnace | Not included; compatible with any commercial furnace |

---

## Process Overview

Binder jetting for metal is a six-step process. The S100 handles steps 1–4 on-machine (or in-station); steps 5–6 happen off-machine.

1. **Powder spreading (recoater pass):** A recoater blade spreads a uniform, thin layer of MIM-grade metal powder across the build platform. Powder is replenished automatically from supply bins at each end of the scan axis.

2. **Binder jetting (print pass):** HP Thermal Inkjet printheads deposit nanogram-scale drops of a water-based latex-polymer binder precisely onto the powder layer at 1,200 dpi. The two print bars span the full build width, enabling single-pass printing.

3. **Layer-by-layer repeat:** The build platform descends by one layer thickness (35–140 µm), the recoater spreads fresh powder, and the printheads fire again. This repeats until the build is complete. The surrounding loose powder acts as self-supporting scaffolding — no support structures are required for most geometries.

4. **Curing (green part → strong green part):** The build unit is moved to the Curing Station, which uses infrared (IR) top heating to evaporate water from the binder and crosslink the long-chain latex polymer. The result is a "green part" with enough handling strength to survive depowdering.

5. **Powder removal:** Loose unbound powder is removed at the Powder Removal Station. The station automates powder recovery and build unit cleaning. Recovered powder is sieved and reclaimed by the Powder Management Station.

6. **Sintering (furnace, off-machine):** Green parts are loaded into a conventional MIM sintering furnace (tube, vacuum, or atmosphere — customer-supplied or outsourced). At sintering temperatures the polymer binder burns out (debinding), then atomic diffusion between powder particles densifies the part to >96% of theoretical density, achieving mechanical properties close to wrought stainless steel.

The four on-site stations — Powder Management Station, Printer, Curing Station, Powder Removal Station — are connected by mobile build units that roll between them on casters. HP's Device API automates scheduling and job tracking across a multi-printer factory cell.

---

## Component Glossary

### Recoater

The recoater is a blade-and-roller assembly that travels across the build platform once per layer to spread a precise, uniform bed of metal powder. It draws from powder supply bins positioned at each end of the scan axis. Consistent layer flatness and density are critical: voids or uneven packing directly cause porosity defects in sintered parts. The recoater's speed and blade geometry are tuned to the specific flowability of each certified powder (316L, 17-4PH).

### Printhead (HP Thermal Inkjet array)

Two print bars, each carrying three HP Thermal Inkjet printheads, span the full 309 mm build width. Each printhead has two independent columns of 5,280 nozzles (10,560 per head; 63,360 total), spaced at 1,200 nozzles per inch. Four nozzles address each 1/1,200-inch dot row — "4× nozzle redundancy" — so a single clogged nozzle does not create a print defect. The binder fluid is a proprietary water-based latex polymer formulated for metal particle wetting and later crosslinking. Drop placement accuracy is what determines the dimensional tolerance of the finished sintered part before shrinkage compensation.

### Heating Elements (Curing Station IR array)

The Curing Station contains an infrared radiant heater array above the build volume. After printing, the entire build unit — powder bed and all — is rolled in and the IR array raises the temperature enough to (a) evaporate the water carrier in the binder and (b) crosslink the latex polymer chains, locking the metal particles in a rigid green matrix. Without this step, the green part would crumble during powder removal. The S100D variant integrates this curing step inside the printer itself to reduce capital cost at the expense of build height (40 mm Z).

---

## Talking Points for the Deck

- **Not a prototype machine.** The S100 is explicitly designed for mass production supply chains, with modularity (multiple build units, multiple printers, one shared Powder Management + Curing + Powder Removal station) to keep the printer running 24/7.
- **No support structures.** Loose powder supports overhangs during printing. This enables complex internal channels and consolidated assemblies that replace many machined parts — the Volkswagen T-Roc A-pillar replaced 8 discrete stamped parts and came out ~50% lighter.
- **HP's printhead pedigree.** The thermal inkjet architecture descends directly from HP's PageWide Web Press and HP Jet Fusion 3D printer printheads — millions of hours of accumulated field data on nozzle reliability.
- **Sintering is industry-standard.** The S100 is deliberately agnostic on furnaces. Customers can use existing MIM furnaces or outsource sintering, removing a capital barrier.
- **Materials are MIM-grade.** 316L and 17-4PH are the same alloys the metal injection molding (MIM) industry has qualified for decades, so supplier chains, sintering recipes, and ASTM acceptance criteria already exist.
- **2024 expansion:** Build height grew from 140 mm to 170 mm (+21%), allowing taller parts and denser part nesting per build.
- **Key industrial customers:** Volkswagen (automotive structural), Schneider Electric / GKN (electrical switchgear air filters), Cobra Golf (golf heads), Parmatech, Legor Group (jewelry).

---

## References

- HP official Metal Jet S100 product page: https://www.hp.com/us-en/printers/3d-printers/products/metal-jet.html
- HP Metal Jet S100 press release (IMTS 2022): https://press.hp.com/us/en/press-releases/2022/hp-new-metal-jet-s100-solution-mass-production.html
- HP Metal Jet Technology White Paper (PDF, garage-press): https://www.hp.com/content/dam/sites/garage-press/press/press-kits/2022/hp-metal-jet-s100-solution/Metal%20Jet%20Tech%20White%20Paper_Final.pdf
- HP Metal Jet S100 Technical Whitepaper 4AA7-3333ENW: https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-3333ENW
- HP Metal Jet S100 Platform datasheet 4AA8-1958ENW: https://h20195.www2.hp.com/v2/getpdf.aspx/4AA8-1958ENW.pdf
- HP Metal Jet S100 Powder Management Station documentation: https://h10032.www1.hp.com/ctg/Manual/c08572126.pdf
- "HP launches new Metal Jet S100 3D printer at IMTS," 3D Printing Industry: https://3dprintingindustry.com/news/hp-launches-new-metal-jet-s100-3d-printer-at-imts-technical-specifications-and-pricing-214678/
- "HP increases build height of S100," TCT Magazine: https://www.tctmagazine.com/additive-manufacturing-3d-printing-news/hp-build-height-s100-metal-jet-software-materials/
- "Understanding HP's Metal Jet," Additive Manufacturing Media: https://www.additivemanufacturing.media/articles/understanding-hps-metal-jet-beyond-part-geometry-now-its-about-modularity-automation-and-scale
- "HP Metal Jet: Growing momentum," PIM International: https://www.pim-international.com/articles/hp-metal-jet-growing-momentum-and-new-applications-as-binder-jetting-comes-of-age/
- "Metal Jet S100 launched by HP," DEVELOP3D: https://develop3d.com/3d-printing/metal-jet-s100-launched-by-hp/
- HP Metal Jet S100 Printing Solution brochure (Endeavor3D/April 2023): https://endeavor3d.com/wp-content/uploads/2024/04/00.-3D-WW-HP-Metal-Jet-S100-Printing-Solution_-Brochure_April2023.pdf
