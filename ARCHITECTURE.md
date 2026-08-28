# PLANFGEN v2 — Architecture

Read on demand. `CLAUDE.md` carries the rules you need every session; this file
carries the reasoning and the specifications behind them.

---

## 1. Why v1 produced a diagram

v1 placed rectangles by graph-guided BFS, then `_voronoi_fill()` discarded them and
re-partitioned the envelope from room **centroids** alone. Only the centre points
survived. Measured on `apartment_7rooms.json`, 12 × 9 m envelope:

| Symptom | Measurement |
|---|---|
| Area fidelity | mean absolute error **47%**, worst room **305%** |
| `couverture` metric | exactly 1.0 on all 40 seeds — one distinct value |
| `compacite` metric | spans 0.9435–1.0000 — 25% of the weight, 1.4 points of signal |
| Corridor width | 2.34–4.27 m across seeds — a room, not a spine |
| Speed | 1.58 s per variant, 63× over the 5 s / 200 variants target |

And three failures that are invisible to a room-polygon model:

- **Chambre 2**: 11.25 m², largest inscribed rectangle **1.30 × 1.75 m**. No bed fits.
- **Access**: filtering contacts to those ≥ 1.00 m (a door needs a leaf plus jambs),
  Chambre 1 opens only onto Chambre 2, the WC and the SDB. *You enter the bedroom
  through the bathroom.* Reported adjacency 7/9; door-capable 5/9.
- **Feasibility**: internal partition run measures 36.47 m. At 0.30 façade /
  0.10 cloison the habitable area is 92.11 m² against 103 m² programmed —
  **short by 10.6%**. The brief cannot be built at any wall thickness.

Root cause: the primitive. Furniture fit needs *shape*; access needs *doors on
walls*; feasibility needs *thickness*. None are properties of a bubble.

---

## 2. Net ↔ gross — the closed form

A slicing tree knows which walls bound a leaf **before** the leaf is sized, so the
correction is exact and needs no iteration. Each room loses half the thickness of
each wall it shares:

```
net_w = axis_w − (t_left + t_right) / 2
net_h = axis_h − (t_bottom + t_top) / 2
```

Inverted, for a target net area `A` and chosen aspect `r = net_w / net_h`:

```python
net_h  = sqrt(A / r)
net_w  = r * net_h
axis_w = net_w + (t_left + t_right) / 2
axis_h = net_h + (t_bottom + t_top) / 2
```

A 3.00 × 3.00 m room measured on axes is **8.41 m²** habitable behind 10 cm
partitions, **7.84 m²** behind 20 cm bearing walls — 6.6% and 12.9% below
programme. That is the difference between a compliant 9 m² chambre and a
non-compliant one.

---

## 3. Feasibility estimate (L0)

Before any partition exists there is no exact internal wall length, so the gate
uses an estimate calibrated against the measured fixture:

```
interior  = area(parcel.outline eroded by facade_thickness)
L_int     ≈ 1.3 * sqrt(n_rooms * interior)
habitable = interior − L_int * cloison_thickness
deficit   = programme.total_utile − habitable
```

Calibration: for the 7-room / 95.76 m² case this predicts L_int = 33.66 m against
36.47 m measured (8% low) and habitable 92.39 m² against 92.11 m² (0.3% off).
Conservative in the right direction — it slightly *over*-estimates habitable area,
so anything it rejects is certainly infeasible. L2 replaces the estimate with the
exact figure once a tree exists.

---

## 4. The band cut

A binary cut splits a rectangle in two and rooms open into each other. A **band
cut** splits it in three — room, corridor band, room — where the band is given a
**clear width** and its length falls out of the plan.

```
band_axis_width = profile.corridor_clear + (t_left + t_right) / 2
```

This is the structural reason the output is a distributed plan rather than a
composition. It is also why `"Couloir": {"surface": 7}` is the wrong input:
circulation area is a *result*, measured afterwards as a coefficient against
surface utile. A T-spine is a band cut nested inside one child of another band
cut; an L-spine is a band cut with one end closed.

---

## 5. Grid vs exactness

Structural cuts snap to the grid; partition cuts do not.

- A cut marked `structural=True` carries a bearing wall. It snaps to a grid line,
  and the areas either side absorb the tolerance.
- A cut marked `structural=False` carries a cloison. It is free, so leaf areas
  come out exact.

Two levels can only align if both were cut on the same structural lines — this is
the whole basis of R+n and costs nothing to honour now.

---

## 6. Where the optimiser sits

Search space is **L1 + L2 only**: room-to-leaf assignment, tree structure, cut
positions, band placement. L3–L8 are deterministic refinements. Inside the loop,
only O(1) or small-graph checks:

```python
def evaluate(tree, brief):
    part = tree.realise(brief)                    # exact areas by construction
    if not part.aspects_ok():         return None # O(n) float compare
    if not part.fits_furniture():     return None # O(n) two compares each
    if not circulation.reachable(part): return None # O(E) BFS from entry
    return metrics.score(part)                    # soft scores only
```

Once rooms are rectangles the largest inscribed rectangle *is* the room, so the
furniture test collapses to two float comparisons and can steer the search rather
than judge it afterwards.

Mutations operate on the tree: `swap_leaves`, `flip_cut`, `slide_cut`,
`rotate_band`, `regroup`.

---

## 7. R+n hooks that must exist in v1

Three things are nearly free now and expensive to retrofit:

1. **Bearing walls typed separately from partitions** — only bearing walls stack.
2. **Shafts are objects with positions**, not a property of a room — they align
   across levels.
3. **The partition sits on a structural grid** — two levels can only align if both
   were cut on the same lines.

`services/stacking.py` implements and tests `assign_stack_ids()` and
`stack_conflicts()` in v1 even though nothing calls them yet.

---

## 8. Migration map from v1

| v1 | v2 | Change |
|---|---|---|
| `core/geometry.py` `Envelope` | `brief/parcel.py` | gains typed edges + north |
| `core/geometry.py` `Room` | `fabric/plan.py` `Space` | derived, not authored |
| `core/geometry.py` graph utils | `topology/relations.py` | relations become typed |
| `core/generator.py` BFS | `topology/gradient.py` | orders the tree, stops placing |
| `core/generator.py` `_voronoi_fill` | — | deleted |
| `core/walls.py` `Wall/Door/Window` | `fabric/` + `openings/` | vocabulary kept, direction inverted |
| `core/walls.py` `door_graph()` | `circulation/reachable.py` | finally wired in |
| `core/scorer.py` | `evaluate/metrics.py` | `couverture` out, gates split off |
| `core/optimizer.py` | `search/loop.py` | random restart → annealing |
| `rules/base_rules.py` | `evaluate/constraints.py` | taxonomy kept |
| `rules/ma_rules.py` | `brief/regulation.py` | values become data |
| `rules/access_rules.py` | `circulation/` + `habitability/` | dead code becomes live |
| `export/`, `grasshopper/` | `document/` | real rectangles at last |

---

## 9. Caveat on the numbers

Wall thicknesses, door widths, allège heights, daylight ratios, furniture
footprints and minimum corridor width in this repo are **conventional placeholder
values**, not verified Moroccan regulatory requirements. They live in
`brief/regulation.py` as data precisely so a single file can be checked and
corrected by someone with the current code in hand. Everything else in this
document is measured against the v1 repository and reproducible from the fixture.
