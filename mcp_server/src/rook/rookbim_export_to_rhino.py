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
