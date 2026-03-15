"""
examples/office_layout.py
==========================
Runs the optimizer on an open-plan office programme.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from planfgen.core.optimizer import run_optimization

W, H = 20.0, 15.0

programme = [
    {"nom": "Open Space",      "surface": 80, "couleur": "#4a9eff", "facade": True},
    {"nom": "Salle de réunion","surface": 30, "couleur": "#3ecf8e", "facade": True},
    {"nom": "Bureau Direction","surface": 25, "couleur": "#f0a500", "facade": True},
    {"nom": "Accueil",        "surface": 15, "couleur": "#f1948a", "facade": True},
    {"nom": "Cuisine bureau",  "surface": 12, "couleur": "#94a3b8", "facade": False},
    {"nom": "WC",              "surface":  6, "couleur": "#fb923c", "facade": False},
    {"nom": "Local tech",      "surface":  8, "couleur": "#78716c", "facade": False},
]

adjacencies = [
    ("Accueil",         "Open Space"),
    ("Open Space",      "Salle de réunion"),
    ("Open Space",      "Bureau Direction"),
    ("Open Space",      "Cuisine bureau"),
    ("Cuisine bureau",  "WC"),
]

if __name__ == "__main__":
    import time
    print("PLANFGEN — Office Layout Example")
    t0 = time.perf_counter()
    results = run_optimization(programme, adjacencies, W, H, N=100, top_k=3)
    print(f"100 variants in {time.perf_counter()-t0:.2f}s\n")
    for i, r in enumerate(results):
        s = r["scores"]
        print(f"#{i+1} seed={r['seed']}  global={s['global']:.2%}")
