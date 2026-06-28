# Relationship Profile v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, data-defined relationship vocabulary profile and use it to enrich object semantic context cards without changing relationship fact truth.

**Architecture:** Implement a focused pure profile resolver module under `rook.scene`, backed by a checked-in default JSON profile and an optional explicit project-root JSON override. Thread the resolved profile into `scene_object_semantic_context` for additive metadata only, then expose `scene_relationship_profile` through the existing MCP/local scene-tool registration seams.

**Tech Stack:** Python 3, pytest, JSON, existing MCP `server.py`, existing local `rook.agent.tool_dispatcher`, existing `SceneGraphAnalytics` semantic inspector/card layers.

---

## 1. Source Spec

Implement this reviewed spec:

```text
docs/superpowers/specs/2026-06-28-relationship-profile-v1-design.md
```

Worktree and branch:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
codex/relationship-profile-v1
```

Stack base:

```text
0db99309 test: add live architectural relationship fixture gate
```

Spec commits:

```text
e28987be docs: design relationship profile v1
fc28aba0 docs: clarify relationship profile project roots
```

## 2. File Structure

Create:

```text
mcp_server/src/rook/scene/default_relationship_profile.json
mcp_server/src/rook/scene/relationship_profile.py
mcp_server/tests/test_relationship_profile.py
mcp_server/tests/test_relationship_profile_tool.py
```

Modify:

```text
mcp_server/src/rook/scene/object_semantic_context.py
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_dispatcher.py
mcp_server/src/rook/agent/tool_groups.py
mcp_server/src/rook/targeting.py
mcp_server/tests/test_object_semantic_context.py
mcp_server/tests/test_object_semantic_context_tool.py
mcp_server/tests/architectural_fixture_helpers.py
mcp_server/tests/test_architectural_relationship_fixture.py
```

Do not modify:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
mcp_server/src/rook/scene/semantic_relationship_inspector.py
mcp_server/src/rook/scene/relationship_fact_roundtrip.py
```

Responsibilities:

- `default_relationship_profile.json`: built-in seed vocabulary for current robot and architectural relationship facts.
- `relationship_profile.py`: pure filesystem/data resolver, validator, shallow merger, and lookup/enrichment helpers.
- `object_semantic_context.py`: accepts `project_root`, resolves the profile once, enriches card facts/groups/summaries additively.
- `server.py`, `tool_dispatcher.py`, `tool_groups.py`, `targeting.py`: thin registration/dispatch/visibility policy only.
- Tests: pin resolver behavior, card enrichment, tool wiring, and no hidden cwd behavior.

## 3. Public Contracts

### 3.1 `scene_relationship_profile`

Inputs:

```python
project_root: str | None = None
```

Success with defaults only:

```json
{
  "success": true,
  "schema": "rook.relationship_profile.v1",
  "projectProfileLoaded": false,
  "profileSources": [
    {"kind": "default", "path": "...default_relationship_profile.json", "loaded": true},
    {"kind": "project", "path": null, "loaded": false, "reason": "project_root_not_supplied"}
  ],
  "profile": {
    "relationships": {},
    "contactKinds": {},
    "objectKinds": {},
    "metadata": {}
  },
  "diagnostics": {}
}
```

Error for relative project root:

```json
{
  "success": false,
  "error": "invalid_project_root",
  "message": "project_root must be an absolute path in v1",
  "diagnostics": {"invalidProjectRoot": 1}
}
```

Error for nonexistent project root:

```json
{
  "success": false,
  "error": "invalid_project_root",
  "message": "project_root must exist and be a directory in v1",
  "diagnostics": {"missingProjectRoot": 1}
}
```

Error for file path as project root:

```json
{
  "success": false,
  "error": "invalid_project_root",
  "message": "project_root must exist and be a directory in v1",
  "diagnostics": {"projectRootNotDirectory": 1}
}
```

Error for invalid project profile:

```json
{
  "success": false,
  "error": "invalid_relationship_profile",
  "message": "Project relationship profile is invalid",
  "diagnostics": {"invalidSchema": 1}
}
```

### 3.2 `scene_object_semantic_context`

Add:

