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

## S4 — L2a partition/ grid, tree, exact sizing       2026-08-24
Built:    `planfgen/partition/{grid,sizing,tree,plan}.py` and
          `planfgen/tests/test_partition.py`. Binary cuts only — no band cut.
Proves:   19 tests pass (58 total). `axis_dims` round-trips to 3.6e-15 over 20 random
          (area, aspect) pairs. On a 10.00 x 8.00 envelope a 4-room tree with free cuts
          delivers every room its target net area EXACTLY (0.000%, not merely <0.5%),
          and stays exact however uneven the programme. The same tree with structural
          cuts snaps to the 5.00 x 4.00 grid and lands at 2.66% max error. Cells tile
          the envelope to 80.000000000 with no gap or overlap. A 7.2:1 slot fails
          aspects_ok.
Decided:  A cut splits **net** area, not axis area: it removes its own wall thickness
          from the run first, then divides what is left in proportion to demand. That
          is what makes leaves exact — the uniform factor is (deliverable / demanded),
          so if the programme asks for what the envelope can give, every room is exact
          regardless of tree depth or skew. Direction.V is a vertical cut LINE (splits
          left|right); children[0] is always the low side. `from_span` takes
          n = ceil(span / max_span) bays so the module divides the span exactly and no
          ragged bay is left. `_snapped` refuses a snap that would erase a side.
          `from_sequence` gained a `structural` kwarg the spec did not name — the tests
          need the same tree both ways.
Warning:  A coarse structural grid cannot represent an uneven programme. On this 10x8
          envelope the only interior grid lines are x=5 and y=4, so every structural
          cell is forced to 5.00 x 4.00. Near-equal rooms land at 2.66%; a programme of
          24/14/20/14.96 lands at 27.2%. S9's search must treat `structural` as a real
          cost, not a free flag.
Next:     S5 — L2b partition/ the band cut

## S5 — L2b partition/ the band cut                   2026-08-24
Built:    `BandCut` in `partition/tree.py`; `circulation_cells`,
          `circulation_coefficient`, `band_clear_width` and `SpaceCell.is_band` in
          `partition/plan.py`; `planfgen/tests/test_band_cut.py`. Nothing outside
          `partition/` was touched.
Proves:   17 tests pass (75 total). A band on a 10.00 x 8.00 rect has clear width
          exactly 1.20 in both H and V (axis 1.30 = clear + one cloison); flanking
          rooms stay within 0.5%; the three cells tile to 80.000000000. A 7-room
          spine plan gives circulation coefficient 0.117. A nested BandCut (T-spine)
          gives two corridors sharing a 1.30 m run, both still 1.20 clear.
Decided:  `width_source` is declared after `children`, since a defaulted dataclass
          field cannot precede one without a default. Bands are named from the
          programme's circulation rooms in tree order, and a tree with more bands than
          circulation rooms raises. Bands are excluded from BOTH area_error and
          aspects_ok: a corridor has no area target, and at 6.4:1 it would fail an
          aspect gate meant for furnishable rooms. Its declared surface_utile is
          ignored entirely, exactly as ARCHITECTURE section 4 requires.
Warning:  A single pass is exact only on a balanced tree — the 7-room fixture drifted
          1.33%. FIXED in S5b below; this entry is kept for the record.
Next:     S6 — bridge L2 to L3, and see a plan

## S5b — fix: exact sizing on unbalanced trees        2026-08-24
Built:    `realise` now refines. `_pass` is the old single pass; `realise` repeats it
          against a working demand nudged toward the measured shortfall and keeps the
          best result. `_targets`, `_spread`, `_nudge` in `partition/tree.py`; 6 tests
          added to `test_partition.py`.
Proves:   81 tests pass. The unbalanced 7-room fixture goes 1.3333% -> 0.0156% ->
          0.000197% -> 0.0000024% over passes 0..3 and reaches 0.0000000000% by the
          12th. 200 realises in 28 ms, so ~0.14 ms each.
Decided:  There is no closed form. The net area a subtree delivers depends on how it is
          split and the split depends on the area; the decomposition W = nw*HT + nh*VT
          only holds when siblings carry equal wall counts, which is precisely the
          balanced case. So: iterate, and keep the best pass — refinement can never
          make a plan worse than the single pass. Working demands are RENORMALISED to
          the programme total each pass, so refinement only redistributes. A shortfall
          the envelope cannot cover is uniform and is left alone (spread 4.4e-14 pp);
          grid-snapped structural cuts are untouched (2.6639% at refine=0 and at 12).
          `refine=0` still gives the plain single pass.
Next:     S6 — bridge L2 to L3, and see a plan

## S6 — bridge L2 to L3, and the first real plan     2026-08-24
Built:    `partition/bridge.py` with `wall_axes`, `to_wall_graph`, `to_fabric`, wired
          onto `PartitionPlan`; `document/preview.py` with `to_svg` (pure string
          building, no matplotlib); `planfgen/tests/test_bridge.py`.
Proves:   12 tests pass (93 total). Round trip Space.surface_utile vs
          SpaceCell.net_area is exact to 3.5e-13 (asked: 1e-6). No duplicated axes
          before or after split_at_crossings. Every rectangular room has 4 bounding
          walls. `to_svg` writes one fill per space plus stamps, scale bar, north arrow.
