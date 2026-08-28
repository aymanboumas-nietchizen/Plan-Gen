"""What is actually inside an agency DXF, before anyone writes an extractor.

    python tools/inspect_dxf.py "references/raw/NOUR II - BAT 1 - PC 30-10-2024.dxf"
    python tools/inspect_dxf.py <file> --layer MUR          # drill into one layer
    python tools/inspect_dxf.py <file> --labels 60          # more label samples

Reconnaissance, not extraction. A permis-de-construire drawing of a whole
building carries every level, the structure, the furniture, the hatching and the
title block in one file, so the first problem is not geometry — it is working out
which layers hold the walls and whether rooms exist as closed polylines at all.
Writing `measure_reference.py` before knowing that would be guesswork.

Four questions this answers, in the order they matter:

  1. WHAT UNIT is the file in? Architectural DXF is very often millimetres, and
     an extractor that assumes metres is out by 1000x silently.
  2. ARE THERE ROOMS, or only wall lines? A closed polyline per room means the
     areas can be read directly. Only lines means the faces have to be recovered,
     which is a different and much larger job.
  3. WHICH LAYERS matter? Name and entity count per layer is the whole map.
  4. AXIS OR FACE? The dimensioning convention — see `references/README.md`. A
     3.00 m cote against a 15 cm cloison means 3.00 net or 2.85 net, a 5% error
     on the one quantity this project is exact about. This script cannot decide
     it, but it prints the evidence a human needs: the dimension measurements it
     found, and the parallel-line spacings that are candidate wall thicknesses.

Everything is read-only. The file is never modified.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter, defaultdict

try:
    import ezdxf
    from ezdxf import recover
except ImportError:  # pragma: no cover - ezdxf is a hard dependency of the project
    sys.exit("ezdxf is required: pip install -e .")


#: $INSUNITS. Only the ones an architectural drawing plausibly uses.
UNITS = {
    0: ("unitless", None),
    1: ("inches", 0.0254),
    2: ("feet", 0.3048),
    4: ("millimetres", 0.001),
    5: ("centimetres", 0.01),
    6: ("metres", 1.0),
}

#: Words that mark a text entity as a room label on a Moroccan/French plan.
ROOM_WORDS = (
    "sejour", "séjour", "salon", "chambre", "ch.", "cuisine", "sdb", "s.d.b",
    "salle de bain", "bain", "douche", "wc", "w.c", "couloir", "degagement",
    "dégagement", "hall", "entree", "entrée", "cellier", "buanderie", "terrasse",
    "balcon", "loggia", "placard", "rangement", "bureau", "sechoir", "séchoir",
    "escalier", "ascenseur", "palier", "gaine", "local", "patio", "appartement",
    "appt", "studio", "f2", "f3", "f4", "duplex",
)


def _shoelace(points: list[tuple[float, float]]) -> float:
    """Signed area of a closed ring, in drawing units squared."""
    total = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _open(path: str):
    """Read the file, falling back to ezdxf's recovery reader for damaged ones."""
    try:
        return ezdxf.readfile(path), False
    except ezdxf.DXFStructureError:
        doc, auditor = recover.readfile(path)
        return doc, bool(auditor.errors)


