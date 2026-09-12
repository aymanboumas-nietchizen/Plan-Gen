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
     on the one quantity this project is exact about. This is DECIDED here, by
     geometry: a `DIMENSION` stores the model-space points its extension lines
     spring from, so the test is what sits at the point where a cote terminates.
     On a drawn line means face to face; half a wall from any line means axis to
     axis, because an axis is imaginary and nothing is drawn there.

     An earlier version scored how many cotes landed on a round 10 cm instead.
     That was a proxy and it was too weak: it called ENNAKHIL "a lean" at 34%
     where the geometry says 93% on the line, and on NOUR it gave no signal.

     The comparison takes LINE and LWPOLYLINE on every layer, and reports which
     layers the cotes land on rather than asking for them. Two reasons, both
     learned the hard way: a --walls regex of /mur/ matches NOUR's
     `_Murs - Exterieurs`, which is the ELEVATION's walls; and a wall is not
     always two lines — NOUR draws its as polygons, so a LINE-only pass found
     no wall in its plans at all.

Everything is read-only. The file is never modified.
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import re
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


#: Where ezdxf's ODA addon looks by default. Printed in the error below so the
#: fix is a download rather than a search.
ODA_HINT = r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"

#: Where it actually lands. The installer creates a VERSIONED directory —
#: `ODA\ODAFileConverter 26.2.0\` — while ezdxf's default option is the
#: unversioned path above, so a perfectly good install is still not found.
ODA_GLOBS = (
    r"C:\Program Files\ODA\*\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\*\ODAFileConverter.exe",
)


def find_oda() -> str | None:
    """Point ezdxf at the installed converter, whatever version it is.

    Returns the path it will use, or None if the converter is not installed.
    """
    configured = ezdxf.options.get("odafc-addon", "win_exec_path").strip('"')
    if configured and os.path.exists(configured):
        return configured
    for pattern in ODA_GLOBS:
        found = sorted(glob.glob(pattern))
        if found:
            newest = found[-1]
            ezdxf.options.set("odafc-addon", "win_exec_path", newest)
            return newest
    return None


def _open(path: str):
    """Read the file, falling back to ezdxf's recovery reader for damaged ones.

    DWG is not a format ezdxf reads. It is a closed binary format and there is no
    pure-Python reader worth depending on, so the addon shells out to the free
    ODA File Converter. `.bak` is AutoCAD's backup of a DWG and is the same
    format, which is why it is routed the same way.
    """
    if path.lower().endswith((".dwg", ".bak")):
        from ezdxf.addons import odafc

        located = find_oda()
        if located:
            print(f"  converter     {located}")
        try:
            return odafc.readfile(path), False
        except Exception as exc:
            sys.exit(
                f"cannot read {os.path.basename(path)}: {exc}\n\n"
                "DWG needs the free ODA File Converter. Looked in:\n"
                f"  {ODA_HINT}\n"
                "  " + ODA_GLOBS[0] + "   (versioned install)\n"
                "  " + ODA_GLOBS[1] + "\n\n"
                "Get it from https://www.opendesign.com/guestfiles/oda_file_converter\n"
                "and this works unchanged — the version in the folder name does not\n"
                "matter, it is found by pattern.\n\n"
                "Or open the drawing in Archicad and save a DXF. Better still, export\n"
                "Archicad ZONES: they carry room polygons with their names and areas,\n"
                "which is the one thing a DWG of wall lines does not have."
            )

    try:
        return ezdxf.readfile(path), False
    except ezdxf.DXFStructureError:
        doc, auditor = recover.readfile(path)
        return doc, bool(auditor.errors)


def _rule(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _keep(entity, ranges) -> bool:
    """True when the entity lies in one of the accepted x ranges.

    `ranges` of None accepts everything, so the default behaviour of every pass
    is unchanged and --plans-only is purely additive.
    """
    if EXCLUDE_RE is not None:
        try:
            if EXCLUDE_RE.search(entity.dxf.layer or ""):
                return False
        except AttributeError:
            pass
    if ranges is None:
        return True
    p = _point_of(entity)
    if p is None:
        return False
    return any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1
               for x0, x1, y0, y1 in ranges)


