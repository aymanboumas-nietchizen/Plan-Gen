# Competitors and adjacent tools — residential layout, for a Moroccan agency

Session date: **2026-09-29**. Author: planfgen-scout (research only, no engine code).
PLANFGEN state assumed: through S27 (`b0142fc`, branch `v2-space-planning-engine-vwnu5z`).

---

## 0. Read this first: how far the evidence goes

**All vendor and paper pages were unreachable from this environment.** The egress
proxy refused every direct fetch (organisation policy, not a transient error). I did
not retry blocked hosts or work around the block. The hosts I tested were:
finch3d.com, docs.finch3d.com, testfit.io, blogs.autodesk.com, adsknews.autodesk.com,
aecmag.com, arxiv.org, illustrarch.com, hypar.io, snaptrude.com, maket.ai,
archistar.ai, architechtures.com, giraffe.build, modelur.com, skema.ai, youtube.com,
web.archive.org, sgg.gov.ma, semanticscholar.org, archdaily.com. This matches the S26
finding that Moroccan regulatory sites are blocked too.

So **every claim below comes from web-search result summaries of the cited URLs**, not
from reading the pages myself. That is good enough to place the tools. It is not good
enough to quote a price in a contract. The confidence labels mean this:

- **[doc]**: the claim appears in the vendor's own documentation or product page, as
  summarised by search. This is the strongest evidence available here.
- **[mkt]**: vendor marketing, a press release or a founder's post. It is a claim, not
  proof that it shipped.
- **[3p]**: a third-party review, aggregator or blog. It can be stale or wrong.
- **[unverified]**: I could not tie the claim to any source I could see.

Every URL was accessed 2026-09-29. Publication dates are given where the result showed them.

---

## 1. Alarms first

### 1a. The regulation moat: no alarm, but one tool to watch

**I found no tool that encodes Moroccan regulation**: not décret 2-64-445, not the
Casablanca arrêté, and not the plans d'aménagement. Searches in English, French and
Spanish for Moroccan or North African compliance in a generative layout tool found
nothing. The only Moroccan hits were:

