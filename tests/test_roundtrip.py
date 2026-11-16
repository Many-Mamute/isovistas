"""Self-contained tests (no third-party images): python -m pytest -q"""
import copy
import json
import math
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "examples/peca_n.json").read_text())


@pytest.fixture(scope="module")
def model():
    from isovista.spec import Model
    return Model(SPEC)


def test_build(model):
    assert model.solid.is_valid
    assert abs(model.solid.volume - 88219.7) < 1.0


def test_drawing_lint(model, tmp_path):
    from isovista.drawing import make_drawing
    dr, rec = make_drawing(model, str(tmp_path / "d"), pdf=False)
    texts = [d["text"] for d in rec["dims"]]
    for must in ("Ø40", "Ø20", "Ø30", "R25", "R30", "150°", "110", "70", "60"):
        assert must in texts, must
    assert rec["stats"]["text_text"] == 0
    assert not any("sem vista" in l or "sai da zona" in l for l in rec["lint"])


def test_compare_detects_errors(model):
    from isovista.spec import Model
    from isovista.compare import compare
    same = compare(model, Model(copy.deepcopy(SPEC)))
    assert same["ok"] and same["iou"] > 0.999
    b = copy.deepcopy(SPEC)
    for f in b["f"]:
        if f.get("id") == "cubo":
            f["d"] = 42
    diff = compare(model, Model(b))
    assert not diff["ok"] and diff["regions"]


def test_iso_and_fit(model, tmp_path):
    """Render the isometric figure, detect its grid and fit the model back onto it."""
    from build123d import Vector
    from isovista.iso import iso_drawing
    from isovista.image import detect_grid, fit
    from isovista.geom import basis
    rec = iso_drawing(model, str(tmp_path / "iso"), pdf=False)
    vd, R, U = basis(rec["dir"], (0, 0, 1))
    O, k = rec["origin_paper"], rec["k"]
    s = 150 / 25.4
    def px(p):
        p = Vector(*p)
        return ((O[0] + p.dot(R) * k) * s, (O[1] - p.dot(U) * k) * s)
    pts = [(0, 0, 0), (60, 0, 0), (0, 70, 0), (0, 0, 60), (-55, 10, 10), (55, 60, 10)]
    corr = [[*p, *px(p)] for p in pts]
    g = detect_grid(str(tmp_path / "iso.png"))
    assert abs(g["families"][2]["sp"] - 10 * math.cos(math.radians(30)) * s) < 1.5
    r = fit(model, str(tmp_path / "iso.png"), corr, grid=g)
    assert r["precision"] > 0.95
