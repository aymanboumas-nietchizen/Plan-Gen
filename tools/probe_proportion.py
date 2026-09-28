"""The shape of the rooms the studio's presets actually get.

    python tools/probe_proportion.py

Every gate passes on these plans; this asks what the gates do not — whether the
rooms are rooms or slots. Per preset and profile, four seeds through
`pipeline.generate` (exactly what the studio runs), then for every room that
came out longer than 2:1 on its net dimensions, how often and how bad.

What it found on 2026-09-28 (PROGRESS.md S26): the slots are the small rooms —
the ENTREE at ~1.5 x 3.3 m, the SDB at ~1.7 x 4.1 m, the CUISINE at ~2.1 x 5.3 m
— and neither the compacite formula, nor its weight, nor allowing a kitchen off
the sejour or an en-suite SDB changes them. Each room takes the full depth of
its side of the corridor, and the search cannot build a room behind a room.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from shapely.geometry import Polygon

from planfgen.brief import (
    Brief, EdgeSpec, EdgeType, Orientation, Parcel, Programme, RoomSpec, RoomType,
    check_feasibility,
)
from planfgen.brief.regulation import PROFILES
from planfgen.studio.pipeline import generate
from planfgen.studio.presets import PRESETS
from planfgen.topology import ProgrammeGraph, Relation, RelationType

SEEDS = (1, 2, 3, 4)
ITERATIONS = 200
SLOT = 2.0


def brief_for(key: str, profile) -> tuple[Brief, ProgrammeGraph]:
    preset = PRESETS[key]
    programme = Programme([
        RoomSpec(nom=n, kind=RoomType[k], surface_utile=a, couleur="#888888",
                 orientation_pref=Orientation[o] if o else None)
        for n, k, a, o in preset.rooms
    ])
    w, h = preset.width, preset.depth
    parcel = Parcel(
        outline=Polygon([(0, 0), (w, 0), (w, h), (0, h)]),
        edges=[EdgeSpec(i, EdgeType[e]) for i, e in
               enumerate(("STREET", "MITOYEN", "COURT", "MITOYEN"))],
        north=0.0,
        entry_edge=0,
    )
    graph = ProgrammeGraph(
        [Relation(a, b, RelationType[k], wt) for a, b, k, wt in preset.relations]
    )
    return Brief(programme, parcel, profile, check_feasibility(programme, parcel, profile)), graph


def main() -> None:
    for key in PRESETS:
        for name, profile in PROFILES.items():
            brief, graph = brief_for(key, profile)
            plans, worst, slots = 0, [], defaultdict(list)
            for seed in SEEDS:
                run = generate(brief, graph, seed, ITERATIONS)
                if not run.ok:
                    continue
                plans += 1
                ratios = []
                for cell in run.result.plan.cells:
                    if cell.is_band:
                        continue
                    w, h = cell.net_dims(run.result.brief.profile)
                    ratio = max(w, h) / min(w, h)
                    ratios.append(ratio)
                    if ratio > SLOT:
                        slots[cell.nom].append(f"{min(w, h):.2f}x{max(w, h):.2f}")
                worst.append(max(ratios))
            head = f"{key:5} {name:11} plans {plans}/{len(SEEDS)}"
            if not plans:
                print(head)
                continue
            found = "; ".join(f"{n} {len(v)}x ({v[0]})" for n, v in sorted(slots.items()))
            print(f"{head}  worst room {mean(worst):.2f}:1  slots: {found or '-'}", flush=True)


if __name__ == "__main__":
    main()