- the Archiplan firm's ChatGPT Q&A assistant ([archiplan.ma](https://www.archiplan.ma/post/lintelligence-artificielle-au-service-de-l-architecture)) [mkt]
- blog posts about AI and BIM ([archiplan.ma](https://www.archiplan.ma/post/ia-bim-au-maroc)) [mkt]

Neither generates plans.

This is absence of evidence from search only. It is not proof. Three tools show that
"regulation as the product" is a real market position, and one of them is close by:

| Tool | Regulation it encodes | Why it matters |
|---|---|---|
| **ARCHITEChTURES** (Málaga, Spain) | Spanish regulatory constraints plus financial goals, through a "proprietary NeuroSymbolic AI" trained on BIM samples [mkt] ([datadrivenaec](https://datadrivenaec.com/tools/architechtures), [architechtures.com](https://architechtures.com/en)) | **This is the one to watch.** It generates whole residential schemes (units, commercial, parking) against Spanish regulation, for developers. It is based in Andalusia, a short crossing from Tangier, and Spanish developers are active in northern Morocco. I found no evidence that it supports Morocco. Re-check every quarter. |
| **Hektar** (Stockholm) | Swedish and Dutch *detaljplaner* as "first-class regulatory layers", with generative block configurations against them [3p, but written by Hektar] ([parametric.se](https://www.parametric.se/post/comparing-early-stage-feasibility-tools-2026-forma-giraffe-finch-testfit-hektar)) | It proves that a small vendor can win a region by encoding local plans deeply rather than broadly. It is the same strategy as PLANFGEN's, at the massing scale. |
| **Mesetys** (France, from the interior-architecture studio Ouvrage) | "Integrates the standards in force" for French housing interiors. Options scored out of 100 against the brief. It won the In'li / Action Logement call for projects [mkt] ([mesetys.tech](https://www.mesetys.tech/outil-ia-generation-plan-logement), [monimmeuble.com](https://monimmeuble.com/actualite/ia-en-architecture-dinterieur-mesetys-revolutionne-la-conception-des-logements)) | It is French-language, generates single dwellings, and targets promoteurs. It is **the closest scope match to PLANFGEN today**. French norms are not Moroccan norms, but a Moroccan agency reads French marketing. Outputs and pricing are unverified. |

**Threat:** low today and rising. The moat holds only while it stays deep: sourced
values, gates rather than warnings, and a DXF a bureau de contrôle accepts. A shallow
"Moroccan profile" of COS, CES and height is something any of these vendors could add
in a sprint.

### 1b. `PROMPTS-NEXT.md` has a factual error in a load-bearing sentence

The file says: *"Finch, the market leader, uses no ML for generation."* **This is no
longer true as a statement about the market leader's product.**

- **Finch's floor-plate engine is still algorithmic.** It is a scored search with
  "non-negotiable" variables and user-weighted metrics
  ([docs: Algorithm Theory](https://docs.finch3d.com/floor-plate-studio/algorithm-theory)) [doc].
- **Finch's unit plans now have an ML path.** Generation returns two sets of results:
  (a) plans from the firm's Plan Library, adapted by Finch algorithms, and (b)
  "AI-generated unique plans based on your adaptive plan library's design style and
  rules". Finch builds the library from the firm's `.dwg`, `.pdf` or `.jpg` plans
  ([docs: Enterprise – Generate Unit Plan](https://docs.finch3d.com/unit-plan-studio/enterprise-generate-unit-plan);
  [Architosh, 2024-09](https://architosh.com/2024/09/finch3d-advances-ai-based-floor-plan-generator/)) [doc/mkt].
  However: *"AI Unit plan generation is currently only available for Finch's strategic
  AI customers"* (Finch docs, returned for the [Export](https://docs.finch3d.com/docs/projects-and-variants/export) / [FAQ](https://docs.finch3d.com/readme/faq) pages; exact page not confirmable) [doc].
  So it has shipped, but it is gated.
- **Autodesk Forma's Building Layout Explorer is a neural-CAD foundation model.** It
  produces floor-plan layouts from a massing and structural choices. It is
  *experimental*, for commercial Forma Site Design users with **data stored in the
  US** ([Architosh, 2025-09](https://architosh.com/2025/09/au25-all-about-autodesks-ai-neural-cad-engines/);
  [Autodesk News](https://adsknews.autodesk.com/en/news/building-layout-explorer-in-autodesk-forma/), which is blocked, so this is from the snippet) [mkt].
- **PlanFinder** (a Rhino/Grasshopper plugin) "trains a custom diffusion model on plans,
  that generates the walls automatically", given outer walls, facade and entrance
  ([food4rhino](https://www.food4rhino.com/en/app/planfinder)) [doc]. **This one is in
  the user's own toolchain.**

**Does this reopen training? No.** The project's bar is a working method that produces
metric, wall-structured, code-compliant output. None of the above publishes evidence
that it meets that bar:

- Finch's AI path is gated and unbenchmarked.
- Forma's is experimental and region-locked.
- PlanFinder's quality is unverified.

The newest papers still miss the bar:

| Paper | What it does | Why it misses |
|---|---|---|
| RLVR for floor plans ([arXiv 2605.14117](https://arxiv.org/abs/2605.14117), ACL Findings 2026) | Uses exactly the RLVR recipe that `PROMPTS-NEXT` names as the only acceptable route | Trains on RPLAN and ProcTHOR. Outputs room polygons, not walls. RLVR *reduces* overlap by 65 %, which means overlaps remain. |
| Ergonomic-prior transformer ([arXiv 2604.08411](https://arxiv.org/abs/2604.08411), Eurographics 2026 short paper) | Adds ergonomic priors to a transformer | Same data class |
| SSPT ([arXiv 2602.22507](https://arxiv.org/abs/2602.22507)) | Space-syntax post-training | RPLAN-style layouts |

**Action:** the *conclusion* in `PROMPTS-NEXT.md` stands. The *reason* must be
rewritten, or the next reader will find the Finch docs and conclude the whole section
is stale. Suggested replacement:

> "The market leaders now ship ML unit-plan generation (Finch, gated to strategic
> customers; Forma, experimental, US-only; PlanFinder, a diffusion model in Rhino). None
> publishes metric, wall-structured, code-gated results. Every published method trains
> on RPLAN, LIFULL or ProcTHOR and outputs room polygons. The engine stays the
> prerequisite for any RLVR."

Owner: whoever owns `PROMPTS-NEXT.md` (planfgen-product, with planfgen-optima to sign
off).

---

## 2. The market has two halves, and PLANFGEN is in the smaller one

| Half | Tools | What they generate | Where the unit interior comes from |
|---|---|---|---|
| **Floor-plate packers and feasibility** | TestFit, Finch Floor Plate Studio, Forma, Giraffe, Hektar, ARCHITEChTURES, Digital Blue Foam | massing, cores, corridors, unit mix, yield | **A kit of parts drawn by the architect.** TestFit's Unit Editor builds a "unit library"; TestFit also imports kits of parts from Revit ([support: unit editor](https://support.testfit.io/knowledge/unit-editor), [support: Revit kit of parts](https://support.testfit.io/knowledge/exporting-kit-of-parts-units-site-boundary-from-revit-to-testfit)) [doc] |
| **Unit-interior generators** | Finch Unit Plan (gated AI), PlanFinder, Maket, Mesetys, Snaptrude (programme to spaces), Hypar (space planning and test fits) | rooms, walls, doors, furniture inside a given envelope | generated |

**PLANFGEN today is a unit-interior generator.** Of the three named benchmarks, only
Finch is in the same half, and only through its gated AI path. **TestFit is not a
competitor to PLANFGEN today. It is a complement.** It needs someone to draw the units
it packs. It becomes a competitor only when PLANFGEN builds floor plates.

---

## 3. Per tool

### Finch (Finch3D, Malmö, founded 2019)

| | |
|---|---|
| Generates | **Floor plates:** unit mix around corridors, stairwells and custom cores. Hits requested unit sizes exactly ("if you request a 40 m² apartment, that's what you'll get"; leftover area goes to one unit per stairwell) ([docs: Generate Unit Mix & Corridors](https://docs.finch3d.com/floor-plate-studio/generate-unit-mix-and-corridors)) [doc]. **Unit plans:** Plan Library adaptation, plus gated AI plans (§1b). Also furnished, tagged units. |
| Input | A massing or floor outline, corridor centreline and width, core, unit mix targets, and min/max areas. Rules per plan: "between these spaces X", "at least X m²", "at least X daylight" ([AEC Magazine](https://aecmag.com/ai/finch3d-starts-to-sing/)) [3p] |
| Steering | Weight sliders ("metrics with sliders further right receive higher priority"), real-time metrics, and **Archie**, an agent that places doors, checks compliance and propagates edits across linked units ([finch3d.com/product](https://www.finch3d.com/product)) [mkt] |
| Output | Revit (unit model groups, walls, doors, area plans, sheets, furniture, tags), Rhino (2D and 3D layers), Grasshopper streaming, Archicad, Forma, PNG and CSV ([docs: Export](https://docs.finch3d.com/docs/projects-and-variants/export), [docs: Revit](https://docs.finch3d.com/courses/finch-101/finch-101-download-to-revit)) [doc]. **DWG/DXF and IFC are not listed** [unverified either way]. |
| Codes | "Local codes" are embedded in the firm's own Plan Library entries. It is not a regulation engine [doc/mkt]. |
| Pricing | Basic about €49/month; individual about €79/month; Enterprise €14,500/year minimum for 3 seats (about €4.8k per seat), which includes AI generation, firm libraries and Archie ([finch3d.com/pricing](https://www.finch3d.com/pricing) via aggregators) [3p] |
| Method | Graph of space relations generated automatically, plus optimisation with user weights ([AEC Magazine](https://aecmag.com/ai/finch3d-starts-to-sing/)) [3p]. Library adaptation, plus a learned generator for AI plans [doc]. |

### TestFit (Dallas)

| | |
|---|---|
| Generates | Site plans, parking, buildings, **floor plates packed with units** (inline, inside-corner, outside-corner, dead-end units), cores, corridors and podiums ([support: units layer](https://support.testfit.io/knowledge/unit-editor), [support: core-based buildings](https://support.testfit.io/knowledge/core-based-buildings)) [doc]. It does **not** generate unit interiors: units are a user-drawn kit of parts [doc]. |
| Input | Parcel, zoning profile (user-defined, pass/fail against it), unit mix percentages, corridor width, and more than 100 parameters. Cost, rent and land inputs for yield ([support: zoning profile](https://support.testfit.io/knowledge/getting-started/zoning-profile)) [doc] |
| Steering | Direct manipulation with instant re-solve. Unit-mix sliders repack every floor. "Generative Design" enumerates thousands of options sortable by FAR, parking ratio and yield on cost ([Architosh, 2024-07](https://architosh.com/2024/07/testfit-generative-design-goes-live/)) [mkt]. Method: recursive re-solve until the targets are hit ([Architect Magazine Q&A](https://www.architectmagazine.com/technology/q-a-testfit-ceo-clifton-harness-has-some-reservations-about-his-successful-generative-design-tool_o/)) [3p] |
| Output | `.dxf`, `.skp`, `.csv`, `.glTF`, `.tfrvt` (Revit add-in) ([support: exporting data](https://support.testfit.io/knowledge/getting-started/exporting-data)) [doc]. No IFC listed. |
| International | Metric and euro were added. Data layers are US and Canada only (Canada parcels arrived in 2025) ([2025 year in review](https://www.testfit.io/blog/2025-testfit-year-in-review), [AEC Magazine "TestFit runs free"](https://aecmag.com/software/testfit-runs-free/)) [doc/3p] |
| Pricing | Parking Solver $195/month; **Site Solver from $15,000/year**; Portfolio from $20,000/year ([testfit.io/pricing](https://www.testfit.io/pricing)) [doc, via snippet] |
| 2025 focus | Parking, drive networks, parcels, utilities. **Nothing on unit interiors** [doc] |

### Autodesk Forma (formerly Spacemaker)

| | |
|---|---|
| Generates | **Site Design:** massing, with sun, wind, noise and daylight analysis (its strength) ([parametric.se](https://www.parametric.se/post/comparing-early-stage-feasibility-tools-2026-forma-giraffe-finch-testfit-hektar)) [3p]. **Building Design** (released 2026-04-07): schematic floor plans and modular facades, walls snapping to grids, and unit-level GFA since 2026-07 ([Autodesk blog 2026-07-13](https://blogs.autodesk.com/forma/2026/07/13/whats-new-in-forma-building-design-stairs-section-slicing-and-unit-level-gfa/), [archpaper 2026-04](https://www.archpaper.com/2026/04/autodesk-forma-building-design/)) [doc via snippet]. **Building Layout Explorer:** neural-CAD layouts, single-loaded versus double-loaded corridors side by side, experimental and US-data-only [mkt]. |
| Output | Native, geolocated Revit model with wall, window and slab families [doc via snippet] |
| Pricing | Site Design $700/year (included in the AEC Collection). Building Design is "free for Revit subscribers" per the search summaries ([autodesk.com](https://www.autodesk.com/products/forma-site-design/overview), [illustrarch](https://illustrarch.com/articles/design-softwares/73363-autodesk-forma-review.html)) [doc/3p] |
| Method | 2020 GAN research on apartment layouts ([Spacemaker research blog](https://medium.com/spacemaker-research-blog/space-layouts-gans-2329c8f85fe8)) [doc]; now neural-CAD foundation models trained on "aggregated 3D AEC data" [mkt] |
| For this agency | The threat is **distribution, not capability**. Any agency on a Revit subscription gets Building Design free. Moroccan agencies that work in AutoCAD and Rhino are less exposed. |

### The others, briefly

| Tool | What it does for residential | Output | Price | Relevance to this agency |
|---|---|---|---|---|
| **PlanFinder** | Rhino/GH plugin. *Fit* (library plan into outer walls), *Generate* (diffusion model, walls from outer walls, facade and entrance), *Furnish* ([food4rhino](https://www.food4rhino.com/en/app/planfinder)) [doc] | Rhino, GH, Revit, API | Roughly €10–49/month; 30-day trial ([aggregator](https://www.morningdough.com/ai-tools/planfinder-ai/)) [3p] | **The most direct threat in the user's own toolchain.** Cheap, and scoped to single units. No regulation. |
| **Magnetizing Floor Plan Generator** | Open-source GH plugin. Rooms placed one by one, each with its own corridor attached to the main corridor structure; aimed at public buildings ([GitHub](https://github.com/hellguz/Magnetizing_FloorPlanGenerator), [food4rhino](https://www.food4rhino.com/en/app/magnetizing-floor-plan-generator)) [doc] | GH | Free; licence unverified | It is what a Grasshopper-savvy agency will try first for free. Bubble-level; no walls or regulation. |
| **Maket** | Text prompt to dimensioned house plans with walls, doors and windows. DXF export with walls as linework, labels, door swings and basic dimensions ([maket.ai](https://www.maket.ai/pricing)) [mkt] | DXF, PDF | Free 50 credits; $20/month | Aimed at homeowners. Shows that DXF with door swings is now table stakes. |
| **Hypar** | Space planning and test fits from a programme spreadsheet, CAD, Revit or a scan. Firm-encoded generators. Furniture layouts ([AEC Magazine](https://aecmag.com/features/hypar-2-0/), [docs pricing](https://docs.hypar.io/plans-account-and-admin/plans-pricing-and-licenses)) [doc/3p] | Revit and others | $83–100 per user per month | Workplace-oriented. Its "firm encodes its own generators" model is the same idea as a regulation profile. |
| **Snaptrude** | Programme to stacked spaces to BIM, sized by IBC, ADA and Neufert ([snaptrude.com](https://www.snaptrude.com/pricing)) [mkt] | Revit, Rhino | Free; $60–100/month | Generic; US codes. |
| **Archistar** | Pivoted to **AI PreCheck**: permit-compliance checking for cities, rule-based, with an ICC partnership ([archistar.ai](https://www.archistar.ai/aiprecheck/)) [mkt] | n/a | B2G | Not a design tool. A signal that "regulation as code" sells to authorities; a possible future Rokhas-side checker. |
| **Skema** | Revit concept design that reuses firm layouts (stretch and squeeze) to LOD 350. Grasshopper integration since 2026 ([AEC Magazine](https://aecmag.com/news/skema-ai-conceptual-design-and-re-use-engine-for-revit-launches/)) [mkt] | Revit | [unverified] | Revit-only. The library-reuse idea is shared with Finch. |
| **Giraffe** | Massing plus live pro-forma for developers ([giraffe.build pricing](https://www.giraffe.build/pricing/)) [doc] | n/a | $1k–3k per user per year | Developer tool, not an architect's tool. |
| **Digital Blue Foam** | Massing, typology, facade and "unit layout" generative design ([DBF](https://www.digitalbluefoam.com/capabilities/ai-generative-design)) [mkt] | [unverified] | Custom | Unit layout depth unverified. |
| **Modelur** | SketchUp urban massing with parameters. No 2026 result found | [unverified] | [unverified] | Out of scope. |

---

## 4. Gap table

Rows are ordered by what a Moroccan agency working for promoteurs would refuse to give
up, not by feature count. "Would have to build" is PLANFGEN's cost. "Has that they do
not" is PLANFGEN's edge.

| # | Capability | Finch | TestFit | Forma | PLANFGEN today | PLANFGEN would have to build | PLANFGEN has that they do not |
|---|---|---|---|---|---|---|---|
| 1 | **Works on my real programme, every time, in seconds** | yes, real-time [mkt] | yes, instant [mkt] | seconds [mkt] | **No.** 46/72 on `probe_programmes` after the S27 prototype; 45–90 s on a failing brief; F2 fails | `search/construct.py` productionised (S27 next) | — |
| 2 | **Moroccan regulation as gates** (2-64-445, Casablanca, PA) | no (firm library only) | generic zoning profile, US-centric | no | **3 profiles, hard gates** | sourced accessibility and fire values (blocked here) | **Unique.** No competitor found. |
| 3 | **DXF a bureau de contrôle / AutoCAD user accepts** | Revit, Rhino; no DWG found | `.dxf` (massing and units) | Revit | DXF with walls, cotes, layers | agency layer standards, cartouche, tableau des surfaces, hatching | net-area-true walls in DXF; the others go through Revit |
| 4 | **Unit interior generation (rooms, walls, doors)** | library plus gated AI | **no** (kit of parts) | experimental, US | **yes**, F3/F4, walls authored, doors that swing free | F2, WC/dégagement reliability, proportion | **exact net areas (1e-9 m²), solid wall graph, adjacency in metres** |
| 5 | **Multi-unit floor plate** (core, palier, 2–4 units, mitoyens) | **yes**, strong | **yes**, strongest | yes | **no** | L: core plus units plus courettes composition | — |
| 6 | **Envelope from the plan d'aménagement** (CES, COS, hauteur, reculs H/2, courettes) | no | zoning profile plus massing | massing | **no** (footprint fit only) | M: PA rules into envelope and levels | could be the only tool with *Moroccan* PA rules |
| 7 | Rhino/Grasshopper as a first-class home | GH streaming | no | no | GH JSON export | GH component that runs the engine, not only reads its output | — |
| 8 | Steering: gallery, weights, lock-and-regenerate | weights, Archie, gallery | sliders, direct edit | text prompts | Streamlit form; being replaced | gallery plus weights plus lock | gates never traded in a score |
| 9 | Firm plan library / fit existing plans | **core feature** | kit of parts | no | `measure_reference.py` reads plans; no reuse | M: import agency DXF as seeds/templates | — |
| 10 | Yield / surface vendable / cost | metrics | **full pro-forma** | GFA per unit | area per room only | S: surfaces table plus unit-count plus DH price band | — |
| 11 | Non-rectangular and corner lots | yes | yes | yes | **no** (bbox) | L | — |
| 12 | Furniture fit | furnished units | no | no | **gate** | — | furniture as a gate, not decoration |
| 13 | IFC | via Revit | no | via Revit | **yes** | — | direct IFC without Revit |
| 14 | Environmental analysis (sun, wind, noise) | daylight | no | **strongest** | orientation score | — | — (do not build; see §6) |
| 15 | Parking, site plan | no | **strongest** | yes | no | — | — (do not build) |
| 16 | Price for a small Moroccan agency | €49–79/month, or €14.5k/year for AI | $15k/year | free with Revit | — | — | local, French, could be priced in DH |

---

## 5. Ranked roadmap: what would make this agency pay for it or use it daily

The agency's bread and butter is almost certainly the **R+2 to R+5 immeuble on a
mitoyen lot for a promoteur**: two to four flats per floor, a stair core, courettes,
and wet rooms stacked. It is sold against the 2024–2028 direct-aid price caps of 300k
and 700k DH TTC ([MHPV](https://www.mhpv.gov.ma/fr/programme-daide-directe-au-logement/),
[Le Desk](https://ledesk.ma/encontinu/aide-directe-au-logement-le-coup-denvoi-fixe-au-1er-janvier-2024/)) [doc/3p].
The permit goes through Rokhas, which has been the sole channel since 2026
([bati.ma](https://bati.ma/guide/permis-rokhas-etapes-maroc)) [3p]. That typology is
an inference from the brief (Casablanca arrêté, wall-to-wall between party walls), not
something I measured. planfgen-product should confirm it with the user before item 3
is scheduled.

Effort is in sessions: S is 1–2, M is 3–5, L is 6 or more.

| Rank | Capability | Why it matters to a Moroccan agency | Effort | Depends on | Displaces | Owner |
|---|---|---|---|---|---|---|
| **1** | **Reliable generation on real programmes.** F2 to F4 plus separate WC plus dégagement; at least 1 valid plan per real brief; under 10 s | Nothing else counts if their own F3 returns "0 plans". This is the interaction that makes the tool feel alive or dead. Every competitor is instant. | M | S27 `Finder` into `search/construct.py`; envelope follows the tree | studio work (paused anyway) | **planfgen-engine**, with -optima |
| **2** | **Plan d'aménagement to envelope, plus tableau des surfaces.** CES, COS, hauteur/R+n, reculs (e.g. H/2 min 4 m), courette minima, surface hors œuvre / utile / vendable per flat and per level | Every Moroccan project starts with the note de renseignements urbanistiques. The tableau des surfaces is on every permit set. No competitor does Moroccan PA rules, so this is the moat at the scale the promoteur pays for. | M | sourced PA values (many AU PDFs are indexed but fetches are blocked here; the user must supply them) | non-rectangular parcels (item 8) | **planfgen-regs** (values), -engine (envelope) |
| **3** | **Mitoyen floor plate.** Stair core plus palier plus 2–4 flats wall to wall between party walls, courettes for wet rooms and kitchens, wet rooms stacked across levels (L4 already stacks) | This is the deliverable an immeuble agency actually draws. It is where Finch and TestFit live, but **they need units pre-drawn**, and PLANFGEN can generate them. That is the unique combination. | L | 1, 2; L4 stacks; courette regulation | IFC/GH polish; single-unit refinements | **planfgen-engine** plus -optima (a level as a slicing tree of units: the same representation one scale up), -regs (courettes) |
| **4** | **AutoCAD deliverable to agency standards.** Their layer names, cartouche, hatching, cotations, the tableau des surfaces on the sheet; and **parcel and levé import from DXF** | They live in AutoCAD, and the drawing goes to the bureau de contrôle and Rokhas. A DXF that needs 30 minutes of cleanup is not used. Competitors route through Revit; this agency does not. | M | a sample of the agency's own DWG template (ask the user) | — | **planfgen-product** (spec), -engine (`document/`) |
| **5** | **Grasshopper component as the daily interface.** Run the engine from GH; parcel from Rhino geometry; variants out as Rhino layers | Replaces Streamlit where the agency already works. PlanFinder and Magnetizing already live in GH, so this is where the comparison will be made. | M | 1 | Streamlit maintenance (dropped) | **planfgen-product** |
| **6** | **Gallery plus weights plus lock-and-regenerate.** N distinct valid plans with metrics; sliders for the soft scores; lock a room or wall and regenerate the rest | This is Finch's core loop and the thing architects cite. Gates stay gates, so only scores get sliders. | M | 1, 5 | — | **planfgen-product**, -optima (diversity and archive) |
| **7** | **Agency plan library as seeds.** Import their past F3/F4 DXFs (`measure_reference.py` already recovers rooms from walls) as slicing-tree templates and calibration | Finch's most-sold feature is "your plans, adapted". For a Moroccan agency it is also the fastest route to plans that *look like theirs*, and it answers the S26 proportion problem with measurements. | M | the 15–20 measured fixtures already planned in `PROMPTS-NEXT` | — | **planfgen-optima** (tree extraction), -critique (does it look like theirs) |
| **8** | **Non-rectangular and corner lots** (two frontages, splayed corner) | Common in the Casablanca fabric. Every competitor handles them. | L | 2 | — | **planfgen-engine** |
| **9** | **Yield strip.** Flats per level, m² vendable, DH price band against the 300k and 700k caps | Cheap, and it is the first number the promoteur asks for. Not a pro-forma: TestFit and Giraffe own that, and it is not the agency's job. | S | 2, 3 | — | **planfgen-product** |
| **10** | **Regulation breadth.** Accessibility (décret 2-11-246 and the MHPV/AUT guides), fire safety for R+4 and above, more city arrêtés (Rabat, Tanger, Marrakech) | Each profile widens the moat and the market. Accessibility and fire are what the bureau de contrôle actually checks. | M each | sources (blocked here; the user must supply them) | — | **planfgen-regs**, with -qa for gate tests |

**planfgen-qa**, across the board: every roadmap item needs a "real programme" probe
(the pattern of `probe_programmes.py`) as its acceptance test, not a synthetic fixture.

### Deliberately not on the roadmap

- **Sun, wind and noise analysis.** Forma does it best and is free to Revit
  subscribers. The existing orientation score is enough.
- **Parking and site plans.** TestFit owns this, and it is irrelevant to mitoyen lots.
- **Pro-forma finance.** Giraffe and TestFit own this; it is the promoteur's job, not
  the agency's.
- **ML training.** See §1b. The conclusion stands; fix the stated reason.
- **Revit export.** The agency is on AutoCAD and Rhino, and IFC already covers the
  exchange case.

---

## 6. Literature pointers for the engine (short; for planfgen-optima)

| Pointer | Relevance | Implementable? |
|---|---|---|
| Wong & Liu, *A New Algorithm for Floorplan Design*, DAC 1986, pp. 101–107 ([Semantic Scholar](https://www.semanticscholar.org/paper/A-New-Algorithm-for-Floorplan-Design-Wong-Liu/4cdaaeef14fa8baea385927b332e01f7aedf4c46)) | Normalised Polish expressions with three move types (M1–M3) are the standard move set for annealing over slicing trees. The S27 finding, that valid plans are isolated (3 of 34 505 two-move neighbours pass), is the classic symptom of a **gate-filtered** space being disconnected even when the move set is ergodic over the unfiltered one. The field's answer is the one S25 took (penalty/violation guidance), plus constructive seeding (S27). Nothing new is needed; this confirms the direction. | Public algorithm |
| Young & Wong, *Slicing Floorplans with Boundary Constraints*, TCAD 1999 ([PDF, CUHK](http://www.cse.cuhk.edu.hk/~fyyoung/paper/tcad99_9.pdf)) | Rooms that **must touch a given side** (street facade, courette), handled inside the Polish expression. This maps directly onto "day row on the street" and wet rooms on a courette, as a representation-level constraint rather than a post-check. | Public algorithm |
| GPLAN, Shekhawat et al. ([arXiv 2008.01803](https://arxiv.org/abs/2008.01803); Automation in Construction 2021) and **DPLAN** ([arXiv 2606.21159](https://arxiv.org/abs/2606.21159), 2026-06, Python) | Rectangular duals: adjacency graph to *dimensioned* rectangular floor plan, with no overlaps and no gaps by construction. DPLAN starts from door connectivity. This is a candidate **constructive seeder** for the S27 problem (nesting and dégagements). | Licence and code availability unverified (GitHub was not searchable from here). **Check before use.** |
| Magnetizing FPG ([GitHub](https://github.com/hellguz/Magnetizing_FloorPlanGenerator)) | A corridor-attached greedy placement heuristic. It is weaker than PLANFGEN's, but it is the free baseline that GH users will compare against. | Open source; licence unverified |
| SSPT space-syntax oracle ([arXiv 2602.22507](https://arxiv.org/abs/2602.22507)) | Integration of public space over a door-mediated rectangle graph, used as a *score*. It is cheap on PLANFGEN's L5 graph and could become a soft score for "the séjour dominates". | Formula is public |

---

## 7. Summary in the house format

```
QUESTION   What do Finch, TestFit, Forma and peers do for residential, and what should a
           Moroccan AutoCAD/Rhino agency's PLANFGEN build first?
SOURCES    About 60 URLs, listed inline, all accessed 2026-09-29. Every vendor, arXiv and
           Moroccan-government page was blocked by egress policy; all claims are from
           search summaries, labelled [doc]/[mkt]/[3p]/[unverified].
FINDING    (1) No tool found encoding Moroccan regulation; ARCHITEChTURES (Spain,
           regulation plus finance, generative residential) is the one to watch; Hektar
           and Mesetys prove the "local regulation" positioning.
           (2) PROMPTS-NEXT's "Finch uses no ML" is out of date: Finch (gated), Forma
           (experimental, US) and PlanFinder (diffusion, in Rhino) ship ML unit plans.
           No published result meets the metric/wall/code bar, so the conclusion
           stands and the reason must change.
           (3) TestFit packs user-drawn units; it is a complement until PLANFGEN builds
           floor plates.
THREAT     Near-term: PlanFinder and Forma Building Design (free with Revit) as "good
           enough" unit generators. Mid-term: a Spanish or French regulation-first tool
           adding Morocco.
COST       Top 3 = M + M + L; roughly 12–16 sessions. Displaces Streamlit work and
           single-unit polish.
ROUTED     engine (1, 3, 8), regs (2, 10), product (4, 5, 6, 9, PROMPTS-NEXT fix),
           optima (6, 7, §6), critique (7), qa (acceptance probes).
```
