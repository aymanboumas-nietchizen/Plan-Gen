"""
export/json_export.py
=====================
JSON export for Grasshopper integration and data interchange.

Output format follows the specification in project brief §8.2:
  metadata: seed, score_global, envelope, generated_at
  rooms:    nom, area, cx, cy, x, y, w, h, coords, color, on_facade
  scores:   all 5 scoring metrics

Uses only stdlib — no additional dependencies.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict

from planfgen.core.geometry import Room, Envelope


def export_json(
    placed: Dict[str, Room],
    scores: dict,
    seed: int,
    envelope_or_W=None,
    H: float = None,
    filename: str = "layout",
    output_dir: str = "./outputs",
    *,
    W: float = None,
) -> str:
    """
    Export a layout and its scores to a structured JSON file.

    Parameters
    ----------
    placed        : {nom: Room} layout dict
    scores        : scores dict from score_layout()
    seed          : seed used to generate this layout
    envelope_or_W : Envelope object (preferred) OR W float (backward compat)
    H             : envelope height in metres (only for backward compat)
    filename      : output filename without extension (or full path without ext)
    output_dir    : directory to write the .json file (ignored if filename has dir)
    W             : keyword-only alias for envelope width (backward compat)

    Returns
    -------
    Absolute path to the written .json file.
    """
    # Resolve envelope from the various calling conventions
    if isinstance(envelope_or_W, Envelope):
        envelope = envelope_or_W
    elif isinstance(envelope_or_W, (int, float)):
        _w = float(envelope_or_W)
        _h = float(H) if H is not None else 9.0
        envelope = Envelope.from_rect(_w, _h)
    elif W is not None:
        envelope = Envelope.from_rect(float(W), float(H or 9.0))
    elif envelope_or_W is None and H is not None:
        raise TypeError("Pass Envelope object, or (W, H) floats")
    else:
        envelope = Envelope.from_rect(12.0, 9.0)

    # Handle both "bare filename" and "path/without/extension" cases
    if os.path.dirname(filename):
        out_path = filename + ".json"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{filename}.json")

    # Build envelope metadata — include W/H for rectangle compat plus full coords
    env_meta = envelope.to_dict()
    env_meta["W"] = round(envelope.W, 3)
    env_meta["H"] = round(envelope.H, 3)

    payload = {
        "metadata": {
            "seed":         seed,
            "score_global": scores.get("global", 0.0),
            "envelope":     env_meta,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "rooms": [
            {
                **room.to_dict(),
                "on_facade": room.on_facade(envelope),
            }
            for nom, room in placed.items()
        ],
        "scores": {
            "adjacences": scores.get("adjacences", 0.0),
            "compacite":  scores.get("compacite",  0.0),
            "facade":     scores.get("facade",     0.0),
            "couverture": scores.get("couverture", 0.0),
            "global":     scores.get("global",     0.0),
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return os.path.abspath(out_path)
