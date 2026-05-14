from typing import Any


_GH_STATUS_FIELD_MAP: tuple[tuple[str, str, Any], ...] = (
    ("assemblyVersion", "assembly_version", ""),
    ("hasActiveCanvas", "has_active_canvas", False),
    ("canvasVisible", "canvas_visible", None),
    ("visibilityUnknown", "visibility_unknown", True),
    ("hasActiveDocument", "has_active_document", False),
    ("documentId", "document_id", None),
    ("documentName", "document_name", None),
    ("documentPath", "document_path", ""),
    ("readyForEdit", "ready_for_edit", False),
    ("objectCount", "object_count", 0),
    ("warnings", "warnings", []),
)


def normalize_gh_status_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize managed Grasshopper status DTO fields to the MCP snake_case contract."""
    data = result.get("data")
    if not isinstance(data, dict):
        return result

    normalized = dict(data)
    normalized["available"] = data.get("available", False)

    for camel_key, snake_key, default in _GH_STATUS_FIELD_MAP:
        normalized[snake_key] = data.get(snake_key, data.get(camel_key, default))
        if camel_key != snake_key:
            normalized.pop(camel_key, None)

    merged = dict(result)
    merged["data"] = normalized
    return merged
