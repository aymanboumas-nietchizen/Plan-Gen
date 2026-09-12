"""
examples/basic_apartment.py
============================
Runs the PLANFGEN optimizer on a standard 7-room apartment programme
and prints the top 3 layout scores.

Run from the planfgen/ project root:
    python -m examples.basic_apartment
"""

import json
import os
import sys

# Allow running directly from examples/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from planfgen.core.optimizer import run_optimization

W, H = 12.0, 9.0  # Envelope: 12 m × 9 m

programme = [
    {"nom": "Séjour",    "surface": 30, "couleur": "#4a9eff", "facade": True},
    {"nom": "Cuisine",   "surface": 18, "couleur": "#3ecf8e", "facade": True},
    {"nom": "Chambre 1", "surface": 20, "couleur": "#f0a500", "facade": True},
    {"nom": "Chambre 2", "surface": 15, "couleur": "#f1948a", "facade": True},
    {"nom": "SDB",       "surface":  8, "couleur": "#c084fc", "facade": False},
    {"nom": "WC",        "surface":  5, "couleur": "#fb923c", "facade": False},
    {"nom": "Couloir",   "surface":  7, "couleur": "#94a3b8", "facade": False},
]

adjacencies = [
    ("Séjour",    "Cuisine"),
    ("Séjour",    "Couloir"),
    ("Cuisine",   "Couloir"),
    ("Couloir",   "Chambre 1"),
    ("Couloir",   "Chambre 2"),
    ("Couloir",   "SDB"),
    ("Couloir",   "WC"),
    ("SDB",       "WC"),
    ("Chambre 1", "SDB"),
]

if __name__ == "__main__":
    import time

    print("PLANFGEN — Basic Apartment Example")
    print(f"Envelope: {W} × {H} m   |   {sum(r['surface'] for r in programme)} m² programme\n")

    t0 = time.perf_counter()
    results = run_optimization(programme, adjacencies, W, H, N=200, top_k=3)
    elapsed = time.perf_counter() - t0

    print(f"Generated 200 variants in {elapsed:.2f}s\n")
    print(f"{'#':<4} {'Seed':<8} {'Global':>8} {'Adj':>8} {'Compact':>9} {'Facade':>8} {'Cover':>8}")
    print("─" * 57)
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(results):
        s = r["scores"]
        print(f"{medals[i]:<4} {r['seed']:<8} {s['global']:>8.2%} {s['adjacences']:>8.2%} "
              f"{s['compacite']:>9.2%} {s['facade']:>8.2%} {s['couverture']:>8.2%}")

    best = results[0]
    print(f"\nBest layout (seed {best['seed']}):")
    for nom, rect in best["placed"].items():
        print(f"  {nom:<15} at ({rect.x:.2f}, {rect.y:.2f})  {rect.w:.2f}×{rect.h:.2f} m  = {rect.area:.1f} m²")
