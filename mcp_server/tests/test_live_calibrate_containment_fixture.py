import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
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


def test_open_fixture_in_isolated_context_hydrates_usertext_when_scene_graph_lacks_user_strings(monkeypatch):
    script = _load_script()

    def fake_post(port, path, payload):
        if path == "/document/new":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rook-wall"]}}
        if path == "/usertext/object-get":
            assert payload == {"id": "rook-wall"}
            return {
                "success": True,
                "data": {
                    "id": "rook-wall",
                    "userStrings": {
                        "revit.uniqueId": "uid-wall",
                        "revit.elementId": "101",
                        "revit.category": "Walls",
                    },
                },
            }
        raise AssertionError(path)

    def fake_get(port, path):
        assert path == "/scene/graph?depth=full"
        return {
            "success": True,
            "data": {
                "sequence": 9,
                "nodes": [
                    {"id": "rook-wall", "name": "Wall 101", "layer": "RookBim::L1::Walls"},
                ],
            },
        }

    monkeypatch.setattr(script, "_post", fake_post)
    monkeypatch.setattr(script, "_get", fake_get)

    context = script.open_fixture_in_isolated_context(9876, "fixture.3dm")

    assert context["graphSequence"] == 9
    assert context["runtimeObjects"] == [{
        "runtimeId": "rook-wall",
        "name": "Wall 101",
        "layer": "RookBim::L1::Walls",
        "userStrings": {
            "revit.uniqueId": "uid-wall",
            "revit.elementId": "101",
            "revit.category": "Walls",
        },
    }]


def test_open_fixture_in_isolated_context_raises_when_imported_nodes_lack_revit_metadata(monkeypatch):
    script = _load_script()

    def fake_post(port, path, payload):
        if path == "/document/new":
            return {"success": True, "data": {}}
        if path == "/import":
            return {"success": True, "data": {"importedIds": ["rook-wall"]}}
        if path == "/usertext/object-get":
            return {"success": True, "data": {"id": "rook-wall", "userStrings": {}}}
        raise AssertionError(path)

    def fake_get(port, path):
        return {
            "success": True,
            "data": {
                "sequence": 9,
                "nodes": [
                    {"id": "rook-wall", "name": "Wall 101", "layer": "RookBim::L1::Walls"},
                ],
            },
        }

    monkeypatch.setattr(script, "_post", fake_post)
    monkeypatch.setattr(script, "_get", fake_get)

    with pytest.raises(RuntimeError) as exc:
        script.open_fixture_in_isolated_context(9876, "fixture.3dm")

    assert "revit.uniqueId" in str(exc.value)


def test_run_live_raises_when_no_evaluated_objects_without_filters(monkeypatch, tmp_path):
    script = _load_script()
    model = tmp_path / "a.3dm"
    sidecar = tmp_path / "a.sidecar.json"
    validation = tmp_path / "a.validation.json"
    model.write_bytes(b"fake")
    sidecar.write_text(cal.json_dumps({
        "elements": [{"identity": {"uniqueId": "uid-wall", "elementId": 101}, "category": "Walls", "labels": {}}],
        "rooms": [],
        "relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}},
    }), encoding="utf-8")
    validation.write_text(cal.json_dumps({"relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}}}), encoding="utf-8")

    monkeypatch.setattr(script, "discover_port", lambda: 9876)
    monkeypatch.setattr(script, "open_fixture_in_isolated_context", lambda port, path: {
        "freshDocument": True,
        "documentStatus": {"attempted": True, "succeeded": True, "errors": []},
        "importStatus": {"attempted": True, "succeeded": True, "errors": []},
        "graphStatus": {"attempted": True, "succeeded": True, "errors": []},
        "graphSequence": 7,
        "importedIds": ["rook-wall"],
        "runtimeObjects": [],
    })

    with pytest.raises(RuntimeError) as exc:
        script.main([
            "--model3dm", str(model),
            "--sidecar", str(sidecar),
            "--validation", str(validation),
            "--output-dir", str(tmp_path),
            "--name", "fixture",
        ])

    assert "No evaluable runtime objects" in str(exc.value)
    assert not (tmp_path / "fixture.calibration.json").exists()


def test_run_exact_projection_marks_skipped_sources_unsuccessful(monkeypatch):
    script = _load_script()
    import rook.scene.exact_projection as exact_projection
    import rook.scene.scene_graph as scene_graph

    class FakeProjector:
        async def project(self, object_ids, port=None):
            return {
                "success": True,
                "graphSequence": 11,
                "projected": [
                    {"sourceId": "rook-wall", "routeStatus": "skipped", "error": "object_not_in_scene"},
                ],
            }

    monkeypatch.setattr(scene_graph, "get_scene_graph", lambda: object())
    monkeypatch.setattr(exact_projection, "get_exact_projector", lambda graph: FakeProjector())

    status = script.run_exact_projection(9876, ["rook-wall"])

    assert status["succeeded"] is False
    assert "rook-wall" in status["errors"][0]


def test_run_containment_refinement_raises_when_source_status_is_skipped(monkeypatch):
    script = _load_script()
    import rook.scene.containment_refinement as containment_refinement
    import rook.scene.scene_graph as scene_graph

    class FakeRefiner:
        async def refine(self, object_ids, port=None):
            return {
                "success": True,
                "graphSequence": 5,
                "refined": [],
                "bySource": {
                    "rook-wall": {"status": "skipped", "error": "object_not_in_scene", "asContainer": [], "asContained": []},
                },
            }

    monkeypatch.setattr(scene_graph, "get_scene_graph", lambda: object())
    monkeypatch.setattr(containment_refinement, "get_containment_refiner", lambda graph: FakeRefiner())

    with pytest.raises(RuntimeError) as exc:
        script.run_containment_refinement(9876, ["rook-wall"])

    assert "rook-wall" in str(exc.value)
    assert "skipped" in str(exc.value)


def test_run_containment_refinement_raises_when_source_status_is_missing(monkeypatch):
    script = _load_script()
    import rook.scene.containment_refinement as containment_refinement
    import rook.scene.scene_graph as scene_graph

    class FakeRefiner:
        async def refine(self, object_ids, port=None):
            return {
                "success": True,
                "graphSequence": 5,
                "refined": [],
                "bySource": {},
            }

    monkeypatch.setattr(scene_graph, "get_scene_graph", lambda: object())
    monkeypatch.setattr(containment_refinement, "get_containment_refiner", lambda graph: FakeRefiner())

    with pytest.raises(RuntimeError) as exc:
        script.run_containment_refinement(9876, ["rook-wall"])

    assert "rook-wall" in str(exc.value)
    assert "missing" in str(exc.value)


def test_post_decodes_http_error_json_body(monkeypatch):
    script = _load_script()

    def fake_urlopen(req, timeout=180):
        raise HTTPError(
            url="http://127.0.0.1:9876/document/new",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"success": false, "error": "structured failure"}'),
        )

    monkeypatch.setattr(script.request, "urlopen", fake_urlopen)

    payload = script._post(9876, "/document/new", {})

    assert payload["success"] is False
    assert payload["error"] == "structured failure"
