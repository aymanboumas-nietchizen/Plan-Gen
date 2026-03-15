"""
tests/test_export.py
Unit tests for export/dxf.py and export/json_export.py.
"""

import json, os, pytest
from planfgen.core.geometry   import Envelope
from planfgen.export.json_export import export_json


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "apartment_7rooms.json")

@pytest.fixture
def envelope():
    return Envelope.from_rect(12.0, 9.0)

@pytest.fixture
def apartment_placed():
    """Generate a real layout from the apartment fixture."""
    import json
    from planfgen.core.generator import generate_layout
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    prog = data["programme"]
    adjs = [tuple(a) for a in data["adjacencies"]]
    placed = generate_layout(prog, adjs, 12.0, 9.0, seed=0)
    scores = {"adjacences": 0.9, "compacite": 0.85, "facade": 0.8, "couverture": 0.9, "global": 0.88}
    return placed, scores


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def test_json_file_created(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    assert os.path.exists(out)
    assert out.endswith(".json")

def test_json_valid(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)  # must not raise
    assert isinstance(data, dict)

def test_json_rooms_complete(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    room_names = {r["nom"] for r in data["rooms"]}
    assert "Séjour" in room_names
    assert len(data["rooms"]) == 7

def test_json_metadata_keys(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=42, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    meta = data["metadata"]
    assert "seed" in meta
    assert meta["seed"] == 42
    assert "score_global" in meta
    assert "envelope" in meta
    assert "generated_at" in meta
    assert meta["envelope"]["W"] == 12.0
    assert meta["envelope"]["H"] == 9.0
    assert "coords" in meta["envelope"]

def test_json_on_facade_present(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    for room in data["rooms"]:
        assert "on_facade" in room, f"on_facade missing from {room['nom']}"
        assert isinstance(room["on_facade"], bool)

def test_json_room_coords_present(apartment_placed, envelope, tmp_path):
    """Rooms include polygon coords in export."""
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    for room in data["rooms"]:
        assert "coords" in room, f"coords missing from {room['nom']}"
        assert len(room["coords"]) >= 4

def test_json_backward_compat_w_h(apartment_placed, tmp_path):
    """Old W=, H= keyword calling convention still works."""
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, W=12, H=9, filename=str(tmp_path / "layout"))
    assert os.path.exists(out)
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert data["metadata"]["envelope"]["W"] == 12.0

def test_json_scores_keys(apartment_placed, envelope, tmp_path):
    placed, scores = apartment_placed
    out = export_json(placed, scores, seed=0, envelope_or_W=envelope, filename=str(tmp_path / "layout"))
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert "adjacences" in data["scores"]
    assert "global" in data["scores"]


# ---------------------------------------------------------------------------
# DXF export
# ---------------------------------------------------------------------------

def test_dxf_created(apartment_placed, tmp_path):
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")
    from planfgen.export.dxf import export_dxf
    placed, _ = apartment_placed
    out = export_dxf(placed, "test_layout", 12, 9, output_dir=str(tmp_path))
    assert os.path.exists(out)
    assert out.endswith(".dxf")

def test_dxf_no_error_on_open(apartment_placed, tmp_path):
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")
    from planfgen.export.dxf import export_dxf
    placed, _ = apartment_placed
    out = export_dxf(placed, "test_layout", 12, 9, output_dir=str(tmp_path))
    doc = ezdxf.readfile(out)  # must not raise
    assert doc is not None

def test_dxf_layer_names(apartment_placed, tmp_path):
    try:
        import ezdxf
    except ImportError:
        pytest.skip("ezdxf not installed")
    from planfgen.export.dxf import export_dxf
    placed, _ = apartment_placed
    out = export_dxf(placed, "test_layout", 12, 9, output_dir=str(tmp_path))
    doc = ezdxf.readfile(out)
    layer_names = {layer.dxf.name for layer in doc.layers}
    assert "ENVELOPE" in layer_names
    # At least one room layer must exist
    assert len(layer_names) > 1
