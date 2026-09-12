# PLANFGEN v2 — Space Planning Engine

Generates **architectural floor plans** (not bubble diagrams) from a programme,
a parcel and a regulation profile. Python 3.12 · Shapely · NetworkX · Streamlit.

## The one rule that governs everything

**Walls are authored. Spaces are derived.**

A `Space` is a *face of the wall graph*, never something placed directly.
v1 of this project authored room polygons and reconstructed walls afterwards —
that is why it produced an organigramme. If a change makes rooms primary again,
it is wrong.

Consequences that follow from this rule and must always hold:

- Every room is an **axis-aligned rectangle**. No diagonals. No Voronoi. Ever.
- **Net area ≠ axis area.** A room loses half the thickness of each wall bounding
  it. `surface_utile` is always the net polygon. Code minima apply to net.
- **Adjacency is measured in metres of shared wall**, never in tolerance of contact.
  Two rooms are connectable only if the shared run can host a door.
- **Circulation gets a width, never an area.** Corridor area is an output.
- Openings are intervals hosted on a wall, and only legal where the parcel edge allows.

## Layer stack — data flows down, one contract per step

| Layer | Package | Produces | Guarantees |
|---|---|---|---|
| L0 | `brief/` | `Brief` | programme fits the parcel; edges typed; north known |
| L1 | `topology/` | `TopologyPlan` | typed relations; access gradient; zoning |
| L2 | `partition/` | `PartitionPlan` | exact net areas; orthogonal; corridor band reserved |
| L3 | `fabric/` | `FabricPlan` | wall graph solid; net areas real; adjacency in metres |
| L4 | `services/` | `ServicedPlan` | wet rooms on shafts; stack ids assigned |
| L5 | `circulation/` | `CirculatedPlan` | every space reachable from the entry |
| L6 | `openings/` | `OpenedPlan` | doors swing free; windows only on legal edges |
| L7 | `habitability/` | `HabitablePlan` | furniture fits; no swing collisions |
| L8 | `document/` | `Drawing` | dimensioned, layered; DXF · IFC · Grasshopper |

Beside the stack: `evaluate/` (constraints + metrics + report), `search/` (annealing).

## Conventions

- All lengths in **metres**, all areas in **m²**. Angles in radians, 0 = north = +Y.
- French for domain terms: `nom`, `surface_utile`, `couleur`, `cloison`, `porteur`,
  `allège`, `adjacences`, `compacite`. English for code structure.
- Seeds are ints; the same seed always produces the same plan.
- Regulation values live **only** in `brief/regulation.py`, never as literals in logic.
- Outputs go to `./outputs/`. Type hints on every public function.

## Hard constraints vs soft scores

Area, coverage, orthogonality, reachability and furniture fit are **gates** —
a candidate either passes or is discarded. They are never traded off in a score.
Only judgement calls are scored: weighted adjacency, orientation, circulation
coefficient, envelope compactness, daylight.

## Commands

```bash
python -m pytest planfgen/tests/ -q          # all tests
python -m pytest planfgen/tests/test_X.py -q # one module (prefer this)
python -m planfgen.main --brief <json>       # CLI  (note: -m, not a file path)
streamlit run planfgen/studio/app.py --server.headless true
```

## Working agreement — read this before doing anything

1. **Do exactly the step you were given. Stop at its end.** Do not start the next
   layer, do not refactor neighbouring code, do not "improve while you're here".
2. **Read only the files the prompt names.** Do not scan the repo. Do not open
   `legacy/` — it is the v1 engine, kept only for A/B comparison and it is wrong
   by design.
3. Write the tests in the same session as the code. A layer is not done until its
   own test file passes.
4. Prefer plain float arithmetic on axis-aligned rectangles. Shapely is for
   face extraction, parcel import and export only — never in an inner loop.
   Never call `.buffer()` inside a loop.
5. **Last action of every session:** append a short entry to `PROGRESS.md`
   (what you built, what the tests prove, anything the next session must know)
   and `git commit`. Keep it under 10 lines.

Full architecture and reasoning: `ARCHITECTURE.md`. Session log: `PROGRESS.md`.
