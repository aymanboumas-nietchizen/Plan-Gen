"""Studio — one run, shown at every stage of the layer stack.

    streamlit run planfgen/studio/app.py --server.headless true

The stage selector is the argument of the whole rewrite made visible. L1 is a
graph with no geometry in it; L3 is a plan built from walls. v1 shipped only the
first and called it the second. Here they sit behind adjacent tabs, drawn from
the same run, and are obviously different things.

The feasibility budget is shown *before* anything is generated, because a brief
that cannot be built is not a generation problem. `seed.spine_note` holds that
line for the *tree*: what the spine will be, and what a programme with no
circulation room costs, are on the page before the button is pressed.
"""

from __future__ import annotations

import io
import json

import streamlit as st
from shapely.geometry import Polygon

from planfgen.brief import (
    MA_PROFILE,
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
from planfgen.evaluate import all_gates
from planfgen.openings import place_openings
from planfgen.search import RunStats, anneal, envelope_of, evaluate, grid_for
from planfgen.services import assign_stack_ids, assign_wet_walls, place_shafts
from planfgen.services.stacking import Level
from planfgen.studio.render import partition_svg, topology_svg
from planfgen.studio.seed import seed_tree, spine_note
from planfgen.topology import ProgrammeGraph, Relation, RelationType

st.set_page_config(page_title="PLANFGEN v2", layout="wide")

DEFAULT_ROOMS = [
    ("Sejour", "SEJOUR", 33.8, "S"),
    ("Cuisine", "CUISINE", 13.5, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 19.2, "N"),
    ("Ch2", "CHAMBRE", 15.8, "S"),
    ("SDB", "SDB", 10.2, "E"),
    ("Couloir", "COULOIR", 8.0, ""),
]

DEFAULT_RELATIONS = [
    ("Couloir", "Sejour", "CONNECTED", 2.0),
    ("Couloir", "Ch1", "CONNECTED", 2.0),
    ("Couloir", "Ch2", "CONNECTED", 2.0),
    ("Couloir", "SDB", "CONNECTED", 1.0),
    ("Sejour", "Cuisine", "CONNECTED", 1.5),
    ("Cuisine", "SDB", "ADJACENT", 2.0),
    ("SDB", "Sejour", "SEPARATED", 1.0),
]

EDGE_NAMES = [k.name for k in EdgeType]


# --- the brief --------------------------------------------------------------


def sidebar():
    st.sidebar.header("Parcelle")
    width = st.sidebar.number_input("Largeur (m)", 6.0, 40.0, 12.0, 0.1)
    height = st.sidebar.number_input("Profondeur (m)", 6.0, 40.0, 10.0, 0.1)
    north = st.sidebar.slider("Nord (degres)", 0, 359, 0)
    edges = [
        st.sidebar.selectbox(f"Bord {i} ({side})", EDGE_NAMES, index=default)
        for i, (side, default) in enumerate(
            [("sud", 0), ("est", 3), ("nord", 1), ("ouest", 3)]
        )
    ]
    entry = st.sidebar.number_input("Bord d'entree", 0, 3, 0)

    st.sidebar.header("Recherche")
    seed = st.sidebar.number_input("Graine", 0, 9999, 3)
    iterations = st.sidebar.slider("Iterations", 0, 1000, 200, 20)
    return width, height, north, edges, entry, seed, iterations


def build_brief(width, height, north, edges, entry, rooms):
    import math

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
    budget = check_feasibility(programme, parcel, MA_PROFILE)
    return Brief(programme, parcel, MA_PROFILE, budget), budget


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

width, height, north, edges, entry, seed, iterations = sidebar()

st.subheader("Programme")
rooms = st.data_editor(
    [
        {"nom": n, "kind": k, "surface_utile": a, "orientation": o}
        for n, k, a, o in DEFAULT_ROOMS
    ],
    num_rows="dynamic",
    use_container_width=True,
    key="rooms",
)

with st.expander("Relations (L1)"):
    relations = st.data_editor(
        [{"a": a, "b": b, "kind": k, "weight": w} for a, b, k, w in DEFAULT_RELATIONS],
        num_rows="dynamic",
        use_container_width=True,
        key="relations",
    )

try:
    brief, budget = build_brief(width, height, north, edges, entry, rooms)
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
if note.kind == "band":
    st.caption(note.message)
elif note.kind == "tight":
    st.warning(note.message)
else:
    st.info(note.message)

if not st.button("Generer", type="primary"):
    st.info("Le graphe L1 ci-dessous existe deja. Le plan, non.")
    st.image(topology_svg(graph, brief.programme))
    st.stop()

stats = RunStats()
tree = seed_tree(brief.programme)
best = anneal(brief, tree, int(iterations), seed=int(seed), graph=graph, stats=stats)
if not best:
    st.error(f"Aucun candidat n'a passe les portes. {stats.explain()}")
    st.stop()

result = best[0]
plan = result.plan
fabric = plan.to_fabric(MA_PROFILE)
shafts = place_shafts(fabric, MA_PROFILE)
assign_wet_walls(fabric, shafts)
assign_stack_ids(Level(0, 2.80, fabric, shafts), grid_for(brief))
openings = place_openings(fabric, type("T", (), {"graph": graph})(), MA_PROFILE)

columns = st.columns(5)
for column, (label, value) in zip(
    columns,
    [
        ("Global", f"{result.scores.globale:.3f}"),
        ("Adjacences", f"{result.scores.adjacences:.3f}"),
        ("Orientation", f"{result.scores.orientation:.3f}"),
        ("Circulation", f"{plan.circulation_coefficient(MA_PROFILE) * 100:.1f} %"),
        ("Erreur surface", f"{plan.max_area_error(MA_PROFILE) * 100:.3f} %"),
    ],
):
    column.metric(label, value)
st.caption(stats.explain())

l1, l2, l3, l8 = st.tabs(
    ["L1 Topologie", "L2 Partition", "L3 Fabrique", "L8 Dessin"]
)

with l1:
    st.markdown(
        "Un graphe. Aucune geometrie. **C'est ce que v1 livrait en l'appelant un plan.**"
    )
    st.image(topology_svg(graph, brief.programme))

with l2:
    st.markdown("Des rectangles sur les axes : surface nette / cible.")
    st.image(partition_svg(plan, MA_PROFILE))

with l3:
    st.markdown("Les murs sont solides, les surfaces sont mesurees.")
    st.image(to_svg(fabric, "outputs/studio_preview.svg"))
    st.dataframe(
        [
            {
                "nom": nom,
                "surface_utile": round(space.surface_utile, 2),
                "cible": round(brief.programme.by_nom(nom).surface_utile, 2),
                "net": "%.2f x %.2f" % space.net_dims(),
            }
            for nom, space in fabric.spaces.items()
        ],
        use_container_width=True,
    )

with l8:
    st.markdown(f"{openings.explain()}")
    if openings.errors:
        for error in openings.errors:
            st.warning(error)
    chains = exterior_chains(fabric) + interior_chains(fabric)
    st.caption(f"{len(chains)} chaines de cotation")

    export_dxf(fabric, "outputs/studio.dxf", openings=openings, shafts=shafts)
    with open("outputs/studio.dxf", "rb") as handle:
        st.download_button("plan.dxf", handle.read(), "plan.dxf")
    st.download_button(
        "plan.json (Grasshopper)",
        json.dumps(to_gh_json(fabric, openings, shafts), indent=2, ensure_ascii=False),
        "plan.json",
        mime="application/json",
    )