```python
project_root: str | None = None
```

Rules:

- omitted -> built-in default profile only;
- absolute existing directory -> merge `<project_root>/.rook/relationship_profile.json` if present;
- missing profile file inside existing project root -> success, defaults only;
- invalid project root/profile -> card request returns the resolver error payload;
- no `sync`, no projection, no port, no Rhino dependency;
- existing grouping/count/filter semantics remain unchanged.

## 4. Task 1: Default Profile And Pure Resolver

**Files:**

- Create: `mcp_server/tests/test_relationship_profile.py`
- Create: `mcp_server/src/rook/scene/default_relationship_profile.json`
- Create: `mcp_server/src/rook/scene/relationship_profile.py`

### Task 1A: Write Failing Pure Resolver Tests

- [ ] **Step 1: Create `mcp_server/tests/test_relationship_profile.py`**

Use this complete initial test file:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail because module/file do not exist**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'rook.scene.relationship_profile'
```

### Task 1B: Add Default Profile JSON

- [ ] **Step 1: Create `mcp_server/src/rook/scene/default_relationship_profile.json`**

Use this exact content:

```json
{
  "schema": "rook.relationship_profile.v1",
  "metadata": {
    "name": "Rook Default Relationship Profile",
    "version": "1.0.0",
    "description": "Default labels and categories for neutral Rook relationship facts"
  },
  "relationships": {
    "connects": {
      "label": "connects",
      "inverse": "connected by",
      "category": "assembly",
      "description": "A member, part, or feature is connected to another object"
    },
    "supports": {
      "label": "supports",
      "inverse": "supported by",
      "category": "support",
      "description": "An object bears, props, or otherwise supports another object"
    },
    "hosted_by": {
      "label": "hosted by",
      "inverse": "hosts",
      "category": "hosting",
      "description": "An object is semantically hosted by another object"
    },
    "voids": {
      "label": "voids",
      "inverse": "voided by",
      "category": "voiding",
      "description": "An object or profile creates or represents a void in another object"
    },
    "penetrates": {
      "label": "penetrates",
      "inverse": "penetrated by",
      "category": "penetration",
      "description": "An object passes through another object"
    },
    "bounded_by": {
      "label": "bounded by",
      "inverse": "bounds",
      "category": "boundary",
      "description": "An object or region is bounded by another object or face"
    }
  },
  "contactKinds": {
    "point_to_point": {
      "label": "point to point",
      "category": "discrete_contact"
    },
    "point_to_region": {
      "label": "point to region",
      "category": "region_contact"
    },
    "body_to_region": {
      "label": "body to region",
      "category": "region_contact"
    },
    "profile_to_region": {
      "label": "profile to region",
      "category": "region_contact"
    },
    "line_to_region": {
      "label": "line to region",
      "category": "region_contact"
    },
    "boundary_to_face": {
      "label": "boundary to face",
      "category": "boundary_contact"
    }
  },
  "objectKinds": {
    "member": {
      "label": "member",
      "category": "assembly"
    },
    "joint": {
      "label": "joint",
      "category": "assembly"
    },
    "column": {
      "label": "column",
      "category": "architecture"
    },
    "slab": {
      "label": "slab",
      "category": "architecture"
    },
    "wall": {
      "label": "wall",
      "category": "architecture"
    },
    "door": {
      "label": "door",
      "category": "architecture"
    },
    "opening": {
      "label": "opening",
      "category": "architecture"
    },
    "duct": {
      "label": "duct",
      "category": "architecture"
    },
    "space": {
      "label": "space",
      "category": "architecture"
    }
  }
}
```

### Task 1C: Implement Pure Resolver

- [ ] **Step 1: Create `mcp_server/src/rook/scene/relationship_profile.py`**

Use this implementation structure. Keep the public function names and response shapes exact; small internal refactors are acceptable only if tests stay equivalent.

```python
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


PROFILE_SCHEMA = "rook.relationship_profile.v1"
DEFAULT_PROFILE_PATH = Path(__file__).with_name("default_relationship_profile.json")
PROJECT_PROFILE_RELATIVE_PATH = Path(".rook") / "relationship_profile.json"
PROFILE_SECTIONS = ("relationships", "contactKinds", "objectKinds")


