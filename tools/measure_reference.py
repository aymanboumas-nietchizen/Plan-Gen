"""Recover rooms from wall geometry in a real drawing, and measure them.

    python tools/measure_reference.py <file> --walls "mur|menuiserie"
    python tools/measure_reference.py <file> --walls "..." --plans-only

`tools/inspect_dxf.py` tells you which layers to pass — its CONVENTION pass
reports the layers the cotes terminate on, and those are the walls.

Neither agency file draws rooms as faces: ENNAKHIL's `MUR` layer holds 14 closed
polylines against 8347 lines, and NOUR's plans are polygons and hatch. So a room
has to be *derived* from the walls around it, which is the same thing the engine
does at L3 and is done here the same way — `shapely.ops.polygonize` over noded
segments, exactly as `fabric/graph.py:108` does it.

The difference is that the engine's walls are clean by construction and these
are not. Three things bridge that gap:

  SNAPPING    Coordinates are rounded onto a tolerance grid before noding. Two
              wall ends a tenth of a millimetre apart are one corner to an
              architect and two to `polygonize`, which then finds no face at all.
  DOORS       A doorway is a GAP in the wall, so a face bounded by one leaks
              into the corridor and swallows the flat. Door and window geometry
              (the menuiserie layers) closes those openings, which is why it
              belongs in the barrier set rather than being filtered out as
              furniture.
  HONESTY     Every label that resolves to no face, and every face that holds
              more than one label, is COUNTED AND REPORTED. A leak merges two
              rooms into one plausible-looking polygon, and a measurement taken
              from that is worse than no measurement. The resolve rate is the
              first number printed for that reason.

What comes out is the four figures S18 asks for — room aspect ratios by type,
the circulation coefficient, how many rooms open directly onto circulation, and
how the parcel resolves — measured rather than invented.

Read-only. The drawing is never modified.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shapely.geometry import LineString, Point  # noqa: E402
from shapely.ops import polygonize, unary_union  # noqa: E402

from inspect_dxf import UNITS, _keep, _open, _rule, find_sheets  # noqa: E402

#: Label to room type, first match wins — so the longer, more specific pattern
#: has to come first. `CH.parent` must be tested before `CH.`, and a
#: `Salon Marocain` is a SEJOUR: corrected by the architect, and a Moroccan
#: dwelling may hold both it AND a separate sejour, so two SEJOUR-kind rooms in
#: one plan is typology rather than a duplicate.
ROOM_TYPES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"ch\W*(parents?|princip)", re.I), "CHAMBRE_PRINCIPALE"),
    (re.compile(r"chambre\W*(parents?|princip)", re.I), "CHAMBRE_PRINCIPALE"),
    (re.compile(r"\bch\W*\d|\bchambre", re.I), "CHAMBRE"),
    (re.compile(r"salon|s[ée]jour|living", re.I), "SEJOUR"),
    (re.compile(r"cuisine|kitchen", re.I), "CUISINE"),
    (re.compile(r"s\W*d\W*b|salle de bain|douche|bain", re.I), "SDB"),
    (re.compile(r"\bw\W*c\b|toilette", re.I), "WC"),
    (re.compile(r"couloir|d[ée]gagement|hall|palier|circulation", re.I), "COULOIR"),
    (re.compile(r"entr[ée]e|vestibule", re.I), "ENTREE"),
    (re.compile(r"bureau", re.I), "BUREAU"),
    (re.compile(r"cellier|buanderie|d[ée]barras|rangement|placard", re.I), "CELLIER"),
    (re.compile(r"terrasse|balcon|loggia|patio", re.I), "TERRASSE"),
)

#: Types that are circulation rather than rooms served by it.
CIRCULATION = frozenset({"COULOIR", "ENTREE"})

#: Outside the dwelling's net area. A terrace is not habitable floor and folding
#: it into the circulation coefficient would flatter every plan that has one.
OUTDOOR = frozenset({"TERRASSE"})

#: A face smaller than this is a wall pocket, a column box or a hatch island.
MIN_AREA = 0.8

#: A face larger than this is the building outline or a leak, not a room. Set
#: from the largest room anyone would call a room, with generous headroom.
MAX_AREA = 120.0

#: The short side a face must have to be a room rather than the cavity between
#: a wall's two lines. Below decret ART.4's 2.35 m on purpose: this rejects
#: non-rooms, it does not judge whether a room is legal.
MIN_SIDE = 0.9

#: How much of its bounding box a face must fill to have a meaningful aspect
#: ratio. An L-shaped room or one wrapping a core fills far less, and its bbox
#: says nothing about its proportion.
FILL = 0.62


def classify(label: str) -> str | None:
    """The RoomType a label names, or None if it names nothing we model."""
    for pattern, kind in ROOM_TYPES:
        if pattern.search(label):
            return kind
    return None


def barriers(msp, keep, walls: re.Pattern, snap: float):
    """Every edge that a room's boundary could run along, snapped and noded.

    Arcs are included because a door's swing often closes its own opening, and
    a circle because a column drawn as one is a real obstruction.
    """
    used: Counter = Counter()
    lines: list[LineString] = []

    def add(points, layer):
        pts = [(round(x / snap) * snap, round(y / snap) * snap) for x, y in points]
        clean = [pts[0]]
        for p in pts[1:]:
            if p != clean[-1]:
                clean.append(p)
        if len(clean) >= 2:
            lines.append(LineString(clean))
            used[layer] += 1

    def stream():
        """Modelspace, with block references exploded in place.

        The door symbols are BLOCKS. ENNAKHIL's MENUISERIE layer is 5913 lines,
        835 polylines and 288 INSERTs, and the swing arcs are inside those
        inserts — so a pass that reads only modelspace sees no door geometry at
        all, every doorway stays open, and the whole flat polygonizes into one
        165 m2 face with SDB, Sejour and three Chambres inside it. That was the
        single reason the first version resolved 26%.
        """
        for entity in msp:
            if entity.dxftype() == "INSERT":
                if not walls.search(entity.dxf.layer or "") or not _keep(entity, keep):
                    continue
                try:
                    for sub in entity.virtual_entities():
                        # The parent INSERT already passed the region test and
                        # carries the layer; a virtual sub-entity may have
                        # neither a placeable point nor the parent's layer.
                        yield sub, entity.dxf.layer or "?", True
                except Exception:
                    continue
            else:
                yield entity, entity.dxf.layer or "?", False

    for entity, layer, exploded in stream():
        kind = entity.dxftype()
        if not walls.search(layer):
            continue
        if not exploded and not _keep(entity, keep):
            continue
        try:
            if kind == "LINE":
                a, b = entity.dxf.start, entity.dxf.end
                add([(a[0], a[1]), (b[0], b[1])], layer)
            elif kind == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in entity.get_points("xy")]
                if entity.closed and len(pts) > 2:
                    pts.append(pts[0])
                add(pts, layer)
            elif kind in ("ARC", "CIRCLE", "ELLIPSE"):
                add([(p[0], p[1]) for p in entity.flattening(snap)], layer)
                # A DOOR SWING closes its own opening, but not by its arc.
                # The leaf is drawn perpendicular to the wall, so neither leaf
                # nor arc spans the gap — and with the gap open, the room leaks
                # into the corridor and the merged face is discarded as too
                # large. What does span it is a RADIUS: the arc's centre is the
                # hinge and its ends are the jambs, so centre-to-end is the door
                # standing closed. Adding both radii bridges the opening without
                # inventing geometry that is not implied by the symbol.
                if kind == "ARC":
                    c = entity.dxf.center
                    for point in (entity.start_point, entity.end_point):
                        add([(c[0], c[1]), (point[0], point[1])], layer)
        except Exception:
            continue
    return lines, used


#: The width of an opening worth bridging. A door leaf is 0.70–0.90 m and a
#: cased opening between a sejour and a hall runs wider; past the upper bound it
#: is not an opening, it is the room.
OPENING = (0.55, 2.10)

#: How near to collinear the bridge must be with the wall it continues, in
#: degrees. The gap left by a doorway sits on ONE straight wall line, so the
#: bridge runs along that line at both ends. Requiring it at both is what stops
#: this joining two unrelated walls across a room.
COLLINEAR = 18.0

#: Loose ends closer than this are the same corner drawn twice, and are welded
#: shut without asking anything about direction. Measured: on ENNAKHIL the
#: nearest other loose end is 4 cm away at the median. Kept under half a cloison
#: so it cannot weld a wall's two faces together.
STITCH = 0.25


def _ends(line: LineString):
    """Each end of a line, with the unit vector pointing out of it.

    The outward direction is the direction the wall would carry on in if it had
    not stopped — which is exactly where a doorway's far jamb lies.
    """
    pts = list(line.coords)
    for near, far in ((pts[0], pts[1]), (pts[-1], pts[-2])):
        dx, dy = near[0] - far[0], near[1] - far[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            yield (round(near[0], 6), round(near[1], 6)), (dx / length, dy / length)


def bridge_openings(lines: list[LineString], cell: float = 4.0):
    """Close doorways by joining wall ends that a door was drawn between.

    A doorway is a GAP in a wall line, so the room it serves never closes and
    polygonize merges it with the corridor — 78 of ENNAKHIL's labels shared a
    face for this reason. Where a door symbol exists its block geometry closes
    the gap, but a cased opening or an arch has no symbol at all, and nothing in
    the drawing can be snapped to bridge it.

    What CAN be used is that a doorway interrupts one straight wall. So: take
    every end that no other segment shares, and join two of them when they are a
    door's width apart AND the line between them continues both walls. The
    collinearity test at both ends is the safety: without it this would happily
    join opposite sides of a room and invent a wall that was never there.
    """
    degree: dict[tuple, list] = defaultdict(list)
    for line in lines:
        for point, direction in _ends(line):
            degree[point].append(direction)

    loose = [(p, d[0]) for p, d in degree.items() if len(d) == 1]
    grid: dict[tuple[int, int], list] = defaultdict(list)
    for point, direction in loose:
        grid[(int(point[0] // cell), int(point[1] // cell))].append((point, direction))

    def neighbours(point):
        cx, cy = int(point[0] // cell), int(point[1] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield from grid.get((cx + dx, cy + dy), ())

    # STITCHING comes first, and it is the one that matters. Measured on
    # ENNAKHIL: the nearest other loose end is 4 cm away at the median and
    # within 15 cm for three quarters of them. That is not a doorway, it is the
    # drawing being drawn by hand — ends that an architect reads as one corner
    # and `polygonize` reads as two, so the face never closes. Snapping at 2 cm
    # leaves them apart and snapping coarsely enough to merge them would
    # collapse a 10 cm cloison onto itself, so they are stitched instead.
    # No collinearity test: these ends are not continuing a wall, they ARE the
    # same point drawn twice.
    stitches, welded = [], set()
    for point, _ in loose:
        if point in welded:
            continue
        best, best_gap = None, None
        for other, _ in neighbours(point):
            if other == point or other in welded:
                continue
            gap = math.dist(point, other)
            if gap <= STITCH and (best_gap is None or gap < best_gap):
                best, best_gap = other, gap
        if best is not None:
            stitches.append(LineString([point, best]))
            welded.add(point)
            welded.add(best)

    limit = math.cos(math.radians(COLLINEAR))
    bridges, used = [], set(welded)
    for point, direction in loose:
        if point in used:
            continue
        best, best_gap = None, None
        for other, other_dir in neighbours(point):
            if other == point or other in used:
                continue
            vx, vy = other[0] - point[0], other[1] - point[1]
            gap = (vx * vx + vy * vy) ** 0.5
            if not OPENING[0] <= gap <= OPENING[1]:
                continue
            ux, uy = vx / gap, vy / gap
            # Leaving this end along its outward direction, and arriving at the
            # other against its outward direction.
            if ux * direction[0] + uy * direction[1] < limit:
                continue
            if -ux * other_dir[0] - uy * other_dir[1] < limit:
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = other, gap
        if best is not None:
            bridges.append(LineString([point, best]))
            used.add(point)
            used.add(best)
    return stitches, bridges


def labels_in(msp, keep) -> list[tuple[str, str, Point]]:
    """Room labels as (text, kind, point). Unclassifiable text is dropped."""
    found = []
    for entity in msp:
        kind = entity.dxftype()
        if kind not in ("TEXT", "MTEXT") or not _keep(entity, keep):
            continue
        try:
            raw = entity.dxf.text if kind == "TEXT" else entity.plain_text()
            p = entity.dxf.get("insert")
        except Exception:
            continue
        text = " ".join(raw.split())
        if not text or len(text) > 28:
            continue
        room = classify(text)
        if room:
            found.append((text, room, Point(p[0], p[1])))
    return found


def resolve(faces, labels):
    """Which face each label falls inside.

    Returns the assignments, the labels that landed in no face, and the faces
    that caught more than one. Both failures matter and neither is an error to
    swallow: a label in no face means its room never closed, and two labels in
    one face means a doorway leaked and merged them.
    """
    assigned: dict[int, list] = defaultdict(list)
    homeless = []
    for text, kind, point in labels:
        for i, face in enumerate(faces):
            if face.contains(point):
                assigned[i].append((text, kind))
                break
        else:
            homeless.append((text, kind))
    merged = {i: v for i, v in assigned.items() if len(v) > 1}
    return assigned, homeless, merged


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path")
    parser.add_argument("--walls", default=r"mur|wall|menuiserie|cloison",
                        help="layers forming the barrier set — inspect_dxf's "
                             "CONVENTION pass names them")
    parser.add_argument("--snap", type=float, default=0.02,
                        help="metres; coordinates are rounded onto this grid "
                             "before noding, to close near-misses")
    parser.add_argument("--no-bridge", action="store_true",
                        help="do not infer openings — for comparison")
    parser.add_argument("--plans-only", action="store_true")
    parser.add_argument("--gap", type=float, default=15.0)
    args = parser.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"no such file: {args.path}")

    print("Reading —")
    doc, _ = _open(args.path)
    msp = doc.modelspace()
    to_m = UNITS.get(doc.header.get("$INSUNITS", 0), ("?", None))[1]
    if to_m is None:
        sys.exit("no unit declared in the drawing; areas would be meaningless")
    if abs(to_m - 1.0) > 1e-9:
        sys.exit(f"drawing is not in metres (scale {to_m}); not handled yet")

    keep = None
    if args.plans_only:
        sheets = find_sheets(msp, to_m, args.gap)
        keep = [(x0, x1, y0, y1) for kind, x0, x1, y0, y1, _, _ in sheets
                if kind == "plan"]
        if not keep:
            sys.exit("--plans-only: no region classified as plan")
        print(f"  {len(keep)} plan region(s)")

    _rule("BARRIERS")
    lines, used = barriers(msp, keep, re.compile(args.walls, re.I), args.snap)
    print(f"  edges         {len(lines)} on layers matching /{args.walls}/")
    if not lines:
        sys.exit("\n  No barrier geometry. Run inspect_dxf and pass its wall layers.")
    for layer, n in used.most_common(6):
        print(f"    {layer[:40]:<40}{n:>7}")

    _rule("OPENINGS")
    stitches, bridges = ([], []) if args.no_bridge else bridge_openings(lines)
    print(f"  stitched      {len(stitches)} ends under {STITCH} m apart"
          f"  <- the same corner drawn twice")
    print(f"  bridged       {len(bridges)} gaps {OPENING[0]}–{OPENING[1]} m wide,"
          f" collinear within {COLLINEAR:.0f} deg  <- doorways")

    _rule("FACES")
    print("  noding and polygonizing —")
    faces = [f for f in polygonize(unary_union(lines + stitches + bridges))
             if MIN_AREA <= f.area <= MAX_AREA]
    print(f"  faces         {len(faces)} between {MIN_AREA} and {MAX_AREA} m2")
    if not faces:
        sys.exit("\n  Nothing closed. Try a larger --snap, or add the door layer\n"
                 "  to --walls so openings are bridged.")

    labels = labels_in(msp, keep)
    assigned, homeless, merged = resolve(faces, labels)
    resolved = sum(len(v) for v in assigned.values())
    total = len(labels)

    _rule("ROOMS")
    print(f"  labels        {total} classified")
    print(f"  resolved      {resolved}  ({100.0 * resolved / total:.0f}%)"
          if total else "  resolved      0")
    print(f"  in no face    {len(homeless)}  <- their room never closed")
    print(f"  shared a face {len(merged)}  <- a doorway leaked and merged rooms")

    # A face has to be room-SHAPED as well as room-sized. Polygonize returns
    # the cavity between a wall's two lines as a face too, and a label sitting
    # near a wall can land in one: the first run reported an SDB at 8.85:1,
    # which is a wall cavity, not a bathroom. Two cheap guards, both on
    # dimensions already computed.
    rooms, slivers, ragged = [], 0, 0
    for i, occupants in assigned.items():
        if len(occupants) != 1:
            continue
        text, kind = occupants[0]
        face = faces[i]
        minx, miny, maxx, maxy = face.bounds
        w, h = max(maxx - minx, maxy - miny), min(maxx - minx, maxy - miny)
        if h < MIN_SIDE:
            slivers += 1
            continue
        # Area well under its bounding box means an L, a ring round a core, or
        # a leak that wandered. Its bbox is not its proportion, so measuring an
        # aspect ratio from it would be quietly wrong.
        if face.area < FILL * (maxx - minx) * (maxy - miny):
            ragged += 1
            continue
        rooms.append({"nom": text, "kind": kind, "area": face.area,
                      "w": w, "h": h})

    print(f"  too thin      {slivers}  <- wall cavities, under {MIN_SIDE} m across")
    print(f"  not rectangular {ragged}  <- fills under {FILL:.0%} of its bounding box")
    print(f"  MEASURED      {len(rooms)}")

    if not rooms:
        sys.exit("\n  No room resolved uniquely — nothing to measure.")

    _rule("ASPECT RATIO BY TYPE  (against the engine's max_ratio = 3.0)")
    print(f"  {'type':<22}{'n':>4}{'median':>9}{'p90':>8}{'max':>8}{'median m2':>11}")
    by_kind = defaultdict(list)
    for r in rooms:
        by_kind[r["kind"]].append(r)
    for kind in sorted(by_kind, key=lambda k: -len(by_kind[k])):
        group = by_kind[kind]
        ratios = sorted(r["w"] / r["h"] for r in group if r["h"] > 0)
        areas = sorted(r["area"] for r in group)
        if not ratios:
            continue
        p90 = ratios[min(len(ratios) - 1, int(0.9 * len(ratios)))]
        print(f"  {kind:<22}{len(group):>4}{statistics.median(ratios):>9.2f}"
              f"{p90:>8.2f}{ratios[-1]:>8.2f}{statistics.median(areas):>11.1f}")

    over = [r for r in rooms if r["h"] > 0 and r["w"] / r["h"] > 3.0]
    print(f"\n  over 3.0:1    {len(over)} of {len(rooms)} "
          f"({100.0 * len(over) / len(rooms):.0f}%)  <- the engine refuses these")
    for r in sorted(over, key=lambda r: -(r["w"] / r["h"]))[:6]:
        print(f"    {r['nom'][:22]:<22}{r['w'] / r['h']:>6.2f}:1"
              f"  {r['w']:.2f} x {r['h']:.2f} m")

    _rule("CIRCULATION")
    circ = [r for r in rooms if r["kind"] in CIRCULATION]
    served = [r for r in rooms if r["kind"] not in CIRCULATION | OUTDOOR]
    net = sum(r["area"] for r in circ + served)
    if net and circ:
        print(f"  coefficient   {100.0 * sum(r['area'] for r in circ) / net:.1f} %"
              f"  of {net:.1f} m2 net")
        print(f"  run per room  {sum(r['w'] for r in circ) / max(1, len(served)):.2f}"
              f" m over {len(served)} rooms served")
    else:
        print("  no circulation room resolved — cannot measure")


if __name__ == "__main__":
    main()
