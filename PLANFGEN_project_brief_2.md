# PLANFGEN — Space Planning Engine
## Project Brief for Development

> **Author:** Architect & Developer  
> **Date:** March 2026  
> **Status:** Pre-development — ready to build  
> **Stack:** Python · Shapely · NetworkX · Streamlit · GhPython

---

## 1. What We Are Building

PLANFGEN is a **local, open-source architectural space planning engine** that automatically generates and scores floor plan layouts from a building program and adjacency rules.

It is architecturally inspired by Finch3D but fundamentally different:
- Runs **100% locally** — no cloud, no SaaS, no subscription
- Uses **soft constraints** (weighted scores) instead of hard elimination rules — more transparent and controllable
- Embeds **Moroccan building codes** (DTU) from day one — no existing tool does this
- Designed to integrate natively with **Grasshopper / Rhino / Revit** workflows
- Every algorithmic decision is **explainable** — the architect understands why a layout scores well

The target user is a practicing architect in a small-to-medium firm who wants early-stage layout exploration without leaving their existing CAD environment.

---

## 2. Algorithmic Foundation

The engine is built on three algorithms studied and partially implemented before this project starts:

### 2.1 Slicing (Mirahmadi & Shami, 2012)
- **Paradigm:** Top-down recursive space partitioning
- **How it works:** Takes the envelope, cuts it into sub-rectangles alternating H/V directions, assigns rooms proportionally to their target area
- **Role in PLANFGEN:** Used in Sprint 1 as the base generator before graph-guided placement is complete
- **Key property:** Always produces valid geometry (no overlaps, no voids), but blind to spatial relationships

### 2.2 Graph-Guided BFS Placement (our implementation, inspired by Graph2Plan)
- **Paradigm:** Bottom-up placement guided by adjacency graph
- **How it works:** Builds a NetworkX graph where nodes = rooms and edges = desired adjacencies. Traverses via BFS from the most-connected hub. Places each room by testing 8 directional candidates around its already-placed neighbors
- **Role in PLANFGEN:** Core generator from Sprint 1 onward
- **Key property:** Respects spatial relationships without requiring ML training data

### 2.3 Stochastic Optimization (our implementation)
- **Paradigm:** Generate N variants (different seeds), evaluate each, rank by weighted score
- **How it works:** Each seed produces a different layout via varied BFS start order, room ratios, and placement direction priorities. All N layouts are scored and the TOP K are returned
- **Role in PLANFGEN:** Optimization layer wrapping the BFS generator
- **Future upgrade path:** Replace with NSGA-II via DEAP for true multi-objective Pareto front (v2)

---

## 3. Scoring System

Every generated layout is evaluated on 4 metrics, combined into a weighted global score:

```
Score_global = 0.40 × adjacences
             + 0.25 × compacite
             + 0.20 × facade
             + 0.15 × couverture
```

| Metric | Description | Ideal |
|---|---|---|
| `adjacences` | % of desired adjacency rules respected (rooms that should touch, do touch) | 1.0 |
| `compacite` | Average room shape ratio — penalizes rooms with w/h > 2.5 (long corridors, narrow strips) | 1.0 |
| `facade` | % of rooms flagged `facade=True` that actually touch an exterior wall | 1.0 |
| `couverture` | % of the envelope area covered by rooms — penalizes wasted space | 1.0 |

Two rooms are considered adjacent if their bounding boxes overlap within a tolerance of 0.15m.

---

## 4. Data Structures

### 4.1 Programme (input)
```python
programme = [
    {"nom": "Séjour",    "surface": 30, "couleur": "#4a9eff", "facade": True},
    {"nom": "Cuisine",   "surface": 18, "couleur": "#3ecf8e", "facade": True},
    {"nom": "Chambre 1", "surface": 20, "couleur": "#f0a500", "facade": True},
    {"nom": "Chambre 2", "surface": 15, "couleur": "#f1948a", "facade": True},
    {"nom": "SDB",       "surface":  8, "couleur": "#c084fc", "facade": False},
    {"nom": "WC",        "surface":  5, "couleur": "#fb923c", "facade": False},
    {"nom": "Couloir",   "surface":  7, "couleur": "#94a3b8", "facade": False},
]
```