def _diagnostic_error(error: str, message: str, diagnostics: dict[str, int]) -> dict[str, Any]:
    return {
        "success": False,
        "error": error,
        "message": message,
        "diagnostics": diagnostics,
    }


def _load_json(path: Path) -> tuple[dict[str, Any] | None, dict[str, int]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, {"invalidJson": 1}
    except OSError:
        return None, {"profileReadFailed": 1}
    if not isinstance(data, dict):
        return None, {"profileNotObject": 1}
    return data, {}


def _validate_profile(data: dict[str, Any]) -> dict[str, int]:
    diagnostics: dict[str, int] = {}
    if data.get("schema") != PROFILE_SCHEMA:
        diagnostics["invalidSchema"] = 1
    relationships = data.get("relationships")
    if relationships is None:
        diagnostics["missingRelationships"] = 1
    elif not isinstance(relationships, dict):
        diagnostics["relationshipsNotObject"] = 1
    for section in ("contactKinds", "objectKinds", "metadata"):
        if section in data and not isinstance(data[section], dict):
            diagnostics[f"{section}NotObject"] = 1
    for section in PROFILE_SECTIONS:
        section_data = data.get(section)
        if not isinstance(section_data, dict):
            continue
        for key, entry in section_data.items():
            if not isinstance(key, str) or not key:
                diagnostics[f"{section}InvalidKey"] = diagnostics.get(f"{section}InvalidKey", 0) + 1
            if not isinstance(entry, dict):
                diagnostics[f"{section}EntryNotObject"] = diagnostics.get(f"{section}EntryNotObject", 0) + 1
    return diagnostics


def _entry_with_defaults(
    key: str,
    entry: dict[str, Any],
    *,
    source: str,
    fill_defaults: bool,
) -> dict[str, Any]:
    enriched = {"key": key, **copy.deepcopy(entry)}
    if fill_defaults:
        enriched.setdefault("label", key)
        enriched.setdefault("category", "uncategorized")
    enriched["source"] = source
    return enriched


def _normalize_profile(data: dict[str, Any], *, source: str, fill_defaults: bool) -> dict[str, Any]:
    normalized = {
        "relationships": {},
        "contactKinds": {},
        "objectKinds": {},
        "metadata": copy.deepcopy(data.get("metadata", {})) if isinstance(data.get("metadata", {}), dict) else {},
    }
    for section in PROFILE_SECTIONS:
        section_data = data.get(section, {})
        if not isinstance(section_data, dict):
            continue
        for key, entry in section_data.items():
            if isinstance(key, str) and key and isinstance(entry, dict):
                normalized[section][key] = _entry_with_defaults(
                    key,
                    entry,
                    source=source,
                    fill_defaults=fill_defaults,
                )
    return normalized


def _shallow_overlay_entry(base: dict[str, Any], overlay: dict[str, Any], *, source: str) -> dict[str, Any]:
    merged = {**copy.deepcopy(base), **copy.deepcopy(overlay)}
    merged["source"] = source
    return merged


def _merge_profiles(default_profile: dict[str, Any], project_profile: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(default_profile)
    if project_profile is None:
        return merged
    for section in PROFILE_SECTIONS:
        for key, entry in project_profile.get(section, {}).items():
            if key in merged[section]:
                merged[section][key] = _shallow_overlay_entry(merged[section][key], entry, source="project")
            else:
                merged[section][key] = copy.deepcopy(entry)
    merged["metadata"] = {
        **copy.deepcopy(default_profile.get("metadata", {})),
        **copy.deepcopy(project_profile.get("metadata", {})),
    }
    return merged


def _project_root_error(project_root: str) -> dict[str, Any] | None:
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        return _diagnostic_error(
            "invalid_project_root",
            "project_root must be an absolute path in v1",
            {"invalidProjectRoot": 1},
        )
    if not root.exists():
        return _diagnostic_error(
            "invalid_project_root",
            "project_root must exist and be a directory in v1",
            {"missingProjectRoot": 1},
        )
    if not root.is_dir():
        return _diagnostic_error(
            "invalid_project_root",
            "project_root must exist and be a directory in v1",
            {"projectRootNotDirectory": 1},
        )
    return None


def resolve_relationship_profile(project_root: str | None = None) -> dict[str, Any]:
    default_data, default_load_diagnostics = _load_json(DEFAULT_PROFILE_PATH)
    if default_data is None:
        return _diagnostic_error(
            "invalid_relationship_profile",
            "Default relationship profile is invalid",
            default_load_diagnostics,
        )
    default_diagnostics = _validate_profile(default_data)
    if default_diagnostics:
        return _diagnostic_error(
            "invalid_relationship_profile",
            "Default relationship profile is invalid",
            default_diagnostics,
        )

    default_profile = _normalize_profile(default_data, source="default", fill_defaults=True)
    profile_sources: list[dict[str, Any]] = [
        {"kind": "default", "path": str(DEFAULT_PROFILE_PATH), "loaded": True}
    ]

    project_profile: dict[str, Any] | None = None
    project_profile_loaded = False
    if project_root is None:
        profile_sources.append(
            {"kind": "project", "path": None, "loaded": False, "reason": "project_root_not_supplied"}
        )
    else:
        root_error = _project_root_error(project_root)
        if root_error is not None:
            return root_error
        project_path = Path(project_root).expanduser().resolve() / PROJECT_PROFILE_RELATIVE_PATH
        if not project_path.exists():
            profile_sources.append(
                {
                    "kind": "project",
                    "path": str(project_path),
                    "loaded": False,
                    "reason": "project_profile_missing",
                }
            )
        else:
            project_data, project_load_diagnostics = _load_json(project_path)
            if project_data is None:
                return _diagnostic_error(
                    "invalid_relationship_profile",
                    "Project relationship profile is invalid",
                    project_load_diagnostics,
                )
            project_diagnostics = _validate_profile(project_data)
            if project_diagnostics:
                return _diagnostic_error(
                    "invalid_relationship_profile",
                    "Project relationship profile is invalid",
                    project_diagnostics,
                )
            project_profile = _normalize_profile(project_data, source="project", fill_defaults=False)
            project_profile_loaded = True
            profile_sources.append({"kind": "project", "path": str(project_path), "loaded": True})

    return {
        "success": True,
        "schema": PROFILE_SCHEMA,
        "projectProfileLoaded": project_profile_loaded,
        "profileSources": profile_sources,
        "profile": _merge_profiles(default_profile, project_profile),
        "diagnostics": {},
    }


def relationship_profile(profile_result: dict[str, Any], relationship: Any) -> dict[str, Any]:
    key = str(relationship) if relationship not in (None, "") else "unknown"
    profile = profile_result.get("profile", {}) if isinstance(profile_result, dict) else {}
    relationships = profile.get("relationships", {}) if isinstance(profile, dict) else {}
    entry = relationships.get(key)
    if isinstance(entry, dict):
        return copy.deepcopy(entry)
    return {
        "key": key,
        "label": key,
        "inverse": "connected by",
        "category": "unknown",
        "source": "fallback",
    }


def contact_kind_profile(profile_result: dict[str, Any], contact_kind: Any) -> dict[str, Any]:
    key = str(contact_kind) if contact_kind not in (None, "") else "unknown"
    profile = profile_result.get("profile", {}) if isinstance(profile_result, dict) else {}
    contact_kinds = profile.get("contactKinds", {}) if isinstance(profile, dict) else {}
    entry = contact_kinds.get(key)
    if isinstance(entry, dict):
        return copy.deepcopy(entry)
    return {"key": key, "label": key, "category": "unknown", "source": "fallback"}
```

- [ ] **Step 2: Run pure resolver tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 3: Commit resolver checkpoint**

Run:

```powershell
git add mcp_server/src/rook/scene/default_relationship_profile.json mcp_server/src/rook/scene/relationship_profile.py mcp_server/tests/test_relationship_profile.py
git commit -m "feat: add relationship profile resolver"
```

## 5. Task 2: Object Semantic Context Enrichment

**Files:**

- Modify: `mcp_server/src/rook/scene/object_semantic_context.py`
- Modify: `mcp_server/tests/test_object_semantic_context.py`
- Modify: `mcp_server/tests/architectural_fixture_helpers.py`
- Modify: `mcp_server/tests/test_architectural_relationship_fixture.py`

### Task 2A: Add Failing Card Enrichment Tests

- [ ] **Step 1: Append built-in enrichment assertion to `test_object_semantic_context.py`**

Add this assertion block to `test_card_preserves_order_metadata_summary_and_ignores_fuzzy_edges` after the existing `member["summary"]["poses"]` assertion:

```python
    connects_group = member["groups"][0]
    assert connects_group["relationshipLabel"] == "connects"
    assert connects_group["inverseRelationship"] == "connected by"
    assert connects_group["relationshipCategory"] == "assembly"
    assert member["summary"]["byRelationshipCategory"] == {"assembly": 1, "support": 1}
    assert member["groups"][0]["sampleFacts"][0]["relationshipLabel"] == "connects"
    assert member["groups"][0]["sampleFacts"][0]["contactKindLabel"] == "point to point"
    assert member["groups"][1]["relationshipCategory"] == "support"
```

- [ ] **Step 2: Add project override card test to `test_object_semantic_context.py`**

Append:

```python
def test_project_profile_enriches_card_labels(tmp_path):
    profile_dir = tmp_path / ".rook"
    profile_dir.mkdir()
    (profile_dir / "relationship_profile.json").write_text(
        """
{
  "schema": "rook.relationship_profile.v1",
  "relationships": {
    "supports": {
      "label": "props up",
      "category": "structural_support"
    }
  },
  "contactKinds": {
    "point_to_region": {
      "label": "bearing point to region"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        relationship_types=["supports"],
        project_root=str(tmp_path),
    )

    assert result["success"] is True
    group = result["cards"][0]["groups"][0]
    assert group["relationship"] == "supports"
    assert group["relationshipLabel"] == "props up"
    assert group["inverseRelationship"] == "supported by"
    assert group["relationshipCategory"] == "structural_support"
    assert group["sampleFacts"][0]["relationshipLabel"] == "props up"
    assert group["sampleFacts"][0]["contactKindLabel"] == "bearing point to region"
    assert result["cards"][0]["summary"]["byRelationshipCategory"] == {"structural_support": 1}
```

- [ ] **Step 3: Add invalid profile propagation test to `test_object_semantic_context.py`**

Append:

```python
def test_invalid_project_profile_fails_card_request(tmp_path):
    profile_dir = tmp_path / ".rook"
    profile_dir.mkdir()
    (profile_dir / "relationship_profile.json").write_text(
        '{"schema": "wrong.schema", "relationships": {}}',
        encoding="utf-8",
    )

    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        project_root=str(tmp_path),
    )

    assert result == {
        "success": False,
        "error": "invalid_relationship_profile",
        "message": "Project relationship profile is invalid",
        "diagnostics": {"invalidSchema": 1},
    }
```

- [ ] **Step 4: Run card tests and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py -q
```

Expected:

```text
failures mentioning missing relationshipLabel/byRelationshipCategory or unexpected project_root
```

### Task 2B: Implement Card Enrichment

- [ ] **Step 1: Update imports in `object_semantic_context.py`**

Change the imports to include profile helpers:

```python
from .relationship_profile import (
    contact_kind_profile,
    relationship_profile,
    resolve_relationship_profile,
)
from .semantic_relationship_inspector import PROJECTION_KIND, query_semantic_relationships
```

- [ ] **Step 2: Add enrichment helper functions in `object_semantic_context.py`**

Insert after `_sample_sort_key`:

```python
def _enrich_fact(fact: dict[str, Any], profile_result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(fact)
    relationship_entry = relationship_profile(profile_result, fact.get("relationship"))
    contact_entry = contact_kind_profile(profile_result, fact.get("contactKind"))
    enriched["relationshipLabel"] = relationship_entry.get("label")
    enriched["inverseRelationship"] = relationship_entry.get("inverse")
    enriched["relationshipCategory"] = relationship_entry.get("category")
    enriched["contactKindLabel"] = contact_entry.get("label")
    enriched["contactKindCategory"] = contact_entry.get("category")
    return enriched
```

Modify `_line_for_fact` to use profile labels while preserving generic fallback:

```python
def _line_for_fact(fact: dict[str, Any]) -> str:
    relationship = fact.get("relationshipLabel") or fact.get("relationship") or "relates to"
    inverse = fact.get("inverseRelationship") or "connected by"
    other_name = fact.get("otherName") or fact.get("otherObjectId")
    if fact.get("direction") == "outgoing":
        prefix = f"{relationship} {other_name}"
    else:
        prefix = f"{inverse} {other_name}"
    feature_part = ""
    if fact.get("fromFeature") and fact.get("toFeature"):
        feature_part = f" via {fact['fromFeature']} -> {fact['toFeature']}"
    details = [
        str(value)
        for value in (
            fact.get("contactKindLabel") or fact.get("contactKind"),
            fact.get("status"),
            fact.get("provenance"),
        )
        if value
    ]
    suffix = f", {', '.join(details)}" if details else ""
    return f"{prefix}{feature_part}{suffix}"
```

- [ ] **Step 3: Update `_zero_summary` and `_summary_for_facts`**

Add `byRelationshipCategory` to `_zero_summary`:

```python
        "byRelationshipCategory": {},
```

Update `_summary_for_facts` to count relationship categories:

```python
    by_relationship_category: dict[str, int] = {}
```

Inside the fact loop:

```python
        _bump(by_relationship_category, fact.get("relationshipCategory"))
```

In the return dict:

```python
        "byRelationshipCategory": dict(sorted(by_relationship_category.items())),
```

- [ ] **Step 4: Update `_groups_for_facts`**

Keep grouping keyed on raw `relationship`, `direction`, `status`, and `provenance`; do not include labels or categories in `_group_key`.

Add these fields to each visible group from `first`:

```python
                "relationshipLabel": first.get("relationshipLabel"),
                "inverseRelationship": first.get("inverseRelationship"),
                "relationshipCategory": first.get("relationshipCategory"),
```

Add the same fields to expandable groups:

```python
            "relationshipLabel": group.get("relationshipLabel"),
            "inverseRelationship": group.get("inverseRelationship"),
            "relationshipCategory": group.get("relationshipCategory"),
```

- [ ] **Step 5: Update `_card_from_object_entry` signature and fact preparation**

Change signature:

```python
def _card_from_object_entry(
    analytics: Any,
    entry: dict[str, Any],
    *,
    max_groups: int,
    max_facts_per_group: int,
    profile_result: dict[str, Any],
) -> dict[str, Any]:
```

Change facts initialization:

```python
    facts = [_enrich_fact(fact, profile_result) for fact in entry.get("facts", [])]
```

- [ ] **Step 6: Update `query_object_semantic_context` signature and resolver call**

Add parameter:

```python
    project_root: str | None = None,
```

After card-bound validation and before `query_semantic_relationships`, add:

```python
    profile_result = resolve_relationship_profile(project_root=project_root)
    if profile_result.get("success") is False:
        return profile_result
```

Pass `profile_result=profile_result` into `_card_from_object_entry`.

- [ ] **Step 7: Run card tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py -q
```

Expected:

```text
18 passed
```

If the count differs because tests were added upstream, all tests in this file must pass.

### Task 2C: Add Architectural Fixture Profile Assertions

- [ ] **Step 1: Update `architectural_fixture_helpers.py` card assertions**

In `assert_architectural_card_expectations`, add these assertions:

```python
    assert column["groups"][0]["relationshipCategory"] == "support"
    assert slab["groups"][0]["inverseRelationship"] == "supported by"
    assert door["groups"][0]["relationshipCategory"] == "hosting"
    assert duct["groups"][0]["relationshipCategory"] == "penetration"
    assert space["groups"][0]["relationshipCategory"] == "boundary"
    assert wall["summary"]["byRelationshipCategory"] == {
        "boundary": 1,
        "hosting": 1,
        "penetration": 1,
        "voiding": 1,
    }
```

- [ ] **Step 2: Run architectural fixture tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 3: Commit card enrichment checkpoint**

Run:

```powershell
git add mcp_server/src/rook/scene/object_semantic_context.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/architectural_fixture_helpers.py
git commit -m "feat: enrich semantic context cards from relationship profile"
```

## 6. Task 3: Tool Surface And Registration

**Files:**

- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Create: `mcp_server/tests/test_relationship_profile_tool.py`
- Modify: `mcp_server/tests/test_object_semantic_context_tool.py`

### Task 3A: Write Failing Tool Tests

- [ ] **Step 1: Create `mcp_server/tests/test_relationship_profile_tool.py`**

Use:

```python
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_relationship_profile_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_relationship_profile"].inputSchema

    assert schema["type"] == "object"
    assert schema["properties"]["project_root"]["type"] == "string"
    assert "project_root" not in schema.get("required", [])


def test_tool_group_contains_scene_relationship_profile():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_relationship_profile" in TOOL_GROUPS["scene_graph"]


def test_scene_relationship_profile_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_relationship_profile")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_relationship_profile" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_relationship_profile():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_relationship_profile" in tools
    assert callable(tools["scene_relationship_profile"])


@pytest.mark.asyncio
async def test_local_scene_relationship_profile_returns_defaults():
    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_relationship_profile"]()

    assert result["success"] is True
    assert result["projectProfileLoaded"] is False
    assert "supports" in result["profile"]["relationships"]


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_profile_rejects_relative_project_root():
    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_relationship_profile", {"project_root": "."})

    assert result == {
        "success": False,
        "data": {
            "success": False,
            "error": "invalid_project_root",
            "message": "project_root must be an absolute path in v1",
            "diagnostics": {"invalidProjectRoot": 1},
        },
    }
```

- [ ] **Step 2: Add object-card tool project-root dispatch tests**

Append to `mcp_server/tests/test_object_semantic_context_tool.py`:

```python
@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_passes_project_root(monkeypatch, tmp_path):
    sg = _scene_graph()
    seen = {}

    def fake_query(analytics, **kwargs):
        assert analytics is sg
        seen.update(kwargs)
        return {"success": True, "counts": {}, "cards": [], "diagnostics": {}}

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr("rook.scene.object_semantic_context.query_object_semantic_context", fake_query)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_object_semantic_context",
        {"object_ids": ["member-id"], "project_root": str(tmp_path)},
    )

    assert result["success"] is True
    assert seen["project_root"] == str(tmp_path)
```

- [ ] **Step 3: Update the existing object-card schema test**

In `test_server_tool_schema_exposes_scene_object_semantic_context_parameters`, add:

```python
    assert schema["properties"]["project_root"]["type"] == "string"
    assert "project_root" not in schema["required"]
```

- [ ] **Step 4: Run tool tests and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
failures for missing scene_relationship_profile schema/registration and missing project_root forwarding
```

### Task 3B: Register `scene_relationship_profile`

- [ ] **Step 1: Add server tool schema in `server.py`**

In the `list_tools` scene section near `scene_object_semantic_context`, add:

```python
        Tool(
            name="scene_relationship_profile",
            description="""Return the resolved read-only relationship profile.

Loads the built-in default relationship profile and, when project_root is supplied, merges the explicit project-local .rook/relationship_profile.json override. Does not inspect Rhino, sync the scene graph, project facts, infer relationships, or write files.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "Optional absolute project root containing .rook/relationship_profile.json",
                    },
                },
                "required": [],
            },
        ),
