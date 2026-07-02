# Director v2 Relative Actor Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement strict v2 Director actor metadata generation, resolution, runtime reading, and explicit v1-to-v2 migration using `.rook/...` project-relative refs rooted at the active `.3dm` directory.

**Architecture:** Add a Python Director actor metadata layer and update the live Director authoring path that produces Pearson V2 metadata. `director_actor_metadata.py` owns the v2 ref protocol, metadata-kind validation, active-document project-root resolution, atomic JSON writes, the production writer entry point, and runtime reads. `director_actor_migration.py` owns explicit offline conversion of curated v1 ActorSet/subset/grouping/snapshot JSON. `server.py` exposes only focused writer/reader MCP tools for Codex/Claude execution. The updated Director GH component/template emits the semantic metadata bundle; the execution agent then calls the MCP writer. GH does not call MCP directly in this phase. Migration remains a repo-level offline utility and test harness, not a public MCP tool in this phase.

**Tech Stack:** Python 3 stdlib (`pathlib`, `json`, `copy`, `datetime`, `hashlib`, `re`), pytest, existing MCP `server.py` patterns, existing native `/document` route via `call_rhino`.

---

## File Structure

- Create `mcp_server/src/rook/director_actor_metadata.py`
  - Constants: v2 schema version, required `metadata_kind` values, old durable path fields.
  - Exceptions: `DirectorActorMetadataError` with stable `code` and `to_data()`.
  - Ref protocol: validate `.rook/...` strings, resolve refs under a model directory, convert absolute project-local paths to refs.
  - Active document resolver: call `/document`, require a non-empty `.3dm` path, derive project root from its parent.
  - Runtime reader: load a ref, require `schema_version == 2`, require expected `metadata_kind`, reject old durable path fields.
  - Production writer entry point: `write_actor_metadata_bundle_v2(...)`. This is the writer path Lane A must use.

- Create `mcp_server/src/rook/director_actor_migration.py`
  - Explicit v1-to-v2 conversion functions for ActorSet, actor subset/intermediate grouping, ActorGrouping/band-set, and SelectionSnapshot.
  - Conversion report with changed fields, written files, and rejected fields.
  - No runtime fallback and no MCP exposure in this phase. This module is called only by direct tests, its module CLI, or an intentional local script command.

- Modify `mcp_server/src/rook/server.py`
  - Import `director_actor_metadata`.
  - Add MCP tools:
    - `rhino_director_write_actor_metadata_v2`
    - `rhino_director_read_actor_metadata_v2`
  - Add dispatch cases.

- Modify `mcp_server/src/rook/agent/tool_groups.py`
  - Add the writer/reader tools to `TOOL_GROUPS["director"]`.

- Modify `mcp_server/src/rook/targeting.py`
  - Add targeting policy entries for the new exposed writer/reader tools. The writer is Rhino-dependent mutating because it writes project metadata based on the active `.3dm`; the reader is Rhino-dependent read because it resolves the active `.3dm` directory through `/document`.

- Create `mcp_server/tests/test_director_actor_metadata.py`
  - Unit tests for v2 ref validation, expected-kind validation, writer behavior, active document path handling, and old durable path rejection.

- Create `mcp_server/tests/test_director_actor_migration.py`
  - Unit tests for explicit v1-to-v2 field conversion and semantic preservation.

- Modify `mcp_server/tests/test_director_mcp_tools.py`
  - Tool registration, schemas free of rejected keywords, dispatch success/failure, Director tool group membership.

- Modify `mcp_server/tests/test_multi_instance_targeting.py`
  - Explicitly assert targeting policies for `rhino_director_write_actor_metadata_v2` and `rhino_director_read_actor_metadata_v2`.

- Update validation artifact `H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\animation test.gh`
  - Regenerate or patch the live Director authoring component/template so Lane A emits a semantic metadata bundle consumed by the execution agent.
  - Treat the `.gh` file as a validation artifact, not repo contract authority.

No native C++, managed C#, or `.vcxproj` file is modified in this plan. The V2 `.gh` file is updated only as a live validation artifact so Lane A is executable as an agent-mediated capture flow through the production writer path.

---

### Task 1: v2 Ref Protocol And Runtime Reader

**Files:**
- Create: `mcp_server/src/rook/director_actor_metadata.py`
- Test: `mcp_server/tests/test_director_actor_metadata.py`

**Interfaces introduced:**

```python
SCHEMA_VERSION = 2
KIND_ACTOR_SET = "director_actor_set"
KIND_ACTOR_SUBSET = "director_actor_subset"
KIND_ACTOR_GROUPING = "director_actor_grouping"
KIND_SELECTION_SNAPSHOT = "director_selection_snapshot"

class DirectorActorMetadataError(Exception):
    def __init__(self, code: str, message: str, **data): ...
    def to_data(self) -> dict: ...

def validate_metadata_ref(ref: str) -> str: ...
def resolve_metadata_ref(project_root: Path, ref: str) -> Path: ...
def ref_from_project_path(project_root: Path, path: Path) -> str: ...
def load_metadata_ref(project_root: Path, ref: str, *, expected_kind: str) -> dict: ...
```

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_director_actor_metadata.py`:

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_actor_metadata as dam


def test_validate_metadata_ref_accepts_rook_scoped_forward_slash_ref():
    assert (
        dam.validate_metadata_ref(".rook/director_planning/actor_sets/a.json")
        == ".rook/director_planning/actor_sets/a.json"
    )


@pytest.mark.parametrize(
    "bad_ref",
    [
        "",
        "director_planning/a.json",
        "/.rook/a.json",
        r"C:\project\.rook\a.json",
        r"\\server\share\.rook\a.json",
        ".rook\\a.json",
        ".rook/../a.json",
        ".rook/./a.json",
        ".rook//a.json",
    ],
)
def test_validate_metadata_ref_rejects_non_contract_refs(bad_ref):
    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        dam.validate_metadata_ref(bad_ref)
    assert ei.value.code == "invalid_metadata_ref"


def test_resolve_metadata_ref_stays_under_project_root(tmp_path):
    root = tmp_path / "model"
    target = root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")

    resolved = dam.resolve_metadata_ref(
        root, ".rook/director_planning/actor_sets/a.json"
    )

    assert resolved == target.resolve()


def test_ref_from_project_path_converts_project_local_path(tmp_path):
    root = tmp_path / "model"
    p = root / ".rook" / "director_planning" / "selection_snapshots" / "s.json"
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")

    assert dam.ref_from_project_path(root, p) == (
        ".rook/director_planning/selection_snapshots/s.json"
    )


def test_ref_from_project_path_rejects_path_outside_project(tmp_path):
    root = tmp_path / "model"
    outside = tmp_path / "other" / ".rook" / "x.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        dam.ref_from_project_path(root, outside)
    assert ei.value.code == "path_outside_project_root"


def test_load_metadata_ref_requires_schema_version_and_kind(tmp_path):
    root = tmp_path / "model"
    p = root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "metadata_kind": dam.KIND_ACTOR_SET,
                "actor_set_id": "a",
            }
        ),
        encoding="utf-8",
    )

    payload = dam.load_metadata_ref(
        root,
        ".rook/director_planning/actor_sets/a.json",
        expected_kind=dam.KIND_ACTOR_SET,
    )

    assert payload["actor_set_id"] == "a"


def test_load_metadata_ref_rejects_v1():
    root = Path("C:/project")
    data = {"schema_version": 1, "metadata_kind": dam.KIND_ACTOR_SET}

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        dam.validate_loaded_metadata(data, expected_kind=dam.KIND_ACTOR_SET)
    assert ei.value.code == "metadata_schema_unsupported"


def test_load_metadata_ref_rejects_wrong_or_missing_kind():
    with pytest.raises(dam.DirectorActorMetadataError) as wrong:
        dam.validate_loaded_metadata(
            {"schema_version": 2, "metadata_kind": dam.KIND_SELECTION_SNAPSHOT},
            expected_kind=dam.KIND_ACTOR_SET,
        )
    assert wrong.value.code == "metadata_kind_mismatch"

    with pytest.raises(dam.DirectorActorMetadataError) as missing:
        dam.validate_loaded_metadata({"schema_version": 2}, expected_kind=dam.KIND_ACTOR_SET)
    assert missing.value.code == "metadata_kind_mismatch"


def test_loaded_v2_rejects_old_durable_path_fields():
    payload = {
        "schema_version": 2,
        "metadata_kind": dam.KIND_ACTOR_SET,
        "source_snapshot_path": r"H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\x.json",
    }

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        dam.validate_loaded_metadata(payload, expected_kind=dam.KIND_ACTOR_SET)
    assert ei.value.code == "legacy_path_field_present"
    assert ei.value.data["field_path"] == "$.source_snapshot_path"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_metadata.py -q
```

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `rook.director_actor_metadata`.

