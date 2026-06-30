from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MESH_HANDLER = REPO_ROOT / "src" / "RookNative" / "Handlers" / "MeshHandler.cpp"


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract function for {signature!r}")


def test_mesh2splat_capture_rejects_locked_objects_as_unsupported():
    source = MESH_HANDLER.read_text(encoding="utf-8")
    body = _extract_function(source, "static std::string BuildSkipReason")

    assert "obj->IsLocked()" in body
    assert "Object is locked" in body


def test_mesh2splat_capture_rejects_zero_triangle_meshes():
    source = MESH_HANDLER.read_text(encoding="utf-8")
    body = _extract_function(source, "static bool CountMeshTriangles")

    assert "triangleCount <= 0" in body
    assert "Mesh contains no triangle faces" in body