### 4.2 Adjacency Rules (input)
```python
adjacencies = [
    ("Séjour",    "Cuisine"),
    ("Séjour",    "Couloir"),
    ("Cuisine",   "Couloir"),
    ("Couloir",   "Chambre 1"),
    ("Couloir",   "Chambre 2"),
    ("Couloir",   "SDB"),
    ("Couloir",   "WC"),
    ("SDB",       "WC"),
    ("Chambre 1", "SDB"),
]
```

### 4.3 Placed Layout (output of generator)
```python
placed = {
    "Séjour":    {"x": 0.0,  "y": 4.0, "w": 6.2, "h": 4.8},  # in meters
    "Cuisine":   {"x": 6.2,  "y": 6.1, "w": 5.8, "h": 2.9},
    "Chambre 1": {"x": 0.0,  "y": 0.0, "w": 5.9, "h": 3.9},
    # ... etc
}
```

### 4.4 Scores (output of scorer)
```python
scores = {
    "adjacences": 0.89,
    "compacite":  0.91,
    "facade":     0.75,
    "couverture": 0.94,
    "global":     0.88,
    "adj_details": [
        {"a": "Séjour", "b": "Cuisine",  "ok": True},
        {"a": "Séjour", "b": "Couloir",  "ok": True},
        {"a": "SDB",    "b": "WC",       "ok": False},
        # ...
    ]
}
```

---

## 5. Project Structure

```
planfgen/
├── core/
│   ├── __init__.py
│   ├── geometry.py          # Rect class, adjacency checks, envelope validation
│   ├── generator.py         # generate_layout(programme, adjacencies, W, H, seed) → placed
│   ├── scorer.py            # score_layout(placed, adjacencies, W, H, facade_rooms) → scores
│   └── optimizer.py         # run_optimization(N, ...) → list[Result] sorted by score
│
├── rules/
│   ├── __init__.py
│   ├── base_rules.py        # Generic rules: min area, max ratio, corridor width
│   └── ma_rules.py          # Moroccan DTU rules: room-specific dimensions, PMR
│
├── export/
│   ├── __init__.py
│   ├── dxf.py               # export_dxf(placed, filename) via ezdxf
│   ├── ifc.py               # export_ifc(placed, filename) via ifcopenshell
│   └── json_export.py       # export_json(placed, scores) for Grasshopper
│
├── studio/
│   ├── app.py               # Streamlit local studio
│   └── components.py        # Reusable UI components
│
├── grasshopper/
│   └── planfgen_component.py  # GhPython component code
│
├── tests/
│   ├── test_geometry.py
│   ├── test_generator.py
│   ├── test_scorer.py
│   └── fixtures/
│       ├── apartment_7rooms.json
│       └── school_programme.json
│
├── examples/
│   ├── basic_apartment.py
│   ├── school_layout.py
│   └── office_layout.py
│
├── requirements.txt
├── README.md
└── main.py                  # CLI entry point
```

---

## 6. Module Specifications

### 6.1 `geometry.py`

```python
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    nom: str
    color: str = "#ffffff"

    @property
    def area(self) -> float: ...

    @property
    def cx(self) -> float: ...  # centroid x

    @property
    def cy(self) -> float: ...  # centroid y

    @property
    def ratio(self) -> float: ...  # max(w,h) / min(w,h)

    def intersects(self, other: "Rect", tol: float = 0.05) -> bool: ...
    def touches(self, other: "Rect", tol: float = 0.15) -> bool: ...
    def in_envelope(self, W: float, H: float) -> bool: ...
    def on_facade(self, W: float, H: float, tol: float = 0.15) -> bool: ...
    def to_dict(self) -> dict: ...

def build_graph(rooms: list, adjacencies: list) -> dict:
    """Returns adjacency map: {room_nom: [neighbor_noms]}"""
    ...

def bfs_order(graph: dict, start: str, all_rooms: list) -> list:
    """BFS traversal from start, appends unvisited rooms at end"""
    ...
```