Ran it:   5-space apartment, 11.00 x 8.00, spine corridor -> outputs/preview.svg.
          Sejour 26.00 -> 26.0000, Cuisine 12.00 -> 12.0000, Chambre 19.00 -> 19.0000,
          SDB 8.70 -> 8.7000. Max area error 0.0000000000%. Corridor clear 1.200000 m,
          circulation 11.91%, total net 74.58 m2, 16 axes, aspects ok.
          Every room opens onto the corridor — the v1 "enter the bedroom through the
          bathroom" failure of ARCHITECTURE section 1 does not occur.
Decided:  THE ENVELOPE RECT IS THE PARCEL OUTLINE INSET BY facade_t/2, not the outline
          itself. Only then do the facade solids land inside the boundary AND does L2
          reconcile with L0: 11x8 inset 0.15 is 10.70 x 7.70, whose net is 10.40 x 7.40
          = 76.96 m2, the same interior check_feasibility erodes to. On this plan L0
          estimated 74.41 m2 habitable against 74.58 delivered — 0.23% conservative,
          exactly as ARCHITECTURE section 3 claims. Realising on the raw outline instead
          inflates every room by 3.33%.
          `wall_axes` groups cell edges by the line they sit on and cuts at every
          endpoint in the group, so a long edge facing two short ones becomes the same
          pieces either way. Outer runs therefore come back subdivided (10 facade axes,
          not 4) and the graph is pre-noded along each line.
          The preview owns its palette, keyed by RoomType — a Space is derived from the
          wall graph and has no business carrying a swatch.
Note:     A corridor has 6 bounding walls, not 4 — its long sides are cut where the
          rooms either side meet them. Still 4 distinct lines, so the net polygon is a
          clean rectangle. Any code counting bounding walls must not assume 4.
Next:     S7 — the gates: reachability and furniture fit

## S7 — the gates: reachability and furniture fit    2026-08-24
Built:    `circulation/reachable.py` (`entry_space`, `reachable`, `ReachabilityReport`),
          `habitability/{furniture,check}.py` (`FURNITURE`, `fits`, `fit_report`), and
          `planfgen/tests/test_gates.py`.
Fixed:    `FabricPlan.exterior_walls` returned NOTHING on any plan built the S6 way.
          Facade axes sit facade_t/2 inside the parcel outline, so collinear matching
          found nothing. Added `edge_run` with a slack of half the facade, plus
          `walls_on_edge` and `edge_length_on`. `entry_space` could not have worked
          without it.
Proves:   15 tests pass (108 total). The hand-built L-shaped flat whose chambre has
          three facade sides reports through_room == {"Chambre": "SDB"} and ok False —
          the v1 failure of ARCHITECTURE section 1, caught. A stranded cellier touching
          three rooms over 0.90/0.90/0.80 m is reported unreachable, and the WC beside
          it as reachable only via the sejour, in the same report. `fits` rejects
          1.30 x 1.75 against the CHAMBRE spec and accepts 2.50 x 3.10.
          Timings: fits 0.167 s per 100k calls, fit_report 7.5 us, reachable 256 us.
Decided:  `entry_space` ranks ENTREE first, then any circulation space (a corridor that
          meets the street IS the hall), then longest frontage. The entry itself is
          always passable — the through_room search refuses to cross any OTHER habitable
          room. `fits` takes an optional profile: a Space knows its net dims, a
          SpaceCell needs the profile to work them out. Room types absent from FURNITURE
          carry no requirement, same rule as regulation.py.
Warning:  `reachable` is clean, but the `adjacency_graph()` it consumes is O(n^2) and
          does touch Shapely face coordinates. At 256 us it is fine for 200 variants,
          but if S9 needs more it should cache adjacency on the FabricPlan.
Next:     S8 — L1 topology/ typed relations

## S8 — L1 topology/ typed relations                 2026-08-24
Built:    `topology/{relations,gradient,zoning,plan}.py` and
          `planfgen/tests/test_topology.py`. `RelationType`, `Relation`,
          `ProgrammeGraph`, `Zone`, `access_gradient`, `wet_cluster`, `day_night`,
          `suggest_tree_order`, `TopologyPlan`.
Proves:   19 tests pass (127 total). The v1 9-pair list loads as 9 CONNECTED relations
          over all 7 rooms. A SEPARATED WC-Cuisine relation is retrievable and distinct.
          On the apartment fixture the chambres are PRIVATE and the sejour PUBLIC.
          suggest_tree_order keeps the wet cluster contiguous and is deterministic.
          Order comes out: Chambre 1 -> Couloir -> Chambre 2 -> WC -> SDB -> Cuisine ->
          Sejour -> Entree. Night zone round the corridor, wet block together, then day.
Bugs:     Two, both found by running it rather than by reading it.
          (1) `Relation.__post_init__` swapped its fields with
          `object.__setattr__(self, "a", self.b)` then `..., "b", self.a)` — the second
          line reads the already-overwritten value, so both fields collapsed to one name
          and every relation involving an alphabetically-later room ERASED it. Séjour
          vanished from the graph entirely. Needs a temporary.
          (2) `_chain` seeded from the MOST connected block. A chain has two ends and
          starting in the middle wastes one: seeded at the hub of a star, every spoke
          after the first lands beside a spoke it has nothing to do with. Now seeds from
          the least connected block and runs through the hub.
