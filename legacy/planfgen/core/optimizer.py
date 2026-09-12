"""
core/optimizer.py  –  Sprint 0 update
========================================
Stochastic optimization layer: generate N variants, validate, score, return top K.

Updated to accept an Envelope object (or backward-compat W/H floats) and pass
it through to generate_layout() and score_layout().
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from planfgen.core.geometry import Envelope

log = logging.getLogger("planfgen.optimizer")


def run_optimization(
    programme: list,
    adjacencies: list,
    envelope_or_W,
    H: float = None,
    N: int = 200,
    top_k: int = 6,
    weights: Optional[Dict] = None,
    rules: Optional[list] = None,
    on_progress: Optional[Callable] = None,
    min_adj_score: float = 0.5,
) -> List[dict]:
    """
    Generate N layout variants, validate, score, and return top_k results.

    Parameters
    ----------
    programme       : list of room dicts (nom, surface, couleur, facade)
    adjacencies     : list of (str, str) adjacency pairs
    envelope_or_W   : Envelope object (preferred) OR W float (backward compat)
    H               : envelope height in metres (only for backward compat)
    N               : number of seeds to try (default 200)
    top_k           : number of best results to return (default 6)
    weights         : optional scoring weight overrides
    rules           : list of Rule objects (default: empty list)
    on_progress     : optional callback(current: int, total: int, best: float)
    min_adj_score   : minimum adjacency score to keep a layout (0.0-1.0).
                      Layouts where fewer than this fraction of required
                      adjacencies are satisfied are discarded. Default 0.5.

    Returns
    -------
    list of {seed, placed, scores} dicts sorted by global score descending
    """
    from planfgen.core.generator import generate_layout
    from planfgen.core.scorer   import score_layout

    # Resolve envelope
    if isinstance(envelope_or_W, Envelope):
        envelope = envelope_or_W
    elif isinstance(envelope_or_W, (int, float)) and H is not None:
        envelope = Envelope.from_rect(float(envelope_or_W), float(H))
    elif envelope_or_W is None and H is None:
        raise TypeError("Pass Envelope object, or (W, H) floats")
    else:
        envelope = Envelope.from_rect(float(envelope_or_W or 12.0),
                                      float(H or 9.0))

    if rules is None:
        rules = []

    facade_rooms = [r["nom"] for r in programme if r.get("facade", False)]

    results:    List[dict] = []
    best_so_far: float     = 0.0

    for i in range(N):
        placed = generate_layout(programme, adjacencies, envelope, seed=i)

        if rules:
            from planfgen.rules.base_rules import validate_layout
            validation = validate_layout(placed, rules)
            if not validation["valid"]:
                log.debug(f"seed={i} discarded (rule): {validation['errors'][0].message}")
                if on_progress:
                    on_progress(i + 1, N, best_so_far)
                continue

        scores = score_layout(placed, adjacencies, envelope,
                              facade_rooms=facade_rooms, weights=weights)

        # Hard adjacency filter: discard if too few adjacencies satisfied
        if adjacencies and scores["adjacences"] < min_adj_score:
            log.debug(f"seed={i} discarded (adj): {scores['adjacences']:.2f} < {min_adj_score}")
            if on_progress:
                on_progress(i + 1, N, best_so_far)
            continue

        best_so_far = max(best_so_far, scores["global"])
        results.append({"seed": i, "placed": placed, "scores": scores})

        if on_progress:
            on_progress(i + 1, N, best_so_far)

    # If adjacency filter was too strict and no results passed, relax and retry
    if not results and adjacencies and min_adj_score > 0:
        log.warning(f"No layouts passed adj filter ({min_adj_score}), relaxing to 0.0")
        return run_optimization(
            programme, adjacencies, envelope_or_W, H=H, N=N, top_k=top_k,
            weights=weights, rules=rules, on_progress=None,
            min_adj_score=0.0,
        )

    results.sort(key=lambda r: r["scores"]["global"], reverse=True)
    top = results[:top_k]
    log.info(f"Optimization done: {len(results)}/{N} valid, best={best_so_far:.3f}")
    return top