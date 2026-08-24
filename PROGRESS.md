# PROGRESS

Append one entry per session. Newest at the bottom. Keep entries under 10 lines.
This file is how the next session learns where the last one stopped — it is read
every time, so do not let it grow into an essay.

**Format**

```
## S<n> — <layer / what was built>            <date>
Built:    <files created or changed>
Proves:   <what the tests assert and that they pass>
Decided:  <any judgement call the next session must respect>
Next:     <the step number that should follow>
```

---

## S0 — scaffold                                     2026-08-24
Built:    repo restored from Plan-Gen-backup.zip (4 commits of v1 history intact);
          v1 `planfgen/` git-mv'd to `legacy/planfgen/` + `legacy/README.md`;
          v2 skeleton `planfgen/{brief,topology,partition,fabric,services,circulation,
          openings,habitability,evaluate,search,document,tests}/` (__init__.py only);
          fixtures git-mv'd to `planfgen/tests/fixtures/`; `pyproject.toml`.
Proves:   nothing functional — `import planfgen` succeeds, `pytest` collects 0 tests
          with no collection error (exit 5).
Decided:  repo root is the working dir; v1 preserved under `legacy/` for A/B only,
          never imported. `planfgen-v2-kit/` (holds PROMPTS.md) is gitignored.
Next:     S1 — L0 brief/ and the feasibility gate

## S1 — L0 brief/ and the feasibility gate            2026-08-24
Built:    `planfgen/brief/{programme,parcel,regulation,feasibility,plan}.py` and
          `planfgen/tests/test_brief.py`. `Brief.load()` gates on `AreaBudget`
          and raises `InfeasibleBrief` carrying it.
Proves:   13 tests pass. Edge orientations for north=0 and north=pi/2 (and a CW
          ring); MITOYEN/RETRAIT not openable; MITOYEN entry rejected;
          `estimate_partition_length(7, 95.76)` = 33.66 m; the v1 7-room fixture
          reproduces ARCHITECTURE section 3 exactly — interior 95.76, habitable
          92.39, deficit 10.61 m2.
Decided:  Bearings run clockwise from +Y as `atan2(x, y)`, minus `north`; the
          outward normal flips with ring winding rather than reordering edges.
          `from_json` is strict on v2 field names — the v1 nom->RoomType map
          lives in the test adapter, not in the library. `min_area`/`min_width`
          hold only the room types v1 stated; the rest carry no minimum.
          `AreaBudget.partition_estimate` is a length in m, not an area.
Next:     S2 — L3a fabric/ (PROMPTS.md orders fabric before topology)

## S2 — L3a fabric/ WallAxis and WallGraph            2026-08-24
Built:    `planfgen/fabric/{axis,graph}.py` and `planfgen/tests/test_fabric_graph.py`.
          `WallKind`/`WallAxis` with the axis-aligned guard, and `WallGraph` with
          `split_at_crossings`, `faces`, `bounding_walls`, `wall_between`,
          `shared_length`. No solidification — that is S3.
Proves:   16 tests pass (29 in total). The 6.00 x 4.00 grid cut at x=3, y=2 nodes
          6 authored axes into 12 segments, yields 4 faces of exactly 6.00 m2 with
          4 bounding walls each, 2.00 m shared horizontally and 0.0 diagonally.
          The notched 6x4 gives 5 faces of 4.00 m2, 20 m2 total.
Decided:  Axis endpoints are normalised to p0 <= p1 lexicographically — an axis is
          undirected and a canonical order keeps splitting deterministic. WallAxis
          is mutable so L4 can assign `stack_id` in place. `split_at_crossings`
          drops duplicate segments and is idempotent. `faces()` does NOT auto-node;
          call `split_at_crossings` first. `shared_length` measures boundary against
          boundary, so it stays exact when a run spans several split segments.
          Shapely appears only as polygonize/LineString/Polygon; axis.py is pure float.
Next:     S3 — L3b fabric/ solidify, Space, FabricPlan

## S3 — L3b fabric/ solidify, Space, FabricPlan       2026-08-24
Built:    `planfgen/fabric/{solidify,plan}.py` and `planfgen/tests/test_fabric_plan.py`.
          `net_polygon`, `wall_solids`, `Space`, `FabricPlan`.
Proves:   10 tests pass (39 total). The closed form of ARCHITECTURE section 2 lands
          exactly: a 3.00 x 3.00 axis cell is 8.41 m2 behind CLOISON and 7.84 m2
          behind PORTEUR, both below the 9.00 m2 chambre minimum. A grid cell is
          2.80 x 1.80 = 5.04 m2 against a 3.00 x 2.00 axis. door_capable is True at
          2.00 m and False at 0.63 m; the 2x2 grid gives every cell 2 neighbours.
Decided:  `net_polygon` offsets each edge along its own inward normal and recovers
          corners by intersecting consecutive offset lines — no Shapely buffer, which
          would round or mitre them. It reads winding off the face, because polygonize
          returns CW rings here. Collinear edges of unequal thickness emit a jog rather
          than being smoothed. `_wall_on_edge` takes the greatest overlap and raises if
          a face edge has no wall. `wall_solids` rectangles stop at the axis ends, so
          walls meeting at a corner abut rather than overlap. 7.84 is not exactly
          representable (2.8*2.8 = 7.839999999999999), so areas assert to abs=1e-9.
          `exterior_walls` takes a Space, not a nom, unlike the other FabricPlan methods.
Next:     S4 — L2a partition/ grid, slicing tree, exact sizing

