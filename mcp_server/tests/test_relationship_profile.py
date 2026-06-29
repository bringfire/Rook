from __future__ import annotations

import json
from pathlib import Path

from rook.scene.relationship_profile import (
    PROFILE_SCHEMA,
    contact_kind_profile,
    relationship_profile,
    resolve_relationship_profile,
)


def _write_project_profile(project_root: Path, profile: dict) -> Path:
    profile_dir = project_root / ".rook"
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / "relationship_profile.json"
    path.write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_loads_default_relationship_profile():
    result = resolve_relationship_profile()

    assert result["success"] is True
    assert result["schema"] == PROFILE_SCHEMA
    assert result["projectProfileLoaded"] is False
    assert result["profileSources"][0]["kind"] == "default"
    assert result["profileSources"][0]["loaded"] is True
    assert result["profileSources"][1] == {
        "kind": "project",
        "path": None,
        "loaded": False,
        "reason": "project_root_not_supplied",
    }
    assert set(result["profile"]["relationships"]) >= {
        "connects",
        "supports",
        "hosted_by",
        "voids",
        "penetrates",
        "bounded_by",
    }
    assert set(result["profile"]["contactKinds"]) >= {
        "point_to_point",
        "point_to_region",
        "body_to_region",
        "profile_to_region",
        "line_to_region",
        "boundary_to_face",
    }
    assert set(result["profile"]["objectKinds"]) >= {
        "member",
        "joint",
        "column",
        "slab",
        "wall",
        "door",
        "opening",
        "duct",
        "space",
    }


def test_rejects_relative_project_root():
    result = resolve_relationship_profile(project_root=".")  # type: ignore[arg-type]

    assert result == {
        "success": False,
        "error": "invalid_project_root",
        "message": "project_root must be an absolute path in v1",
        "diagnostics": {"invalidProjectRoot": 1},
    }


def test_rejects_missing_project_root(tmp_path):
    missing = tmp_path / "missing-project"

    result = resolve_relationship_profile(project_root=str(missing))

    assert result == {
        "success": False,
        "error": "invalid_project_root",
        "message": "project_root must exist and be a directory in v1",
        "diagnostics": {"missingProjectRoot": 1},
    }


def test_rejects_file_project_root(tmp_path):
    file_root = tmp_path / "not-a-directory.txt"
    file_root.write_text("not a directory", encoding="utf-8")

    result = resolve_relationship_profile(project_root=str(file_root))

    assert result == {
        "success": False,
        "error": "invalid_project_root",
        "message": "project_root must exist and be a directory in v1",
        "diagnostics": {"projectRootNotDirectory": 1},
    }


def test_missing_project_profile_inside_existing_root_succeeds(tmp_path):
    result = resolve_relationship_profile(project_root=str(tmp_path))

    assert result["success"] is True
    assert result["projectProfileLoaded"] is False
    assert result["profileSources"][1] == {
        "kind": "project",
        "path": str(tmp_path / ".rook" / "relationship_profile.json"),
        "loaded": False,
        "reason": "project_profile_missing",
    }
    assert "supports" in result["profile"]["relationships"]


def test_omitted_project_root_does_not_read_process_cwd(monkeypatch, tmp_path):
    _write_project_profile(
        tmp_path,
        {
            "schema": PROFILE_SCHEMA,
            "relationships": {
                "supports": {"label": "cwd should not be used"}
            },
        },
    )
    monkeypatch.chdir(tmp_path)

    result = resolve_relationship_profile()

    assert result["success"] is True
    assert result["projectProfileLoaded"] is False
    assert result["profileSources"][1] == {
        "kind": "project",
        "path": None,
        "loaded": False,
        "reason": "project_root_not_supplied",
    }
    assert result["profile"]["relationships"]["supports"]["label"] == "supports"


