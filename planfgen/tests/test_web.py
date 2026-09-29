"""Web studio — the HTTP API over `studio.pipeline`, tested without a browser.

What is pinned is what the page relies on: a brief the form can send builds, a
bad one is refused with a French message and never reaches a worker, one
request is one option with its drawing, and a download does not depend on the
server remembering anything — the same seed is the same plan.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("starlette", reason="the web studio rides on the studio extra")
pytest.importorskip("uvicorn", reason="the web studio rides on the studio extra")

import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from contextlib import contextmanager  # noqa: E402

import uvicorn  # noqa: E402

from web import engine  # noqa: E402
from web.server import create_app  # noqa: E402


class Reply:
    """What a request came back with."""

    def __init__(self, status: int, headers, content: bytes):
        self.status_code = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self):
        return json.loads(self.content)


class Client:
    """The real server on a free local port, spoken to with the standard library.

    `starlette.testclient` needs `httpx2`, which the studio extra does not bring;
    a live uvicorn is closer to what the architect runs anyway.
    """

    def __init__(self, base: str):
        self.base = base

    def _send(self, path: str, data: bytes | None, headers: dict) -> Reply:
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=300) as r:
                return Reply(r.status, dict(r.headers), r.read())
        except urllib.error.HTTPError as e:
            return Reply(e.code, dict(e.headers), e.read())

    def get(self, path: str) -> Reply:
        return self._send(path, None, {})

    def post(self, path: str, json: dict | None = None, content: bytes | None = None) -> Reply:
        data = content if content is not None else __import__("json").dumps(json).encode()
        return self._send(path, data, {"Content-Type": "application/json"})


@contextmanager
def TestClient(app):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("the web studio did not start")
        time.sleep(0.02)
    try:
        yield Client(f"http://127.0.0.1:{port}")
    finally:
        server.should_exit = True
        thread.join(timeout=10)

ITER = 200


def _first(ok: bool) -> int | None:
    """The first seed of F4 on the decret that passes (or is refused). Found, not
    pinned: the search is being rewritten, and on 2026-09-29 it was 1 and 2."""
    for seed in range(1, 13):
        if engine.run(engine.default_spec("F4", "economique"), seed, ITER).payload["ok"] is ok:
            return seed
    return None


PASSES = _first(True)
REFUSED = _first(False)
needs_refusal = pytest.mark.skipif(REFUSED is None, reason="no F4 seed in 1..12 is refused")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(lambda: ThreadPoolExecutor(2))) as c:
        yield c


def f4() -> dict:
    return engine.default_spec("F4", "economique")


def generate(client, spec, seed=PASSES, iterations=ITER):
    return client.post("/api/unit/generate", json={"spec": spec, "seed": seed, "iterations": iterations})


# --- the page and its data ---------------------------------------------------


def test_some_seed_of_the_f4_preset_passes():
    assert PASSES is not None, "no F4 seed in 1..12 generates on the decret"


def test_the_page_and_its_modules_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and 'lang="fr"' in page.text
    for asset in ("app.js", "plan.js", "style.css"):
        assert client.get(f"/static/{asset}").status_code == 200
    assert client.get("/favicon.ico").status_code == 204


def test_meta_carries_every_preset_and_profile(client):
    meta = client.get("/api/meta").json()
    assert set(meta["presets"]) == set(engine.PRESETS)
    assert set(meta["profiles"]) == {"economique", "casablanca", "placeholder"}
    assert set(meta["edges"]) == {"STREET", "COURT", "GARDEN", "MITOYEN", "RETRAIT"}
    assert meta["sides"] == ["bas", "droite", "haut", "gauche"]


def test_every_preset_is_a_brief_the_engine_builds():
    for key in engine.PRESETS:
        for profile in engine.PROFILE_LABELS:
            brief, graph = engine.build(engine.default_spec(key, profile))
            assert brief.budget.ok, (key, profile, brief.budget.explain())
            assert graph.relations


def test_check_reports_the_budget_and_the_spine(client):
    check = client.post("/api/unit/check", json={"spec": f4()}).json()
    assert check["ok"] and check["slack"] > 0
    assert "Couloir" in check["spine"]


def test_a_lot_too_small_is_not_ok(client):
    spec = f4() | {"width": 6.0, "depth": 6.0}
    check = client.post("/api/unit/check", json={"spec": spec}).json()
    assert not check["budget_ok"] and check["slack"] < 0


# --- refusals, in French, before any worker runs ---------------------------------


@pytest.mark.parametrize(
    "change, words",
    [
        ({"profile": "paris"}, "Profil"),
        ({"width": "large"}, "width"),
        ({"width": 1.0}, "entre"),
        ({"edges": ["STREET", "MITOYEN"]}, "quatre limites"),
        ({"entry_edge": 1}, "Rue ou Jardin"),
        ({"rooms": []}, "vide"),
    ],
)
def test_a_bad_brief_is_refused_with_a_french_message(client, change, words):
    response = generate(client, f4() | change)
    assert response.status_code == 422
    assert words in response.json()["error"]


def test_two_rooms_with_one_name_are_refused():
    spec = f4()
    spec["rooms"] = spec["rooms"] + [dict(spec["rooms"][0])]
    with pytest.raises(engine.BriefError, match="Deux pièces"):
        engine.build(spec)


def test_a_relation_to_a_deleted_room_is_dropped_not_an_error():
    spec = f4()
    spec["rooms"] = [r for r in spec["rooms"] if r["nom"] != "Ch3"]
    _, graph = engine.build(spec)
    assert all("Ch3" not in (r.a, r.b) for r in graph.relations)


def test_effort_and_seed_are_bounded(client):
    assert generate(client, f4(), iterations=10**6).status_code == 422
    assert generate(client, f4(), seed=-1).status_code == 422
    assert client.post("/api/unit/generate", content=b"not json").status_code == 422


# --- one option ----------------------------------------------------------------


def test_an_option_is_a_drawn_plan_with_scores(client):
    option = generate(client, f4()).json()

    assert option["ok"], option.get("refusal")
    assert set(option["scores"]) == {"adjacences", "orientation", "circulation", "compacite", "globale"}
    assert 0 < option["scores"]["globale"] <= 1
    assert option["area_error"] <= 0.05
    assert "Emprise" in option["note"]

    doc = option["document"]
    assert doc["schema_version"] == "2.0"
    assert doc["solids"], "the walls, as poché"
    assert doc["openings"]["doors"] and doc["openings"]["windows"]
    assert len(doc["footprint"]) == 4

    noms = {room["nom"] for room in option["rooms"]}
    assert noms == {r["nom"] for r in f4()["rooms"]}
    for room in option["rooms"]:
        if room["kind"] == "COULOIR":
            assert room["error"] is None, "a corridor has a width, its area is a result"
        else:
            assert abs(room["error"]) <= 0.05


def test_the_net_area_on_the_card_is_the_net_polygon(client):
    """What is coloured is what is stamped: the net area, not the axis area."""
    from shapely.geometry import Polygon

    doc = generate(client, f4()).json()["document"]
    for space in doc["spaces"]:
        assert abs(Polygon(space["net_outline"]).area - space["surface_utile"]) < 1e-3
        assert space["surface_utile"] < space["axis_area"]


def test_the_poche_has_the_openings_cut_out(client):
    """A door is a gap in the wall, not a symbol laid over a solid one."""
    from shapely.geometry import Point, Polygon

    doc = generate(client, f4()).json()["document"]
    walls = [Polygon(rings[0], rings[1:]) for rings in doc["solids"]]
    for door in doc["openings"]["doors"]:
        x, y = door["position"]
        assert not any(w.contains(Point(x, y)) for w in walls), door


@needs_refusal
def test_a_refused_option_says_which_gates_refused_it(client):
    option = generate(client, f4(), seed=REFUSED).json()

    assert not option["ok"]
    assert "document" not in option
    assert option["refusal"].startswith("Aucun des")
    assert any(label in option["refusal"] for label in engine.GATE_LABELS.values())
    assert sum(option["stats"]["rejected_by"].values()) > 0


def test_opening_errors_are_translated():
    assert engine.opening_error(
        "Entree~Sejour: 0.00 m of shared wall, under the 1.00 m a door needs"
    ) == "Porte Entree – Sejour impossible : 0.00 m de mur commun, il en faut 1.00 m."
    assert "pas de jour" in engine.opening_error(
        "Ch2: needs daylight and has no openable exterior wall"
    )
    assert engine.opening_error("something new") == "something new"


# --- the same seed is the same plan: downloads need no server memory ------------


def test_the_same_request_is_the_same_plan(client):
    a = generate(client, f4()).json()
    b = engine.run(f4(), PASSES, ITER).payload
    assert a["key"] == b["key"]
    assert a["document"]["spaces"] == b["document"]["spaces"]


def test_the_dxf_downloads_from_the_cache_and_after_a_restart(client):
    body = {"spec": f4(), "seed": PASSES, "iterations": ITER, "format": "dxf"}
    cached = client.post("/api/unit/export", json=body)
    assert cached.status_code == 200
    assert cached.content.startswith(b"  0\r\nSECTION") or b"SECTION" in cached.content[:40]
    assert f'filename="planfgen_F4_economique_graine{PASSES}.dxf"' in cached.headers["content-disposition"]

    with TestClient(create_app(lambda: ThreadPoolExecutor(1))) as fresh:
        again = fresh.post("/api/unit/export", json=body)
    assert again.status_code == 200
    assert b"MUR_FACADE" in again.content and b"OUVERTURE_PORTE" in again.content


def test_the_grasshopper_json_is_the_bridge_document(client):
    body = {"spec": f4(), "seed": PASSES, "iterations": ITER, "format": "gh"}
    doc = json.loads(client.post("/api/unit/export", json=body).content)
    assert doc["schema_version"] == "2.0" and doc["units"] == "m"
    assert "solids" not in doc, "the bridge carries axes, not the page's drawing"


@needs_refusal
def test_a_refused_option_has_nothing_to_export(client):
    body = {"spec": f4(), "seed": REFUSED, "iterations": ITER, "format": "dxf"}
    assert client.post("/api/unit/export", json=body).status_code == 409


def test_options_run_in_parallel_in_worker_processes(monkeypatch):
    """The real pool, as the studio starts it: four requests, four processes.

    A spawned worker re-imports the parent's `__main__`. Under `python -m web`
    that is the guarded `web/__main__.py`; in a full test run, Streamlit's
    `AppTest` (test_studio) has left `planfgen/studio/app.py` there, and every
    worker would run the Streamlit page. So the test gives the pool a bare one.
    """
    import sys
    import types
    from concurrent.futures import as_completed

    from web.server import _process_pool

    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))

    spec = f4()
    with _process_pool() as pool:
        futures = [pool.submit(engine.run, spec, seed, 60) for seed in (1, 2, 3, 4)]
        options = [f.result() for f in as_completed(futures)]
    assert sorted(o.payload["seed"] for o in options) == [1, 2, 3, 4]
    assert all(isinstance(o.payload["ok"], bool) for o in options)


# --- the project: building > storey > unit ------------------------------------------

from web import project  # noqa: E402


def test_the_default_project_is_a_building_not_a_flat(client):
    doc = client.get("/api/project/default").json()
    assert doc["schema"] == project.SCHEMA
    assert len(doc["storeys"]) >= 2 and len(doc["units"]) >= 2
    assert any(len(s["slots"]) >= 2 for s in doc["storeys"]), "a plate carries several flats"


def test_the_summary_counts_storeys_flats_and_frontage(client):
    doc = project.default_project()
    summary = client.post("/api/building/summary", json={"project": doc}).json()

    assert summary["height"] == "R+2" and summary["levels"] == 3
    assert summary["logements"] == 5 and summary["mix"] == {"F3": 2, "F4": 3}
    courant = next(s for s in summary["storeys"] if s["kind"] == "COURANT")
    assert courant["frontage"] == 20.0 and courant["free"] == 4.0 and courant["fits"]
    assert summary["utile"] == 99.0 + 2 * (75.0 + 99.0)


def test_a_plate_wider_than_the_lot_does_not_fit():
    doc = project.default_project()
    doc["lot"]["width"] = 18.0
    courant = next(s for s in project.summary(doc)["storeys"] if s["kind"] == "COURANT")
    assert not courant["fits"] and courant["free"] == -2.0


def test_a_storey_placing_an_unknown_unit_is_refused(client):
    doc = project.default_project()
    doc["storeys"][0]["slots"].append({"unit": "Z"})
    reply = client.post("/api/building/summary", json={"project": doc})
    assert reply.status_code == 422 and "inconnu" in reply.json()["error"]


def test_the_storey_route_exists_and_says_it_is_not_built_yet(client):
    reply = client.post("/api/storey/generate", json={"project": project.default_project()})
    assert reply.status_code == 501
    assert "S19" in reply.json()["error"]


def test_a_unit_is_generated_in_its_slot_between_blind_walls():
    doc = project.default_project()
    doc["lot"]["edges"] = ["STREET", "STREET", "GARDEN", "MITOYEN"]  # a corner lot
    spec = project.unit_spec(doc, "A")

    assert (spec["width"], spec["depth"]) == (9.0, 11.0), "the slot, not the 24 m lot"
    assert spec["edges"] == ["STREET", "MITOYEN", "GARDEN", "MITOYEN"]
    assert set(spec) == set(engine.default_spec()), "the unit brief is the engine brief"
    engine.build(spec)


def test_the_page_composes_the_unit_brief_with_the_same_fields():
    """`unitSpec` in app.js mirrors `project.unit_spec`: same keys, nothing more."""
    import re
    from pathlib import Path

    source = (Path(engine.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    body = re.search(r"function unitSpec\(uid\) \{(.*?)\n\}", source, re.S).group(1)
    returned = re.search(r"return \{(.*?)\};", body, re.S).group(1)
    keys = set(re.findall(r"^\s*(\w+)\s*[:,]", returned, re.M))
    assert keys == set(engine.default_spec())


def test_every_default_unit_generates_in_its_slot():
    """The demo is not a hand-calibrated fixture: both unit types of the default
    project pass on some seed of the first six."""
    doc = project.default_project()
    for unit in doc["units"]:
        spec = project.unit_spec(doc, unit["id"])
        assert any(engine.run(spec, seed, ITER).payload["ok"] for seed in range(1, 7)), unit["id"]