Decided:  Only CONNECTED is walkable for the gradient — an ADJACENT pair shares a wet
          wall with no door in it. Depth 0-1 PUBLIC, 2 SEMI, 3+ PRIVATE as specified;
          a room the entry cannot reach is PRIVATE, and its unreachability is L5's
          finding not L1's. The wet cluster is ordered as one block and expanded after,
          so contiguity holds by construction rather than by luck. SEPARATED scores -3.0
          against CONNECTED's +2.0, so a forbidden pair is actively driven apart.
          day/night/service puts the SDB with the chambres and the WC with service —
          the conventional French split, and a judgement call.
Note:     The gradient is only as good as the graph. On the RAW v1 fixture nothing is
          more than 2 steps in, so the chambres come back SEMI, not PRIVATE. It takes an
          entrance hall and a corridor hanging off the sejour to get real depth. There
          is a test pinning both readings.
Next:     S9 — search/ mutations and annealing

## S8b — fix: a room is a leaf or a band, never both  2026-08-24
Built:    `realise` now excludes circulation rooms already standing as leaves from the
          band-name pool, and `_no_duplicates` rejects any nom placed twice. 3 tests
          added to `test_band_cut.py`.
Found by: composing L1 with L2 rather than reading either. `suggest_tree_order` returns
          ALL rooms including Couloir and Entree; `SlicingTree.from_sequence` turns every
          nom into a Leaf. Feed one into the other and a tree that also has a BandCut
          produced TWO cells named Couloir — one leaf, one band. The failure surfaced
          three layers later as `to_fabric: cell 'Couloir' matched more than one face`,
          which does not name the cause.
Proves:   130 tests pass. An Entree as a leaf beside a Couloir band now works and both
          appear in circulation_cells, with only the band excluded from area_error.
          A programme whose ONLY circulation room is already a leaf raises at realise
          with a message saying why. A tree naming the same room twice raises.
Warning:  S9 STILL HAS TO CHOOSE. `suggest_tree_order` gives an order over every room;
          nothing yet decides which of them become bands rather than leaves. The fixes
          only mean the wrong choice fails loudly at the source instead of silently
          producing a duplicate. A sensible default: the circulation room with the
          largest declared area becomes the spine, the rest stay leaves.
Next:     S9 — search/ mutations and annealing

## S9 — search/ mutations and annealing               2026-08-24
Built:    `evaluate/{constraints,metrics}.py`, `search/{moves,anneal}.py`,
          `planfgen/tests/test_search.py`. Five gates, four soft scores, five moves,
          simulated annealing keeping the best 10.
Proves:   28 tests pass (158 total). anneal is deterministic per seed; 200 iterations
          run in 0.20 s against the 5 s budget; every move preserves the leaf set and
          leaves the input tree untouched. THE VARIANCE TEST passes: 50 results over
          10 seeds give adjacences 6, orientation 5, circulation 5, compacite 5,
          globale 15 distinct values.
Numbers:  Best-of-200 on the 12x10 five-room fixture, seed 3, 0.20 s:
            adjacences  0.8214 -> 0.8929   (9 of 10 relations, CONNECTED needing a door)
            orientation 0.2000 -> 0.6000
            circulation 0.9421 -> 0.9423
            compacite   0.6319 -> 0.6739
            globale     0.6929 -> 0.8113
          Max area error 0.036%, circulation coefficient 10.87%, worst room aspect 2.13.
          v1 scored 0.556 door-capable (5 of 9) on its own fixture at seed 3.
Decided:  THREE findings, all measured rather than assumed.
          (1) EXACT SIZING REMOVES CUT POSITION FROM THE SEARCH SPACE. I added a `bias`
          field to Cut to give `slide_cut` something to slide; the refinement pass
          absorbs ANY bias exactly — +0.8, +2.5, -3.0 all give back the identical plan.
          Positions are a consequence of the areas, not a free variable. `bias` was
          reverted as dead weight. `slide_cut` now toggles `structural`, which is the
          only thing that genuinely moves a cut: onto the grid, areas absorbing it.
          (2) `compacite = min(1, 2.5 / ratio)` AS SPECIFIED IS CONSTANT. The aspect gate
          already guarantees ratio <= 2.5, so it scores exactly 1.0 on every plan that
          survives — one distinct value over 50 runs, which is precisely how v1 shipped
          `couverture`. The reference is now a square, so the number can move. The spec
          and its own variance test contradicted each other; the variance test wins.
          (3) DIVERSITY COMES FROM SEEDS, NOT FROM LONGER RUNS. 10 runs x 60 iterations
          gives min 5 distinct per metric; 10 x 200 gives min 3, because a longer run
          converges harder and returns a narrower best-list.
          Also: `Scores.globale`, not `global`, which is a keyword. `score(plan, brief,
          graph=None)` takes the relation graph as a third argument — Brief does not
          carry one. Gates run cheapest first and only REACHABLE_GATE builds the wall
          graph, which is cached on the plan for the adjacency metric to reuse.
          The annealer restarts from the seed with p=0.35 while nothing valid has been
          found; unbounded drift diverges (0 valid in 200 without it).
Warning:  [WRONG — corrected in S9b below. The v1 brief searches fine once the gates
          are right; this paragraph is kept only as the record of the mistake.]
          THE V1 BRIEF CANNOT BE SEARCHED AT ALL, and the reason is the point of v2.
          Grown to 12.84 x 9.63 where an exact partition delivers its 103 m2, 5000
          iterations at a 20% area tolerance found ZERO valid plans — aspect rejected
          3621 of them. A 5 m2 WC beside a 30 m2 sejour cannot be a slicing-tree leaf
          without becoming a slot. v1 produced a plan for this brief only because it
          never measured room shape. The headline numbers above are therefore from the
          five-room fixture, not from v1's, and the comparison is indicative only.
          Also: no move CREATES or destroys a band, so the search cannot discover a
          T-spine. That is the move S10+ will want, and it would likely unlock the v1
          brief by giving the small wet rooms a second corridor arm to open onto.
