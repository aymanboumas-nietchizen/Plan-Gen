# PLANFGEN — Revit (pyRevit extension)

The deliverable of PLANFGEN is a Revit model built from the agency's own
families (`ARCHITECTURE.md` §0, "The output target"). This folder is the
Revit side of that link. Target: Revit 2025 + pyRevit.

## Install (once, on the agency PC)

1. Install pyRevit: https://github.com/pyrevitlabs/pyRevit/releases
2. In a terminal: `pyrevit extend ui PLANFGEN "<path to this repo>\revit"`
   — or copy `PLANFGEN.extension` into `%APPDATA%\pyRevit\Extensions\`.
3. Restart Revit. A **PLANFGEN** tab appears.

## Step 1 — export the family list (what PLANFGEN needs now)

1. Open the agency template (`.rte`) in Revit 2025.
2. PLANFGEN › Familles › **Exporter familles**.
3. A file `<template>_familles_planfgen.json` is written next to the template
   (or on the Desktop). It holds only names and dimensions: category, family,
   type, and widths/heights/thicknesses.
4. Put that JSON in `revit/mapping/` and commit it (or send it). From it the
   mapping table `family key → Revit family + type` is built.

The `.rte`, `.rvt` and `.rfa` files themselves never go into git — they are the
agency's work (see `.gitignore`).

## Coming next

- `Construire` — read a PLANFGEN building model (JSON) and place walls, doors,
  windows, rooms, furniture and placards with the agency's families.
- `Envoyer le squelette` — export a footprint, stair core and landing drawn in
  Revit to PLANFGEN, to get a gallery of floor plates back.
