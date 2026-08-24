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

