import importlib.util
import json
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


def test_offline_main_propagates_runtime_flags_into_report(tmp_path):
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
        "--no-project-exact-adjacency",
        "--category", "Walls",
        "--category", "Doors",
        "--cap", "5",
    ])

    assert code == 0
    report_path = tmp_path / "fixture.calibration.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    runtime = payload["fixtures"][0]["runtime"]
    assert runtime["projectExactAdjacency"] is False
    assert runtime["categoryFilters"] == ["Walls", "Doors"]
    assert runtime["cap"] == 5


def test_live_orchestration_runs_exact_before_refinement_and_never_passes_labels(monkeypatch, tmp_path):
    script = _load_script()
    model = tmp_path / "a.3dm"
    sidecar = tmp_path / "a.sidecar.json"
    validation = tmp_path / "a.validation.json"
    model.write_bytes(b"fake")
    sidecar.write_text(cal.json_dumps({
        "elements": [
            {
                "identity": {"uniqueId": "uid-wall", "elementId": 101},
                "category": "Walls",
                "name": "Wall 101",
                "labels": {
                    "hostId": {"value": None},
                    "containingRoomId": {"value": "room-1"},
                    "level": {"value": "L1"},
                },
            },
            {
                "identity": {"uniqueId": "uid-door", "elementId": 202},
                "category": "Doors",
                "name": "Door 202",
                "labels": {
                    "hostId": {"value": "uid-wall"},
                    "containingRoomId": {"value": "room-1"},
                    "level": {"value": "L1"},
                },
            },
        ],
        "rooms": [{"uniqueId": "room-1", "number": "101", "name": "Office", "level": {"value": "L1"}}],
        "relationships": {
            "hostMembership": [{"elementUniqueId": "uid-door", "hostUniqueId": "uid-wall"}],
            "roomMembership": [
                {"elementUniqueId": "uid-door", "roomUniqueId": "room-1"},
                {"elementUniqueId": "uid-wall", "roomUniqueId": "room-1"},
            ],
            "levelMembership": [
                {"elementUniqueId": "uid-door", "levelName": "L1"},
                {"elementUniqueId": "uid-wall", "levelName": "L1"},
            ],
        },
    }), encoding="utf-8")
    validation.write_text(cal.json_dumps({
        "relationships": {
            "hostMembership": {"count": 1},
            "roomMembership": {"count": 2},
            "levelMembership": {"count": 2},
        }
    }), encoding="utf-8")

    calls = []

    monkeypatch.setattr(script, "discover_port", lambda: 9876)
    monkeypatch.setattr(script, "open_fixture_in_isolated_context", lambda port, path: {
        "freshDocument": True,
        "documentStatus": {"attempted": True, "succeeded": True, "errors": []},
        "importStatus": {"attempted": True, "succeeded": True, "errors": []},
        "graphSequence": 7,
        "runtimeObjects": [
            {
                "runtimeId": "rook-wall",
                "name": "Wall 101",
                "layer": "RookBim::L1::Walls",
                "userStrings": {
                    "revit.uniqueId": "uid-wall",
                    "revit.elementId": "101",
                    "revit.category": "Walls",
                },
            },
            {
                "runtimeId": "rook-door",
                "name": "Door 202",
                "layer": "RookBim::L1::Doors",
                "userStrings": {
                    "revit.uniqueId": "uid-door",
                    "revit.elementId": "202",
                    "revit.category": "Doors",
                },
            },
        ],
    })

    def fake_exact(port, object_ids):
        calls.append(("exact", list(object_ids)))
        return {
            "attempted": True,
            "succeeded": True,
            "errors": [],
            "graphSequence": 7,
            "attemptedObjectCount": len(object_ids),
            "elapsedMs": 12,
        }

    def fake_refine(port, object_ids):
        calls.append(("refine", list(object_ids)))
        assert object_ids == ["rook-wall", "rook-door"]
        return {
            "status": {"attempted": True, "succeeded": True, "errors": []},
            "payload": {
                "success": True,
                "graphSequence": 7,
                "refined": [{
                    "candidateId": "rook-wall|contains|rook-door",
                    "containerId": "rook-wall",
                    "containedId": "rook-door",
                    "verdict": "contains_semantic",
                    "confidence": "high",
                    "reason": "strong_clearance_plausible_container",
                    "evidence": [{"signal": "bbox_margin", "polarity": "supports", "detail": "positive"}],
                }],
            },
        }

    monkeypatch.setattr(script, "run_exact_projection", fake_exact)
    monkeypatch.setattr(script, "run_containment_refinement", fake_refine)

    code = script.main([
        "--model3dm", str(model),
        "--sidecar", str(sidecar),
        "--validation", str(validation),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
    ])

    assert code == 0
    assert calls == [
        ("exact", ["rook-wall", "rook-door"]),
        ("refine", ["rook-wall", "rook-door"]),
    ]
    report_path = tmp_path / "fixture.calibration.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "live_calibration"
    runtime = payload["fixtures"][0]["runtime"]
    assert runtime["projectExactAdjacency"] is True
    assert runtime["sceneExactNeighbors"]["succeeded"] is True
    assert runtime["sceneRefineContainment"]["succeeded"] is True