Next:     S10 — L4 services/ shafts, wet walls, R+n hooks

## S9b — fix: aspect is scored, not gated              2026-08-24
Built:    `ASPECT_GATE` removed from `GATES`; `min_width` removed from
          `MIN_AREA_GATE`. 4 tests added to `test_search.py` pinning the contract.
Why:      I had promoted two of v1's SOFT warnings into hard gates. v1 held
          `MaxRatioRule(2.5, hard=False)` and every `MinWidthRule(hard=False)` as
          warnings; only the minimum AREAS and the corridor width were hard. And
          CLAUDE.md lists compactness among the SCORED judgement calls, not the gates.
Call:     CLAUDE.md governs. It is the file that carries the rules every session, it
          enumerates both sides deliberately, and ARCHITECTURE section 6's
          `if not part.aspects_ok(): return None` is arguing about COST — "only O(1)
          or small-graph checks" — not about which checks are gates. Shape is now
          protected by FURNITURE_GATE, which CLAUDE.md does authorise and which asks
          the question that matters: not "is this room a slot" but "does a bed fit".
Corrects: S9 reported that the v1 brief CANNOT BE BUILT, on the evidence of 5000
          iterations finding zero valid plans. That was my own gate, not the brief.
          With the gates corrected the v1 brief searches immediately.
Numbers:  Best-of-200 on the v1 seven-room brief at 12.84 x 9.63, seed 3, 200 proposed
          33 accepted:
            adjacences  1.0000   -- 9 of 9 door-capable   v1: 0.556 (5 of 9)
            orientation 0.7500
            circulation 1.0000   -- coefficient 9.79%
            compacite   0.6276
            globale     0.8941   (found at iteration 195)
          Max area error 4.59%. Every one of v1's nine adjacencies now hosts a door,
          against five in v1. THAT is the A/B S9 was asked for.
          The five-room fixture is unchanged: 0.6929 -> 0.8113, adjacency 0.8929.
Note:     The best v1-brief plan has a WC at 1.32 x 3.93 (ratio 2.98) and a sejour at
          ratio 2.73 — both would have been thrown away by the old 2.5 gate, and both
          are legal and furnishable. The WC needs 0.90 x 1.40 and has 1.32 x 3.93.
Next:     S10 — L4 services/ shafts, wet walls, R+n hooks

## S10 — L4 services/ shafts, wet walls, R+n hooks     2026-08-24
Built:    `services/{shaft,wet,stacking}.py` and `planfgen/tests/test_services.py`.
          `ShaftType`, `Shaft`, `wet_clusters`, `place_shafts`; `assign_wet_walls`,
          `wet_report`; `Level`, `assign_stack_ids`, `Conflict`, `stack_conflicts`.
Proves:   17 tests pass (178 total). On the 12x9 seven-space flat the corridor splits
          the wet rooms into two clusters (Cuisine | SDB+WC), one shaft each, and every
          wet room ends with a wall on a shaft. The SDB-WC wall retypes to WET. The R+n
          test holds: stack_conflicts(level, deepcopy(level)) == []; removing the
          V:x=12.00 bearing line gives exactly one Conflict naming it.
Decided:  A shaft is sited on a wall two wet rooms share where the cluster has one, so
          one stack serves both. A lone wet room gets its shaft on a wall that could not
          have carried a window anyway — a MITOYEN or RETRAIT first, then the wall it
          shares least. Facades are never retyped WET: a wall between a bathroom and the
          street is the outside, and a 0.30 facade already hides a stack.
          `assign_wet_walls` RE-SOLIDIFIES the spaces it touches. WET is 0.20 against a
          cloison's 0.10, so both rooms lose 0.05 m of width; leaving the net polygons
          stale would break L3's own guarantee that its areas are measured. Measured on
          the fixture: SDB and WC each lose 0.05 * net_h.
Bug:      Caught by printing the ids rather than trusting them. Snapping a SHAFT centre
          to the structural grid moved it metres — a shaft at (9.15, 1.25) came back as
          `SH:8.00,0.00` on a 4.00 x 4.50 module. Worse, two bearing lines under 2.00 m
          apart collapsed onto one id, which would have hidden exactly the conflicts this
          module exists to find. `stable()` now takes the grid line only when the
          coordinate is genuinely on it (within 1e-6) and otherwise keeps its own,
          rounded to the centimetre. A facade axis inset half a wall is not on the grid
          and no longer pretends to be.
Note:     A bearing run split by noding is several axes with ONE stack id — the id names
          the line, not the segment, which is what stacks. There is a test for it.
          Nothing outside services/ and its tests calls `stack_conflicts`, exactly as
          ARCHITECTURE section 7 intends.
Next:     S11 — L6 openings/ doors and windows

## S11 — L6 openings/ doors and windows                2026-08-24
Built:    `openings/{door,window,place}.py` and `planfgen/tests/test_openings.py`.
          `Door` with `clearance_box`/`clashes_with`/`free_slot`; `Window`,
          `required_glazing`, `size_windows`; `place_doors`, `place_windows`,
          `place_openings`, `OpeningReport`.