### 6.2 `generator.py`

```python
def generate_layout(
    programme: list,      # list of room dicts
    adjacencies: list,    # list of (str, str) tuples
    W: float,             # envelope width in meters
    H: float,             # envelope height in meters
    seed: int = 0,        # random seed for reproducibility
) -> dict:                # {room_nom: Rect}
    """
    Generates a floor plan layout using graph-guided BFS placement.

    Algorithm:
    1. Build adjacency graph from adjacencies list
    2. Find hub room (most connections)
    3. BFS traversal order from hub
    4. For each room in order:
       a. Find already-placed neighbors
       b. Generate 8 directional candidate positions around first placed neighbor
       c. Filter: must be inside envelope AND not intersect any placed room
       d. Pick first valid candidate (shuffled by seed)
       e. If none valid: fallback grid scan (0.3m step)
    5. Return placed dict
    """
    ...
```

### 6.3 `scorer.py`

```python
def score_layout(
    placed: dict,          # {room_nom: Rect}
    adjacencies: list,     # list of (str, str) tuples
    W: float,
    H: float,
    facade_rooms: list,    # list of room_nom that need facade access
    weights: dict = None,  # override default weights
) -> dict:
    """
    Evaluates a layout on 4 metrics.

    Default weights: {adjacences: 0.40, compacite: 0.25, facade: 0.20, couverture: 0.15}
    Returns: {adjacences, compacite, facade, couverture, global, adj_details}
    """
    ...
```

### 6.4 `optimizer.py`

```python
def run_optimization(
    programme: list,
    adjacencies: list,
    W: float,
    H: float,
    N: int = 200,
    top_k: int = 6,
    weights: dict = None,
    on_progress=None,      # callback(current, total, best_so_far)
) -> list:
    """
    Generates N layout variants (seeds 0..N-1), scores each,
    returns top_k sorted by global score descending.

    Each result in list:
    {
        "seed": int,
        "placed": dict,
        "scores": dict,
    }
    """
    ...
```

### 6.5 `rules/base_rules.py`

```python
from dataclasses import dataclass

@dataclass
class RuleResult:
    ok: bool
    rule_name: str
    room: str
    message: str
    severity: str  # "error" | "warning"

class Rule:
    name: str
    hard: bool  # True = eliminate layout, False = penalize score

    def check(self, placed: dict) -> RuleResult: ...

# Concrete rules to implement:
class MinAreaRule(Rule):
    """room.area >= min_area"""
    def __init__(self, room_type: str, min_area: float, hard=True): ...

class MaxRatioRule(Rule):
    """room.ratio <= max_ratio"""
    def __init__(self, max_ratio: float = 2.5, hard=False): ...

class MinCorridorWidthRule(Rule):
    """corridor min(w,h) >= 1.20m"""
    def __init__(self, hard=True): ...

def validate_layout(placed: dict, rules: list) -> dict:
    """
    Runs all rules against a layout.
    Returns {valid: bool, errors: list, warnings: list, score_penalty: float}
    """
    ...
```

### 6.6 `rules/ma_rules.py`

```python
# Moroccan DTU Building Code Rules

MA_RULES = [
    MinAreaRule("chambre principale", min_area=12.0, hard=True),
    MinAreaRule("chambre",            min_area=9.0,  hard=True),
    MinAreaRule("cuisine",            min_area=6.0,  hard=True),
    MinAreaRule("sdb",                min_area=3.5,  hard=True),
    MinCorridorWidthRule(hard=True),
    MaxRatioRule(max_ratio=2.5, hard=False),
    FacadeRule(room_types=["séjour", "chambre"], hard=False),
    # Add more as needed
]
```

---

