from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any


WORKFLOW_NAME = "rookbim_export_preset_to_rhino"

EXPORT_FIELD_NAMES = {
    "preset",
    "output",
    "scope",
    "includeCategories",
    "excludeCategories",
    "layerPolicy",
    "namePolicy",
    "metadataProfile",
    "rooms",
    "limitPerCategory",
    "allowTruncated",
    "allowBboxProxy",
}


def _safe_preset_name(preset: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(preset or "")).strip("._-")
    return safe or "rookbim"


def default_output_for_preset(preset: str, now: dt.datetime | None = None) -> dict[str, str]:
    stamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    return {
        "directory": str(root / "rookbim-export-to-rhino"),
        "name": f"{_safe_preset_name(preset)}-{stamp}",
    }


def build_export_request(
    arguments: dict[str, Any],
    now: dt.datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {
        key: value
        for key, value in arguments.items()
        if key in EXPORT_FIELD_NAMES and value is not None
    }
    if "output" not in request:
        request["output"] = default_output_for_preset(str(arguments.get("preset", "")), now=now)
    effective_output = dict(request["output"])
    return request, effective_output


def _nested_get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_str(mapping: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> str | None:
    for path in paths:
        value = _nested_get(mapping, path)
        if value:
            return str(value)
    return None


def resolve_artifact_paths(
    export_response: dict[str, Any],
    effective_output: dict[str, Any],
) -> dict[str, str]:
    directory = str(effective_output["directory"])
    name = str(effective_output["name"])
    fallback_model = str(Path(directory) / f"{name}.3dm")
    fallback_sidecar = str(Path(directory) / f"{name}.sidecar.json")
    fallback_validation = str(Path(directory) / f"{name}.validation.json")

    model3dm = _first_str(
        export_response,
        (
            ("data", "paths", "model3dm"),
            ("data", "paths", "model3dmPath"),
            ("data", "bundle", "model3dm"),
            ("data", "bundle", "model3dmPath"),
            ("data", "model3dm"),
            ("data", "model3dmPath"),
            ("bundle", "model3dm"),
            ("model3dm",),
        ),
    ) or fallback_model
    sidecar = _first_str(
        export_response,
        (
            ("data", "paths", "sidecar"),
            ("data", "paths", "sidecarPath"),
            ("data", "bundle", "sidecar"),
            ("data", "bundle", "sidecarPath"),
            ("data", "sidecar"),
            ("data", "sidecarPath"),
            ("bundle", "sidecar"),
            ("sidecar",),
        ),
    ) or fallback_sidecar
    validation = _first_str(
        export_response,
        (
            ("data", "paths", "validation"),
            ("data", "paths", "validationPath"),
            ("data", "bundle", "validation"),
            ("data", "bundle", "validationPath"),
            ("data", "validation"),
            ("data", "validationPath"),
            ("bundle", "validation"),
            ("validation",),
        ),
    ) or fallback_validation
    bundle_dir = _first_str(
        export_response,
        (
            ("data", "paths", "directory"),
            ("data", "bundle", "directory"),
            ("data", "bundleDirectory"),
            ("bundle", "directory"),
        ),
    ) or str(Path(model3dm).parent)
    return {
        "bundleDirectory": bundle_dir,
        "model3dm": model3dm,
        "sidecar": sidecar,
        "validation": validation,
    }


def stage_failure(
    stage: str,
    error: str,
    message: str,
    *,
    partial_success: bool = True,
    export: Any = None,
    paths: Any = None,
    import_result: Any = None,
    projection: Any = None,
    bimFacts: Any = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "partialSuccess": partial_success,
        "workflow": WORKFLOW_NAME,
        "stage": stage,
        "error": error,
        "message": message,
    }
    if export is not None:
        result["export"] = export
    if paths is not None:
        result["paths"] = paths
    if import_result is not None:
        result["import"] = import_result
    if projection is not None:
        result["projection"] = projection
    if bimFacts is not None:
        result["bimFacts"] = bimFacts
    return result
