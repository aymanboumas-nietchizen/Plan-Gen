"""
core/scorer.py  –  Sprint 0 update
=====================================
Layout evaluation — computes 4 metrics and a weighted global score.

Updated: on_facade() and couverture now accept an Envelope object
so they work correctly for L-shaped and non-rectangular envelopes.
Backward compat: still accepts (W, H) floats for rectangular envelopes.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from planfgen.core.geometry import Room, Envelope


DEFAULT_WEIGHTS: Dict[str, float] = {
    "adjacences": 0.40,
    "compacite":  0.25,
    "facade":     0.20,
    "couverture": 0.15,
}

_RATIO_THRESHOLD = 2.5


def score_layout(
    placed: Dict[str, Room],
    adjacencies: list,
    envelope_or_W,
    H: float = None,
    facade_rooms: List[str] = None,
    weights: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Evaluate a layout on 4 metrics and compute a weighted global score.

    Parameters
    ----------
    placed          : {nom: Room} dict
    adjacencies     : list of (str, str) desired adjacency pairs
    envelope_or_W   : Envelope object (preferred) OR envelope width W (float,
                      backward compat when H is provided)
    H               : envelope height in metres (only for backward compat)
    facade_rooms    : list of room noms that need exterior wall access
    weights         : optional override of DEFAULT_WEIGHTS (must sum to 1.0)

    Returns
    -------
    dict with keys: adjacences, compacite, facade, couverture, global, adj_details
    """
    # Resolve envelope
    if isinstance(envelope_or_W, Envelope):
        envelope = envelope_or_W
        envelope_area = envelope.area
    elif isinstance(envelope_or_W, (int, float)) and H is not None:
        envelope = Envelope.from_rect(float(envelope_or_W), float(H))
        envelope_area = envelope.area
    else:
        raise TypeError("Pass Envelope object, or (W: float, H=float)")

    if facade_rooms is None:
        facade_rooms = []

    w = _validate_weights(weights or DEFAULT_WEIGHTS)

    # 1. Adjacences
    adj_details = []
    adj_ok = 0
    for a, b in adjacencies:
        room_a = placed.get(a)
        room_b = placed.get(b)
        ok = bool(room_a and room_b and room_a.touches_room(room_b))
        adj_details.append({"a": a, "b": b, "ok": ok})
        if ok:
            adj_ok += 1
    score_adj = adj_ok / len(adjacencies) if adjacencies else 1.0

    # 2. Compacite
    compacite_vals = []
    for room in placed.values():
        r = room.ratio
        compacite_vals.append(1.0 if r <= _RATIO_THRESHOLD else _RATIO_THRESHOLD / r)
    score_comp = sum(compacite_vals) / len(compacite_vals) if compacite_vals else 1.0

    # 3. Facade  (uses envelope.polygon.boundary for any shape)
    if facade_rooms:
        facade_ok = sum(
            1 for nom in facade_rooms
            if nom in placed and placed[nom].on_facade(envelope)
        )
        score_facade = facade_ok / len(facade_rooms)
    else:
        score_facade = 1.0

    # 4. Couverture  (uses envelope.area which is correct for any polygon)
    covered_area = sum(r.area for r in placed.values())
    score_couv   = min(covered_area / envelope_area, 1.0) if envelope_area > 0 else 0.0

    # 5. Global
    score_global = min(1.0, max(0.0,
        w["adjacences"] * score_adj  +
        w["compacite"]  * score_comp +
        w["facade"]     * score_facade +
        w["couverture"] * score_couv
    ))

    return {
        "adjacences":  round(score_adj,    4),
        "compacite":   round(score_comp,   4),
        "facade":      round(score_facade, 4),
        "couverture":  round(score_couv,   4),
        "global":      round(score_global, 4),
        "adj_details": adj_details,
    }


def _validate_weights(weights: Dict[str, float]) -> Dict[str, float]:
    required = {"adjacences", "compacite", "facade", "couverture"}
    merged   = {**DEFAULT_WEIGHTS, **weights}
    total    = sum(merged[k] for k in required)
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Scoring weights must sum to 1.0 (got {total:.4f})")
    return merged