"""
studio/app.py
=============
PLANFGEN Studio -- Streamlit local interface.

Run with: streamlit run studio/app.py
(from the planfgen/ project root, or the Plan Gen/ parent)
"""
from __future__ import annotations

import json
import os
import sys

# Ensure planfgen package is importable when launched from any directory
_APP_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_APP_DIR)       # planfgen/
_PARENT   = os.path.dirname(_ROOT_DIR)      # Plan Gen/
for _p in (_ROOT_DIR, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
from streamlit_drawable_canvas import st_canvas

from planfgen.core.geometry  import Envelope
from planfgen.core.optimizer import run_optimization
from planfgen.core.walls     import build_wall_system
from planfgen.rules.ma_rules import MA_RULES
from planfgen.export.json_export import export_json
from planfgen.studio.components  import render_floor_plan, render_score_bar, medal

# -- Page config --------------------------------------------------------------
st.set_page_config(
    page_title="PLANFGEN Studio",
    page_icon="\U0001f3db\ufe0f",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- Global CSS ---------------------------------------------------------------
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0f172a; }
  [data-testid="stHeader"] { background: #0f172a; }
  body, .stMarkdown, label, .stSelectbox, .stTextInput { color: #e2e8f0 !important; }
  .card {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 12px; cursor: pointer; transition: border 0.2s;
  }
  .card:hover { border-color: #6366f1; }
  .card.selected { border-color: #6366f1; box-shadow: 0 0 0 2px #6366f180; }
  .score-badge {
    background: linear-gradient(135deg,#6366f1,#8b5cf6);
    color: #fff; border-radius: 20px; padding: 2px 10px;
    font-weight: 700; font-size: 1.1em; display: inline-block;
  }
  .section-title { color: #94a3b8; font-size: 0.72em; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 4px; }
  hr { border-color: #334155; }
  .stButton button {
    background: linear-gradient(135deg,#6366f1,#8b5cf6) !important;
    color: white !important; border: none !important; border-radius: 8px !important;
    font-weight: 600 !important;
  }
</style>
""", unsafe_allow_html=True)

# -- Session state defaults ---------------------------------------------------
def _init_state():
    if "programme" not in st.session_state:
        st.session_state.programme = [
            {"nom": "S\u00e9jour",    "surface": 30, "couleur": "#4a9eff", "facade": True},
            {"nom": "Cuisine",   "surface": 18, "couleur": "#3ecf8e", "facade": True},
            {"nom": "Chambre 1", "surface": 20, "couleur": "#f0a500", "facade": True},
            {"nom": "Chambre 2", "surface": 15, "couleur": "#f1948a", "facade": True},
            {"nom": "SDB",       "surface":  8, "couleur": "#c084fc", "facade": False},
            {"nom": "WC",        "surface":  5, "couleur": "#fb923c", "facade": False},
            {"nom": "Couloir",   "surface":  7, "couleur": "#94a3b8", "facade": False},
        ]
    if "adjacencies" not in st.session_state:
        st.session_state.adjacencies = [
            ("S\u00e9jour","Cuisine"),("S\u00e9jour","Couloir"),("Cuisine","Couloir"),
            ("Couloir","Chambre 1"),("Couloir","Chambre 2"),("Couloir","SDB"),
            ("Couloir","WC"),("SDB","WC"),("Chambre 1","SDB"),
        ]
    if "results"   not in st.session_state: st.session_state.results   = []
    if "selected"  not in st.session_state: st.session_state.selected  = 0
    if "show_adj"  not in st.session_state: st.session_state.show_adj  = False
    if "N"         not in st.session_state: st.session_state.N         = 200
    if "weights"   not in st.session_state:
        st.session_state.weights = {"adjacences":0.40,"compacite":0.25,"facade":0.20,"couverture":0.15}
    # Envelope: stored as an Envelope object
    if "envelope" not in st.session_state:
        st.session_state.envelope = Envelope.from_rect(12.0, 9.0)
    # Envelope input mode: "rect" | "canvas" | "json"
    if "env_mode" not in st.session_state:
        st.session_state.env_mode = "rect"
    # Rectangle quick-set values
    if "env_W" not in st.session_state: st.session_state.env_W = 12.0
    if "env_H" not in st.session_state: st.session_state.env_H = 9.0

_init_state()

# -- Header -------------------------------------------------------------------
st.markdown("""
<div style="display:flex;align-items:center;gap:12px;padding:8px 0 16px 0;">
  <span style="font-size:2em;">\U0001f3db\ufe0f</span>
  <div>
    <div style="font-size:1.5em;font-weight:800;color:#f1f5f9;letter-spacing:-0.5px;">PLANFGEN Studio</div>
    <div style="color:#64748b;font-size:0.8em;">Architectural Space Planning Engine \u00b7 Local \u00b7 Open Source</div>
  </div>
  <div style="margin-left:auto;background:#1e293b;border:1px solid #334155;border-radius:8px;padding:4px 14px;">
    <span style="color:#64748b;font-size:0.75em;">v0.2</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ===========================================================================
# Helper: extract envelope polygon from canvas JSON objects
# ===========================================================================
def _canvas_objects_to_envelope(objects: list, scale: float,
                                canvas_h: int) -> Envelope | None:
    """
    Convert Fabric.js polygon/path objects from streamlit-drawable-canvas
    into an Envelope.  Returns None if no valid polygon found.

    The canvas coordinate system has Y going down; we flip to Y-up
    and apply the scale factor (metres per pixel).
    """
    if not objects:
        return None

    for obj in reversed(objects):  # use the last drawn shape
        obj_type = obj.get("type", "")

        # -- Fabric.js polygon object (from "polygon" drawing mode) ----------
        if obj_type == "polygon":
            # Depending on version, coords may be in "path" or directly in the object
            points = obj.get("path", [])
            if not points:
                continue
            coords_m = []
            for pt in points:
                px, py = float(pt[0]), float(pt[1])
                mx = px * scale
                my = (canvas_h - py) * scale  # flip Y
                coords_m.append((round(mx, 3), round(my, 3)))
            if len(coords_m) >= 3:
                return Envelope.from_coords(coords_m)

        # -- Fabric.js path object (SVG path from "freedraw" or "polygon") ---
        if obj_type == "path":
            path_cmds = obj.get("path", [])
            if not path_cmds:
                continue
            coords_m = []
            left = obj.get("left", 0)
            top  = obj.get("top", 0)
            sx   = obj.get("scaleX", 1)
            sy   = obj.get("scaleY", 1)
            for cmd in path_cmds:
                if len(cmd) >= 3 and cmd[0] in ("M", "L"):
                    px = left + float(cmd[1]) * sx
                    py = top  + float(cmd[2]) * sy
                    coords_m.append((round(px * scale, 3),
                                     round((canvas_h - py) * scale, 3)))
            if len(coords_m) >= 3:
                return Envelope.from_coords(coords_m)

        # -- Fabric.js rect object (from "rect" drawing mode) ----------------
        if obj_type == "rect":
            left   = obj.get("left", 0)
            top    = obj.get("top", 0)
            width  = obj.get("width", 0) * obj.get("scaleX", 1)
            height = obj.get("height", 0) * obj.get("scaleY", 1)
            x0 = left * scale
            y0 = (canvas_h - top - height) * scale
            x1 = (left + width) * scale
            y1 = (canvas_h - top) * scale
            coords_m = [
                (round(x0, 3), round(y0, 3)),
                (round(x1, 3), round(y0, 3)),
                (round(x1, 3), round(y1, 3)),
                (round(x0, 3), round(y1, 3)),
            ]
            return Envelope.from_coords(coords_m)

    return None


# ===========================================================================
# Three-column layout
# ===========================================================================
col_left, col_center, col_right = st.columns([1, 2.2, 1.2])

# --- LEFT PANEL -- Programme Editor -----------------------------------------
with col_left:
    st.markdown('<div class="section-title">Programme</div>', unsafe_allow_html=True)

    # --- Room list with delete ----------------------------------------
    to_delete = None
    for idx, room in enumerate(st.session_state.programme):
        c1, c2 = st.columns([5,1])
        with c1:
            st.markdown(
                f'<div style="background:{room["couleur"]}22;border-left:3px solid {room["couleur"]};'
                f'border-radius:6px;padding:4px 8px;margin-bottom:4px;">'
                f'<b style="color:#f1f5f9">{room["nom"]}</b>'
                f'<span style="color:#64748b;font-size:0.8em;"> \u00b7 {room["surface"]} m\u00b2'
                f'{" \U0001fa9f" if room["facade"] else ""}</span></div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("\u2715", key=f"del_{idx}", help="Remove room"):
                to_delete = idx
    if to_delete is not None:
        st.session_state.programme.pop(to_delete)
        st.rerun()

    # --- Add room form ------------------------------------------------
    with st.expander("\uff0b Add Room", expanded=False):
        with st.form("add_room", clear_on_submit=True):
            new_nom    = st.text_input("Name", placeholder="e.g. Bureau")
            new_surf   = st.number_input("Area (m\u00b2)", min_value=1.0, max_value=200.0, value=15.0, step=1.0)
            new_color  = st.color_picker("Colour", "#6366f1")
            new_facade = st.checkbox("Needs facade access")
            if st.form_submit_button("Add"):
                if new_nom.strip():
                    st.session_state.programme.append({
                        "nom": new_nom.strip(), "surface": new_surf,
                        "couleur": new_color, "facade": new_facade
                    })
                    st.rerun()

    st.markdown("---")
    st.markdown('<div class="section-title">Adjacency Rules</div>', unsafe_allow_html=True)

    # --- Adjacency list with delete -----------------------------------
    to_del_adj = None
    for i, (a, b) in enumerate(st.session_state.adjacencies):
        ca, cb = st.columns([5,1])
        with ca:
            st.markdown(
                f'<div style="background:#1e293b;border-radius:6px;padding:3px 8px;margin-bottom:3px;'
                f'font-size:0.85em;color:#cbd5e1">{a} \u2194 {b}</div>',
                unsafe_allow_html=True,
            )
        with cb:
            if st.button("\u2715", key=f"deladj_{i}"):
                to_del_adj = i
    if to_del_adj is not None:
        st.session_state.adjacencies.pop(to_del_adj)
        st.rerun()

    # --- Add adjacency rule -------------------------------------------
    room_names = [r["nom"] for r in st.session_state.programme]
    if len(room_names) >= 2:
        with st.expander("\uff0b Add Rule", expanded=False):
            with st.form("add_adj", clear_on_submit=True):
                ra = st.selectbox("Room A", room_names, key="adj_a")
                rb = st.selectbox("Room B", room_names, key="adj_b")
                if st.form_submit_button("Add"):
                    if ra != rb and (ra, rb) not in st.session_state.adjacencies \
                            and (rb, ra) not in st.session_state.adjacencies:
                        st.session_state.adjacencies.append((ra, rb))
                        st.rerun()

    st.markdown("---")

    # ================================================================
    # ENVELOPE EDITOR (canvas / rectangle / JSON)
    # ================================================================
    st.markdown('<div class="section-title">Envelope</div>', unsafe_allow_html=True)

    env_mode = st.radio(
        "Input mode",
        ["Rectangle", "Draw on canvas", "JSON coords"],
        index=["rect", "canvas", "json"].index(st.session_state.env_mode),
        horizontal=True,
        key="env_mode_radio",
    )
    st.session_state.env_mode = {"Rectangle": "rect", "Draw on canvas": "canvas",
                                  "JSON coords": "json"}[env_mode]

    # -- Mode: Rectangle (quick-set) ------------------------------------
    if st.session_state.env_mode == "rect":
        st.session_state.env_W = st.slider("Width W (m)",  4.0, 40.0, st.session_state.env_W, 0.5)
        st.session_state.env_H = st.slider("Height H (m)", 4.0, 30.0, st.session_state.env_H, 0.5)
        st.session_state.envelope = Envelope.from_rect(st.session_state.env_W,
                                                        st.session_state.env_H)

    # -- Mode: Draw on canvas -------------------------------------------
    elif st.session_state.env_mode == "canvas":
        st.caption("Draw your apartment shape on the canvas below. "
                   "Use the polygon tool to click vertices, or draw a rectangle.")
        canvas_w = 380
        canvas_h = 280
        scale_mpp = st.number_input(
            "Scale (m per 100px)", min_value=0.5, max_value=20.0,
            value=4.0, step=0.5, key="canvas_scale",
        )
        scale = scale_mpp / 100.0  # metres per pixel

        drawing_mode = st.radio("Tool", ["polygon", "rect"],
                                horizontal=True, key="draw_tool")

        canvas_result = st_canvas(
            fill_color="rgba(99, 102, 241, 0.15)",
            stroke_width=2,
            stroke_color="#6366f1",
            background_color="#1e293b",
            width=canvas_w,
            height=canvas_h,
            drawing_mode=drawing_mode,
            key="envelope_canvas",
        )

        if canvas_result and canvas_result.json_data:
            objects = canvas_result.json_data.get("objects", [])
            if objects:
                env = _canvas_objects_to_envelope(objects, scale, canvas_h)
                if env is not None:
                    st.session_state.envelope = env
                    st.success(
                        f"Envelope: {env.W:.1f} \u00d7 {env.H:.1f} m "
                        f"({env.polygon.area:.1f} m\u00b2)"
                    )
                else:
                    st.warning("Could not parse shape. Draw a closed polygon or rectangle.")

        # Show current envelope dimensions
        env = st.session_state.envelope
        st.caption(f"Current: {env.W:.1f} \u00d7 {env.H:.1f} m, area {env.polygon.area:.1f} m\u00b2")

    # -- Mode: JSON coords ----------------------------------------------
    elif st.session_state.env_mode == "json":
        st.caption("Enter vertices as JSON: [[x1,y1],[x2,y2],...]  (metres)")
        env_coords = list(st.session_state.envelope.polygon.exterior.coords)
        default_json = json.dumps(
            [[round(x, 2), round(y, 2)] for x, y in env_coords[:-1]],
            ensure_ascii=False,
        )
        json_input = st.text_area("Coordinates", value=default_json,
                                  height=100, key="env_json")
        try:
            coords = json.loads(json_input)
            if isinstance(coords, list) and len(coords) >= 3:
                tuples = [(float(c[0]), float(c[1])) for c in coords]
                env = Envelope.from_coords(tuples)
                st.session_state.envelope = env
                st.success(
                    f"Envelope: {env.W:.1f} \u00d7 {env.H:.1f} m "
                    f"({env.polygon.area:.1f} m\u00b2)"
                )
            else:
                st.warning("Need at least 3 vertices")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            st.warning(f"Invalid JSON: {exc}")

    st.markdown('<div class="section-title" style="margin-top:12px">Optimization</div>', unsafe_allow_html=True)
    st.session_state.N = st.slider("Variants N", 50, 500, st.session_state.N, 50)

    with st.expander("\u2696\ufe0f Score Weights", expanded=False):
        adj_w  = st.slider("Adjacences",  0.0, 1.0, st.session_state.weights["adjacences"], 0.05)
        comp_w = st.slider("Compacit\u00e9",   0.0, 1.0, st.session_state.weights["compacite"],  0.05)
        fac_w  = st.slider("Fa\u00e7ade",      0.0, 1.0, st.session_state.weights["facade"],     0.05)
        cov_w  = st.slider("Couverture",  0.0, 1.0, st.session_state.weights["couverture"], 0.05)
        total_w = adj_w + comp_w + fac_w + cov_w
        if abs(total_w - 1.0) > 0.05:
            st.warning(f"Weights sum to {total_w:.2f} \u2014 must sum to 1.0")
        else:
            st.session_state.weights = {"adjacences":adj_w,"compacite":comp_w,"facade":fac_w,"couverture":cov_w}

    st.markdown("---")

    # --- Area validation feedback ------------------------------------
    _total_prog = sum(r["surface"] for r in st.session_state.programme)
    _env_area = st.session_state.envelope.polygon.area
    if _env_area > 0:
        _fill_pct = _total_prog / _env_area
        if _fill_pct > 1.0:
            st.warning(
                f"Programme ({_total_prog:.0f} m\u00b2) exceeds envelope "
                f"({_env_area:.0f} m\u00b2) by {(_fill_pct-1)*100:.0f}%. "
                f"Rooms will be undersized to fit."
            )
        elif _fill_pct > 0.92:
            st.info(
                f"Tight fit: {_total_prog:.0f} / {_env_area:.0f} m\u00b2 "
                f"({_fill_pct:.0%}). Some rooms may be compressed."
            )
        elif _fill_pct < 0.35:
            st.info(
                f"Programme ({_total_prog:.0f} m\u00b2) is small for envelope "
                f"({_env_area:.0f} m\u00b2, {_fill_pct:.0%} fill). "
                f"Consider adding rooms or reducing the envelope."
            )

    # --- GENERATE button ----------------------------------------------
    if st.button("\u26a1 GENERATE", use_container_width=True):
        if not st.session_state.programme:
            st.error("Add at least one room.")
        else:
            prog = st.session_state.programme
            adjs = list(st.session_state.adjacencies)
            envelope = st.session_state.envelope
            N    = st.session_state.N
            wts  = st.session_state.weights

            progress_bar = st.progress(0, text="Generating\u2026")
            _best_ref = [0.0]

            def _on_prog(cur, tot, best):
                _best_ref[0] = best
                progress_bar.progress(cur / tot,
                    text=f"Seed {cur}/{tot} \u00b7 best so far {best:.0%}")

            with st.spinner("Running optimizer\u2026"):
                results = run_optimization(prog, adjs, envelope, N=N, top_k=6,
                                           weights=wts, rules=MA_RULES,
                                           on_progress=_on_prog)

            # Build wall system for each result
            for res in results:
                try:
                    ws = build_wall_system(
                        res["placed"], adjs, envelope, programme=prog,
                    )
                    res["wall_system"] = ws
                except Exception:
                    res["wall_system"] = None

            progress_bar.empty()
            st.session_state.results  = results
            st.session_state.selected = 0
            st.rerun()

# --- CENTER PANEL -- Layout Gallery -----------------------------------------
with col_center:
    if not st.session_state.results:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
             height:420px;color:#334155;text-align:center;">
          <div style="font-size:3em">\U0001f3d7\ufe0f</div>
          <div style="font-size:1.1em;font-weight:600;color:#475569;margin-top:8px">
            No layouts yet</div>
          <div style="color:#64748b;font-size:0.85em;margin-top:4px">
            Configure your programme and click \u26a1 GENERATE</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        results  = st.session_state.results
        selected = st.session_state.selected
        envelope = st.session_state.envelope

        # Show selected layout large at top
        res = results[selected]
        score_pct = res["scores"]["global"]
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
            f'<span style="font-size:1.3em">{medal(selected)}</span>'
            f'<span style="color:#f1f5f9;font-weight:700;font-size:1.1em">Best Layout</span>'
            f'<span class="score-badge">{score_pct:.0%}</span>'
            f'<span style="color:#64748b;font-size:0.8em;margin-left:auto">seed {res["seed"]}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        adj_details = res["scores"].get("adj_details", [])
        show_adj = st.toggle("Show adjacency lines", value=st.session_state.show_adj, key="adj_toggle")
        st.session_state.show_adj = show_adj

        fig_main = render_floor_plan(
            res["placed"], envelope, adj_details,
            wall_system=res.get("wall_system"),
            show_adj=show_adj, height=340,
        )
        st.plotly_chart(fig_main, use_container_width=True, key="main_plan")

        st.markdown("---")
        st.markdown('<div class="section-title">All Variants</div>', unsafe_allow_html=True)

        # Cards grid: 3 per row
        cols = st.columns(min(len(results), 3))
        for i, res in enumerate(results):
            with cols[i % 3]:
                is_sel   = (i == selected)
                glob     = res["scores"]["global"]
                fig_mini = render_floor_plan(
                    res["placed"], envelope, [],
                    wall_system=res.get("wall_system"),
                    show_adj=False, height=140, mini=True,
                )
                st.plotly_chart(fig_mini, use_container_width=True, key=f"mini_{i}")
                btn_label = f"{medal(i)}  {glob:.0%}" + ("  \u2713" if is_sel else "")
                if st.button(btn_label, key=f"card_{i}", use_container_width=True):
                    st.session_state.selected = i
                    st.rerun()

# --- RIGHT PANEL -- Inspection Detail ---------------------------------------
with col_right:
    if not st.session_state.results:
        st.markdown('<div style="color:#334155;text-align:center;padding-top:60px">Generate layouts to inspect</div>',
                    unsafe_allow_html=True)
    else:
        res      = st.session_state.results[st.session_state.selected]
        scores   = res["scores"]
        placed   = res["placed"]
        envelope = st.session_state.envelope

        st.markdown('<div class="section-title">Score Breakdown</div>', unsafe_allow_html=True)
        st.plotly_chart(render_score_bar(scores), use_container_width=True, key="score_bar")

        st.markdown("---")
        st.markdown('<div class="section-title">Adjacency Rules</div>', unsafe_allow_html=True)
        for d in scores.get("adj_details", []):
            icon = "\u2705" if d["ok"] else "\u274c"
            st.markdown(
                f'<div style="font-size:0.82em;padding:2px 0;color:#cbd5e1">'
                f'{icon} {d["a"]} \u2194 {d["b"]}</div>',
                unsafe_allow_html=True
            )

        # --- Entrance & Circulation -----------------------------------
        ws = res.get("wall_system")
        if ws is not None:
            st.markdown("---")
            st.markdown('<div class="section-title">Circulation</div>', unsafe_allow_html=True)
            if ws.entrance:
                st.markdown(
                    f'<div style="font-size:0.82em;color:#cbd5e1">'
                    f'\U0001f6aa Entrance: <b>{ws.entrance.wall.room_a}</b> '
                    f'(width {ws.entrance.width:.2f} m)</div>',
                    unsafe_allow_html=True,
                )
            int_doors = [d for d in ws.doors if d.door_type == "interior"]
            st.markdown(
                f'<div style="font-size:0.82em;color:#cbd5e1;margin-top:4px">'
                f'\U0001f6aa {len(int_doors)} interior doors</div>',
                unsafe_allow_html=True,
            )
            # Check reachability from entrance
            if ws.entrance:
                reachable = ws.reachable_from(ws.entrance.wall.room_a)
                unreachable = [n for n in placed if n not in reachable]
                if unreachable:
                    st.warning(f"Unreachable rooms: {', '.join(unreachable)}")
                else:
                    st.markdown(
                        '<div style="font-size:0.82em;color:#22c55e;margin-top:2px">'
                        '\u2705 All rooms reachable from entrance</div>',
                        unsafe_allow_html=True,
                    )
            int_walls = [w for w in ws.walls if w.wall_type == "interior"]
            ext_walls = [w for w in ws.walls if w.wall_type == "exterior"]
            st.markdown(
                f'<div style="font-size:0.82em;color:#64748b;margin-top:4px">'
                f'Walls: {len(ext_walls)} exterior, {len(int_walls)} interior</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown('<div class="section-title">Room Surfaces</div>', unsafe_allow_html=True)

        prog_map = {r["nom"]: r["surface"] for r in st.session_state.programme}
        rows = []
        for nom, rm in placed.items():
            target = prog_map.get(nom, "\u2014")
            actual = round(rm.area, 1)
            diff   = actual - target if isinstance(target, (int,float)) else 0
            diff_s = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
            rows.append({
                "Room":     nom,
                "Target":   f"{target} m\u00b2",
                "Actual":   f"{actual} m\u00b2",
                "\u0394":        diff_s,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True,
                     column_config={"\u0394": st.column_config.TextColumn(width="small")})

        st.markdown("---")
        st.markdown('<div class="section-title">Export</div>', unsafe_allow_html=True)

        # JSON download
        import io, json as _json, datetime
        env_coords = list(envelope.polygon.exterior.coords)
        export_payload = {
            "metadata": {
                "seed": res["seed"],
                "score_global": scores["global"],
                "envelope": {
                    "W": round(envelope.W, 3),
                    "H": round(envelope.H, 3),
                    "coords": [(round(x, 3), round(y, 3)) for x, y in env_coords],
                },
                "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "rooms": [
                {**rm.to_dict(), "on_facade": rm.on_facade(envelope)}
                for rm in placed.values()
            ],
            "scores": {k: v for k,v in scores.items() if k != "adj_details"},
        }

        # Include wall system info if available
        ws = res.get("wall_system")
        if ws is not None:
            export_payload["wall_system"] = ws.to_dict()

        json_bytes = _json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "\u2b07 Export JSON", data=json_bytes,
            file_name=f"planfgen_seed{res['seed']}.json",
            mime="application/json", use_container_width=True
        )

        # DXF download
        try:
            import ezdxf
            _dxf_ok = True
        except ImportError:
            _dxf_ok = False

        if _dxf_ok:
            try:
                import tempfile, pathlib
                from planfgen.export.dxf import export_dxf
                with tempfile.TemporaryDirectory() as tmp:
                    dxf_path = export_dxf(
                        placed, f"seed{res['seed']}",
                        envelope, output_dir=tmp,
                        wall_system=ws,
                    )
                    dxf_bytes = pathlib.Path(dxf_path).read_bytes()
                st.download_button(
                    "\u2b07 Export DXF", data=dxf_bytes,
                    file_name=f"planfgen_seed{res['seed']}.dxf",
                    mime="application/dxf", use_container_width=True
                )
            except Exception as e:
                st.caption(f"DXF unavailable: {e}")
        else:
            st.caption("Install ezdxf for DXF export")