# --- sheets -----------------------------------------------------------------
#
# A *planche permis* is one sheet carrying plans, elevations and sections side
# by side in the same modelspace. Measuring rooms off it means reading only the
# plan regions: an elevation's "rooms" are storey bands and a section's are
# nothing at all. ENNAKHIL reports extents of 104856 x 955 m for exactly this
# reason — the drawings are laid out across the sheet, plus stray geometry.

#: Layers that are never part of a plan. Exact where region clustering is only
#: heuristic: ENNAKHIL draws its elevations on FACADE and its sections on COUPE,
#: so excluding them is certain, while a spatial gap still merges a plan with
#: the elevation drawn above it. Regions remain the fallback for files whose
#: layers do not say.
NOT_PLAN_LAYERS = re.compile(
    r"fa[cç]ade|coupe|section|cartouche|rep[ée]rage|elevation", re.I
)

#: Set from --exclude-layers. None disables layer exclusion entirely.
EXCLUDE_RE: re.Pattern | None = None


#: A layer whose text belongs to the sheet, not to any drawing on it.
CARTOUCHE = re.compile(r"cartouche|titre|title", re.I)

#: A title that classifies the region it sits in.
#: Every pattern must admit the PLURAL. The cartouche reads "PLANS FACADES
#: COUPES", and with `\bplan\b` and `\bcoupe\b` only the facade pattern matched,
#: so the legend looked like a single-kind title and classified the whole
#: drawing as elevation.
SHEET_KINDS = (
    ("elevation", re.compile(r"\bfa[cç]ades?\b|\belevations?\b|\bpignons?\b", re.I)),
    # "coupe-feu" is fire RESISTANCE, not a section: NOUR II's fire-door
    # schedule is titled "PORTE COUPE FEU" and was classified as a section.
    ("section", re.compile(r"\bcoupes?\b(?!\s*-?\s*feu)|\bsections?\b", re.I)),
    ("detail", re.compile(r"\bd[ée]tails?\b|\bcartouches?\b|\brep[ée]rages?\b", re.I)),
    ("plan", re.compile(r"\bplans?\b|\bniv\s*[:.]|\br\.?d\.?c\b|\b[ée]tages?\b"
                        r"|\bmezzanines?\b|\bsous.?sols?\b|\bterrasses?\b", re.I)),
)


def _point_of(entity) -> tuple[float, float] | None:
    """One representative point per entity, without computing a bounding box.

    `ezdxf.bbox` is correct and far too slow for 300k entities; placing each
    entity by a single vertex is enough to cluster sheets, which are metres
    apart.
    """
    d = entity.dxf
    # `defpoint` and `text_midpoint` are here for DIMENSION, which carries
    # neither `insert` nor `start`. Without them every dimension returned None,
    # `_keep` rejected it, and --plans-only reported "0 dimensions" on a file
    # holding 8274 of them — a silent loss that looked like a finding.
    for attr in ("insert", "start", "center", "location",
                 "defpoint", "text_midpoint"):
        if d.hasattr(attr):
            try:
                p = d.get(attr)
                return (float(p[0]), float(p[1]))
            except (TypeError, IndexError, ValueError):
                return None
    if entity.dxftype() == "LWPOLYLINE":
        try:
            pts = entity.get_points("xy")
            return (float(pts[0][0]), float(pts[0][1])) if pts else None
        except (AttributeError, IndexError, ValueError):
            return None
    return None


def _is_legend(title: str) -> bool:
    """True for a title block listing the sheet's contents rather than naming one
    drawing.

    ENNAKHIL's cartouche reads "■ PLANS ■ FACADES ■ COUPES". It names every kind
    at once and sits inside every region, so taken as a title it classified the
    whole drawing as elevation. A string matching more than one kind is a legend,
    not a title, and carries no information about the region it happens to land in.
    """
    return sum(1 for _, pattern in SHEET_KINDS if pattern.search(title)) > 1


#: A room's clear side, in metres. Below this is a door leaf or a wall offset;
#: above it is a whole-building run. Neither carries the dimensioning convention.
ROOM_SCALE = (2.0, 8.0)