- [ ] **Step 3: Implement the ref protocol and reader**

Create `mcp_server/src/rook/director_actor_metadata.py`:

```python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

KIND_ACTOR_SET = "director_actor_set"
KIND_ACTOR_SUBSET = "director_actor_subset"
KIND_ACTOR_GROUPING = "director_actor_grouping"
KIND_SELECTION_SNAPSHOT = "director_selection_snapshot"

METADATA_KINDS = {
    KIND_ACTOR_SET,
    KIND_ACTOR_SUBSET,
    KIND_ACTOR_GROUPING,
    KIND_SELECTION_SNAPSHOT,
}

LEGACY_DURABLE_PATH_FIELDS = {
    "model_path",
    "source_snapshot_path",
    "path",
    "accepted_selection_snapshot_path",
    "exemplar_selection_snapshot_path",
}

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class DirectorActorMetadataError(Exception):
    def __init__(self, code: str, message: str, **data: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_data(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        payload.update(self.data)
        return payload


def validate_metadata_ref(ref: str) -> str:
    if not isinstance(ref, str) or not ref:
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref must be a non-empty string")
    if "\\" in ref:
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref must use forward slashes")
    if ref.startswith("/") or ref.startswith("//") or ref.startswith("\\\\"):
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref must be relative")
    if _WINDOWS_DRIVE_RE.match(ref):
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref must not include a drive prefix")
    if not ref.startswith(".rook/"):
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref must start with .rook/")
    parts = ref.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise DirectorActorMetadataError("invalid_metadata_ref", "metadata ref contains an invalid path segment")
    return ref


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_metadata_ref(project_root: Path, ref: str) -> Path:
    valid = validate_metadata_ref(ref)
    root = Path(project_root).expanduser().resolve()
    resolved = (root / Path(*valid.split("/"))).resolve()
    if not _is_relative_to(resolved, root):
        raise DirectorActorMetadataError(
            "metadata_ref_escape",
            "metadata ref resolves outside the project root",
            ref=ref,
        )
    return resolved


def ref_from_project_path(project_root: Path, path: Path) -> str:
    root = Path(project_root).expanduser().resolve()
    resolved = Path(path).expanduser().resolve()
    if not _is_relative_to(resolved, root):
        raise DirectorActorMetadataError(
            "path_outside_project_root",
            "path is outside the project root",
            path=str(path),
        )
    rel = resolved.relative_to(root).as_posix()
    return validate_metadata_ref(rel)


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, key, child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def validate_loaded_metadata(payload: dict[str, Any], *, expected_kind: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DirectorActorMetadataError("metadata_invalid", "metadata root must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DirectorActorMetadataError(
            "metadata_schema_unsupported",
            "Director actor metadata must use schema_version 2",
            schema_version=payload.get("schema_version"),
        )
    if payload.get("metadata_kind") != expected_kind:
        raise DirectorActorMetadataError(
            "metadata_kind_mismatch",
            "metadata_kind does not match the expected document kind",
            expected_kind=expected_kind,
            actual_kind=payload.get("metadata_kind"),
        )
    for field_path, key, child in _walk(payload):
        if key in LEGACY_DURABLE_PATH_FIELDS and isinstance(child, str):
            raise DirectorActorMetadataError(
                "legacy_path_field_present",
                "v2 metadata contains a legacy durable path field",
                field_path=field_path,
            )
    return payload


def load_metadata_ref(project_root: Path, ref: str, *, expected_kind: str) -> dict[str, Any]:
    path = resolve_metadata_ref(project_root, ref)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DirectorActorMetadataError("metadata_ref_not_found", "metadata ref does not exist", ref=ref) from exc
    except json.JSONDecodeError as exc:
        raise DirectorActorMetadataError("metadata_json_invalid", str(exc), ref=ref) from exc
    return validate_loaded_metadata(payload, expected_kind=expected_kind)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_metadata.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/director_actor_metadata.py mcp_server/tests/test_director_actor_metadata.py
git commit -m "feat(director): add actor metadata v2 ref protocol"
```

---

### Task 2: Production v2 Writer Entry Point

**Files:**
- Modify: `mcp_server/src/rook/director_actor_metadata.py`
- Modify: `mcp_server/tests/test_director_actor_metadata.py`

**Production writer entry point:** `rook.director_actor_metadata.write_actor_metadata_bundle_v2(...)`. This is the Lane A writer path. The MCP tool in Task 4 wraps this function.

The writer accepts a semantic bundle from the updated Director component/template. It does not rerun grouping/classification. It persists supplied ActorSet/subset/grouping/snapshot payloads under `.rook/`, normalizes v2 schema fields, rewrites durable links as refs, rejects legacy durable path fields, and returns refs plus resolved runtime paths.

**Input shape:**

```json
{
  "actor_set": {"actor_set_id": "roof_uplift_vertical_test_chunk_001", "members": []},
  "selection_snapshots": [
    {"snapshot_id": "intent_005_20260701_144245", "selected": []}
  ],
  "subsets": [
    {"subset_id": "same_orientation_mullions_001", "members": []}
  ],
  "groupings": [
    {"band_set_id": "same_orientation_mullions_001_bands_001", "bands": []}
  ]
}
```

- [ ] **Step 1: Write failing writer tests**

Append to `mcp_server/tests/test_director_actor_metadata.py`:

