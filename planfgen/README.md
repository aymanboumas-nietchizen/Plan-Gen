# PLANFGEN — Space Planning Engine

A **local, open-source architectural space planning engine** that automatically generates and scores floor plan layouts from a building programme and adjacency rules.

> Runs 100% locally — no cloud, no SaaS, no subscription.  
> Embeds Moroccan building codes (DTU) from day one.  
> Designed for Grasshopper / Rhino / Revit workflows.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run from the CLI

```bash
python main.py --programme tests/fixtures/apartment_7rooms.json --W 12 --H 9 --N 200
```

### 3. Run the Streamlit Studio *(Sprint 3)*

```bash
streamlit run studio/app.py
```

### 4. Run tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
planfgen/
├── core/          # Generator, scorer, optimizer — the engine
├── rules/         # Base rules + Moroccan DTU rules
├── export/        # DXF and JSON export
├── studio/        # Streamlit UI (Sprint 3)
├── grasshopper/   # GhPython drop-in component (Sprint 5)
├── tests/         # pytest unit tests + fixtures
├── examples/      # Standalone runnable examples
├── outputs/       # All exported files land here (auto-created)
└── main.py        # CLI entry point
```

---

## Algorithm Summary

| Step | What happens |
|---|---|
| `generate_layout(seed)` | BFS graph-guided placement of rooms around the hub room |
| `validate_layout(rules)` | Hard rules discard invalid layouts; soft rules flag warnings |
| `score_layout()` | 4 metrics → weighted global score [0, 1] |
| `run_optimization(N)` | Generates N seeds, returns top-K by score |

### Scoring weights (configurable)

| Metric | Default weight | Meaning |
|---|---|---|
| `adjacences` | 40% | % of desired adjacency rules respected |
| `compacite` | 25% | Room squareness (ratio ≤ 2.5 ideal) |
| `facade` | 20% | % of rooms needing exterior wall that get it |
| `couverture` | 15% | % of envelope area covered |

---

## Grasshopper Integration

1. Open Rhino + Grasshopper
2. Add a **GhPython** component
3. Open `grasshopper/planfgen_component.py` and copy-paste into the component
4. Set `PLANFGEN_PARENT` at the top to the folder containing `planfgen/`
5. Connect inputs: `boundary` (Curve), `programme` (JSON Panel), `adjacencies` (JSON Panel), `run` (Boolean Toggle)
6. Surfaces appear in the Rhino viewport immediately

---

## Moroccan DTU Rules (Sprint 2)

| Rule | Threshold | Hard? |
|---|---|---|
| Chambre principale min area | 12 m² | ✓ |
| Chambre min area | 9 m² | ✓ |
| Cuisine min area | 6 m² | ✓ |
| SDB min area | 3.5 m² | ✓ |
| WC min area | 1.2 m² | ✓ |
| Corridor min width | 1.20 m | ✓ |
| Max room ratio | 2.5 | ✗ (soft) |
| Façade for séjour/chambres | True | ✗ (soft) |

---

## Export Formats

| Format | Description |
|---|---|
| `.dxf` | AutoCAD 2010+ — rooms as LWPOLYLINE on named layers |
| `.json` | Grasshopper-ready — rooms + metadata + scores |
| `.ifc` | *(v2 roadmap)* — IfcSpace per room via ifcopenshell |

---

## Conventions

- All coordinates and dimensions: **metres**
- Seeds: integers 0..N-1 — same seed → same layout (deterministic)
- Scores: floats in [0.0, 1.0]
- All output files → `./outputs/` (auto-created)

---

*PLANFGEN — Start small. Ship early. Iterate with real projects.*
