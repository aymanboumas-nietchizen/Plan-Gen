# PLANFGEN v2 — sessions after S13

The engine is complete for one unit on one rectangle. These sessions close the
gaps named in the deep analysis, in the order that unblocks the most.

Same working agreement as `PROMPTS.md`: one session, one step, tests in the same
session, `PROGRESS.md` entry and a commit at the end. Do not start the next
session early.

---

## The finding that orders everything

`search/anneal.py:73`

```python
def envelope_of(brief: Brief) -> tuple[float, float, float, float]:
    inset = brief.profile.facade_t / 2
    minx, miny, maxx, maxy = brief.parcel.outline.bounds
    return (minx + inset, miny + inset, ...)
```

**The footprint is the parcel's bounding box.** Always. Nothing else in the
engine ever decides how much of the site to build on. Three separate problems
are all this one line:

| Symptom | Cause |
|---|---|
| Programme must be hand-rescaled until the area gate passes | a bigger parcel makes every room bigger, so the brief has to be pre-matched |
| CLAUDE.md lists coverage as a gate; there is no coverage rule anywhere | coverage is trivially 100%, so there was nothing to check |
| Non-rectangular parcels unsupported | `.bounds` of an L is a rectangle that includes the notch |

So S14 is the hinge, and S15–S16 follow from it.

### Two measurements that make S14 small

Run against the 7-room fixture on the décret profile, five parcel sizes from
0.95× to 2.5× the programme:

**The area error is a single scalar, not a per-room problem.** The refinement
loop in `tree.realise` renormalises working demands every pass, so when the
envelope cannot deliver what was asked, every room is short by exactly the same
fraction. Measured spread between the best and worst room: **0.0000%** at every
parcel size. This is `_nudge`'s docstring turning out to be exactly true.

**The delivered total is a function of the footprint and the tree alone** — the
targets only control distribution. So both directions of fit are cheap:

| Approach | Cost | Residual |
|---|---|---|
| Scale the programme to what the footprint delivers | 1 realise + 1 multiply | 0.000000% |
| Solve the footprint that delivers the programme | **4 secant steps** | ~3e-10 m² |

Four realise calls is ~4 ms against a 600-iteration anneal. Automatic fitting is
not a research problem; it is about sixty lines.

---

## S14 — The footprint · *heavy*

Read `CLAUDE.md`, `brief/plan.py`, `brief/feasibility.py`, `brief/regulation.py`,
`partition/tree.py`, `search/anneal.py`, `evaluate/constraints.py`. Nothing else.

Stop the footprint from being the parcel. A footprint is *chosen*, and choosing
it is what reconciles a programme with a site.

```
brief/footprint.py

  @dataclass(frozen=True)
  class Footprint:
      """The rectangle actually built on, and the parcel it sits inside."""
      x: float; y: float; w: float; h: float
      def rect(self) -> tuple[float, float, float, float]
      def coverage(self, parcel: Parcel) -> float     # w*h / parcel.outline.area
      def within(self, parcel: Parcel) -> bool        # contains-test, 1e-9

  def sized_demand(programme: Programme, tree: SlicingTree) -> float
      """Net area the LEAVES ask for — circulation rooms naming a band are not
      leaves and their declared area is never demanded. `total_utile` sums all
      rooms, so it over-states what L2 has to deliver; that is why
      check_feasibility is doubly conservative. Note this in the docstring."""

  def fit_footprint(programme, parcel, profile, tree, aspect=None,
                    tol=1e-9, max_steps=12) -> Footprint
      """The footprint whose leaves deliver `sized_demand` exactly.

      Secant on gross footprint area; `delivered(A)` is monotone in A, so it
      converges in four steps from a 1.25x/1.45x bracket. `aspect` defaults to
      the parcel's own w/h. Raises `InfeasibleBrief` if the solved footprint
      does not fit inside the parcel.
      """

  def fit_programme(programme, footprint, profile, tree) -> Programme
      """The fallback, for when the parcel is too small to hold the programme:
      one realise, then scale every leaf's target by delivered/asked. Rooms get
      less than asked, uniformly, and the caller is told the factor. Circulation
      rooms keep their declared area — it is ignored downstream anyway."""
```

Then:

- `Brief` gains `footprint: Footprint | None = None`. `envelope_of` returns
  `brief.footprint.rect()` inset by `facade_t / 2` when it is set, and the old
  parcel-bounds behaviour when it is not — every existing test must still pass
  untouched.