```python
import asyncio


class FakeDocumentNative:
    def __init__(self, path: str | None):
        self.path = path
        self.calls = []

    async def __call__(self, endpoint, method="GET", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint == "/document":
            return {
                "success": True,
                "data": {
                    "name": "Axon_Pearson_Experimental_TESTING.3dm",
                    "path": self.path,
                },
            }
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _minimal_bundle():
    return {
        "actor_set": {
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            "source_snapshot_entry_id": "intent_005_20260701_144245",
            "summary": {"member_count": 1},
            "members": [{"actor_id": "a0", "ordinal": 0}],
        },
        "selection_snapshots": [
            {
                "snapshot_id": "intent_005_20260701_144245",
                "selected": [{"id": "11111111-1111-1111-1111-111111111111"}],
            },
            {
                "snapshot_id": "intent_007_20260701_151718",
                "selected": [{"id": "22222222-2222-2222-2222-222222222222"}],
            },
        ],
        "subsets": [
            {
                "subset_id": "same_orientation_mullions_001",
                "parent_actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "acceptance": {
                    "accepted_selection_snapshot_id": "intent_005_20260701_144245"
                },
                "band_set_ids": ["same_orientation_mullions_001_bands_001"],
                "members": [{"actor_id": "a0", "ordinal": 0}],
            }
        ],
        "groupings": [
            {
                "band_set_id": "same_orientation_mullions_001_bands_001",
                "parent_actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "parent_subset_id": "same_orientation_mullions_001",
                "exemplar_selection_snapshot_id": "intent_007_20260701_151718",
                "bands": [{"band_id": "b0", "members": [{"actor_id": "a0"}]}],
            }
        ],
    }


def test_write_actor_metadata_bundle_v2_creates_refs_and_no_legacy_paths(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not-a-real-3dm")

    out = asyncio.run(
        dam.write_actor_metadata_bundle_v2(
            _minimal_bundle(),
            call_native=FakeDocumentNative(str(model)),
            port=None,
        )
    )

    assert out["actor_set_ref"] == (
        ".rook/director_planning/actor_sets/"
        "roof_uplift_vertical_test_chunk_001.json"
    )
    actor_set_path = model.parent / out["actor_set_ref"].replace("/", os.sep)
    payload = json.loads(actor_set_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["metadata_kind"] == dam.KIND_ACTOR_SET
    assert payload["source_snapshot_ref"] == (
        ".rook/director_planning/selection_snapshots/"
        "intent_005_20260701_144245.json"
    )
    assert payload["subsets"][0]["ref"].endswith(
        "roof_uplift_vertical_test_chunk_001_subsets/same_orientation_mullions_001.json"
    )
    assert "model_path" not in payload
    assert "source_snapshot_path" not in payload
    assert payload["source_document"]["file_name"] == "Axon_Pearson_Experimental_TESTING.3dm"


def test_write_actor_metadata_bundle_v2_rejects_unsaved_document():
    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        asyncio.run(
            dam.write_actor_metadata_bundle_v2(
                _minimal_bundle(),
                call_native=FakeDocumentNative(""),
                port=None,
            )
        )
    assert ei.value.code == "document_path_required"


def test_write_actor_metadata_bundle_v2_rejects_legacy_input_path_field(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not-a-real-3dm")
    bundle = _minimal_bundle()
    bundle["actor_set"]["model_path"] = r"H:\AI EXPERIMENTS\Pearson\ANIMATION\Axon.3dm"

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        asyncio.run(
            dam.write_actor_metadata_bundle_v2(
                bundle,
                call_native=FakeDocumentNative(str(model)),
                port=None,
            )
        )
    assert ei.value.code == "legacy_path_field_present"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_metadata.py -k "write_actor_metadata_bundle" -q
```

Expected: FAIL with `AttributeError` for `write_actor_metadata_bundle_v2`.

- [ ] **Step 3: Implement writer helpers and writer entry point**

Append to `mcp_server/src/rook/director_actor_metadata.py`:

```python
import copy
from datetime import datetime, timezone

from .bridge import call_rhino


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _reject_legacy_fields(payload: dict[str, Any]) -> None:
    for field_path, key, child in _walk(payload):
        if key in LEGACY_DURABLE_PATH_FIELDS and isinstance(child, str):
            raise DirectorActorMetadataError(
                "legacy_path_field_present",
                "metadata input contains a legacy durable path field",
                field_path=field_path,
            )


async def resolve_active_project_root(*, call_native=call_rhino, port: int | None = None) -> tuple[Path, dict[str, Any]]:
    result = await call_native("/document", "GET", port=port)
    if not result.get("success"):
        raise DirectorActorMetadataError("document_resolution_failed", "failed to read active Rhino document")
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    doc_path = data.get("path") or data.get("documentPath")
    if not isinstance(doc_path, str) or not doc_path.strip():
        raise DirectorActorMetadataError(
            "document_path_required",
            "active Rhino document must be saved before writing Director actor metadata",
        )
    model_path = Path(doc_path).expanduser().resolve()
    return model_path.parent, {
        "file_name": model_path.name,
        "captured_at": _utc_now(),
    }


def _actor_set_ref(actor_set_id: str) -> str:
    return validate_metadata_ref(f".rook/director_planning/actor_sets/{actor_set_id}.json")


def _subset_ref(actor_set_id: str, subset_id: str) -> str:
    return validate_metadata_ref(
        ".rook/director_planning/actor_sets/"
        f"{actor_set_id}_subsets/{subset_id}.json"
    )


def _grouping_ref(actor_set_id: str, subset_id: str, grouping_id: str) -> str:
    return validate_metadata_ref(
        ".rook/director_planning/actor_sets/"
        f"{actor_set_id}_subsets/{subset_id}_band_sets/{grouping_id}.json"
    )


def _snapshot_ref(snapshot_id: str) -> str:
    return validate_metadata_ref(
        f".rook/director_planning/selection_snapshots/{snapshot_id}.json"
    )


def _clone_v2(payload: dict[str, Any], *, kind: str, source_document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DirectorActorMetadataError("metadata_invalid", "metadata item must be an object")
    cloned = copy.deepcopy(payload)
    _reject_legacy_fields(cloned)
    cloned["schema_version"] = SCHEMA_VERSION
    cloned["metadata_kind"] = kind
    cloned["source_document"] = copy.deepcopy(source_document)
    return cloned


def _by_id(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise DirectorActorMetadataError("metadata_invalid", f"{key} is required")
        if value in result:
            raise DirectorActorMetadataError("metadata_invalid", f"{key} duplicated", value=value)
        result[value] = item
    return result


async def write_actor_metadata_bundle_v2(
    arguments: dict[str, Any],
    *,
    call_native=call_rhino,
    port: int | None = None,
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DirectorActorMetadataError("metadata_invalid", "writer arguments must be an object")
    project_root, source_document = await resolve_active_project_root(call_native=call_native, port=port)

    actor_set_raw = arguments.get("actor_set")
    if not isinstance(actor_set_raw, dict):
        raise DirectorActorMetadataError("metadata_invalid", "actor_set is required")
    actor_set_id = actor_set_raw.get("actor_set_id")
    if not isinstance(actor_set_id, str) or not actor_set_id:
        raise DirectorActorMetadataError("metadata_invalid", "actor_set.actor_set_id is required")

    snapshots = _by_id(list(arguments.get("selection_snapshots") or []), "snapshot_id")
    subsets = _by_id(list(arguments.get("subsets") or []), "subset_id")
    groupings = _by_id(list(arguments.get("groupings") or []), "band_set_id")

    written: list[dict[str, str]] = []

    for snapshot_id, snapshot_raw in snapshots.items():
        ref = _snapshot_ref(snapshot_id)
        payload = _clone_v2(snapshot_raw, kind=KIND_SELECTION_SNAPSHOT, source_document=source_document)
        path = resolve_metadata_ref(project_root, ref)
        validate_loaded_metadata(payload, expected_kind=KIND_SELECTION_SNAPSHOT)
        _atomic_write_json(path, payload)
        written.append({"kind": KIND_SELECTION_SNAPSHOT, "ref": ref, "resolved_path": str(path)})

    for grouping_id, grouping_raw in groupings.items():
        parent_subset_id = grouping_raw.get("parent_subset_id")
        if not isinstance(parent_subset_id, str) or not parent_subset_id:
            raise DirectorActorMetadataError("metadata_invalid", "grouping.parent_subset_id is required")
        ref = _grouping_ref(actor_set_id, parent_subset_id, grouping_id)
        payload = _clone_v2(grouping_raw, kind=KIND_ACTOR_GROUPING, source_document=source_document)
        exemplar_id = payload.get("exemplar_selection_snapshot_id")
        if isinstance(exemplar_id, str) and exemplar_id:
            payload["exemplar_selection_snapshot_ref"] = _snapshot_ref(exemplar_id)
        path = resolve_metadata_ref(project_root, ref)
        validate_loaded_metadata(payload, expected_kind=KIND_ACTOR_GROUPING)
        _atomic_write_json(path, payload)
        written.append({"kind": KIND_ACTOR_GROUPING, "ref": ref, "resolved_path": str(path)})

    for subset_id, subset_raw in subsets.items():
        ref = _subset_ref(actor_set_id, subset_id)
        payload = _clone_v2(subset_raw, kind=KIND_ACTOR_SUBSET, source_document=source_document)
        acceptance = payload.get("acceptance")
        if isinstance(acceptance, dict):
            accepted_id = acceptance.get("accepted_selection_snapshot_id")
            if isinstance(accepted_id, str) and accepted_id:
                acceptance["accepted_selection_snapshot_ref"] = _snapshot_ref(accepted_id)
        band_set_ids = payload.pop("band_set_ids", [])
        payload["band_sets"] = [
            {"band_set_id": band_set_id, "ref": _grouping_ref(actor_set_id, subset_id, band_set_id)}
            for band_set_id in band_set_ids
        ]
        path = resolve_metadata_ref(project_root, ref)
        validate_loaded_metadata(payload, expected_kind=KIND_ACTOR_SUBSET)
        _atomic_write_json(path, payload)
        written.append({"kind": KIND_ACTOR_SUBSET, "ref": ref, "resolved_path": str(path)})

    actor_set = _clone_v2(actor_set_raw, kind=KIND_ACTOR_SET, source_document=source_document)
    source_snapshot_id = actor_set.get("source_snapshot_entry_id")
    if isinstance(source_snapshot_id, str) and source_snapshot_id:
        actor_set["source_snapshot_ref"] = _snapshot_ref(source_snapshot_id)
    actor_set["subsets"] = [
        {"subset_id": subset_id, "ref": _subset_ref(actor_set_id, subset_id)}
        for subset_id in subsets
    ]
    actor_set_ref = _actor_set_ref(actor_set_id)
    actor_set_path = resolve_metadata_ref(project_root, actor_set_ref)
    validate_loaded_metadata(actor_set, expected_kind=KIND_ACTOR_SET)
    _atomic_write_json(actor_set_path, actor_set)
    written.append({"kind": KIND_ACTOR_SET, "ref": actor_set_ref, "resolved_path": str(actor_set_path)})

    return {
        "schema_version": SCHEMA_VERSION,
        "actor_set_ref": actor_set_ref,
        "resolved_actor_set_path": str(actor_set_path),
        "written": written,
    }
```