## 7. Rules Engine Integration

The rules engine runs **after** the layout generator and **before** scoring:

```
generate_layout()
        ↓
validate_layout()   ← hard rules: invalid layouts are DISCARDED here
        ↓
score_layout()      ← soft rule penalties applied to scores
        ↓
rank & return TOP K
```

This separation is intentional:
- Hard rules protect regulatory compliance (non-negotiable)
- Soft rules guide quality (negotiable, architect can override weights)
- Generator stays simple — it doesn't know about rules

---

## 8. Export Formats

### 8.1 DXF Export
```python
# Each room → closed LWPOLYLINE on its own layer
# Layer name = room name
# Centered TEXT with room name + area
# Compatible with AutoCAD 2010+
```

### 8.2 JSON Export (Grasshopper)
```json
{
  "metadata": {
    "seed": 42,
    "score_global": 0.87,
    "envelope": {"W": 12.0, "H": 9.0},
    "generated_at": "2026-03-01T10:00:00"
  },
  "rooms": [
    {
      "nom": "Séjour",
      "x": 0.0, "y": 4.0,
      "w": 6.2, "h": 4.8,
      "area": 29.76,
      "color": "#4a9eff",
      "on_facade": true
    }
  ],
  "scores": {
    "adjacences": 0.89,
    "compacite": 0.91,
    "facade": 0.75,
    "couverture": 0.94,
    "global": 0.88
  }
}
```

### 8.3 IFC Export (v2, not Sprint 1)
- Each room → `IfcSpace` with correct area and name
- Envelope → `IfcBuildingStorey`
- Compatible with Revit import

---

## 9. Streamlit Studio (`studio/app.py`)

### Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  PLANFGEN Studio                                    v0.1 local  │
├───────────────┬──────────────────────────────┬──────────────────┤
│  PROGRAMME    │      GENERATED LAYOUTS        │  SELECTED DETAIL │
│               │                              │                  │
│  + Add Room   │  [Card 🥇 88%] [Card 🥈 82%] │  Score breakdown │
│  Room list    │  [Card 🥉 79%] [Card #4 71%] │  Adj rules OK/KO │
│  Adj rules    │                              │  Room surfaces   │
│  W × H sliders│                              │  Export DXF btn  │
│  N variants   │  Click a card to inspect     │                  │
│               │  → adjacency lines appear    │                  │
│  [GENERATE]   │                              │                  │
└───────────────┴──────────────────────────────┴──────────────────┘
```

### Key interactions
- Adding a room: name + area (m²) + color picker + facade checkbox
- Adding adjacency rule: select Room A → select Room B → Add
- Generate button: runs `run_optimization()` with progress bar
- Card click: shows adjacency lines (green = respected, red = missing)
- Export button: calls `export_dxf()` → saves to `./outputs/`

---

## 10. Grasshopper Component

File: `grasshopper/planfgen_component.py`  
Usage: Copy-paste into a GhPython component in Grasshopper

```python
"""
PLANFGEN — GhPython Component

Inputs:
    boundary    : Curve  — closed curve defining the envelope
    programme   : str    — JSON string of room programme
    adjacencies : str    — JSON string of adjacency rules
    n_variants  : int    — number of variants to generate (default: 100)
    run         : bool   — toggle to trigger generation

Outputs:
    surfaces    : list[Surface] — one surface per room (best layout)
    scores      : str           — JSON score breakdown
    report      : str           — human-readable summary
"""

import sys, json
sys.path.append(r'C:\Users\[USERNAME]\planfgen')  # adjust path

if run:
    from planfgen.core.optimizer import run_optimization

    # Parse inputs
    prog  = json.loads(programme)
    adjs  = json.loads(adjacencies)

    # Get envelope dimensions from Rhino curve
    bbox = boundary.GetBoundingBox(True)
    W = bbox.Max.X - bbox.Min.X
    H = bbox.Max.Y - bbox.Min.Y
    ox = bbox.Min.X
    oy = bbox.Min.Y

    # Run
    results = run_optimization(prog, adjs, W, H, N=n_variants)
    best = results[0]

    # Build Rhino surfaces
    import Rhino.Geometry as rg
    surfaces = []
    for rect in best["placed"].values():
        pt = rg.Point3d(ox + rect["x"], oy + rect["y"], 0)
        plane = rg.Plane(pt, rg.Vector3d.ZAxis)
        srf = rg.PlaneSurface(plane, rg.Interval(0, rect["w"]), rg.Interval(0, rect["h"]))
        surfaces.append(srf)

    scores  = json.dumps(best["scores"], indent=2)
    report  = f"Best layout: {best['scores']['global']:.0%} (seed {best['seed']})"
```

---

## 11. Testing Strategy

### Unit tests (run with `pytest`)

| Test file | What it tests |
|---|---|
| `test_geometry.py` | Rect intersects/touches/on_facade, BFS order, graph building |
| `test_generator.py` | layout always fits envelope, no overlaps, seed reproducibility |
| `test_scorer.py` | score values in [0,1], weights sum to 1, adj_details length matches |
| `test_rules.py` | hard rule elimination, soft rule penalties, MA rules |
| `test_export.py` | DXF file opens without error, JSON valid, all rooms present |

### Integration test fixtures

**`fixtures/apartment_7rooms.json`** — standard 2-bed apartment, 108m², 12×9m envelope  
**`fixtures/school_programme.json`** — classroom block, 10 rooms, 24×18m envelope

### Acceptance criteria per sprint

```
Sprint 1: generate 200 variants of 7-room apartment in < 5 seconds
Sprint 2: 0 layouts violating MA hard rules in TOP 10
Sprint 3: non-developer colleague can use studio without instructions
Sprint 4: exported DXF opens in AutoCAD with correct layers and dimensions
Sprint 5: Rhino envelope curve → Grasshopper surfaces in < 10 seconds
```

---

## 12. Dependencies

```txt
# requirements.txt
shapely>=2.0.0
networkx>=3.0
matplotlib>=3.7.0
streamlit>=1.30.0
plotly>=5.18.0
ezdxf>=1.1.0
ifcopenshell>=0.7.0   # optional, for IFC export
pytest>=7.4.0
```

All dependencies are free and open source. No API keys required. No internet connection required after install.

---

## 13. Conventions

- All coordinates are in **meters**
- Room names are stored as lowercase internally but displayed as-is
- Seeds are integers 0..N-1 — same seed always produces same layout
- Scores are floats in [0.0, 1.0]
- Colors are hex strings `#rrggbb`
- All file outputs go to `./outputs/` directory (auto-created)
- Log level: `INFO` by default, `DEBUG` with `--verbose` flag

---

## 14. What This Is Not (Explicit Non-Goals for v1)

- Not a machine learning system — no training data, no neural networks
- Not a cloud service — runs entirely on the developer's machine
- Not a generative AI tool — every decision is deterministic and explainable
- Not a final design tool — outputs are early-stage layout explorations
- Not a structural engineering tool — no loads, no beams, no columns
- Not a full BIM authoring tool — DXF/IFC export is geometry only, no properties

---

## 15. Context Notes for the Developer

The person giving you this brief is an architect (licensed, Morocco) currently working at a design firm. They have:
- Strong expertise in Revit, Grasshopper, Rhino, parametric design
- Intermediate Python skills (working knowledge of Shapely, NetworkX, Matplotlib)
- Deep knowledge of Moroccan building codes and architectural programme types
- The algorithm concepts (Etapes 1-4) have already been prototyped in Python and in JavaScript

The priority is **clarity and controllability over performance**. Every function should be readable. Comments should explain the architectural reasoning, not just the code. When in doubt, choose the simpler implementation.

Start with Sprint 1 (`core/` modules only). Do not build the studio or export modules until the core engine is tested and validated.

---

*PLANFGEN — Start small. Ship early. Iterate with real projects.*