```

Also add `project_root` to the existing `scene_object_semantic_context` schema:

```python
                    "project_root": {
                        "type": "string",
                        "description": "Optional absolute project root containing .rook/relationship_profile.json for card enrichment",
                    },
```

- [ ] **Step 2: Add server dispatch case in `_call_tool_dispatch`**

Add before `case "scene_semantic_relationships"`:

```python
        case "scene_relationship_profile":
            from .scene.relationship_profile import resolve_relationship_profile

            payload = resolve_relationship_profile(project_root=arguments.get("project_root"))
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

Update the `scene_object_semantic_context` call:

```python
                project_root=arguments.get("project_root"),
```

- [ ] **Step 3: Add local dispatcher registration**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, before the semantic inspector local tool block, add:

```python
    # --- scene_relationship_profile (Python-side relationship profile resolver) ---
    try:
        from ..scene.relationship_profile import resolve_relationship_profile

        async def _scene_relationship_profile(project_root=None, **kwargs) -> dict:
            return resolve_relationship_profile(project_root=project_root)

        tools["scene_relationship_profile"] = _scene_relationship_profile
    except ImportError:
        logger.debug("scene_relationship_profile local tool unavailable (import failed)")
```

Update local `_scene_object_semantic_context` signature:

```python
            project_root=None,
```