- [ ] **Step 4: Run writer tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_metadata.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/director_actor_metadata.py mcp_server/tests/test_director_actor_metadata.py
git commit -m "feat(director): write actor metadata v2 bundles"
```

---

### Task 3: Explicit v1-to-v2 Migration

**Files:**
- Create: `mcp_server/src/rook/director_actor_migration.py`
- Create: `mcp_server/tests/test_director_actor_migration.py`

**Interfaces introduced:**

```python
def convert_v1_payload(payload: dict, *, project_root: Path, source_path: Path) -> tuple[dict, list[dict]]:
    ...

def migrate_actor_metadata_v2(arguments: dict) -> dict:
    ...

def main(argv: list[str] | None = None) -> int:
    ...
```

The migrator reads only explicit v1 files. It does not run during runtime metadata loading and is not exposed as an MCP tool in this phase.

- [ ] **Step 1: Write failing migration tests**

Create `mcp_server/tests/test_director_actor_migration.py`:

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_actor_metadata as dam
from rook import director_actor_migration as mig


def test_convert_v1_actor_set_payload_renames_paths_and_preserves_members(tmp_path):
    root = tmp_path / "project"
    snapshot = root / ".rook" / "director_planning" / "selection_snapshots" / "intent_005.json"
    subset = root / ".rook" / "director_planning" / "actor_sets" / "set_001_subsets" / "subset_001.json"
    snapshot.parent.mkdir(parents=True)
    subset.parent.mkdir(parents=True)
    snapshot.write_text("{}", encoding="utf-8")
    subset.write_text("{}", encoding="utf-8")

    payload = {
        "schema_version": 1,
        "actor_set_id": "set_001",
        "model_path": str(root / "model.3dm"),
        "source_snapshot_path": str(snapshot),
        "members": [{"actor_id": "a0", "ordinal": 0}],
        "subsets": [{"subset_id": "subset_001", "path": str(subset)}],
    }

    converted, changes = mig.convert_v1_payload(
        payload,
        project_root=root,
        source_path=root / ".rook" / "director_planning" / "actor_sets" / "set_001.json",
    )

    assert converted["schema_version"] == 2
    assert converted["metadata_kind"] == dam.KIND_ACTOR_SET
    assert converted["source_snapshot_ref"] == ".rook/director_planning/selection_snapshots/intent_005.json"
    assert converted["subsets"][0]["ref"].endswith("set_001_subsets/subset_001.json")
    assert converted["members"] == [{"actor_id": "a0", "ordinal": 0}]
    assert "model_path" not in converted
    assert "source_snapshot_path" not in converted
    assert "path" not in converted["subsets"][0]
    assert {change["field"] for change in changes} >= {
        "$.model_path",
        "$.source_snapshot_path",
        "$.subsets[0].path",
    }


def test_convert_v1_snapshot_replaces_model_path_and_document_path(tmp_path):
    root = tmp_path / "project"
    source = root / ".rook" / "director_planning" / "selection_snapshots" / "intent_005.json"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_005",
        "model_path": str(root / "model.3dm"),
        "document": {"path": str(root / "model.3dm"), "units": "Millimeters"},
        "selected": [{"id": "11111111-1111-1111-1111-111111111111"}],
    }

    converted, changes = mig.convert_v1_payload(payload, project_root=root, source_path=source)

    assert converted["metadata_kind"] == dam.KIND_SELECTION_SNAPSHOT
    assert converted["source_document"]["file_name"] == "model.3dm"
    assert converted["document"]["units"] == "Millimeters"
    assert "path" not in converted["document"]
    assert "model_path" not in converted
    assert {change["field"] for change in changes} >= {"$.model_path", "$.document.path"}


def test_convert_v1_rejects_model_path_outside_project(tmp_path):
    root = tmp_path / "project"
    outside_model = tmp_path / "outside" / "model.3dm"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_005",
        "model_path": str(outside_model),
    }

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        mig.convert_v1_payload(
            payload,
            project_root=root,
            source_path=root / ".rook" / "director_planning" / "selection_snapshots" / "intent_005.json",
        )
    assert ei.value.code == "path_outside_project_root"
    assert ei.value.data["field"] == "$.model_path"


def test_convert_v1_rejects_document_path_outside_project(tmp_path):
    root = tmp_path / "project"
    outside_model = tmp_path / "outside" / "model.3dm"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_005",
        "document": {"path": str(outside_model), "units": "Millimeters"},
    }

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        mig.convert_v1_payload(
            payload,
            project_root=root,
            source_path=root / ".rook" / "director_planning" / "selection_snapshots" / "intent_005.json",
        )
    assert ei.value.code == "path_outside_project_root"
    assert ei.value.data["field"] == "$.document.path"


def test_convert_v1_rejects_absolute_path_outside_project(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "outside" / ".rook" / "selection.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "actor_set_id": "set_001",
        "source_snapshot_path": str(outside),
    }

    with pytest.raises(dam.DirectorActorMetadataError) as ei:
        mig.convert_v1_payload(
            payload,
            project_root=root,
            source_path=root / ".rook" / "director_planning" / "actor_sets" / "set_001.json",
        )
    assert ei.value.code == "path_outside_project_root"


def test_migrate_actor_metadata_v2_writes_converted_copy_and_report(tmp_path):
    root = tmp_path / "project"
    actor_set_path = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    snapshot_path = root / ".rook" / "director_planning" / "selection_snapshots" / "intent_005.json"
    actor_set_path.parent.mkdir(parents=True)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_text(
        json.dumps({"schema_version": 1, "snapshot_id": "intent_005"}),
        encoding="utf-8",
    )
    actor_set_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "actor_set_id": "set_001",
                "source_snapshot_path": str(snapshot_path),
                "members": [{"actor_id": "a0"}],
            }
        ),
        encoding="utf-8",
    )

    out = mig.migrate_actor_metadata_v2(
        {
            "project_root": str(root),
            "files": [str(actor_set_path), str(snapshot_path)],
            "write": True,
            "suffix": ".v2",
        }
    )

    assert out["state"] == "complete"
    assert len(out["files"]) == 2
    written = actor_set_path.with_name("set_001.v2.json")
    assert written.is_file()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_migration.py -q
```

