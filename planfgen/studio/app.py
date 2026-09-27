"""Studio — one run, shown at every stage of the layer stack.

    streamlit run planfgen/studio/app.py --server.headless true

The page opens on the plan, because the plan is what an architect came for.
The organigramme is still here, last, drawn deliberately as a graph with no
geometry in it — L1 and L3 side by side are the argument of the rewrite — but
it is no longer the first thing a result shows.

The feasibility budget is shown *before* anything is generated, because a brief
that cannot be built is not a generation problem. Generation itself lives in
`pipeline.py`: the footprint is solved there, so the lot only has to be large
enough for the programme, not calibrated to it.

A result is kept in `st.session_state`. Streamlit reruns this script on every
interaction, and the plan used to exist only for the one run in which the
button read True — downloading the DXF discarded it.
"""

from __future__ import annotations

import json
import math

import streamlit as st
from shapely.geometry import Polygon

from planfgen.brief import (
    Brief,
    EdgeSpec,
    EdgeType,
    Orientation,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    check_feasibility,
)
from planfgen.document import export_dxf, to_gh_json, to_svg
from planfgen.document.dimensions import exterior_chains, interior_chains
from planfgen.studio.pipeline import PROFILE_CHOICES, generate
from planfgen.studio.presets import PRESETS
from planfgen.studio.render import partition_svg, topology_svg
from planfgen.studio.seed import spine_note
from planfgen.topology import ProgrammeGraph, Relation, RelationType

st.set_page_config(page_title="PLANFGEN v2", layout="wide")

EDGE_NAMES = [k.name for k in EdgeType]

#: Edge i of the rectangle, as it appears on the drawing. Not a compass
#: direction: that depends on the north slider.
EDGE_SIDES = ["bas", "droite", "haut", "gauche"]
EDGE_DEFAULTS = ["STREET", "MITOYEN", "COURT", "MITOYEN"]


# --- the brief --------------------------------------------------------------


def sidebar():
    st.sidebar.header("Typologie")
    preset_key = st.sidebar.selectbox(
        "Point de depart",
        list(PRESETS),
        format_func=lambda key: PRESETS[key].label,
    )
    preset = PRESETS[preset_key]
    profile_label = st.sidebar.selectbox("Reglementation", list(PROFILE_CHOICES))

    st.sidebar.header("Parcelle")
    # Keyed on the preset so that choosing a typology also resets the lot.
    width = st.sidebar.number_input(
        "Largeur (m)", 6.0, 40.0, preset.width, 0.1, key=f"w_{preset_key}"
    )
    height = st.sidebar.number_input(
        "Profondeur (m)", 6.0, 40.0, preset.depth, 0.1, key=f"h_{preset_key}"
    )
    north = st.sidebar.slider("Nord (degres)", 0, 359, 0)
    edges = [
        st.sidebar.selectbox(
            f"Bord {i} ({side})", EDGE_NAMES, index=EDGE_NAMES.index(default)
        )
        for i, (side, default) in enumerate(zip(EDGE_SIDES, EDGE_DEFAULTS))
    ]
    entry = st.sidebar.selectbox(
        "Entree par le bord",
        range(4),
        format_func=lambda i: f"{i} ({EDGE_SIDES[i]}, {edges[i]})",
    )

    st.sidebar.header("Recherche")
    seed = st.sidebar.number_input("Graine", 0, 9999, 3)
    iterations = st.sidebar.slider("Iterations", 0, 1000, 200, 20)
    return (preset_key, profile_label, width, height, north, edges, entry,
            seed, iterations)


def build_brief(width, height, north, edges, entry, rooms, profile):
    programme = Programme(
        [
            RoomSpec(
                nom=r["nom"],
                kind=RoomType[r["kind"]],
                surface_utile=float(r["surface_utile"]),
                couleur="#888888",
                orientation_pref=Orientation[r["orientation"]] if r["orientation"] else None,
            )
            for r in rooms
        ]
    )
    parcel = Parcel(
        outline=Polygon([(0, 0), (width, 0), (width, height), (0, height)]),
        edges=[EdgeSpec(i, EdgeType[name]) for i, name in enumerate(edges)],
        north=math.radians(north),
        entry_edge=int(entry),
    )
    budget = check_feasibility(programme, parcel, profile)
    return Brief(programme, parcel, profile, budget), budget


def build_graph(relations) -> ProgrammeGraph:
    return ProgrammeGraph(
        [
            Relation(r["a"], r["b"], RelationType[r["kind"]], float(r["weight"]))
            for r in relations
        ]
    )


# --- the page ---------------------------------------------------------------


st.title("PLANFGEN v2")
st.caption("Les murs sont dessines. Les pieces en decoulent.")

(preset_key, profile_label, width, height, north, edges, entry,
 seed, iterations) = sidebar()
preset = PRESETS[preset_key]
profile = PROFILE_CHOICES[profile_label]