#: Distinct room labels that make a region a plan whatever its title says.
ROOM_EVIDENCE = 3


def _classify(titles: list[str]) -> str:
    """What kind of drawing a region is, from the text inside it.

    ROOM LABELS DECIDE FIRST. ENNAKHIL's plans carry no sheet title at all — the
    only titled regions are `FACADE PRINCIPALE`, `FACADE ARRIERE` and
    `COUPE A-A` — so classifying on titles alone found no plan anywhere and
    `--plans-only` had nothing to select. A region holding `Chambre 1`,
    `Cuisine` and `SDB` is a plan; no elevation has three room names scattered
    across it. That is the stronger signal and it costs nothing, because the
    labels are already collected.

    Failing that, fall back to the sheet title, where elevation and section beat
    plan: a region titled "COUPE A-A" may also carry the word "plan" in a note,
    and reading a section as a plan is the error that silently corrupts a
    measurement.
    """
    usable = [t for t in titles if not _is_legend(t)]
    rooms = {
        t.lower() for t in usable
        if any(word in t.lower() for word in ROOM_WORDS)
    }
    if len(rooms) >= ROOM_EVIDENCE:
        return "plan"
    for kind, pattern in SHEET_KINDS:
        if any(pattern.search(t) for t in usable):
            return kind
    return "unknown"


def find_sheets(msp, to_m: float | None, gap: float = 15.0):
    """Split modelspace into regions separated by empty space, and name them.

    Returns a list of (kind, x0, x1, count, titles). `gap` is in metres: sheets
    on a planche sit well apart, while everything within one drawing is
    continuous.
    """
    points, titles = [], []
    for entity in msp:
        p = _point_of(entity)
        if p is None:
            continue
        points.append(p)
        kind = entity.dxftype()
        if kind in ("TEXT", "MTEXT"):
            # Text on the title block describes the sheet, not the drawing it
            # sits over. ENNAKHIL keeps it on a CARTOUCHE layer, which is the
            # cheapest signal available.
            if CARTOUCHE.search(entity.dxf.layer or ""):
                continue
            try:
                text = entity.plain_text() if kind == "MTEXT" else entity.dxf.text
            except Exception:
                continue
            text = " ".join(text.split())
            if text and len(text) <= 40:
                titles.append((p[0], p[1], text))
    if not points:
        return []

    scale = to_m or 1.0

    def split(values: list[float]) -> list[list[float]]:
        """One dimension, broken wherever `gap` metres of nothing separate two
        values."""
        values = sorted(values)
        groups: list[list[float]] = [[values[0]]]
        for v in values[1:]:
            if (v - groups[-1][-1]) * scale > gap:
                groups.append([v])
            else:
                groups[-1].append(v)
        return groups

    # A planche lays its drawings out in a GRID, so splitting on x alone merges
    # a plan with the elevation above it and the elevation's title wins. Split
    # on x, then split each column on y.
    out = []
    by_x: dict[int, list[tuple[float, float]]] = defaultdict(list)
    columns = split([x for x, _ in points])
    edges = [(c[0], c[-1]) for c in columns]
    for x, y in points:
        for i, (lo, hi) in enumerate(edges):
            if lo <= x <= hi:
                by_x[i].append((x, y))
                break

    for i, column in by_x.items():
        for band in split([y for _, y in column]):
            y0, y1 = band[0], band[-1]
            x0, x1 = edges[i]
            members = [(x, y) for x, y in column if y0 <= y <= y1]
            inside = [t for tx, ty, t in titles
                      if x0 <= tx <= x1 and y0 <= ty <= y1]
            out.append((_classify(inside), x0, x1, y0, y1, len(members), inside))
    return out