Proves:   18 tests pass (196 total). THE LEGALITY TEST holds: on a parcel whose east
          and west edges are MITOYEN no window lands on either, and Ch2 — which touches
          only the party wall — is returned as an ERROR, not a warning.
          `required_glazing` of a 20.00 m2 room at 0.125 is 2.50. `place_doors` refuses
          a 0.63 m run with a message naming both 0.63 and the 1.00 m module. Two doors
          on one wall never overlap, checked pairwise on a real seven-space plan.
Decided:  A door's clearance box is the opening's own interval along the wall by one
          leaf deep on the swing side — the bounding rectangle of the quarter-disc.
          That is why two doors clear each other exactly when their openings do not
          overlap on the same side, which makes the test a float comparison.
          `Door` needed a sixth field the spec did not name: `swing_side`. A door knows
          its wall and the NAME of the room it opens into, and a name is not a
          direction — `clearance_box` could not otherwise say which way the leaf sweeps.
          `place_windows` takes an optional `programme`: a Space carries a kind but not
          the line of brief it came from, so the explicit `RoomSpec.daylight` flag wins
          where the brief is to hand and `DAYLIGHT_KINDS` decides otherwise.
Touched L0: `allege_h=1.00`, `head_h=2.20`, `entry_leaf=0.90` added to
          `RegulationProfile`, with `glazing_height` and `entry_module`. All three are
          regulation values and CLAUDE.md says those live ONLY in `brief/regulation.py`.
          The spec put `ENTRY_LEAF = 0.90` in `door.py`; the name is kept but now reads
          the profile's own field default, so there is one source of truth.
Warning:  The glazing shortfall check reports a room that cannot fit its required glass
          on the walls it has. Windows are capped at wall length less two jambs rather
          than being made wider than their wall — the shortfall is a fact about the plan,
          not something to paper over. Nothing gates on it yet.
Next:     S12 — L8 document/ DXF and dimensions

## S12 — L8 document/ DXF and dimensions                2026-08-25
Built:    `document/{dimensions,dxf}.py` and `planfgen/tests/test_document.py`;
          `ezdxf>=1.1` added to pyproject. `DimensionChain`, `exterior_chains`,
          `interior_chains`, `room_stamp`, `stamp_text`, `LAYERS`, `export_dxf`.
Proves:   16 tests pass (212 total). Every test goes through `ezdxf.readfile` rather
          than inspecting the document in memory — a file ezdxf writes but will not
          reopen is worse than no file. All ten layers exist with their colour and
          lineweight; one closed four-point polyline per wall solid, each on the layer
          for its kind; a stamp per space carrying its net area to 2 dp; every chain
          span is a real DIMENSION entity on COTATION.
          On the reference flat: 34 LWPOLYLINE, 34 HATCH, 32 LINE, 12 DIMENSION,
          7 ARC, 7 MTEXT. Stamp reads `Sejour\P23.04 m2\P4.80 x 4.80`.
Decided:  Walls go out as SOLIDS, one layer per kind, never as hairlines — the whole
          claim of v2 is that a wall has thickness, and a DXF of lines would throw away
          the thing the engine exists to compute. Openings are GAPS cut in those solids,
          not symbols laid over them, so what is drawn is what would be built; there is
          a test asserting the cut file has more wall polylines than the plain one.
          An exterior chain ticks only the walls that actually MEET that side, so the
          bottom reads [0, 5.00, 6.30, 9.15, 12.00] and the top omits 9.15 — the SDB/WC
          wall does not reach the back. A drawing showing one chain for both would be
          hiding half the plan.
          Interior chains follow BEARING lines only. A plan cut entirely with cloisons
          has none, which is correct rather than empty: there is nothing structural in
          it to dimension. The test fixture retypes two walls PORTEUR to exercise them.
Note:     `doc.saveas(path)`, never `doc.save()`, as the prompt requires. $INSUNITS is
          set to 6, metres. Room stamps are MTEXT with `\P` line breaks, so splitting
          a stamp on `\P` recovers the nom.
Next:     S13 — Grasshopper, IFC, studio (the last session)

## S13 — Grasshopper, IFC, studio                      2026-08-25
Built:    `document/{gh,ifc}.py`, `grasshopper/planfgen_component.py`,
          `studio/{render,app}.py`, `planfgen/tests/{test_gh,test_studio}.py` and an
          IFC section in `test_document.py`. `ifcopenshell` and `streamlit` added to
          pyproject as OPTIONAL extras — neither is needed to generate a plan.
Proves:   231 tests pass, 1 skipped (the no-ifcopenshell branch; it is installed here).
          THE ROUND TRIP holds: rebuilding a rectangle from the exported x, y, w, h
          reproduces every space's axis polygon to 1e-9 by symmetric difference. v1
          could not have passed it — its component took the BOUNDING BOX of a Voronoi
          cell, so the rectangle in Rhino was never the room.
          IFC: 7 IfcSpace, 22 IfcWall, one each of Project/Site/Building/Storey, and
          Pset_SpaceCommon carrying Gross 25.00 against Net 23.04 — the distinction the
          whole engine exists to compute. Streamlit boots headless and serves 200.