Expected: FAIL with `ImportError` for `rook.director_actor_migration`.

- [ ] **Step 3: Implement migration module**

Create `mcp_server/src/rook/director_actor_migration.py`:

```python
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from . import director_actor_metadata as dam


def _source_document_from_path(path_value: Path | None) -> dict[str, Any]:
    if path_value is not None:
        return {"file_name": path_value.name}
    return {"file_name": "unknown.3dm"}


def _validated_project_path_for_identity(
    project_root: Path,
    path_value: Any,
    *,
    field_path: str,
) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    resolved = Path(path_value).expanduser().resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise dam.DirectorActorMetadataError(
            "path_outside_project_root",
            "absolute v1 path is outside the project root",
            field=field_path,
            path=str(resolved),
            project_root=str(project_root),
        ) from exc
    return resolved


def _classify_kind(payload: dict[str, Any], source_path: Path) -> str:
    if "actor_set_id" in payload:
        return dam.KIND_ACTOR_SET
    if "subset_id" in payload:
        return dam.KIND_ACTOR_SUBSET
    if "band_set_id" in payload:
        return dam.KIND_ACTOR_GROUPING
    if "snapshot_id" in payload or "entry_id" in payload:
        return dam.KIND_SELECTION_SNAPSHOT
    name = source_path.name.lower()
    if name.startswith("intent_"):
        return dam.KIND_SELECTION_SNAPSHOT
    raise dam.DirectorActorMetadataError(
        "metadata_kind_unknown",
        "could not infer v1 metadata kind",
        path=str(source_path),
    )


def _record(changes: list[dict[str, str]], field: str, action: str) -> None:
    changes.append({"field": field, "action": action})


def _pop_path_to_ref(
    obj: dict[str, Any],
    *,
    old_key: str,
    new_key: str,
    field_path: str,
    project_root: Path,
    changes: list[dict[str, str]],
) -> None:
    if old_key not in obj:
        return
    old_value = obj.pop(old_key)
    if isinstance(old_value, str) and old_value:
        obj[new_key] = dam.ref_from_project_path(project_root, Path(old_value))
        _record(changes, field_path, f"{old_key} -> {new_key}")


def convert_v1_payload(
    payload: dict[str, Any],
    *,
    project_root: Path,
    source_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not isinstance(payload, dict):
        raise dam.DirectorActorMetadataError("metadata_invalid", "metadata root must be an object")
    if payload.get("schema_version") != 1:
        raise dam.DirectorActorMetadataError(
            "metadata_schema_unsupported",
            "migration accepts only schema_version 1",
            schema_version=payload.get("schema_version"),
        )

    converted = copy.deepcopy(payload)
    changes: list[dict[str, str]] = []
    kind = _classify_kind(converted, source_path)
    model_path = converted.pop("model_path", None)
    model_identity_path = _validated_project_path_for_identity(
        project_root,
        model_path,
        field_path="$.model_path",
    )
    if model_path is not None:
        _record(changes, "$.model_path", "model_path -> source_document.file_name")
    converted["schema_version"] = dam.SCHEMA_VERSION
    converted["metadata_kind"] = kind
    converted["source_document"] = _source_document_from_path(model_identity_path)

    document = converted.get("document")
    if isinstance(document, dict) and "path" in document:
        doc_path = document.pop("path")
        doc_identity_path = _validated_project_path_for_identity(
            project_root,
            doc_path,
            field_path="$.document.path",
        )
        if not converted["source_document"].get("file_name") or converted["source_document"]["file_name"] == "unknown.3dm":
            converted["source_document"] = _source_document_from_path(doc_identity_path)
        _record(changes, "$.document.path", "document.path -> source_document.file_name")

    _pop_path_to_ref(
        converted,
        old_key="source_snapshot_path",
        new_key="source_snapshot_ref",
        field_path="$.source_snapshot_path",
        project_root=project_root,
        changes=changes,
    )
    _pop_path_to_ref(
        converted,
        old_key="exemplar_selection_snapshot_path",
        new_key="exemplar_selection_snapshot_ref",
        field_path="$.exemplar_selection_snapshot_path",
        project_root=project_root,
        changes=changes,
    )

    subsets = converted.get("subsets")
    if isinstance(subsets, list):
        for index, subset in enumerate(subsets):
            if isinstance(subset, dict):
                _pop_path_to_ref(
                    subset,
                    old_key="path",
                    new_key="ref",
                    field_path=f"$.subsets[{index}].path",
                    project_root=project_root,
                    changes=changes,
                )

    acceptance = converted.get("acceptance")
    if isinstance(acceptance, dict):
        _pop_path_to_ref(
            acceptance,
            old_key="accepted_selection_snapshot_path",
            new_key="accepted_selection_snapshot_ref",
            field_path="$.acceptance.accepted_selection_snapshot_path",
            project_root=project_root,
            changes=changes,
        )

    band_sets = converted.get("band_sets")
    if isinstance(band_sets, list):
        for index, band_set in enumerate(band_sets):
            if isinstance(band_set, dict):
                _pop_path_to_ref(
                    band_set,
                    old_key="path",
                    new_key="ref",
                    field_path=f"$.band_sets[{index}].path",
                    project_root=project_root,
                    changes=changes,
                )

    dam.validate_loaded_metadata(converted, expected_kind=kind)
    return converted, changes


def _output_path_for(source: Path, suffix: str) -> Path:
    if suffix:
        return source.with_name(source.stem + suffix + source.suffix)
    return source


def migrate_actor_metadata_v2(arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise dam.DirectorActorMetadataError("metadata_invalid", "migration arguments must be an object")
    project_root = Path(str(arguments.get("project_root", ""))).expanduser().resolve()
    files = arguments.get("files")
    if not isinstance(files, list) or not files:
        raise dam.DirectorActorMetadataError("metadata_invalid", "files must be a non-empty array")
    write = bool(arguments.get("write", False))
    suffix = str(arguments.get("suffix", ".v2"))
    report = {"state": "complete", "project_root": str(project_root), "write": write, "files": []}

    for file_value in files:
        source = Path(str(file_value)).expanduser().resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        converted, changes = convert_v1_payload(payload, project_root=project_root, source_path=source)
        out_path = _output_path_for(source, suffix)
        if write:
            out_path.write_text(json.dumps(converted, indent=2) + "\n", encoding="utf-8")
        report["files"].append(
            {
                "source_path": str(source),
                "output_path": str(out_path),
                "metadata_kind": converted["metadata_kind"],
                "changes": changes,
            }
        )
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Migrate explicit Director actor metadata files to v2 refs.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--file", dest="files", action="append", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--suffix", default=".v2")
    args = parser.parse_args(argv)
    report = migrate_actor_metadata_v2(
        {
            "project_root": args.project_root,
            "files": args.files,
            "write": args.write,
            "suffix": args.suffix,
        }
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run migration tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_migration.py tests/test_director_actor_metadata.py -q
```

Expected: PASS.

- [ ] **Step 5: Verify the offline CLI entry point**

Run:

```powershell
cd mcp_server
$env:PYTHONPATH = (Resolve-Path src).Path
python -m rook.director_actor_migration --help
```

