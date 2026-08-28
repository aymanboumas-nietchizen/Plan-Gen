"""
examples/school_layout.py
==========================
Runs the optimizer on a 10-room school classroom block programme.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from planfgen.core.optimizer import run_optimization

W, H = 24.0, 18.0

programme = [
    {"nom": "Salle 1",          "surface": 60, "couleur": "#4a9eff", "facade": True},
    {"nom": "Salle 2",          "surface": 60, "couleur": "#3ecf8e", "facade": True},
    {"nom": "Salle 3",          "surface": 60, "couleur": "#f0a500", "facade": True},
    {"nom": "Salle 4",          "surface": 60, "couleur": "#f1948a", "facade": True},
    {"nom": "Administration",   "surface": 30, "couleur": "#c084fc", "facade": True},
    {"nom": "Infirmerie",       "surface": 15, "couleur": "#fb923c", "facade": True},
    {"nom": "Couloir principal","surface": 40, "couleur": "#94a3b8", "facade": False},
    {"nom": "WC Garçons",       "surface": 12, "couleur": "#64748b", "facade": False},
    {"nom": "WC Filles",        "surface": 12, "couleur": "#e879f9", "facade": False},
    {"nom": "Local technique",  "surface": 10, "couleur": "#78716c", "facade": False},
]

adjacencies = [
    ("Salle 1",        "Couloir principal"),
    ("Salle 2",        "Couloir principal"),
    ("Salle 3",        "Couloir principal"),
    ("Salle 4",        "Couloir principal"),
    ("Administration", "Couloir principal"),
    ("Infirmerie",     "Couloir principal"),
    ("WC Garçons",     "Couloir principal"),
    ("WC Filles",      "Couloir principal"),
]

if __name__ == "__main__":
    import time
    print("PLANFGEN — School Layout Example")
    print(f"Envelope: {W}×{H}m  |  {sum(r['surface'] for r in programme)}m² programme\n")
    t0 = time.perf_counter()
    results = run_optimization(programme, adjacencies, W, H, N=100, top_k=3)
    print(f"100 variants in {time.perf_counter()-t0:.2f}s\n")
    for i, r in enumerate(results):
        s = r["scores"]
        print(f"#{i+1} seed={r['seed']}  global={s['global']:.2%}  adj={s['adjacences']:.2%}  facade={s['facade']:.2%}")