st.subheader("Programme")
rooms = st.data_editor(
    [
        {"nom": n, "kind": k, "surface_utile": a, "orientation": o}
        for n, k, a, o in preset.rooms
    ],
    num_rows="dynamic",
    use_container_width=True,
    key=f"rooms_{preset_key}",
)

with st.expander("Relations (L1)"):
    relations = st.data_editor(
        [{"a": a, "b": b, "kind": k, "weight": w} for a, b, k, w in preset.relations],
        num_rows="dynamic",
        use_container_width=True,
        key=f"relations_{preset_key}",
    )

try:
    brief, budget = build_brief(width, height, north, edges, entry, rooms, profile)
    graph = build_graph(relations)
except Exception as exc:  # a half-edited table is not an error worth a traceback
    st.warning(f"Brief incomplet : {exc}")
    st.stop()

st.subheader("Faisabilite")
st.code(budget.explain(), language=None)
if not budget.ok:
    st.error(
        "Le programme ne tient pas dans la parcelle. Rien n'est genere : "
        "ce n'est pas un probleme de generation."
    )
    st.stop()
st.success(f"Marge : {-budget.deficit:.2f} m2")

note = spine_note(brief.programme, budget)
if not note.ok:
    st.error(note.message)
    st.stop()
if note.banded:
    st.caption(note.message)
else:
    st.info(note.message)

# Everything the result depends on. A result generated from other inputs is
# still shown, but marked as stale rather than silently passed off as current.
fingerprint = json.dumps(
    [preset_key, profile_label, width, height, north, edges, entry, seed,
     iterations, rooms, relations],
    sort_keys=True,
    default=str,
)

if st.button("Generer", type="primary"):
    with st.spinner("Recherche en cours..."):
        st.session_state["run"] = (
            fingerprint,
            generate(brief, graph, int(seed), int(iterations)),
        )

if "run" not in st.session_state:
    st.info("Le graphe L1 ci-dessous existe deja. Le plan, non.")
    st.image(topology_svg(graph, brief.programme))
    st.stop()

made_from, run = st.session_state["run"]
if made_from != fingerprint:
    st.warning(
        "Le brief a change depuis cette generation. Le plan affiche est "
        "l'ancien : cliquez sur Generer pour le mettre a jour."
    )

if run.fitting.shrunk:
    st.warning(run.fitting.note)
else:
    st.caption(run.fitting.note)

if not run.ok:
    st.error(f"Aucun candidat n'a passe les portes. {run.stats.explain()}")
    st.stop()

result = run.result
plan = result.plan
fabric = run.fabric
used = result.brief
footprint = used.footprint

columns = st.columns(6)
for column, (label, value) in zip(
    columns,
    [
        ("Global", f"{result.scores.globale:.3f}"),
        ("Adjacences", f"{result.scores.adjacences:.3f}"),
        ("Orientation", f"{result.scores.orientation:.3f}"),
        ("Circulation", f"{plan.circulation_coefficient(used.profile) * 100:.1f} %"),
        ("Erreur surface", f"{plan.max_area_error(used.profile) * 100:.3f} %"),
        ("Emprise", f"{footprint.w:.1f} x {footprint.h:.1f}"),
    ],
):
    column.metric(label, value)
st.caption(run.stats.explain())

l3, l8, l2, l1 = st.tabs(
    ["L3 Plan", "L8 Dessin", "L2 Partition", "L1 Topologie"]
)

with l3:
    st.markdown("Les murs sont solides, les surfaces sont mesurees.")
    st.image(to_svg(fabric, "outputs/studio_preview.svg"))
    st.dataframe(
        [
            {
                "nom": nom,
                "surface_utile": round(space.surface_utile, 2),
                "cible": round(used.programme.by_nom(nom).surface_utile, 2),
                "net": "%.2f x %.2f" % space.net_dims(),
            }
            for nom, space in fabric.spaces.items()
        ],
        use_container_width=True,
    )

with l8:
    openings = run.openings
    st.markdown(f"{openings.explain()}")
    if openings.errors:
        for error in openings.errors:
            st.warning(error)
    chains = exterior_chains(fabric) + interior_chains(fabric)
    st.caption(f"{len(chains)} chaines de cotation")

    export_dxf(fabric, "outputs/studio.dxf", openings=openings, shafts=list(run.shafts))
    with open("outputs/studio.dxf", "rb") as handle:
        st.download_button("plan.dxf", handle.read(), "plan.dxf")
    st.download_button(
        "plan.json (Grasshopper)",
        json.dumps(
            to_gh_json(fabric, openings, list(run.shafts)), indent=2, ensure_ascii=False
        ),
        "plan.json",
        mime="application/json",
    )

with l2:
    st.markdown("Des rectangles sur les axes : surface nette / cible.")
    st.image(partition_svg(plan, used.profile))

with l1:
    st.markdown(
        "Un graphe. Aucune geometrie. **C'est ce que v1 livrait en l'appelant un plan.**"
    )
    st.image(topology_svg(graph, used.programme))
