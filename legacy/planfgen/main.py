#!/usr/bin/env python3
"""
PLANFGEN — CLI Entry Point
Usage: python main.py --programme tests/fixtures/apartment_7rooms.json --W 12 --H 9 --N 200
"""

import argparse
import json
import logging
import os
import sys
import time

def main():
    parser = argparse.ArgumentParser(
        description="PLANFGEN — Architectural Space Planning Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--programme", required=True, help="Path to JSON programme file")
    parser.add_argument("--W", type=float, default=None, help="Envelope width in meters")
    parser.add_argument("--H", type=float, default=None, help="Envelope height in meters")
    parser.add_argument("--envelope", default=None, help="Path to DXF or JSON file defining polygon envelope (overrides --W/--H)")
    parser.add_argument("--N", type=int, default=200, help="Number of layout variants to generate (default: 200)")
    parser.add_argument("--top-k", type=int, default=6, dest="top_k", help="Number of top results to return (default: 6)")
    parser.add_argument("--output-dir", default="./outputs", dest="output_dir", help="Output directory (default: ./outputs)")
    parser.add_argument("--no-export", action="store_true", help="Skip JSON export")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger("planfgen")

    # Load programme
    prog_path = args.programme
    if not os.path.exists(prog_path):
        log.error(f"Programme file not found: {prog_path}")
        sys.exit(1)

    with open(prog_path, encoding="utf-8") as f:
        data = json.load(f)

    programme   = data["programme"]
    adjacencies = [tuple(a) for a in data["adjacencies"]]

    from planfgen.core.geometry import Envelope

    # Build envelope: --envelope flag > programme JSON > --W/--H
    if args.envelope:
        if args.envelope.lower().endswith(".dxf"):
            envelope = Envelope.from_dxf(args.envelope)
        else:
            import json as json2
            with open(args.envelope, encoding="utf-8") as ef:
                envelope = Envelope.from_json(json2.load(ef))
    elif "envelope" in data:
        envelope = Envelope.from_json(data["envelope"])
    elif args.W is not None and args.H is not None:
        envelope = Envelope.from_rect(args.W, args.H)
    else:
        log.error("Envelope required: use --W/--H, --envelope, or include 'envelope' in programme JSON")
        sys.exit(1)

    log.info(f"Loaded programme: {len(programme)} rooms, envelope {envelope.W:.1f}×{envelope.H:.1f}m (area={envelope.area:.1f}m²)")
    log.info(f"Running optimization: N={args.N}, top_k={args.top_k}")

    from planfgen.core.optimizer import run_optimization

    t0 = time.perf_counter()

    def on_progress(current, total, best):
        if current % 50 == 0 or current == total:
            bar_len = 30
            filled = int(bar_len * current / total)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {current}/{total}  best={best:.2%}", end="", flush=True)

    results = run_optimization(
        programme, adjacencies, envelope,
        N=args.N,
        top_k=args.top_k,
        on_progress=on_progress,
    )
    elapsed = time.perf_counter() - t0
    print()  # newline after progress bar

    log.info(f"Done in {elapsed:.2f}s — {len(results)} results")

    # Print summary table
    print("\n" + "─" * 60)
    print(f"{'Rank':<6} {'Seed':<8} {'Global':>8} {'Adj':>8} {'Compact':>9} {'Facade':>8} {'Cover':>8}")
    print("─" * 60)
    for i, r in enumerate(results):
        s = r["scores"]
        medal = ["🥇", "🥈", "🥉"] + ["  "] * 10
        print(f"{medal[i]:<4} {r['seed']:<8} {s['global']:>8.2%} {s['adjacences']:>8.2%} "
              f"{s['compacite']:>9.2%} {s['facade']:>8.2%} {s['couverture']:>8.2%}")
    print("─" * 60)

    # Export
    if not args.no_export:
        os.makedirs(args.output_dir, exist_ok=True)
        from planfgen.export.json_export import export_json
        out_path = export_json(
            results[0]["placed"],
            results[0]["scores"],
            results[0]["seed"],
            envelope,
            filename=os.path.join(args.output_dir, "best_layout"),
        )
        log.info(f"Exported best layout → {out_path}")

if __name__ == "__main__":
    main()