def _rule(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def report_file(path: str, doc, recovered: bool) -> float | None:
    """Header, units, extents. Returns metres per drawing unit, or None."""
    _rule("FILE")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  path          {path}")
    print(f"  size          {size_mb:.1f} MB")
    print(f"  dxf version   {doc.dxfversion} ({doc.acad_release})")
    if recovered:
        print("  NOTE          the file needed ezdxf's recovery reader — it has errors")

    code = doc.header.get("$INSUNITS", 0)
    name, to_m = UNITS.get(code, (f"code {code}", None))
    print(f"  units         {name}  ($INSUNITS = {code})")
    if to_m is None:
        print("  WARNING       no unit declared. Every area below is in drawing units")
        print("                squared. Settle the scale before trusting any of it.")

    # $EXTMIN/$EXTMAX are +/-1e20 when the drawing has never been regenerated.
    # Subtracting them gives -2e20, which looked like a real extent until it was
    # printed as "-200000000000000000 m".
    try:
        low = doc.header["$EXTMIN"]
        high = doc.header["$EXTMAX"]
        w, h = high[0] - low[0], high[1] - low[1]
        if any(abs(v) > 1e19 for v in (*low[:2], *high[:2])) or w <= 0 or h <= 0:
            print("  extents       header sentinel, never regenerated — unknown")
        elif to_m:
            print(f"  extents       {w * to_m:.1f} x {h * to_m:.1f} m")
        else:
            print(f"  extents       {w:.1f} x {h:.1f} drawing units")
    except (KeyError, TypeError, IndexError):
        print("  extents       not recorded in the header")

    layouts = [name for name in doc.layout_names()]
    print(f"  layouts       {len(layouts)}: {', '.join(layouts[:8])}"
          + (" …" if len(layouts) > 8 else ""))
    return to_m


def report_layers(msp, limit: int) -> None:
    """The map. Which layer holds what, by entity type."""
    _rule("LAYERS  (modelspace, by entity count)")
    per_layer: dict[str, Counter] = defaultdict(Counter)
    for entity in msp:
        try:
            per_layer[entity.dxf.layer][entity.dxftype()] += 1
        except AttributeError:
            continue

    if not per_layer:
        print("  modelspace is empty — the drawing may live entirely in paperspace")
        return

    ordered = sorted(per_layer.items(), key=lambda kv: -sum(kv[1].values()))
    print(f"  {'layer':<34}{'total':>8}   commonest types")
    for layer, counts in ordered[:limit]:
        total = sum(counts.values())
        types = ", ".join(f"{t} {n}" for t, n in counts.most_common(3))
        print(f"  {layer[:34]:<34}{total:>8}   {types}")
    if len(ordered) > limit:
        rest = sum(sum(c.values()) for _, c in ordered[limit:])
        print(f"  … {len(ordered) - limit} more layers, {rest} entities "
              f"(raise --layers to see them)")


def report_rooms(msp, to_m: float | None, layer: str | None) -> None:
    """Closed polylines are room candidates. Their absence is the finding."""
    _rule("CLOSED POLYLINES  (room candidates)")
    areas: list[tuple[float, str]] = []
    open_count = 0

    for entity in msp:
        kind = entity.dxftype()
        if kind not in ("LWPOLYLINE", "POLYLINE"):
            continue
        if layer and entity.dxf.layer != layer:
            continue
        try:
            closed = entity.closed if kind == "LWPOLYLINE" else entity.is_closed
        except AttributeError:
            continue
        if not closed:
            open_count += 1
            continue
        try:
            if kind == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in entity.get_points("xy")]
            else:
                pts = [(v.dxf.location[0], v.dxf.location[1]) for v in entity.vertices]
        except (AttributeError, IndexError):
            continue
        if len(pts) >= 3:
            areas.append((_shoelace(pts), entity.dxf.layer))

    print(f"  closed        {len(areas)}")
    print(f"  open          {open_count}")
    if not areas:
        print("\n  NO CLOSED POLYLINES. Rooms are not drawn as faces in this file, so")
        print("  areas cannot be read directly — the faces have to be recovered from")
        print("  the wall lines. That is a materially bigger job; say so before")
        print("  anyone estimates the corpus track.")
        return

    scale = (to_m or 1.0) ** 2
    unit = "m2" if to_m else "du2"
    sized = sorted((a * scale, layer) for a, layer in areas)

    # Rooms in a residential plan live roughly 1-60 m2. Anything far outside is
    # a title block, a hatch boundary or the parcel itself.
    plausible = [a for a, _ in sized if 1.0 <= a <= 60.0] if to_m else []
    print(f"  smallest      {sized[0][0]:.2f} {unit}  (layer {sized[0][1]})")
    print(f"  median        {sized[len(sized) // 2][0]:.2f} {unit}")
    print(f"  largest       {sized[-1][0]:.2f} {unit}  (layer {sized[-1][1]})")
    if to_m:
        print(f"  1-60 m2       {len(plausible)}  <- the room-shaped ones")

    by_layer = Counter(layer for _, layer in sized)
    print("\n  closed polylines by layer:")
    for name, count in by_layer.most_common(8):
        print(f"    {name[:38]:<38}{count:>6}")


def report_blocks(doc, msp, limit: int) -> None:
    """A plate often repeats one apartment as a block. That is free structure."""
    _rule("BLOCKS  (a repeated apartment is usually one)")
    inserts = Counter()
    for entity in msp:
        if entity.dxftype() == "INSERT":
            try:
                inserts[entity.dxf.name] += 1
            except AttributeError:
                continue
    if not inserts:
        print("  no block references in modelspace")
        return
    print(f"  {len(inserts)} distinct blocks, {sum(inserts.values())} placements")
    print(f"\n  {'block':<40}{'placed':>8}")
    for name, count in inserts.most_common(limit):
        print(f"  {name[:40]:<40}{count:>8}")


