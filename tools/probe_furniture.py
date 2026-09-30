"""Probe — do generated plans furnish? (S31, planfgen-engine)

Runs `planfgen.studio.pipeline.generate` on the presets F3, F4 and DEMO and on
F3/F4 with a separate WC, on all three profiles, over several seeds, then
`habitability.layout.furnish` on every plan found, and reports:

- how many plans furnish completely (every required item of every room);
- which items fail most, and why (the failure code and a sample reason);
- the cost of furnishing a plan.

Not a gate: this is the measurement that decides whether it should become one.

    python tools/probe_furniture.py            # 6 seeds, 400 iterations, 4 workers
    python tools/probe_furniture.py --seeds 3 --iterations 200
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILES = ("economique", "casablanca", "placeholder")


def spec_for(case: str, profile: str) -> dict:
    from web.engine import default_spec

    if case in ("F3", "F4", "DEMO"):
        return default_spec(case, profile)
    if case == "F3tight":
        # F3 cut towards the legal minima: where furnishing should start to fail.
        base = default_spec("F3", profile)
        smaller = {"Sejour": 18.0, "Cuisine": 7.0, "Ch1": 12.0, "Ch2": 9.0,
                   "SDB": 4.5, "Entree": 4.0, "Couloir": 5.0}
        rooms = [dict(r, surface=smaller.get(r["nom"], r["surface"])) for r in base["rooms"]]
        return {**base, "rooms": rooms}
    base = default_spec(case[:2], profile)  # "F3+WC" -> F3 with a separate WC
    rooms = [dict(r) for r in base["rooms"]]
    for r in rooms:
        if r["kind"] == "SDB":
            r["surface"] = 5.0
    rooms.append({"nom": "WC", "kind": "WC", "surface": 2.0, "orientation": ""})
    relations = list(base["relations"]) + [
        {"a": "Couloir", "b": "WC", "kind": "CONNECTED", "weight": 2.0}
    ]
    return {**base, "rooms": rooms, "relations": relations}


CASES = ("F3", "F4", "DEMO", "F3+WC", "F4+WC", "F3tight")


def one(job: tuple[str, str, int, int]) -> dict:
    from web.engine import build
    from planfgen.habitability.layout import furnish
    from planfgen.studio.pipeline import generate

    case, profile, seed, iterations = job
    brief, graph = build(spec_for(case, profile))
    generation = generate(brief, graph, seed=seed, iterations=iterations)
    row = {"case": case, "profile": profile, "seed": seed, "ok": generation.ok}
    if not generation.ok:
        return row
    started = time.perf_counter()
    furnished = furnish(generation.fabric, generation.openings, generation.shafts)
    row["ms"] = (time.perf_counter() - started) * 1000
    row["complete"] = furnished.complete
    row["pieces"] = len(furnished.pieces)
    row["missing"] = [
        (generation.fabric.spaces[m.room].kind.name, m.item, m.code, str(m))
        for m in furnished.missing
    ]
    row["optional"] = [
        (generation.fabric.spaces[m.room].kind.name, m.item, m.code, str(m))
        for m in furnished.optional_missing
    ]
    row["families"] = [(generation.fabric.spaces[p.room].kind.name, p.item, p.family)
                       for p in furnished.pieces if not p.loose]
    row["doorless"] = [generation.fabric.spaces[n].kind.name for n in furnished.doorless]
    row["opening_errors"] = len(generation.openings.errors) if generation.openings else 0
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=400)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cases", default=",".join(CASES))
    args = parser.parse_args()

    jobs = [
        (case, profile, seed, args.iterations)
        for case in args.cases.split(",")
        for profile in PROFILES
        for seed in range(args.seeds)
    ]
    with ProcessPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, jobs))

    print(f"{'case':8} {'profile':12} {'plans':>6} {'furnished':>10}")
    for case in args.cases.split(","):
        for profile in PROFILES:
            mine = [r for r in rows if r["case"] == case and r["profile"] == profile]
            plans = [r for r in mine if r["ok"]]
            done = [r for r in plans if r["complete"]]
            print(f"{case:8} {profile:12} {len(plans):>3}/{len(mine):<2} {len(done):>6}/{len(plans):<3}")
    plans = [r for r in rows if r["ok"]]
    done = [r for r in plans if r["complete"]]
    print(f"\nTOTAL: {len(plans)} plans, {len(done)} furnish completely "
          f"({100 * len(done) / max(1, len(plans)):.0f} %)")
    ms = sorted(r["ms"] for r in plans)
    if ms:
        print(f"furnish cost: median {ms[len(ms) // 2]:.0f} ms, max {ms[-1]:.0f} ms per plan")

    fails = Counter((k, item, code) for r in plans for k, item, code, _ in r["missing"])
    sample = {(k, item, code): text for r in plans for k, item, code, text in r["missing"]}
    print("\nRequired items that could not be placed (room kind, item, why): count")
    for key, n in fails.most_common():
        print(f"  {n:3}  {key[0]:18} {key[1]:24} {key[2]:11}  e.g. {sample[key]}")
    opt = Counter((k, item, code) for r in plans for k, item, code, _ in r["optional"])
    print("\nOptional items not placed:")
    for key, n in opt.most_common():
        print(f"  {n:3}  {key[0]:18} {key[1]:24} {key[2]}")
    rooms = Counter(k for r in plans for k, _, _, _ in r["missing"])
    print("\nPlans held back, by room kind:", dict(rooms))
    doorless = Counter(k for r in plans for k in r["doorless"])
    print(f"Plans with a furnished room no door opens into (L6): "
          f"{sum(1 for r in plans if r['doorless'])}/{len(plans)}", dict(doorless))
    chosen = Counter(f for r in plans for f in r["families"])
    print("\nWhat the main items came out as (room kind, item: family x count):")
    for kind, item in sorted({(k, i) for k, i, _ in chosen}):
        fams = {f: n for (k, i, f), n in chosen.items() if k == kind and i == item}
        print(f"  {kind:18} {item:24} " + ", ".join(f"{f} x{n}" for f, n in sorted(fams.items())))


if __name__ == "__main__":
    main()
