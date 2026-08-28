"""L2 -> L3 — turning a tiling of rectangles into an authored wall graph.

This is the one place where the two representations meet, and the direction
matters: the partition is not the plan. Its cut lines are *authored* as wall
axes, the graph is noded, and the spaces are then read back out as faces. A cell
that came out of the slicing tree and the space that comes back out of the
fabric are two different objects, and the round trip is only trustworthy because
both compute their net area from the same walls.

An edge shared by two cells is one wall, not two, and where the two cells
disagree about its kind the thicker wall wins — a room may never be given a
thinner wall than its neighbour believes is there.
"""

from __future__ import annotations

from shapely.geometry import Polygon

from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallAxis, WallKind
from planfgen.fabric.graph import WallGraph
from planfgen.fabric.plan import FabricPlan, Space
from planfgen.fabric.solidify import net_polygon

#: Coordinates are compared at this many decimals when grouping collinear edges.
PLACES = 9


def _thicker(a: WallKind, b: WallKind, profile: RegulationProfile) -> WallKind:
    """The wall that takes more room. A tie goes to the one that carries load."""
    ta = profile.thickness_of(a.value)
    tb = profile.thickness_of(b.value)
    if ta > tb:
        return a
    if tb > ta:
        return b
    return a if a.bearing else b


def wall_axes(cells, profile: RegulationProfile) -> list[WallAxis]:
    """One axis per distinct run of cell edge, thicker kind winning.

    Cell edges are grouped by the line they sit on and cut at every endpoint in
    that group, so a long edge facing two short ones becomes the same three
    pieces either way and no run is emitted twice.
    """
    groups: dict[tuple[bool, float], list[tuple[float, float, WallKind]]] = {}
    for cell in cells:
        kinds = cell.wall_kinds
        for horizontal, fixed, lo, hi, kind in (
            (False, cell.x, cell.y, cell.y + cell.h, kinds["left"]),
            (False, cell.x + cell.w, cell.y, cell.y + cell.h, kinds["right"]),
            (True, cell.y, cell.x, cell.x + cell.w, kinds["bottom"]),
            (True, cell.y + cell.h, cell.x, cell.x + cell.w, kinds["top"]),
        ):
            groups.setdefault((horizontal, round(fixed, PLACES)), []).append(
                (lo, hi, kind)
            )

    axes: list[WallAxis] = []
    for (horizontal, fixed), runs in sorted(groups.items()):
        breaks = sorted({round(v, PLACES) for lo, hi, _ in runs for v in (lo, hi)})
        for lo, hi in zip(breaks, breaks[1:]):
            covering = [k for a, b, k in runs if a <= lo + 1e-9 and b >= hi - 1e-9]
            if not covering:
                continue
            kind = covering[0]
            for other in covering[1:]:
                kind = _thicker(kind, other, profile)
            p0 = (lo, fixed) if horizontal else (fixed, lo)
            p1 = (hi, fixed) if horizontal else (fixed, hi)
            axes.append(WallAxis(p0, p1, kind))
    return axes


def to_wall_graph(plan, profile: RegulationProfile) -> WallGraph:
    """Author the partition's cut lines as a wall graph."""
    return WallGraph(wall_axes(plan.cells, profile))


def to_fabric(plan, profile: RegulationProfile) -> FabricPlan:
    """Node the graph, read the faces back out, and name them from the cells.

    Each face is matched to the cell that contains its representative point.
    Because the cells tile the envelope and the walls are exactly their edges,
    that match is one to one.
    """
    graph = to_wall_graph(plan, profile)
    graph.split_at_crossings()
    faces = graph.faces()

    programme = plan.brief.programme
    by_nom = {cell.nom: cell for cell in plan.cells}
    spaces: dict[str, Space] = {}

    for face in faces:
        point = face.representative_point()
        cell = _cell_at(plan.cells, point.x, point.y)
        if cell is None:
            raise ValueError(
                f"face centred on ({point.x:.3f}, {point.y:.3f}) matches no cell; "
                f"the partition and the wall graph disagree"
            )
        if cell.nom in spaces:
            raise ValueError(f"cell {cell.nom!r} matched more than one face")
        bounding = graph.bounding_walls(face)
        spaces[cell.nom] = Space(
            nom=cell.nom,
            kind=programme.by_nom(cell.nom).kind,
            axis_polygon=face,
            net_polygon=net_polygon(face, bounding, profile),
            bounding=bounding,
        )

    missing = set(by_nom) - set(spaces)
    if missing:
        raise ValueError(f"no face was found for {sorted(missing)}")

    return FabricPlan(
        graph=graph,
        spaces=spaces,
        parcel=plan.brief.parcel,
        profile=profile,
        envelope_rect=plan.envelope_rect,
    )


def _cell_at(cells, x: float, y: float):
    for cell in cells:
        if cell.x <= x <= cell.x + cell.w and cell.y <= y <= cell.y + cell.h:
            return cell
    return None


def cell_polygon(cell) -> Polygon:
    """The cell's axis rectangle, for comparison against the face it produced."""
    return Polygon(
        [
            (cell.x, cell.y),
            (cell.x + cell.w, cell.y),
            (cell.x + cell.w, cell.y + cell.h),
            (cell.x, cell.y + cell.h),
        ]
    )
