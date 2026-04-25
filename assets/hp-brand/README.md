# HP Brand Assets

Mirror of HP's official brand assets pulled from [HP Brand Central](https://www.hp.com/us-en/hp-information/brandcentral/resource-library.html). Each top-level folder is the unzipped contents of one ZIP that HP serves at `https://www.hp.com/content/dam/sites/brand-central/private/<name>.zip` (id.hp.com login required).

Large binaries (`*.pptx`, `*.psb`, `*.psd`, `*.aep`, `*.mov`, `*.mp4`, `*.gif`) are tracked via Git LFS — see the repo-root `.gitattributes`. Vector and raster source files (`.ai .eps .pdf .png .jpg`) live in regular git so they're previewable in the GitHub UI.

## Inventory

| Folder | Source ZIP | Contents |
| --- | --- | --- |
| `Brand_Core_Public/` | `Brand_Core_Public.zip` | `Brand_Core_Public.pdf` (executive summary, 312 KB) |
| `HP_Brand_Line/` | `HP_Brand_Line.zip` | 2 PNG assets of the HP brand line |
| `HP_Color_Swatches/` | `HP_Color_Swatches.zip` | 27 files: AI swatches + ASE palettes for the three core color families (Electric Blue, Orange Bloom, Power Storm) plus the Pantone Connect palette and per-color reference PDFs |
| `HP_Email_Templates/` | `HP_Email_Templates.zip` | 3 Outlook `.oft` templates (Memo, Newsletter, Memo+Image) |
| `HP_Logo_White_Keyline/` | `HP_Logo_White_Keyline.zip` | 16 logo lockups across CMYK / RGB / HEX / PMS color modes |
| `HP_Motion_Assets/` | `HP_Motion_Assets.zip` | After Effects projects, end-frame and logo animations, MP4/MOV/GIF exports, plus the Photoshop sources for the layout work (~725 MB total) |
| `HP_Partner_Logo_Lockups_Templates/` | `HP_Partner_Logo_Lockups_Templates.zip` | `HP_Partner_Logo_Lockups_Templates.ai` |
| `HP_PowerPoint_Template_2025/` | `HP_PowerPoint_Template_2025.zip` | Standard + Vertical `.potx` master templates for 2025 |
| `HP_Stripes/` | `HP_Stripes.zip` | Stripe assets at 100 / 500 / 1000 widths in CMYK / RGB / HEX |
| `Naming_Lockup_Template_2026/` | `Naming_Lockup_Template_2026.zip` | `Naming Lockup Template 2026.ai` |
| `One_HP_Retail_Etail_Guidelines/` | `One_HP_Retail_Etail_Guidelines.zip` | One HP Retail/Etail Playbook PPTX (R5, Mar 2026, ~620 MB — LFS) |

## Linked external resources (not mirrored)

These are referenced from Brand Central but live behind separate auth surfaces our session couldn't reach — listed for traceability:

- Technical Guidelines deck — `https://www.figma.com/deck/tDdMASBx8cOajXHsZEAtu2/Technical-Guidelines`
- Executive Summary deck — `https://www.figma.com/deck/NFqIAk3WyS0cxcJKVWW588/Executive-Summary`
- HP Digital Guidelines deck — `https://www.figma.com/deck/D2a4CknTEUlERXp7Gj0G4I/HP-Digital-Guidelines`
- NPI Supplemental Guidelines deck — `https://www.figma.com/deck/oDJ05J5ATaRLFyiFkG56XS/NPI-Supplemental-Guidelines`
- Brand photography DAM — `https://assetmanager.hp.com/dam/savedsearches.table:rowaction?action=view&recordId=savedfieldsearch%3A7962ee7b-ca06-4c14-baaf-3851b2a913d2`
- Brand VisID news archive — `https://content.int.hp.com/sites/Portal/news/2025/20250304_News_Brand_VisID.page?yid=6589707`
- Veneer fonts — `https://veneer.hp.com/foundation/design-language/typography/font-files/`
- HP Partnership portal — `https://partnership.hp.com/`

## Source pages crawled

- `/us-en/hp-information/brandcentral.html`
- `/us-en/hp-information/brandcentral/brand-framework.html`
- `/us-en/hp-information/brandcentral/our-visual-identity.html`
- `/us-en/hp-information/brandcentral/resource-library.html`

Pulled on 2026-04-25.