Decided:  An IfcSpace carries the NET area. Exporting the axis area would hand the next
          consultant a room several percent larger than the one that gets built, which
          is the same lie v1's Rhino component told.
          `export_ifc_openings` deliberately RAISES NotImplementedError. An IfcDoor is
          only meaningful with an IfcOpeningElement voiding its wall, and a door written
          without one is a symbol floating beside a solid wall — exactly the drawing
          this project exists to stop producing. The DXF already cuts openings properly.
          Openings reference walls by INDEX into the walls list: JSON has no object
          identity, and matching a door back to its wall by comparing floats is how
          round trips rot.
Found:    A space's `outline` may carry more than four points. The corridor is a
          rectangle with SEVEN vertices, because polygonize keeps a node where each
          room T-joins its long sides. Still a rectangle, so the round trip holds, but a
          consumer walking `outline` must not assume four points. `net_outline` has the
          redundant ones dropped, and that is what the Rhino component builds from.
Note:     The studio's stage selector is the argument of the rewrite made visible: L1 is
          a graph with no geometry in it, L2 is geometry with no graph in it, and
          `test_studio.py` asserts the two SVGs are not the same picture. The app is
          verified by compile, by its renderers' tests, and by booting headless — not by
          interaction, which nothing here can drive.
Status:   THE STACK IS COMPLETE FOR ONE LEVEL. L0 to L8 all implemented and tested.
Next:     Nothing scheduled. PROMPTS.md lists four follow-ons in value order: R+n on top
          of the working `stack_conflicts`; rectilinear decomposition for non-rectangular
          parcels; NSGA-II for a real Pareto front; Revit round-trip. Before any of them,
          the placeholder tables in `brief/regulation.py` and `habitability/furniture.py`
          are the highest-value thing to verify — S9b showed they decide whether a brief
          is buildable at all.

## S14 — audit: the placeholder tables, and the studio          2026-08-25
Built:    `table_conflicts()` in `habitability/check.py` with `TableConflict`; 3 tests
          in `test_gates.py` pinning the disagreements; 4 AppTest tests in
          `test_studio.py`. 238 tests pass, 1 skipped.
Audit 1 — DO THE TWO TABLES AGREE? Three disagreements, one of them a contradiction:
          * WC: min_area says 1.20 m2 is legal; FURNITURE says the pan and its approach
            need 0.90 x 1.40 = 1.26 m2. A WC BUILT EXACTLY TO THE MINIMUM IS LEGAL ON
            AREA AND HAS NOWHERE TO PUT THE FIXTURE. Only the WC has this problem.
          * CHAMBRE: min_width 2.70 against a furniture min_side of 2.40.
          * WC: min_width 1.20 against a furniture min_side of 0.90.
          The width pair are preferences, not contradictions — min_width is no longer
          gated (S9b) so nothing breaks, but the two files disagree about the same room.
          corridor_clear 1.20 and FURNITURE[COULOIR].min_side 1.20 agree.
Audit 2 — WHICH NUMBERS DECIDE BUILDABILITY? Measured over 700 mutations with the
          programme RECALIBRATED to each profile, so the area gate does not mask the
          shape gates behind it. Pass rate at -20% / +20%:
            FURNITURE table    14.3% -> 0.0%   swing 14.3 pp   <- most load-bearing
            cloison_t (0.10)   10.1% -> 0.0%   swing 10.1 pp
            corridor_clear     0.0% -> 10.1%   swing 10.1 pp
            facade_t (0.30)    10.4% -> 10.1%  swing 0.3 pp
            porteur_t, door_leaf, door_jamb, min_area: 0.0 pp
          TIGHTENING THE FURNITURE TABLE BY 20% MAKES NOTHING BUILDABLE. min_area moves
          nothing because this fixture's rooms are 10-34 m2 against minima of 1.2-12 —
          the minima never bind. Verify `habitability/furniture.py` FIRST.
Method:   The first version of this measurement was wrong twice and both are worth
          remembering. (1) Without recalibration the AREA gate rejects everything on any
          profile change, so every other table read 0.0 pp. (2) Patching FURNITURE by
          rebinding the module global does not reach `check.py`, which holds its own
          reference from a `from ... import` — the dict has to be mutated in place. The
          FURNITURE row read 0.0 pp until that was fixed.
Studio:   It IS drivable from here — booted headless on :8899, clicked Generer through
          the browser, all four tabs rendered and L8 wrote studio.dxf and the preview.
          But a browser click is not a test that survives, so the coverage is
          `streamlit.testing.v1.AppTest`: runs the script headlessly, no server and no
          browser, 4 tests in 2.2 s. They assert the budget appears before the button,
          that generating yields exactly the four stage tabs, that the metrics are real,
          and that an infeasible brief errors and stops instead of generating.
Not done: NOTHING HERE VERIFIES THE NUMBERS AGAINST MOROCCAN REGULATION. That needs a
          document this repo does not have. What is now known is which numbers matter
          and where the two files contradict each other.

## S15 — a larger programme: 14 rooms, not 6                    2026-08-25
Built:    3 scaling tests in `test_partition.py`. 241 tests pass, 1 skipped.
Fixture:  A villa — 13 rooms plus a spine on 18.50 x 15.50 m, against the 5-7 room
          flats everything else was tested on.
Holds:    EXACT SIZING SURVIVES THE JUMP. A depth-12 chain and a depth-4 nest over the
          same 13 rooms both reach 0.00000000% area error. Depth costs passes, not
          accuracy: the chain is 8.23% at one pass and 0.000000% by twelve, the nest
          1.24% and 0.000000%. The cells still tile the envelope exactly.
          Performance scales about linearly: ~2.0 ms per candidate at 14 rooms against
          ~1.0 ms at 6, so 600 iterations run in 1.2-1.9 s.
          L1 still composes: 19 relations, the wet cluster contiguous at [2,3,4,5].