and pass:

```python
                project_root=project_root,
```

- [ ] **Step 4: Add tool group entry**

In `mcp_server/src/rook/agent/tool_groups.py`, add `scene_relationship_profile` to the `scene_graph` group before `scene_semantic_relationships`:

```python
        "scene_project_relationship_facts", "scene_relationship_profile",
        "scene_semantic_relationships",
```

- [ ] **Step 5: Add targeting policy**

In `mcp_server/src/rook/targeting.py`, add `scene_relationship_profile` to `_ALL_KNOWN_TOOLS` near other scene tools and to `_RHINO_INDEPENDENT_READ_TOOLS`:

```python
    "scene_relationship_profile",
```

- [ ] **Step 6: Run tool tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 7: Commit tool surface checkpoint**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context_tool.py
git commit -m "feat: expose relationship profile tool"
```

## 7. Task 4: Focused Regression Suite

**Files:**

- Verify all files touched above.

- [ ] **Step 1: Run pure relationship profile tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 2: Run profile/card tool tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
33 passed
```

- [ ] **Step 3: Run semantic/projector guard tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py -q
```

Expected:

```text
35 passed
```

- [ ] **Step 4: Run architectural fixture regression**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 5: Run whitespace and commit checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
```

Expected:

```text
no whitespace errors
```