def report_labels(msp, limit: int) -> None:
    """Text that names a room is what turns a rectangle into a CUISINE."""
    _rule("TEXT  (room labels)")
    hits: list[tuple[str, str]] = []
    total = 0
    for entity in msp:
        kind = entity.dxftype()
        if kind not in ("TEXT", "MTEXT"):
            continue
        total += 1
        try:
            raw = entity.dxf.text if kind == "TEXT" else entity.text
        except AttributeError:
            continue
        text = " ".join(raw.split())
        if not text:
            continue
        if any(word in text.lower() for word in ROOM_WORDS):
            hits.append((text[:44], entity.dxf.layer))

    print(f"  text entities {total}")
    print(f"  room-like     {len(hits)}")
    if not hits:
        print("\n  No text matched the French room vocabulary. Either the labels are")
        print("  images, or they are on a layout this pass did not read, or the")
        print("  drawing names rooms some other way. Rooms without names cannot be")
        print("  typed, and an untyped room cannot be measured by RoomType.")
        return
    print()
    for text, layer in hits[:limit]:
        print(f"    {text:<46}  [{layer[:22]}]")
    if len(hits) > limit:
        print(f"    … {len(hits) - limit} more (raise --labels)")


def report_dimensions(msp, to_m: float | None, limit: int) -> None:
    """The evidence for axis-versus-face. This script does not decide it."""
    _rule("DIMENSIONS  (evidence for the axis / face question)")
    measurements: list[float] = []
    styles = Counter()
    for entity in msp:
        if entity.dxftype() != "DIMENSION":
            continue
        try:
            styles[entity.dxf.dimstyle] += 1
        except AttributeError:
            pass
        try:
            value = entity.get_measurement()
        except Exception:  # ezdxf raises several different things here
            continue
        if isinstance(value, (int, float)) and value > 0:
            measurements.append(float(value))

    print(f"  dimensions    {len(measurements)} with a readable measurement")
    if styles:
        top = ", ".join(f"{name} ({n})" for name, n in styles.most_common(4))
        print(f"  styles        {top}")
    if not measurements:
        print("\n  No readable dimensions. The convention will have to come from the")
        print("  drawing by eye, or from whoever drew it. Record it either way —")
        print("  references/README.md requires it on every fixture.")
        return

    scale = to_m or 1.0
    unit = "m" if to_m else "du"
    values = sorted(v * scale for v in measurements)
    print(f"  range         {values[0]:.3f} … {values[-1]:.3f} {unit}")
    print(f"  median        {values[len(values) // 2]:.3f} {unit}")

    # A cote to the wall FACE tends to land on round numbers (3.00, 3.20); one
    # to the AXIS carries the half-thicknesses and rarely does. Weak evidence on
    # its own, decisive alongside the drawing.
    if to_m:
        room_sized = [v for v in values if 0.5 <= v <= 12.0]
        if room_sized:
            round_5cm = sum(1 for v in room_sized if abs(v * 20 - round(v * 20)) < 1e-6)
            share = 100.0 * round_5cm / len(room_sized)
            print(f"  on a 5 cm grid {round_5cm}/{len(room_sized)}  ({share:.0f}%)")
            print("                 a high share leans FACE, a low share leans AXIS —")
            print("                 weak on its own, decisive with the drawing open")


def main() -> None:
    # A Moroccan drawing is full of accents and this prints to a Windows console
    # that defaults to cp1252, which turned "Unités" into "Unit?s" on the first
    # run. Replace rather than raise: a mangled glyph is a nuisance, a crash
    # halfway through the report loses the whole pass over a 30 MB file.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="the .dxf to inspect (never modified)")
    parser.add_argument("--layer", help="restrict the polyline pass to one layer")
    parser.add_argument("--layers", type=int, default=25, help="layers to list")
    parser.add_argument("--labels", type=int, default=25, help="label samples")
    parser.add_argument("--blocks", type=int, default=15, help="blocks to list")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"no such file: {args.path}")

    print("Reading — a large DXF takes a moment and a good deal of memory.")
    doc, recovered = _open(args.path)
    msp = doc.modelspace()

    to_m = report_file(args.path, doc, recovered)
    report_layers(msp, args.layers)
    report_rooms(msp, to_m, args.layer)
    report_blocks(doc, msp, args.blocks)
    report_labels(msp, args.labels)
    report_dimensions(msp, to_m, args.labels)

    _rule("WHAT TO DO WITH THIS")
    print("  Paste this output back, or hand it to planfgen-regs in a session on")
    print("  the machine holding the file. The three answers that decide the")
    print("  corpus track: the unit, whether rooms exist as closed polylines, and")
    print("  which layers carry the walls. Everything else follows from those.")


if __name__ == "__main__":
    main()