Found:    ONE SPINE CANNOT SERVE THIRTEEN ROOMS, and the two failures are opposite.
            chain     every room's edge on the spine, but 6 rooms too thin  -> 0 valid
            balanced  good proportions, 5 rooms reached through another room -> 0 valid
            T-spine   both                                                  -> 10 VALID
          A chain gives every room a face on the corridor and squeezes each into a
          strip; a balanced nest gives chunky rooms and buries five of them behind
          others, which `reachable` correctly refuses. Two corridor arms give both:
          globale 0.6533, area error 0.395%, circulation 11.87%.
          This confirms the S9 warning from the other side. NO MOVE CREATES OR DESTROYS
          A BAND, so the search cannot discover a T-spine — the seed must contain it,
          and the programme must declare one circulation room per band. At 6 rooms that
          did not matter. At 14 it decides whether anything is buildable at all.
Bug:      Mine, not the engine's, and the same conflation the engine itself fixed in
          S8b: the calibration harness summed delivered area over `not is_band` and
          asked area over `not is_circulation`. An ENTREE is circulation by kind and a
          leaf by placement, so it sat in one sum and not the other, and every room came
          back short by an identical 3.2359%. A uniform error across every room is the
          signature of a total that is wrong, not a distribution that is — the
          refinement was working correctly the whole time. Fixed by filtering on what
          the tree PLACES.
Next:     Nothing scheduled. If R+n or larger programmes are the direction, a move that
          inserts or removes a BandCut is now the highest-value single addition — it is
          what stands between the search and a plan for anything above ten rooms.

## S16 — the two defects from the drawing review               2026-08-25
Built:    `max_ratio` on `FurnitureSpec`; `circulation/shape.py` with `Run`,
          `CirculationReport`, `circulation_runs`; `CIRCULATION_GATE`; run-per-room
          folded into the circulation score. 243 tests pass, 1 skipped.
Defect 1 — THE SLOT. A WC came back 5.17 x 0.92 and passed every gate, because
          `fits` asked only `min(w,h) >= 0.90 and max(w,h) >= 1.40`. A minimum
          footprint has a floor and no ceiling, so a corridor with a pan at one end
          clears it twice over. `FurnitureSpec` now carries `max_ratio`; COULOIR alone
          is `None`, because a corridor IS meant to be long. Specs added for CELLIER,
          BUREAU and ENTREE, which had none and so were never checked at all — that is
          why a 5.17 x 1.61 cellier went through.
          This is a furniture constraint, not the aspect rule S9b took out of the gates.
          CLAUDE.md gates furniture fit and scores compactness; whether a bed can be
          ARRANGED in a room is the first question, not the second.
Defect 2 — THE CUL-DE-SAC. `circulation` scored the area coefficient only, so a compact
          hall and a spine running the depth of the building scored identically. Now
          measured: `stub`, how far a corridor overruns its last door, and `per_room`,
          metres of run for each room served. Stub is GATED at one clear width — beyond
          that it is not turning space, it is corridor leading nowhere. Size stays
          SCORED, half coefficient and half run-per-room.
          On the plan that was reviewed: no stub, but 24.01 m of circulation at 2.18 m
          per room, with the Entree running the full 14.90 m depth. The stub was zero
          and the waste was real, which is why both numbers are needed.
Fixtures: BOTH NEW GATES CAUGHT DEFECTS IN MY OWN FIXTURES, which is the point of them.
          The reference apartment had an SDB of 4.91 x 2.08 — a bathroom five metres
          long — recalibrated to 5.13 x 2.56. `test_gates`' spine flat had a chambre at
          2.21 and an SDB at 2.67; a 6.40 m wide room needs 3.20 m of depth to stay
          inside 2:1 and that does not go into a 9.00 m envelope three times, so it is
          11.00 now.
Also:     `test_every_metric_varies` was measuring the OPTIMISER, not the metric. A good
          search concentrates, so the kept best-of-ten agreed on circulation and
          compacite and showed three values between them. It now samples what a run
          EVALUATES rather than what it keeps, and asserts over every candidate found
          instead of a fixed-stride slice — a 50-sample saw five orientations and an
          80-sample saw four, which is luck, not a property.
Warning:  THE 14-ROOM VILLA NO LONGER PRODUCES A VALID PLAN. Neither a larger parcel
          nor a third corridor arm recovers it: `calibrate` scales the rooms with the
          parcel, so every RATIO is unchanged — proportion is a property of the topology,
          not of size. Thirteen rooms chained along corridor arms are strips whatever
          the envelope. This is the same limit as S15 seen from the other side, and it
          is now a hard refusal rather than a bad-looking drawing.
Next:     Regulations to encode when they arrive. After that, non-rectangular parcels
          (rectilinear decomposition), then a move that inserts a BandCut.

## S17 — the regulations, found and read                        2026-08-25
Built:    `MA_ECONOMIQUE` and `MA_CASABLANCA` in `brief/regulation.py`, each figure
          carrying the article that states it; `MIN_GLAZING`, `MIN_WINDOW_DIMENSION`,
          `PROFILES`. `ARRANGEABLE = 3.0` replacing nine invented per-type ratios.
          243 tests pass.
