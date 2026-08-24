"""L2a — the net/gross inversion, as pure arithmetic.

ARCHITECTURE section 2. A room loses half the thickness of each wall bounding
it, so given a target *net* area and an aspect the axis dimensions follow in
closed form — no iteration, because the slicing tree knows which walls bound a
leaf before the leaf is sized. Nothing in this module imports anything.
"""

from __future__ import annotations

import math


def axis_dims(
    net_area: float,
    aspect: float,
    t_left: float,
    t_right: float,
    t_bottom: float,
    t_top: float,
) -> tuple[float, float]:
    """Axis (w, h) for a room of `net_area` at `aspect` = net_w / net_h."""
    if net_area <= 0:
        raise ValueError(f"net_area must be positive, got {net_area}")
    if aspect <= 0:
        raise ValueError(f"aspect must be positive, got {aspect}")
    net_h = math.sqrt(net_area / aspect)
    net_w = aspect * net_h
    return net_w + (t_left + t_right) / 2, net_h + (t_bottom + t_top) / 2


def aspect_ok(w: float, h: float, max_ratio: float = 2.5) -> bool:
    """True if the room is not so elongated as to be unusable.

    ARCHITECTURE section 1: v1's Chambre 2 was 11.25 m² of floor into which no
    bed fitted, because area says nothing about shape.
    """
    if w <= 0 or h <= 0:
        return False
    return max(w, h) / min(w, h) <= max_ratio