- `RegulationProfile` gains `coverage_max: float = 1.0` — the CES, emprise au
  sol. **Neither the décret nor the Casablanca arrêté states one**: both are
  building-form texts (gabarit, alignement, saillies), and the CES comes from
  the zone's plan d'aménagement, not from a national rule. So it stays 1.0 in
  every profile, marked unsourced in the comment, and is a per-project input.
  Ask for the zone's CES rather than inventing one — inventing regulation
  numbers is exactly what cost five cells of capacity last time.
- Add `COVERAGE_GATE` to `GATES`, second, right after `AREA_GATE` — it is a
  float comparison and belongs among the cheap ones. **CLAUDE.md names coverage
  as a gate and it has never existed.** With the footprint equal to the parcel
  it would have failed every plan, which is presumably why it was skipped; it is
  checkable now, and at `coverage_max = 1.0` it passes everything until someone
  supplies a real figure.

`planfgen/tests/test_footprint.py`:

- `fit_footprint` lands within 1e-9 of `sized_demand` on four aspect ratios
  (1.0, 1.25, 1.6, 2.0) and four parcel sizes (1.0x, 1.4x, 1.8x, 2.5x), and
  takes no more than six steps in any of them.
- After fitting, `plan.max_area_error(profile)` is below `AREA_TOLERANCE`
  *without any hand calibration* — assert this on a brief built straight from
  `apartment_7rooms.json`, which is the thing that cannot be done today.
- A parcel smaller than the programme raises `InfeasibleBrief` from
  `fit_footprint`, and `fit_programme` on that same parcel returns a scaled
  programme whose factor is below 1.
- `sized_demand` excludes a COULOIR that names a band and includes one standing
  as a leaf.
- `envelope_of` with `footprint=None` returns exactly what it returned before.
- `Footprint.coverage` on a footprint half the parcel's area is 0.5.

Update `PROGRESS.md` and commit. **Stop here.**

---

## S15 — Where the footprint sits · *light*

Read `brief/footprint.py`, `brief/parcel.py`, `search/moves.py`, `search/anneal.py`.

S14 solves the footprint's *size*. Its *position* in the parcel is a real design
decision and is currently unmade — `fit_footprint` should centre it as a
placeholder, and this session gives it a reason.

- `Footprint.aligned_to(parcel, edge)` — push the footprint against one edge of
  the parcel. A dwelling addresses its street; a mitoyen edge is built up to,
  not set back from.
- `place_footprint(programme, parcel, profile, tree)` — default placement rule:
  flush to every MITOYEN edge, then flush to the entry edge, then centred in
  whatever freedom is left.
- Setbacks belong to the **edge**, not to the profile: a parcel's boundaries are
  set back by different amounts and `EdgeSpec` already types them one by one.
  Add `setback: float = 0.0` to `EdgeSpec`, read from the brief JSON. Do not add
  a `retrait_min` to `RegulationProfile` — décret ART.46's 2 m retrait is a
  roof-superstructure rule (terrace annexes set back from the façade), not a
  ground-floor setback, and neither text gives a general one.
- A `slide_footprint` move for the annealer, and a `shape_footprint` move that
  trades w against h at constant area. Both must preserve the solved area, so
  they re-solve rather than nudge; measure the cost per candidate before and
  after and record it in `PROGRESS.md`.

`planfgen/tests/test_footprint_place.py`: a footprint on a parcel with one
MITOYEN edge touches that edge to 1e-9; an edge with `setback=2.0` is respected
to 1e-9;
`shape_footprint` preserves area to 1e-9; the moves never leave the parcel.

Update `PROGRESS.md` and commit. **Stop here.**

---

## S16 — Rectilinear parcels · *heavy*

Read `partition/tree.py`, `brief/footprint.py`, `fabric/solidify.py`,
`tests/test_fabric_graph.py` (the L-shaped case at line 176). Nothing else.

L3 already handles rectilinear faces — `solidify.py:56` says so and the L-shaped
fabric test proves it. The gap is entirely at L2: a slicing tree realises onto
one rectangle.

Do **not** generalise the slicing tree. It is axis-aligned rectangles by the one
rule that governs everything, and it should stay that way. Decompose instead:

```
partition/decompose.py

  def rectangles_of(outline: Polygon, tol=1e-9) -> list[tuple[float,float,float,float]]
      """A rectilinear polygon cut into disjoint rectangles by sweeping the
      distinct x-coordinates of its vertices. Shapely for the geometry — this is
      not an inner loop. Raises if the outline is not rectilinear."""

  @dataclass(frozen=True)
  class Compound:
      """A footprint of more than one rectangle, and the tree assigned to each."""
      parts: tuple[tuple[Footprint, SlicingTree], ...]
      def realise(self, brief, grid) -> PartitionPlan   # concatenate the cells
```