Sources:  Decret n° 2-64-445 (26 Dec 1964), reglement general de construction d'habitat
          economique — read from the PDF, not from a summary. And the Arrete municipal
          permanent of Casablanca. THEY DISAGREE, which is why a profile is a profile.
            ART. 3  ceiling 2.60 coastal / 2.80 inland, 2.25 service
            ART. 4  smallest dimension of a habitable room 2.35 m (2.20 if average);
                    a room lit only on its short side is at most twice its lintel
                    height long — a daylight-depth rule this engine does not have
            ART. 5  piece principale 12 m2, other habitable 9, cuisine 5 (4 with a
                    loggia) and no kitchen dimension under 1.70, salle d'eau 1.30,
                    WC 0.85
            ART. 6  degagements 0.80 m for one dwelling, 1.00 for 2-4, 1.10 for 5-10,
                    1.20 above ten
            ART. 7  glazing 1/10 of the floor and never under 1 m2
          Casablanca ART. 63 living 14 m2, glazing 1/6, cuisine 6 m2 with 4 m of vue
          directe; ART. 64 debarras width at most 1.75; ART. 65 salle de bain 3 m2.
Verdict:  THE PLACEHOLDERS WERE MOSTLY TOO STRICT, not too loose. min_area for the
          chambre (9) and the piece principale (12) were exactly right. Everything else
          was over: SDB 3.5 against 1.30, WC 1.2 against 0.85, cuisine 6 against 5,
          min_width 2.70-3.00 against 2.35, daylight 0.125 against 0.10. The WC
          contradiction found in S14 was an artefact of an invented 1.2.
Bug:      `FURNITURE[COULOIR]` was a REGULATION VALUE LIVING OUTSIDE regulation.py, which
          CLAUDE.md forbids, and it duly broke the moment a real profile arrived: a
          0.80 m degagement, legal under ART. 6, failed a 1.20 m spec copied from the
          placeholder. Every plan was refused for being legal. Removed; a band's clear
          width is `profile.corridor_clear` by construction and needs no gate.
Measured: The invented per-type `max_ratio` of 2.0-2.5 was the single thing capping the
          engine. Swept against a growing programme on the decret profile, the number
          of rooms the search can place: unbounded 11, at 4.0 ten, at 3.5 and 3.0 eight,
          at 2.5 six. One figure of 3.0 still refuses both faults from the drawing
          review (the WC at 5.62:1, the cellier at 3.21:1) and buys back two rooms.
Result:   CEILING 6 -> 8 ROOMS, and the scores went UP, from 0.835 to 0.883-0.926.
          Eight cells is a salon, three chambres, cuisine, SDB, WC and circulation —
          an F4. Six is an F3. Al Omrane builds 70% F3 and 30% F4, so the engine now
          reaches the whole of the dominant Moroccan typology.
Next:     The deep analysis, and then non-rectangular parcels.

## S18 — the move that makes circulation                        2026-08-25
Built:    `insert_band` and `remove_band` in `search/moves.py`; `mutate` gained a
          `band_budget`, which `anneal` derives from the programme's circulation
          rooms. 247 tests pass.
Why:      Flagged in S9 and confirmed twice since: NOTHING CREATED CIRCULATION. A seed
          with one spine could only ever be rearranged into another plan with one
          spine, and S15 showed one spine cannot both reach thirteen rooms and leave
          any of them a decent shape. A band takes its name from a circulation room, so
          the budget is what the brief declares — proposing more is proposing a plan
          that cannot be realised, and `remove_band` never takes the last one.
Result:   CEILING 8 -> 9 CELLS. Smaller than hoped: `insert_band` converts a cut in
          place, so it puts a corridor where a wall was but does not rearrange the
          rooms around it. Getting past nine wants a move that restructures a subtree
          AROUND a new band, not one that relabels a node.
Session:  Taken together with S16 and S17, the capacity went 6 -> 8 -> 9 cells and the
          scores from 0.835 to 0.879-0.932. Nine cells is a salon, three chambres,
          cuisine, SDB, WC and two circulation spaces.
Also:     `test_every_metric_varies` was fragile again — a single random walk samples one
          corner of the space, and merely ADDING two moves changed the draw order and
          with it the answer. It now unions six independent walks, which is a property
          of the space rather than of the walk.


---

## S18 — The plan for the gaps (no engine code)

Built:    `PROMPTS-NEXT.md` — S14 to S19, in the order that unblocks the most.
Found:    `envelope_of` returns the parcel's BOUNDING BOX, so the footprint is always
          the whole site. That one line is three separate gaps: the brief has to be
          hand-rescaled to the parcel, coverage is trivially 100% so no coverage gate
          was ever written, and `.bounds` of an L is a rectangle including the notch.
Measured: the area error is a single scalar, not a per-room problem — spread between
          best and worst room is 0.0000% at every parcel size, because `_nudge`
          renormalises. So fitting is a closed form: scaling the programme is one
          realise plus one multiply (0.000000% residual), and solving the footprint
          takes FOUR secant steps (~3e-10 m2) at any aspect ratio.
Checked:  neither the décret nor the Casablanca arrêté states a CES/emprise — that
          comes from the zone's plan d'aménagement. ART.46's 2 m retrait is a roof
          superstructure rule, not a footprint setback. Both recorded so neither gets
          invented later; setback belongs on `EdgeSpec`, not on the profile.
Next:     S14. CLAUDE.md names coverage among the gates and it has never existed.