def report_sheets(sheets, to_m: float | None, limit: int = 14) -> None:
    _rule("SHEET REGIONS  (a planche permis holds plans, elevations and sections)")
    if not sheets:
        print("  could not place entities — no representative points found")
        return
    scale = to_m or 1.0
    unit = "m" if to_m else "du"
    kinds = Counter(k for k, *_ in sheets)
    print("  " + "  ".join(f"{k} {n}" for k, n in kinds.most_common()))
    print(f"\n  {'kind':<10}{'entities':>9}   {'centre (' + unit + ')':>20}   title")
    for kind, x0, x1, y0, y1, count, titles in sorted(
        sheets, key=lambda s: -s[5]
    )[:limit]:
        centre = f"{(x0 + x1) / 2 * scale:,.0f}, {(y0 + y1) / 2 * scale:,.0f}"
        title = next(
            (t for t in titles if not _is_legend(t) and _classify([t]) == kind),
            titles[0] if titles else "-",
        )
        print(f"  {kind:<10}{count:>9}   {centre:>20}   {title[:34]}")
    if len(sheets) > limit:
        print(f"  … {len(sheets) - limit} more regions")

    plans = [s for s in sheets if s[0] == "plan"]
    other = [s for s in sheets if s[0] in ("elevation", "section", "detail")]
    if other:
        print(f"\n  {sum(s[5] for s in other)} entities are in elevation/section/detail")
        print("  regions and must not be measured as plan. Use --plans-only.")
    if not plans:
        print("\n  NO REGION CLASSIFIED AS PLAN. Either the titles use other words,")
        print("  or this file is elevations and sections only.")


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


def report_rooms(msp, to_m: float | None, layer: str | None, keep=None) -> None:
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
        if not _keep(entity, keep):
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


def report_labels(msp, limit: int, keep=None) -> None:
    """Text that names a room is what turns a rectangle into a CUISINE."""
    _rule("TEXT  (room labels)")
    hits: list[tuple[str, str]] = []
    total = 0
    for entity in msp:
        kind = entity.dxftype()
        if kind not in ("TEXT", "MTEXT"):
            continue
        if not _keep(entity, keep):
            continue
        total += 1
        try:
            # MTEXT.text is the RAW string, carrying inline formatting —
            # "\A1;{\pqc;\fTimes New Roman|b1|i0|c0|p22;Cuisine". Printed, it is
            # unreadable; matched against room words, the codes are noise.
            # plain_text() is what the drawing actually shows.
            raw = entity.dxf.text if kind == "TEXT" else entity.plain_text()
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


def report_dimensions(msp, to_m: float | None, limit: int, keep=None,
                      band: tuple[float, float] = ROOM_SCALE) -> None:
    """The evidence for axis-versus-face. This script does not decide it."""
    _rule("DIMENSIONS  (evidence for the axis / face question)")
    measurements: list[float] = []
    styles = Counter()
    for entity in msp:
        if entity.dxftype() != "DIMENSION":
            continue
        if not _keep(entity, keep):
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


#: Distance under which a cote endpoint counts as sitting ON a drawn line.
ON_LINE = 0.005

#: Half the thickness of an ordinary wall. A cote landing here terminates where
#: nothing is drawn, which is what an axis is.
HALF_WALL = (0.06, 0.13)

#: Metres per spatial-hash cell. Nothing is compared across a cell boundary,
#: which both fixes the contamination described below and makes the pass fast.
CELL = 50.0