Expected: PASS and prints arguments for `--project-root`, `--file`, `--write`, and `--suffix`. Do not add this migration path to `server.py` or `TOOL_GROUPS["director"]`.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/director_actor_migration.py mcp_server/tests/test_director_actor_migration.py
git commit -m "feat(director): migrate actor metadata to v2 refs"
```

---

### Task 4: MCP Tool Registration, Targeting Policy, And Dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Write failing MCP tests**

Append to `mcp_server/tests/test_director_mcp_tools.py`:

```python
@pytest.mark.asyncio
async def test_actor_metadata_v2_tools_registered():
    tools = {tool.name: tool for tool in await server.list_tools()}
    for name in [
        "rhino_director_write_actor_metadata_v2",
        "rhino_director_read_actor_metadata_v2",
    ]:
        assert name in tools
        assert tools[name].inputSchema["type"] == "object"
        assert _find_rejected_schema_keywords(tools[name].inputSchema) == []


def test_actor_metadata_v2_tools_are_in_director_group():
    for name in [
        "rhino_director_write_actor_metadata_v2",
        "rhino_director_read_actor_metadata_v2",
    ]:
        assert name in tool_groups.TOOL_GROUPS["director"]


@pytest.mark.asyncio
async def test_actor_metadata_migration_is_not_exposed_as_mcp_tool():
    migration_tool = "rhino_director_migrate_actor_metadata_v2"
    tools = {tool.name for tool in await server.list_tools()}

    assert migration_tool not in tools
    assert migration_tool not in tool_groups.TOOL_GROUPS["director"]


@pytest.mark.asyncio
async def test_write_actor_metadata_v2_tool_dispatch_success():
    async def fake_write(arguments, *, port=None):
        assert arguments["actor_set"]["actor_set_id"] == "set_001"
        return {"schema_version": 2, "actor_set_ref": ".rook/director_planning/actor_sets/set_001.json"}

    with patch("rook.server.director_actor_metadata.write_actor_metadata_bundle_v2", new=fake_write):
        out = await server.call_tool(
            "rhino_director_write_actor_metadata_v2",
            {"actor_set": {"actor_set_id": "set_001"}},
        )
    data = json.loads(out[0].text)
    assert data["actor_set_ref"] == ".rook/director_planning/actor_sets/set_001.json"


@pytest.mark.asyncio
async def test_write_actor_metadata_v2_tool_dispatch_error():
    async def fake_write(arguments, *, port=None):
        from rook import director_actor_metadata
        raise director_actor_metadata.DirectorActorMetadataError(
            "document_path_required",
            "active document must be saved",
        )

    with patch("rook.server.director_actor_metadata.write_actor_metadata_bundle_v2", new=fake_write):
        out = await server.call_tool("rhino_director_write_actor_metadata_v2", {})
    text = out[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text[len("Error: "):])
    assert payload["code"] == "document_path_required"


@pytest.mark.asyncio
async def test_read_actor_metadata_v2_tool_dispatch_success(tmp_path):
    from pathlib import Path

    async def fake_resolve_active_project_root(*, port=None):
        return tmp_path, {"file_name": "model.3dm"}

    def fake_load_metadata_ref(project_root, ref, *, expected_kind):
        assert project_root == tmp_path
        assert ref == ".rook/director_planning/actor_sets/set_001.json"
        assert expected_kind == "director_actor_set"
        return {
            "schema_version": 2,
            "metadata_kind": "director_actor_set",
            "actor_set_id": "set_001",
        }

    def fake_resolve_metadata_ref(project_root, ref):
        assert project_root == tmp_path
        assert ref == ".rook/director_planning/actor_sets/set_001.json"
        return Path(tmp_path) / ".rook" / "director_planning" / "actor_sets" / "set_001.json"

    with patch("rook.server.director_actor_metadata.resolve_active_project_root", new=fake_resolve_active_project_root), \
         patch("rook.server.director_actor_metadata.load_metadata_ref", new=fake_load_metadata_ref), \
         patch("rook.server.director_actor_metadata.resolve_metadata_ref", new=fake_resolve_metadata_ref):
        out = await server.call_tool(
            "rhino_director_read_actor_metadata_v2",
            {
                "ref": ".rook/director_planning/actor_sets/set_001.json",
                "expected_kind": "director_actor_set",
            },
        )

    data = json.loads(out[0].text)
    assert data["ref"] == ".rook/director_planning/actor_sets/set_001.json"
    assert data["expected_kind"] == "director_actor_set"
    assert data["payload"]["actor_set_id"] == "set_001"
    assert data["source_document"]["file_name"] == "model.3dm"
    assert data["resolved_metadata_path"].endswith("set_001.json")


@pytest.mark.asyncio
async def test_read_actor_metadata_v2_tool_dispatch_error():
    async def fake_resolve_active_project_root(*, port=None):
        from rook import director_actor_metadata
        raise director_actor_metadata.DirectorActorMetadataError(
            "document_path_required",
            "active document must be saved",
        )

    with patch("rook.server.director_actor_metadata.resolve_active_project_root", new=fake_resolve_active_project_root):
        out = await server.call_tool(
            "rhino_director_read_actor_metadata_v2",
            {
                "ref": ".rook/director_planning/actor_sets/set_001.json",
                "expected_kind": "director_actor_set",
            },
        )

    text = out[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text[len("Error: "):])
    assert payload["code"] == "document_path_required"

```

- [ ] **Step 2: Write failing targeting policy tests**

Append to `mcp_server/tests/test_multi_instance_targeting.py`:

```python
def test_director_actor_metadata_v2_tool_policies():
    assert targeting.policy_for_tool("rhino_director_write_actor_metadata_v2") == targeting.RhinoToolPolicy(True, "mutate")
    assert targeting.policy_for_tool("rhino_director_read_actor_metadata_v2") == targeting.RhinoToolPolicy(True, "read")


def test_director_actor_metadata_migration_has_no_targeting_policy():
    migration_tool = "rhino_director_migrate_actor_metadata_v2"

    assert migration_tool not in targeting._ALL_KNOWN_TOOLS
    assert migration_tool not in targeting.TOOL_POLICIES
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest `
  tests/test_director_mcp_tools.py `
  tests/test_multi_instance_targeting.py `
  -k "actor_metadata_v2 or actor_metadata_migration or director_actor_metadata_v2_tool_policies or director_actor_metadata_migration_has_no_targeting_policy or every_exposed_tool_has_policy_entry" `
  -q
```

Expected: FAIL because the tools are not registered and do not have targeting policies.

- [ ] **Step 4: Import the metadata module in `server.py`**

Modify the existing import line near the top of `mcp_server/src/rook/server.py` so it includes the new modules:

```python
from . import artifacts, director, director_actor_metadata, director_compiler, director_preview, director_publish, director_video, merge_execution, script_library, targeting, workbench, work_units
```

- [ ] **Step 5: Add Tool definitions near the other Director tools**

Add these `Tool(...)` blocks after `rhino_director_preview_motion`:

```python
        Tool(
            name="rhino_director_write_actor_metadata_v2",
            description=(
                "RookVisionDirector: production writer for v2 ActorSet, actor subset, "
                "ActorGrouping, and SelectionSnapshot metadata. Resolves the active saved "
                ".3dm directory via /document, writes schema_version 2 metadata under .rook, "
                "and emits durable .rook/... refs. This is the Lane A writer path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "actor_set": {"type": "object", "description": "ActorSet semantic payload with actor_set_id and members."},
                    "selection_snapshots": {"type": "array", "items": {"type": "object"}, "description": "SelectionSnapshot payloads keyed by snapshot_id."},
                    "subsets": {"type": "array", "items": {"type": "object"}, "description": "Actor subset/intermediate grouping payloads keyed by subset_id."},
                    "groupings": {"type": "array", "items": {"type": "object"}, "description": "ActorGrouping/band-set payloads keyed by band_set_id."},
                },
                "required": ["actor_set"],
            },
        ),
        Tool(
            name="rhino_director_read_actor_metadata_v2",
            description=(
                "RookVisionDirector: strict runtime reader for v2 actor metadata refs. "
                "Accepts a .rook/... ref and expected metadata_kind, resolves against the "
                "active saved .3dm directory, rejects v1 or legacy path fields, and returns "
                "the loaded payload plus resolved runtime path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Durable .rook/... metadata ref."},
                    "expected_kind": {"type": "string", "description": "Expected metadata_kind discriminator."},
                },
                "required": ["ref", "expected_kind"],
            },
        ),