The programme is split across parts in proportion to each part's area, and
`fit_footprint` runs per part. Two parts that share an edge must produce cells
that meet on it exactly, or `to_wall_graph` will author two walls where there is
one — assert that, it is the failure mode.

`planfgen/tests/test_decompose.py`:

- a 6×4 with a 2×2 notch decomposes into rectangles whose union equals the
  original to 1e-9 and whose pairwise intersections are empty
- an L-shaped parcel realises, and `to_fabric` gives one face per room
- cells from two parts sharing an edge are coincident there to 1e-9
- a non-rectilinear outline (a triangle) raises, with a message that says so

Update `PROGRESS.md` and commit. **Stop here.**

---

## S17 — ART. 4, the daylight-depth rule · *light*

Read `brief/regulation.py`, `habitability/check.py`, `openings/window.py`,
`evaluate/metrics.py`, and `regs/decret_2-64-445.txt`.

> ART. 4 — a room lit only on its short side may not be longer than twice the
> height under the lintel.

The only real regulation still unimplemented, and it is the honest version of
the aspect ratio I invented. `head_h` is 2.20, so the cap is 4.40 m.

- `daylight_depth_ok(cell, fabric, profile)` — find which walls of the space can
  carry a window (`parcel.openable`), and if the only openable wall is the short
  one, require `long <= 2 * profile.head_h`.
- It is a **gate**: it comes from a decree, it is not a judgement call. Add it
  after `FURNITURE_GATE`; it needs the fabric, so keep it before the wall graph
  is needed — or accept the cost and put it after `CIRCULATION_GATE` and say why
  in the docstring.
- Then re-run the ceiling sweep. `max_ratio=3.0` in `furniture.py` is a guess
  standing in for exactly this rule. If ART. 4 catches what 3.0 was catching,
  **raise `max_ratio` or drop it**, and record the before/after cell count. The
  measured sweep says unbounded gives 11 cells against 9 — some of that is
  reachable honestly.

`planfgen/tests/test_daylight.py`: a 2.0 × 5.0 room lit only on its 2.0 m side
fails; the same room lit on its 5.0 m side passes; a room with two openable
walls passes at any depth; an internal room with no openable wall is not judged
by this rule (it is judged by whether it may exist at all).

Update `PROGRESS.md` and commit. **Stop here.**

---

## S18 — Reference plans as fixtures · *light, and mostly not code*

Needs the plans. Ask before starting.

Fifteen to twenty measured Moroccan apartment plans, as JSON fixtures in the
existing `tests/fixtures/` format. Not training data — **calibration data**, to
replace guesses with measurements:

- room aspect ratios by `RoomType`, as a distribution, against the invented 3.0
- circulation coefficient, and metres of run per room served
- how many rooms open directly onto circulation rather than through another room
- how real plans resolve non-rectangular parcels

Write `tools/measure_reference.py` that reads a fixture and prints those four
figures, and a test that every fixture parses and passes `all_gates` — a real
built plan that the engine refuses is either a bug in the engine or a number in
the wrong place, and either way it is the most valuable failing test available.

Update `PROGRESS.md` and commit. **Stop here.**

---

## S19 — The floor plate · *heavy, several sessions*

Do not start until S14 and S16 are done; it needs both.

`stack_conflicts()` and the shaft stack ids have been waiting since S10. A
`Building` container, unit subdivision from a floor plate, a core reserved
before partition, and shared circulation as a band whose doors are unit entries
rather than room doors.

Finch's scope, and the one a promoteur actually buys. Scope it properly in its
own session before writing any of it.

---

## Deliberately not next

**Training.** Finch, the market leader, uses no ML for generation. The published
learned methods produce rasterised, non-metric layouts with unusable wall
structure, and the datasets are Chinese and Japanese. It would trade this
engine's one measured advantage for a known weakness. Revisit only as RLVR, with
`all_gates()` as the reward function and a corpus from S18 — the engine is the
prerequisite, not the thing being replaced.

**UI.** The studio boots, generates, renders four stages and exports DXF, and it
is covered headlessly. When it is worth returning to, take two things from
Finch: the score weights on sliders so the architect makes the trade-offs, and a
per-room fit breakdown so a rejected plan explains itself.