def report_convention(msp, to_m, keep, band) -> None:
    """Whether cotes measure to the wall FACE or to its AXIS — by geometry.

    A `DIMENSION` stores `defpoint2` and `defpoint3`, the model-space points its
    extension lines spring from. So the question needs no guessing from whether
    the values look round: ask what is AT the point where the cote terminates.
    On a drawn line, and it measures face to face. Half a wall away from any
    line, and it measures axis to axis — an axis is imaginary, so nothing is
    drawn there.

    This replaced a test that scored how many cotes landed on a 10 cm grid.
    That was a proxy: it called ENNAKHIL "a lean" at 34% where this says 76% on
    the line, and on NOUR it gave no signal at all.

    Comparison is bucketed by a 50 m spatial cell. Without it, NOUR reported a
    median distance of 96.9 m: its sheet regions sit ~100 m apart and
    `_Murs - Exterieurs` belongs to the elevation, so plan cotes were being
    measured against facade walls.
    """
    _rule("CONVENTION  (axis or face, from the geometry)")
    if not to_m:
        print("  no unit declared — distances would be meaningless")
        return

    grid: dict[tuple[int, int], list] = defaultdict(list)
    points: list[tuple[float, float]] = []
    segments = 0

    for entity in msp:
        kind = entity.dxftype()
        # EVERY line, not the ones on a layer guessed to be walls. An earlier
        # version took a --walls regex, and on NOUR the obvious /mur/ matched
        # `_Murs - Exterieurs` — the ELEVATION's walls — leaving 382 lines for
        # 3712 cote ends. Which layer a cote terminates on is the thing to
        # report, not the thing to require as an argument.
        # LINE *and* LWPOLYLINE. A wall is not always two lines: NOUR draws its
        # as filled polygons and hatch, so its plan regions hold 3716 lines for
        # 3712 cote ends and the cotes appeared to terminate on ESCALIER and
        # SANETAIRE — never on a wall, because no wall was in the comparison.
        if kind in ("LINE", "LWPOLYLINE"):
            if not _keep(entity, keep):
                continue
            layer = entity.dxf.layer or "?"
            if kind == "LINE":
                a, b = entity.dxf.start, entity.dxf.end
                edges = [(a[0], a[1], b[0], b[1])]
            else:
                try:
                    pts = [(p[0], p[1]) for p in entity.get_points("xy")]
                except (AttributeError, IndexError, ValueError):
                    continue
                if entity.closed and len(pts) > 2:
                    pts.append(pts[0])
                edges = [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                         for i in range(len(pts) - 1)]
            for x0, y0, x1, y1 in edges:
                seg = (x0, y0, x1, y1, layer)
                segments += 1
                for cx in range(int(min(x0, x1) // CELL), int(max(x0, x1) // CELL) + 1):
                    for cy in range(int(min(y0, y1) // CELL), int(max(y0, y1) // CELL) + 1):
                        grid[(cx, cy)].append(seg)
        elif kind == "DIMENSION":
            if not _keep(entity, keep):
                continue
            try:
                measured = entity.get_measurement()
            except Exception:
                continue
            if not isinstance(measured, (int, float)):
                continue
            if not band[0] <= measured * to_m <= band[1]:
                continue
            for attr in ("defpoint2", "defpoint3"):
                if entity.dxf.hasattr(attr):
                    p = entity.dxf.get(attr)
                    points.append((p[0], p[1]))

    print(f"  edges         {segments}  from LINE and LWPOLYLINE on every layer kept")
    print(f"  cote ends     {len(points)}  from cotes {band[0]:.1f}–{band[1]:.1f} m")
    if not segments or not points:
        print("\n  Not enough to measure. Check --walls against the layer list above.")
        return

    distances, orphans = [], 0
    for px, py in points:
        cx, cy = int(px // CELL), int(py // CELL)
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(grid.get((cx + dx, cy + dy), ()))
        if not near:
            orphans += 1
            continue
        distances.append(_nearest(px, py, near))

    if orphans:
        print(f"  orphaned      {orphans} with no wall inside {CELL:.0f} m")
    if not distances:
        print("\n  No cote shares a neighbourhood with a wall. Wrong --walls layer,")
        print("  or the cotes belong to a drawing whose walls are elsewhere.")
        return

    touching = Counter(layer for d, layer in distances if d < ON_LINE)
    distances = sorted(d for d, _ in distances)
    on = sum(1 for d in distances if d < ON_LINE)
    axis = sum(1 for d in distances if HALF_WALL[0] <= d <= HALF_WALL[1])
    total = len(distances)
    print(f"\n  median        {distances[total // 2]:.4f} m")
    print(f"  on the line   {on:>6}  ({100.0 * on / total:.0f}%)   <{ON_LINE * 1000:.0f} mm  -> FACE")
    print(f"  half a wall   {axis:>6}  ({100.0 * axis / total:.0f}%)   "
          f"{HALF_WALL[0] * 100:.0f}–{HALF_WALL[1] * 100:.0f} cm  -> AXIS")

    if touching:
        print("\n  cotes terminate on these layers — this is where the walls are:")
        for layer, n in touching.most_common(6):
            print(f"    {layer[:40]:<40}{n:>6}")

    # Share and ratio are different questions and NOUR separates them: 29% on
    # the line against 7% half a wall in is four to one, but two thirds of its
    # cotes land on neither, so the ratio is worth reporting and the share is
    # not yet worth trusting alone.
    ratio = (on / axis) if axis else float("inf") if on else 0.0
    if on > total * 0.4 and on >= 2 * axis:
        print("\n  FACE. Cotes terminate on drawn wall lines.")
    elif axis > total * 0.4 and axis >= 2 * on:
        print("\n  AXIS. Cotes terminate where nothing is drawn, half a wall in.")
    elif on >= 3 * axis and on > total * 0.15:
        print(f"\n  Leans FACE, {ratio:.0f} to 1 — but only {100.0 * on / total:.0f}% land")
        print("  cleanly, so corroborate on the drawing before recording it.")
    elif axis >= 3 * on and axis > total * 0.15:
        print(f"\n  Leans AXIS, {1 / ratio if ratio else 0:.0f} to 1 — but only "
              f"{100.0 * axis / total:.0f}% land")
        print("  cleanly, so corroborate on the drawing before recording it.")
    else:
        print("\n  Not settled — neither reading dominates. Record it by eye.")


def _nearest(px: float, py: float, segments) -> tuple[float, str]:
    """Distance from a point to the closest segment, and that segment's layer.

    The layer is the useful half: it names which layer the cotes are actually
    measuring against, which is what tells you where the walls are.
    """
    best, best_layer = float("inf"), "?"
    for x0, y0, x1, y1, layer in segments:
        dx, dy = x1 - x0, y1 - y0
        length = dx * dx + dy * dy
        t = 0.0 if length == 0 else max(
            0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length)
        )
        d = math.hypot(x0 + t * dx - px, y0 + t * dy - py)
        if d < best:
            best, best_layer = d, layer
    return best, best_layer


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
    parser.add_argument("--plans-only", action="store_true",
                        help="measure only regions classified as plan — a planche "
                             "permis carries elevations and sections too")
    parser.add_argument("--exclude-layers", metavar="REGEX",
                        default=NOT_PLAN_LAYERS.pattern,
                        help="layers never measured as plan; '' to disable")
    parser.add_argument("--band", type=float, nargs=2, default=list(ROOM_SCALE),
                        metavar=("LOW", "HIGH"),
                        help="room-scale cote band in metres, for axis/face")
    parser.add_argument("--gap", type=float, default=15.0,
                        help="metres of empty space that separate two sheet regions")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"no such file: {args.path}")

    print("Reading — a large DXF takes a moment and a good deal of memory.")
    doc, recovered = _open(args.path)
    msp = doc.modelspace()

    to_m = report_file(args.path, doc, recovered)
    report_layers(msp, args.layers)

    sheets = find_sheets(msp, to_m, args.gap)
    report_sheets(sheets, to_m)

    global EXCLUDE_RE
    EXCLUDE_RE = re.compile(args.exclude_layers, re.I) if args.exclude_layers else None
    if EXCLUDE_RE is not None:
        print(f"\n  excluding layers matching /{args.exclude_layers}/")

    keep = None
    if args.plans_only:
        keep = [(x0, x1, y0, y1)
                for kind, x0, x1, y0, y1, _, _ in sheets if kind == "plan"]
        if not keep:
            sys.exit("\n--plans-only: no region classified as plan, "
                     "nothing to measure.")
        print(f"\n  --plans-only: measuring {len(keep)} plan region(s), "
              f"ignoring the rest")

    report_rooms(msp, to_m, args.layer, keep)
    report_blocks(doc, msp, args.blocks)
    report_labels(msp, args.labels, keep)
    report_dimensions(msp, to_m, args.labels, keep, tuple(args.band))
    report_convention(msp, to_m, keep, tuple(args.band))

    _rule("WHAT TO DO WITH THIS")
    print("  Paste this output back, or hand it to planfgen-regs in a session on")
    print("  the machine holding the file. The three answers that decide the")
    print("  corpus track: the unit, whether rooms exist as closed polylines, and")
    print("  which layers carry the walls. Everything else follows from those.")


if __name__ == "__main__":
    main()