```

- [ ] **Step 6: Add dispatch cases**

Add cases near the other `rhino_director_*` dispatch blocks:

```python
        case "rhino_director_write_actor_metadata_v2":
            try:
                result = {"success": True, "data": await director_actor_metadata.write_actor_metadata_bundle_v2(arguments, port=port)}
            except director_actor_metadata.DirectorActorMetadataError as exc:
                result = {"success": False, "data": exc.to_data()}
        case "rhino_director_read_actor_metadata_v2":
            try:
                project_root, source_document = await director_actor_metadata.resolve_active_project_root(port=port)
                payload = director_actor_metadata.load_metadata_ref(
                    project_root,
                    arguments.get("ref"),
                    expected_kind=arguments.get("expected_kind"),
                )
                resolved_path = director_actor_metadata.resolve_metadata_ref(project_root, arguments.get("ref"))
                result = {
                    "success": True,
                    "data": {
                        "ref": arguments.get("ref"),
                        "expected_kind": arguments.get("expected_kind"),
                        "resolved_metadata_path": str(resolved_path),
                        "source_document": source_document,
                        "payload": payload,
                    },
                }
            except director_actor_metadata.DirectorActorMetadataError as exc:
                result = {"success": False, "data": exc.to_data()}
```

- [ ] **Step 7: Add tools to Director group**

Modify `mcp_server/src/rook/agent/tool_groups.py`:

```python
    "director": [
        "rhino_director_run",
        "rhino_director_curve_samples",
        "rhino_director_replay",
        "rhino_director_replay_cancel",
        "rhino_director_compile_motion",
        "rhino_director_preview_motion",
        "rhino_director_write_actor_metadata_v2",
        "rhino_director_read_actor_metadata_v2",
        "rhino_director_assemble_video",
        "rhino_director_publish_video",
    ],
```

- [ ] **Step 8: Add targeting policies**

Modify `mcp_server/src/rook/targeting.py`:

```python
_ALL_KNOWN_TOOLS = {
    ...
    "rhino_director_read_actor_metadata_v2",
    "rhino_director_write_actor_metadata_v2",
    ...
}

_RHINO_READ_TOOLS = {
    ...
    "rhino_director_curve_samples",
    "rhino_director_read_actor_metadata_v2",
    ...
}
```

Do not add a migration tool to `_ALL_KNOWN_TOOLS`; it is intentionally offline only. `rhino_director_write_actor_metadata_v2` becomes Rhino-dependent mutating through the existing `_RHINO_MUTATE_TOOLS` complement.

- [ ] **Step 9: Run MCP and targeting tests**

Run:

```powershell
cd mcp_server
python -m pytest `
  tests/test_director_mcp_tools.py `
  tests/test_multi_instance_targeting.py `
  -k "actor_metadata_v2 or actor_metadata_migration or director_actor_metadata_v2_tool_policies or director_actor_metadata_migration_has_no_targeting_policy or every_exposed_tool_has_policy_entry" `
  -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_multi_instance_targeting.py
git commit -m "feat(director): expose actor metadata v2 tools"
```

---

### Task 5: Update V2 Director Authoring Output And Agent-Mediated Writer Path

**Files:**
- Update validation artifact only: `H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\animation test.gh`

This task makes Lane A executable as a product gate without inventing an in-canvas MCP transport. The copied `animation test.gh` is not contract authority, but the live authoring path must be patched or regenerated so it emits the semantic metadata bundle that the execution agent passes to `rhino_director_write_actor_metadata_v2`. Do not satisfy Lane A by copied metadata, migrated metadata, or a one-off Python JSON fixture.

Important transport boundary: Grasshopper script components run inside Rhino/Grasshopper. MCP tools are called by Codex/Claude through `mcp_server/src/rook/server.py`. In this phase, GH does not call MCP directly. Adding an in-Rhino HTTP/MCP bridge is out of scope and would require a separate design.

Minimum Lane A fixture state: active V2 `.3dm`, the copied V2 `animation test.gh`, and the existing authoring inputs already present on that canvas or selected from the active model. The task is to keep that capture flow intact while replacing only the metadata persistence protocol.

- [ ] **Step 1: Open the V2 test bed**

Open the active model:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\Axon_Pearson_Experimental_TESTING.3dm
```

Open the copied Grasshopper file:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\animation test.gh
```

Confirm the V2 directory still has no `.rook` before the authoring flow runs.

- [ ] **Step 2: Identify the current metadata writer component**

Use existing GH inspection tools such as `gh_snapshot`, `gh_selection`, `gh_inspect_output`, and `gh_batch_component_info` to locate the component or script that currently writes or outputs ActorSet, ActorGrouping, actor subset, and SelectionSnapshot metadata.

The component may be a prototype script. Treat its semantic payload construction as useful, but treat any absolute path constants or direct JSON file-write logic as prototype debt.

- [ ] **Step 3: Patch or regenerate the component/template**

Use `gh_update_script`, `gh_set_script_pins`, or the appropriate existing GH editing tool to replace only the persistence boundary:

- preserve current authoring inputs, object IDs, grouping membership, accepted band order, classifier/provenance values, and summary fields;
- remove hardcoded original `H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook` assumptions;
- remove direct durable JSON writes from the GH script;
- emit a single semantic bundle output compatible with the `rhino_director_write_actor_metadata_v2` input schema:
  - `actor_set`
  - `selection_snapshots`
  - `subsets`
  - `groupings`
- include enough stable identifiers in the output to let the execution agent correlate the writer result back to the canvas.

The updated component/template must not construct v2 JSON independently in the GH script. It should produce semantic data only; the execution agent owns the MCP writer call.

- [ ] **Step 4: Smoke-test the updated authoring output**

Run the component/template once with the V2 model active and no starting `.rook`. The expected behavior is:

- the GH output is a semantic bundle, not durable metadata JSON;
- the GH output contains no durable drive-root or UNC identity refs;
- no `.rook/...` metadata is created by GH itself;
- the bundle can be read through `gh_inspect_output` or an equivalent GH output inspection route.

- [ ] **Step 5: Agent calls the production writer with the GH bundle**

The execution agent reads the semantic bundle from the updated GH output, then calls:

```text
rhino_director_write_actor_metadata_v2
```

The expected behavior is:

- the MCP writer resolves the active saved V2 `.3dm` through `/document`;
- `.rook/...` metadata is created under `H:\AI EXPERIMENTS\Pearson\ANIMATION\V2`;
- writer output contains durable `.rook/...` refs and runtime `resolved_*_path` diagnostics;
- failures for unsaved or inactive Rhino documents are surfaced as writer errors, not swallowed into fallback paths.

- [ ] **Step 6: Save the V2 GH validation artifact**

Save:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\animation test.gh
```

This file is a live validation artifact. Do not commit it to the repo unless a later task explicitly creates a repo-owned Director template or fixture.

---

### Task 6: Tighten Tests For Durable Absolute Paths And Semantic Preservation

**Files:**
- Modify: `mcp_server/tests/test_director_actor_metadata.py`
- Modify: `mcp_server/tests/test_director_actor_migration.py`

- [ ] **Step 1: Add recursive no-durable-absolute assertion tests**

Append to `mcp_server/tests/test_director_actor_metadata.py`:

