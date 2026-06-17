import importlib.util
from pathlib import Path

from rook.scene import calibration as cal


SCRIPT = Path(__file__).parents[2] / "docs" / "rook_docs" / "rookbim-export-spike" / "live_calibrate_containment_fixture.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("live_calibrate_containment_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults_exact_projection_on(tmp_path):
    script = _load_script()
    args = script.parse_args([
        "--model3dm", str(tmp_path / "a.3dm"),
        "--sidecar", str(tmp_path / "a.sidecar.json"),
        "--validation", str(tmp_path / "a.validation.json"),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
        "--offline",
    ])

    assert args.project_exact_adjacency is True
    assert args.offline is True


def test_offline_main_writes_schema_report(monkeypatch, tmp_path):
    script = _load_script()
    model = tmp_path / "a.3dm"
    sidecar = tmp_path / "a.sidecar.json"
    validation = tmp_path / "a.validation.json"
    model.write_bytes(b"fake")
    sidecar.write_text(cal.json_dumps({
        "elements": [{"identity": {"uniqueId": "u1", "elementId": 1}, "category": "Walls", "labels": {}}],
        "rooms": [],
        "relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}},
    }), encoding="utf-8")
    validation.write_text(cal.json_dumps({"relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}}}), encoding="utf-8")

    code = script.main([
        "--model3dm", str(model),
        "--sidecar", str(sidecar),
        "--validation", str(validation),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
        "--offline",
    ])

    assert code == 0
    report = tmp_path / "fixture.calibration.json"
    assert report.exists()
    assert '"mode": "offline_fixture_validation"' in report.read_text(encoding="utf-8")
