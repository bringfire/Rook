"""Gated live calibration for RookBIM threshold fixtures.

Offline mode validates fixture/report shape only. Live mode requires Rhino/Rook.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[3]
MCP_SRC = ROOT / "mcp_server" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from rook.scene import calibration as cal  # noqa: E402


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("--cap must be >= 0")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model3dm", required=True)
    parser.add_argument("--sidecar", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--project-exact-adjacency", dest="project_exact_adjacency", action="store_true", default=True)
    parser.add_argument("--no-project-exact-adjacency", dest="project_exact_adjacency", action="store_false")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--cap", type=_non_negative_int, default=None)
    return parser.parse_args(argv)


def run_offline(args) -> dict:
    paths = cal.FixturePaths(args.model3dm, args.sidecar, args.validation)
    loaded = cal.load_fixture_bundle(paths)
    report = cal.build_offline_fixture_validation_report(
        loaded.fixture,
        paths=loaded.paths,
        fixture_id=args.name,
    )
    report["fixtures"][0]["runtime"] = {
        "projectExactAdjacency": args.project_exact_adjacency,
        "freshDocument": None,
        "graphSequence": None,
        "sceneExactNeighbors": None,
        "sceneRefineContainment": None,
        "inputObjectCount": None,
        "joinedObjectCount": None,
        "evaluatedObjectCount": None,
        "categoryFilters": args.category,
        "cap": args.cap,
    }
    cal.write_report_bundle(report, args.output_dir, args.name)
    return report


def discover_port() -> int:
    from rook.bridge import discover_instances

    instances = discover_instances()
    for instance in instances:
        if instance.get("pluginType") != "native":
            continue
        port = instance.get("port")
        if isinstance(port, int):
            return port
        if isinstance(port, str) and port.isdigit():
            return int(port)
    raise RuntimeError("No native Rook instance found. Start Rhino/Rook before live calibration.")


def _decode_response(response) -> dict:
    return json.loads(response.read().decode("utf-8"))


def _post(port: int, path: str, payload: dict) -> dict:
    req = request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=180) as response:
        return _decode_response(response)


def _get(port: int, path: str) -> dict:
    with request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=180) as response:
        return _decode_response(response)


def _response_data(payload: dict) -> dict:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _status_from_response(payload: dict) -> dict:
    if payload.get("success") is True:
        return {"attempted": True, "succeeded": True, "errors": []}
    error = payload.get("error") or payload.get("data") or payload
    return {"attempted": True, "succeeded": False, "errors": [str(error)]}


def _runtime_object_id(obj: dict) -> str:
    runtime_id = obj.get("runtimeId") or obj.get("id") or obj.get("objectId")
    return str(runtime_id) if runtime_id else ""


def _runtime_object_user_strings(obj: dict) -> dict:
    raw = obj.get("userStrings") or obj.get("user_strings") or {}
    return raw if isinstance(raw, dict) else {}


def _runtime_object_revit_uid(obj: dict) -> str | None:
    value = _runtime_object_user_strings(obj).get("revit.uniqueId") or obj.get("revitUniqueId")
    return str(value) if value else None


def _runtime_object_category(obj: dict) -> str | None:
    strings = _runtime_object_user_strings(obj)
    value = (
        strings.get("revit.category")
        or obj.get("revitCategory")
        or obj.get("category")
    )
    return str(value) if value else None


def open_fixture_in_isolated_context(port: int, model3dm: str) -> dict:
    document_response = _post(port, "/document/new", {})
    document_status = _status_from_response(document_response)
    if not document_status["succeeded"]:
        raise RuntimeError(f"failed to create fresh document: {document_status['errors'][0]}")

    import_response = _post(port, "/import", {"path": model3dm})
    import_status = _status_from_response(import_response)
    if not import_status["succeeded"]:
        raise RuntimeError(f"failed to import fixture: {import_status['errors'][0]}")

    import_data = _response_data(import_response)
    imported_ids = import_data.get("importedIds") or import_response.get("importedIds") or []
    imported_id_set = {str(value) for value in imported_ids if value}

    graph_response = _get(port, f"/scene/graph?{parse.urlencode({'depth': 'full'})}")
    graph_status = _status_from_response(graph_response)
    if not graph_status["succeeded"]:
        raise RuntimeError(f"failed to fetch scene graph: {graph_status['errors'][0]}")

    graph_data = _response_data(graph_response) or graph_response
    nodes = graph_data.get("nodes") or []
    runtime_objects = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        runtime_id = _runtime_object_id(node)
        if not runtime_id:
            continue
        if imported_id_set and runtime_id not in imported_id_set:
            continue
        if not _runtime_object_revit_uid(node):
            continue
        runtime_objects.append({
            "runtimeId": runtime_id,
            "name": str(node.get("name") or ""),
            "layer": str(node.get("layer") or ""),
            "userStrings": _runtime_object_user_strings(node),
        })

    return {
        "freshDocument": True,
        "documentStatus": document_status,
        "importStatus": import_status,
        "graphStatus": graph_status,
        "importedIds": sorted(imported_id_set),
        "runtimeObjects": runtime_objects,
        "graphSequence": graph_data.get("sequence"),
    }


def run_exact_projection(port: int, object_ids: list[str]) -> dict:
    from rook.scene.exact_projection import get_exact_projector
    from rook.scene.scene_graph import get_scene_graph

    started = time.perf_counter()
    try:
        graph = get_scene_graph()
        projector = get_exact_projector(graph)
        result = asyncio.run(projector.project(object_ids, port=port))
    except Exception as exc:
        return {
            "attempted": True,
            "succeeded": False,
            "errors": [str(exc)],
            "graphSequence": None,
            "attemptedObjectCount": len(object_ids),
            "elapsedMs": int((time.perf_counter() - started) * 1000),
        }

    errors = []
    if result.get("success") is not True:
        errors.append(str(result.get("error") or result))
    for block in result.get("projected") or []:
        if not isinstance(block, dict):
            continue
        route_status = block.get("routeStatus")
        if route_status in ("ok", "skipped", None):
            continue
        source_id = block.get("sourceId")
        error = block.get("error") or route_status
        errors.append(f"{source_id}: {error}" if source_id else str(error))

    return {
        "attempted": True,
        "succeeded": result.get("success") is True and not errors,
        "errors": errors,
        "graphSequence": result.get("graphSequence"),
        "attemptedObjectCount": len(object_ids),
        "elapsedMs": int((time.perf_counter() - started) * 1000),
    }


def run_containment_refinement(port: int, object_ids: list[str]) -> dict:
    from rook.scene.containment_refinement import get_containment_refiner
    from rook.scene.scene_graph import get_scene_graph

    graph = get_scene_graph()
    refiner = get_containment_refiner(graph)
    result = asyncio.run(refiner.refine(object_ids, port=port))
    if result.get("success") is not True:
        raise RuntimeError(f"scene_refine_containment failed: {result}")

    failed_sources = [
        source_id for source_id, block in (result.get("bySource") or {}).items()
        if isinstance(block, dict) and block.get("status") == "failed"
    ]
    if failed_sources:
        raise RuntimeError(f"scene_refine_containment failed for sources: {', '.join(failed_sources)}")

    return {
        "status": {"attempted": True, "succeeded": True, "errors": []},
        "payload": result,
    }


def _bounded_object_ids(runtime_objects: list[dict], categories: list[str], cap: int | None) -> list[str]:
    if cap is not None and cap < 0:
        raise ValueError("cap must be >= 0")

    category_filter = {value.casefold() for value in categories}
    object_ids: list[str] = []
    for obj in runtime_objects:
        runtime_id = _runtime_object_id(obj)
        if not runtime_id:
            continue
        category = _runtime_object_category(obj)
        if category_filter and (category is None or category.casefold() not in category_filter):
            continue
        object_ids.append(runtime_id)
        if cap is not None and len(object_ids) >= cap:
            break
    return object_ids


def run_live(args) -> dict:
    paths = cal.FixturePaths(args.model3dm, args.sidecar, args.validation)
    loaded = cal.load_fixture_bundle(paths)
    port = discover_port()
    context = open_fixture_in_isolated_context(port, args.model3dm)
    runtime_objects = context.get("runtimeObjects") or []
    join = cal.build_runtime_join_map(runtime_objects, loaded.fixture)
    object_ids = _bounded_object_ids(runtime_objects, args.category, args.cap)

    exact_status = {
        "attempted": False,
        "succeeded": False,
        "skipped": True,
        "errors": [],
        "graphSequence": context.get("graphSequence"),
        "attemptedObjectCount": len(object_ids),
        "elapsedMs": 0,
    }
    if args.project_exact_adjacency:
        exact_status = run_exact_projection(port, object_ids)

    refinement = run_containment_refinement(port, object_ids)
    candidates = cal.build_candidate_records(refinement["payload"], join, loaded.fixture)
    classified = [cal.classify_candidate(candidate, loaded.fixture) for candidate in candidates]
    classified = cal.add_missed_labeled_relation_records(
        classified,
        join,
        loaded.fixture,
        evaluated_runtime_ids=set(object_ids),
    )

    runtime = cal.RuntimeSummary(
        project_exact_adjacency=args.project_exact_adjacency,
        fresh_document=context.get("freshDocument"),
        graph_sequence=refinement["payload"].get("graphSequence") or exact_status.get("graphSequence") or context.get("graphSequence"),
        scene_exact_neighbors=exact_status,
        scene_refine_containment=refinement["status"],
        input_object_count=len(runtime_objects),
        joined_object_count=len(join.by_runtime_id),
        evaluated_object_count=len(object_ids),
        category_filters=list(args.category),
        cap=args.cap,
    )
    report = cal.build_live_calibration_report(
        loaded.fixture,
        paths=loaded.paths,
        fixture_id=args.name,
        runtime=runtime,
        candidates=classified,
    )
    report["fixtures"][0]["runtime"]["documentStatus"] = context.get("documentStatus")
    report["fixtures"][0]["runtime"]["importStatus"] = context.get("importStatus")
    report["fixtures"][0]["runtime"]["sceneGraphStatus"] = context.get("graphStatus")
    cal.write_report_bundle(report, args.output_dir, args.name)
    return report


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.offline:
        run_offline(args)
        return 0
    run_live(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