```python
def _walk_strings(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def test_generated_bundle_contains_no_durable_absolute_identity_paths(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not-a-real-3dm")
    out = asyncio.run(
        dam.write_actor_metadata_bundle_v2(
            _minimal_bundle(),
            call_native=FakeDocumentNative(str(model)),
            port=None,
        )
    )
    for item in out["written"]:
        payload = json.loads(Path(item["resolved_path"]).read_text(encoding="utf-8"))
        for path, value in _walk_strings(payload):
            if path.endswith("resolved_metadata_path") or ".resolved_" in path:
                continue
            assert not value.startswith("\\\\"), (path, value)
            assert not (len(value) >= 3 and value[1:3] == ":\\"), (path, value)
```

- [ ] **Step 2: Add migration semantic preservation test**

Append to `mcp_server/tests/test_director_actor_migration.py`:

```python
def test_migration_preserves_curated_grouping_semantics(tmp_path):
    root = tmp_path / "project"
    source = root / ".rook" / "director_planning" / "actor_sets" / "set_001_subsets" / "subset_001_band_sets" / "bands_001.json"
    snapshot = root / ".rook" / "director_planning" / "selection_snapshots" / "intent_007.json"
    snapshot.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    snapshot.write_text("{}", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "band_set_id": "bands_001",
        "parent_actor_set_id": "set_001",
        "parent_subset_id": "subset_001",
        "exemplar_selection_snapshot_path": str(snapshot),
        "classifier": {
            "method": "connected_components_by_principal_chord_endpoint_adjacency",
            "threshold_model_units": 1000,
        },
        "summary": {"band_count": 2, "member_count": 3},
        "bands": [
            {"band_id": "b0", "sequence_index": 0, "members": [{"actor_id": "a0"}]},
            {"band_id": "b1", "sequence_index": 1, "members": [{"actor_id": "a1"}]},
        ],
    }

    converted, _ = mig.convert_v1_payload(payload, project_root=root, source_path=source)

    assert converted["classifier"] == payload["classifier"]
    assert converted["summary"] == payload["summary"]
    assert converted["bands"] == payload["bands"]
    assert converted["exemplar_selection_snapshot_ref"] == (
        ".rook/director_planning/selection_snapshots/intent_007.json"
    )
```

- [ ] **Step 3: Run focused tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_director_actor_metadata.py tests/test_director_actor_migration.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add mcp_server/tests/test_director_actor_metadata.py mcp_server/tests/test_director_actor_migration.py
git commit -m "test(director): pin actor metadata v2 path invariants"
```

---

### Task 7: Lane A And Lane B Manual Validation Commands

**Files:**
- None required unless validation findings require a doc note.

This task verifies the implementation against real Pearson fixtures. It requires live Rhino only for Lane A because the agent-mediated writer resolves the active `.3dm` through `/document`.

- [ ] **Step 1: Lane A precondition check**

Verify the V2 fixture starts clean:

```powershell
Test-Path 'H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\.rook'
Get-ChildItem -Force 'H:\AI EXPERIMENTS\Pearson\ANIMATION\V2'
```

Expected:

```text
False
animation test.gh
Axon_Pearson_Experimental_TESTING.3dm
```

- [ ] **Step 2: Open the V2 model in Rhino**

Open:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\Axon_Pearson_Experimental_TESTING.3dm
```

Do not copy `.rook` into V2 before this validation.

- [ ] **Step 3: Run Lane A through the updated V2 authoring output and MCP writer**

Use the updated V2 Director authoring component/template from Task 5 to emit the semantic bundle, inspect that bundle from the GH output, then have the execution agent call `rhino_director_write_actor_metadata_v2` with that exact bundle. Direct Python fixture calls, copied metadata, migrated metadata, and GH-authored durable JSON do not satisfy Lane A.

Expected result shape:

```json
{
  "schema_version": 2,
  "actor_set_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json",
  "resolved_actor_set_path": "H:\\AI EXPERIMENTS\\Pearson\\ANIMATION\\V2\\.rook\\director_planning\\actor_sets\\roof_uplift_vertical_test_chunk_001.json",
  "written": []
}
```

- [ ] **Step 4: Inspect generated V2 metadata**

Run:

```powershell
rg -n 'schema_version|metadata_kind|model_path|source_snapshot_path|accepted_selection_snapshot_path|exemplar_selection_snapshot_path|[A-Za-z]:\\|\\\\' 'H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\.rook' -g '*.json'
```

Expected:

- generated metadata contains `schema_version` values of `2`;
- generated metadata contains required `metadata_kind` values;
- generated durable metadata has no `model_path`, `source_snapshot_path`, `accepted_selection_snapshot_path`, or `exemplar_selection_snapshot_path`;
- no durable identity field contains a drive-root or UNC path.

- [ ] **Step 5: Run Lane B migration dry run on original Pearson files**

Run through the offline module CLI or a direct Python test harness call with these files:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\actor_sets\roof_uplift_vertical_test_chunk_001.json
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\actor_sets\roof_uplift_vertical_test_chunk_001_subsets\same_orientation_mullions_001.json
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\actor_sets\roof_uplift_vertical_test_chunk_001_subsets\same_orientation_mullions_001_band_sets\same_orientation_mullions_001_bands_001.json
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\selection_snapshots\intent_005_20260701_144245.json
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\selection_snapshots\intent_006_20260701_150552.json
H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook\director_planning\selection_snapshots\intent_007_20260701_151718.json
```

Expected: report state `complete`, field changes for every mapped v1 path field, and no write when `write` is false. Do not use an MCP migration tool; migration is intentionally offline in this phase.

- [ ] **Step 6: Commit only if validation documentation is added**

If a short validation note is added to the spec or a follow-up doc, commit it:

```powershell
git add docs/superpowers/specs/2026-07-02-director-v2-relative-actor-metadata-design.md
git commit -m "docs(director): record actor metadata v2 validation"
```

---

## Final Verification

Run:

```powershell
cd mcp_server
python -m pytest `
  tests/test_director_actor_metadata.py `
  tests/test_director_actor_migration.py `
  tests/test_director_mcp_tools.py `
  tests/test_multi_instance_targeting.py `
  -q
```

Expected: PASS.

Run the broader Director Python suite:

```powershell
cd mcp_server
python -m pytest tests/ -k director -q
```

Expected: PASS, except live-Rhino tests may require an active Rhino session and can be run separately when marked or documented by the existing test harness.

Before final handoff:

```powershell
git status --short --branch
git diff origin/main --stat
```

Expected:

- working tree clean;
- changed repo files limited to the new actor metadata Python modules, focused tests, `server.py`, `tool_groups.py`, `targeting.py`, and optional validation docs;
- non-repo validation artifact `H:\AI EXPERIMENTS\Pearson\ANIMATION\V2\animation test.gh` updated only if Lane A validation has been performed.

## Plan Self-Review

Spec coverage:

- v2 `.rook/...` resolver and expected-kind validation: Task 1.
- production writer path and Lane A constraint: Task 2, Task 4, and Task 5.
- explicit GH/MCP transport boundary for Lane A: Task 5 and Task 7.
- strict runtime reader rejection of v1 and old durable path fields: Task 1 and Task 4.
- explicit v1-to-v2 migration with project-root validation for every converted absolute path: Task 3.
- MCP targeting policy for document-dependent writer/reader tools and negative migration non-exposure checks: Task 4.
- no durable absolute path invariant: Task 6.
- Lane A and Lane B validation: Task 7.

The implementation steps contain concrete file paths, commands, tests, and code
sketches. Type names and function names are consistent across tasks:

- `DirectorActorMetadataError`
- `validate_metadata_ref`
- `resolve_metadata_ref`
- `ref_from_project_path`
- `load_metadata_ref`
- `write_actor_metadata_bundle_v2`
- `migrate_actor_metadata_v2`