def test_project_profile_shallow_overrides_and_extends_defaults(tmp_path):
    profile_path = _write_project_profile(
        tmp_path,
        {
            "schema": PROFILE_SCHEMA,
            "relationships": {
                "supports": {"label": "structurally supports"},
                "aligns_with": {
                    "label": "aligns with",
                    "inverse": "aligned with",
                    "category": "coordination",
                    "customField": "preserved",
                },
            },
            "contactKinds": {
                "point_to_region": {"label": "point bears on region"},
                "edge_to_edge": {"label": "edge to edge", "category": "linear_contact"},
            },
            "objectKinds": {
                "wall": {"label": "architectural wall"},
                "beam": {"label": "beam", "category": "architecture"},
            },
            "metadata": {"project": "fixture"},
        },
    )

    result = resolve_relationship_profile(project_root=str(tmp_path))

    assert result["success"] is True
    assert result["projectProfileLoaded"] is True
    assert result["profileSources"][1] == {
        "kind": "project",
        "path": str(profile_path),
        "loaded": True,
    }
    supports = result["profile"]["relationships"]["supports"]
    assert supports["label"] == "structurally supports"
    assert supports["inverse"] == "supported by"
    assert supports["category"] == "support"
    assert result["profile"]["relationships"]["aligns_with"]["customField"] == "preserved"
    assert result["profile"]["contactKinds"]["point_to_region"]["label"] == "point bears on region"
    assert result["profile"]["contactKinds"]["point_to_region"]["category"] == "region_contact"
    assert result["profile"]["objectKinds"]["wall"]["label"] == "architectural wall"
    assert result["profile"]["objectKinds"]["wall"]["category"] == "architecture"
    assert result["profile"]["objectKinds"]["beam"] == {
        "key": "beam",
        "label": "beam",
        "category": "architecture",
        "source": "project",
    }
    assert result["profile"]["metadata"]["project"] == "fixture"


def test_sparse_project_entries_get_lookup_fallback_fields(tmp_path):
    _write_project_profile(
        tmp_path,
        {
            "schema": PROFILE_SCHEMA,
            "relationships": {
                "aligns_with": {"description": "Project-specific relationship without labels"}
            },
            "contactKinds": {
                "edge_to_slot": {"description": "Project-specific contact without labels"}
            },
        },
    )

    result = resolve_relationship_profile(project_root=str(tmp_path))

    assert result["success"] is True
    assert result["profile"]["relationships"]["aligns_with"]["description"] == (
        "Project-specific relationship without labels"
    )
    assert relationship_profile(result, "aligns_with") == {
        "key": "aligns_with",
        "label": "aligns_with",
        "inverse": "connected by",
        "category": "unknown",
        "source": "project",
        "description": "Project-specific relationship without labels",
    }
    assert contact_kind_profile(result, "edge_to_slot") == {
        "key": "edge_to_slot",
        "label": "edge_to_slot",
        "category": "unknown",
        "source": "project",
        "description": "Project-specific contact without labels",
    }


def test_invalid_project_profile_schema_fails(tmp_path):
    _write_project_profile(tmp_path, {"schema": "wrong.schema", "relationships": {}})

    result = resolve_relationship_profile(project_root=str(tmp_path))

    assert result["success"] is False
    assert result["error"] == "invalid_relationship_profile"
    assert result["message"] == "Project relationship profile is invalid"
    assert result["diagnostics"] == {"invalidSchema": 1}


def test_invalid_project_profile_shape_fails(tmp_path):
    _write_project_profile(tmp_path, {"schema": PROFILE_SCHEMA, "relationships": []})

    result = resolve_relationship_profile(project_root=str(tmp_path))

    assert result["success"] is False
    assert result["error"] == "invalid_relationship_profile"
    assert result["diagnostics"] == {"relationshipsNotObject": 1}


def test_unknown_relationship_and_contact_kind_return_fallback_entries():
    result = resolve_relationship_profile()

    rel = relationship_profile(result, "custom_relationship")
    contact = contact_kind_profile(result, "custom_contact")

    assert rel == {
        "key": "custom_relationship",
        "label": "custom_relationship",
        "inverse": "connected by",
        "category": "unknown",
        "source": "fallback",
    }
    assert contact == {
        "key": "custom_contact",
        "label": "custom_contact",
        "category": "unknown",
        "source": "fallback",
    }
    assert "custom_relationship" not in result["profile"]["relationships"]
    assert "custom_contact" not in result["profile"]["contactKinds"]