- [ ] **Step 6: Inspect final diff scope**

Run:

```powershell
git diff --stat origin/codex/relationship-profile-v1...HEAD
```

Expected diff is limited to:

```text
relationship profile JSON/module/tests
object semantic context enrichment
thin MCP/local registration surfaces
architectural/card test assertions
```

## 8. Self-Review Checklist

Before handoff, verify:

- [ ] `project_root` is never inferred from process cwd.
- [ ] `project_root` must be absolute when supplied.
- [ ] Supplied nonexistent root fails.
- [ ] Supplied file path root fails.
- [ ] Missing `.rook/relationship_profile.json` inside an existing root succeeds.
- [ ] Project profile merge is shallow per entry.
- [ ] Unknown relationships/contact kinds fall back without mutating the resolved profile.
- [ ] Card enrichment does not affect grouping keys.
- [ ] Card enrichment does not affect relationship counts.
- [ ] Raw `scene_semantic_relationships` output remains unprofiled.
- [ ] No projection parser changes.
- [ ] No geometry evidence or inference added.
- [ ] No YAML parser or dependency added.
- [ ] No ontology/IFC/BOT/Brick/RDF/Revit/TopologicPy dependency added.
- [ ] `scene_relationship_profile` is Rhino-independent read-only.
- [ ] No live Rhino test is required for this slice.

## 9. Push / Handoff

- [ ] **Step 1: Check status**

Run:

```powershell
git status --short --branch
```

Expected after implementation commits:

```text
## codex/relationship-profile-v1
```

or the same branch with an upstream once pushed.

- [ ] **Step 2: Push branch**

Run:

```powershell
git push -u origin codex/relationship-profile-v1
```

Expected:

```text
codex/relationship-profile-v1 -> codex/relationship-profile-v1
```

- [ ] **Step 3: Report handoff**

Report:

```text
Implemented Relationship Profile v1.
Profile resolver tests passed.
Card/tool/semantic guard tests passed.
Architectural fixture regression passed.
Branch clean/synced after push.
```

Do not claim any live Rhino validation. This slice is Python-side read-only and does not require it.
