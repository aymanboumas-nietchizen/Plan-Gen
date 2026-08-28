"""
PLANFGEN — GhPython Component
==============================
Copy-paste this entire file into a GhPython component in Grasshopper.

Inputs (add via Right-click → Manage component I/O):
    boundary    : Curve  — closed curve defining the envelope (any shape)
    programme   : str    — JSON string of room programme
    adjacencies : str    — JSON string of adjacency rules
    n_variants  : int    — number of seeds to try (default: 100)
    run         : bool   — toggle True to trigger generation

Outputs:
    surfaces    : list[Surface]  — one Rhino PlaneSurface per room (best layout)
    scores      : str            — JSON string with score breakdown
    report      : str            — human-readable one-line summary

Example programme JSON input (from a Panel component):
[
  {"nom": "Séjour",    "surface": 30, "couleur": "#4a9eff", "facade": true},
  {"nom": "Cuisine",   "surface": 18, "couleur": "#3ecf8e", "facade": true},
  {"nom": "Chambre 1", "surface": 20, "couleur": "#f0a500", "facade": true},
  {"nom": "Couloir",   "surface":  7, "couleur": "#94a3b8", "facade": false}
]

Example adjacencies JSON:
[["Séjour","Cuisine"],["Séjour","Couloir"],["Cuisine","Couloir"]]
"""

import sys
import json

# ─── Adjust this path to point to the folder CONTAINING planfgen/ ──────────
PLANFGEN_PARENT = r"C:\Users\[USERNAME]\.gemini\antigravity\brain\Plan Gen"
# ────────────────────────────────────────────────────────────────────────────

if PLANFGEN_PARENT not in sys.path:
    sys.path.insert(0, PLANFGEN_PARENT)

surfaces = []
scores   = "{}"
report   = "Not run — set run=True to generate"

if run:
    try:
        import Rhino.Geometry as rg
        from planfgen.core.geometry import Envelope
        from planfgen.core.optimizer import run_optimization

        # --- Parse JSON inputs -------------------------------------------
        prog = json.loads(programme)
        adjs = [tuple(a) for a in json.loads(adjacencies)]
        n    = n_variants if n_variants else 100

        # --- Extract envelope from boundary curve ------------------------
        bbox = boundary.GetBoundingBox(True)
        ox = bbox.Min.X
        oy = bbox.Min.Y

        # Build Envelope from boundary curve vertices (supports any shape)
        try:
            nurbs = boundary.ToNurbsCurve()
            pts = [(nurbs.Points[i].Location.X - ox,
                    nurbs.Points[i].Location.Y - oy)
                   for i in range(nurbs.Points.Count)]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            envelope = Envelope.from_coords(pts)
        except Exception:
            W = bbox.Max.X - bbox.Min.X
            H = bbox.Max.Y - bbox.Min.Y
            if W <= 0 or H <= 0:
                report = "ERROR: boundary curve has zero width or height"
                envelope = None
            else:
                envelope = Envelope.from_rect(W, H)

        if envelope is not None:
            # --- Run optimization ----------------------------------------
            results = run_optimization(prog, adjs, envelope, N=n, top_k=1)

            if not results:
                report = "ERROR: no valid layouts generated — check programme areas"
            else:
                best = results[0]

                # --- Build Rhino surfaces from actual room polygons -------
                for room in best["placed"].values():
                    room_pts = [rg.Point3d(ox + x, oy + y, 0)
                                for x, y in room.coords]
                    polyline = rg.Polyline(room_pts)
                    curve = polyline.ToNurbsCurve()
                    breps = rg.Brep.CreatePlanarBreps(curve, 0.001)
                    if breps and len(breps) > 0:
                        surfaces.append(breps[0])
                    else:
                        # Fallback: bounding box PlaneSurface
                        pt    = rg.Point3d(ox + room.x, oy + room.y, 0)
                        plane = rg.Plane(pt, rg.Vector3d.ZAxis)
                        srf   = rg.PlaneSurface(
                            plane,
                            rg.Interval(0, room.w),
                            rg.Interval(0, room.h),
                        )
                        surfaces.append(srf)

                scores = json.dumps(best["scores"], ensure_ascii=False, indent=2)
                pct    = best["scores"]["global"]
                report = f"Best layout: {pct:.0%}  (seed {best['seed']}, N={n})"

    except ImportError as e:
        report = f"IMPORT ERROR: {e}\nCheck PLANFGEN_PARENT path and that planfgen is installed."
    except json.JSONDecodeError as e:
        report = f"JSON PARSE ERROR: {e}\nCheck your programme/adjacencies Panel inputs."
    except Exception as e:
        import traceback
        report = f"ERROR: {e}\n{traceback.format_exc()}"
