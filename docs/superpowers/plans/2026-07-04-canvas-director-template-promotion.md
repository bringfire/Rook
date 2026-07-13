# CanvasDirector Template Promotion Implementation Plan

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the captured Pearson CanvasDirector prototype into a repo-versioned CanvasDirector template pack with a small Python-owned instantiation path over existing Grasshopper tools.

**Architecture:** Grasshopper remains the editable proposal surface and Director remains the runtime truth. The template pack is a package-readable authoring asset bundle under `mcp_server/src/rook/canvas_director_templates/`; generic scripts emit typed authoring payloads, a Pearson fixture supplies project bindings, and a thin Python helper builds or applies existing `gh_create_script`, `gh_snapshot`, and `gh_edit` calls. No Native route, public Companion surface, Director compiler, capture, video, or runtime artifact contract changes are part of this slice.

**Tech Stack:** Python 3.10, pytest, JSON manifests, Hatch packaging, RhinoCode C# Grasshopper script components, existing Rook MCP Grasshopper tools.

---

## Approved Constraints

- Promote `canvas_director.transform` as the durable transform primitive.
- Treat `band_peel_wave` as a transform strategy or preset.
- Do not promote `canvas_director.band_peel_wave_preview`.
- Keep `Director Block Piece Preview` diagnostic and deferred.
- Keep Pearson ids, project paths, frame counts, motion heights, export ids, and proposal ids in fixture binding files, not in generic scripts or the generic manifest.
- Make the export marker a typed assembler: it consumes typed upstream authoring payloads plus fixture-bound ids and emits the existing `rook.canvas_director.export` shape.
- Keep the v0 instantiator thin over existing Grasshopper routes. It may build and optionally apply `gh_create_script`, `gh_snapshot`, and `gh_edit` calls; it must not create a new route, graph language, Native endpoint, Companion API, or Director runtime.
- Treat `template_id` values and node aliases as durable semantic identity. Live Grasshopper component GUIDs are session receipts only; `T*` temp ids are same-batch `gh_edit` wiring handles only.

## Source Evidence

- Design spec: `docs/superpowers/specs/2026-07-04-canvas-director-template-promotion-design.md`
- Prototype root: `C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2/.rook/director/prototype_captures/pearson_canvas_director_prototype_20260704_144510`
- Candidate manifest: `C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2/.rook/director/prototype_captures/pearson_canvas_director_prototype_20260704_144510/template_candidates/canvas_director_pearson_prototype.template_candidates.json`
- Captured scripts manifest: `C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2/.rook/director/prototype_captures/pearson_canvas_director_prototype_20260704_144510/scripts/manifest.json`
- Canvas snapshot: `C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2/.rook/director/prototype_captures/pearson_canvas_director_prototype_20260704_144510/gh_snapshot.data.json`
- Extraction envelope: `C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2/.rook/director/prototype_captures/pearson_canvas_director_prototype_20260704_144510/canvas_extract_envelope.raw.json`

## File Structure

Create this package:

- `mcp_server/src/rook/canvas_director_templates/__init__.py`
  - Public Python import surface for template pack loading, validation, fixture loading, and instantiation plan construction.
- `mcp_server/src/rook/canvas_director_templates/loader.py`
  - Reads `manifest.json`, validates scripts, hashes, schema fields, naming guards, fixture references, and Pearson leakage.
- `mcp_server/src/rook/canvas_director_templates/instantiator.py`
  - Builds deterministic existing-tool calls for a fixture and can execute them through an injected async `call_tool` callable.
- `mcp_server/src/rook/canvas_director_templates/manifest.json`
  - Versioned template pack manifest with exactly the eight promoted template ids.
- `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs`
  - C# script component body for `canvas_director.export_marker`.
- `mcp_server/src/rook/canvas_director_templates/scripts/clock.cs`
  - C# script component body for `canvas_director.clock`.
- `mcp_server/src/rook/canvas_director_templates/scripts/timing_gate.cs`
  - C# script component body for `canvas_director.timing_gate`.
- `mcp_server/src/rook/canvas_director_templates/scripts/oscillator.cs`
  - C# script component body for `canvas_director.oscillator`.
- `mcp_server/src/rook/canvas_director_templates/scripts/actors_v2.cs`
  - C# script component body for `canvas_director.actors_v2`.
- `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs`
  - C# script component body for `canvas_director.transform`; includes `band_peel_wave` as a strategy.
- `mcp_server/src/rook/canvas_director_templates/scripts/camera_path.cs`
  - C# script component body for `canvas_director.camera_path`.
- `mcp_server/src/rook/canvas_director_templates/scripts/camera_controller.cs`
  - C# script component body for `canvas_director.camera_controller`.
- `mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json`
  - Pearson-specific fixture binding for smoke instantiation. This is test/support data, not a packaged runtime template asset.

Modify these existing files only if the task reaches the relevant step:

- `mcp_server/pyproject.toml`
  - Add Hatch package-data inclusion only if the package-data test proves Hatch omits generic template JSON or C# assets.

Add tests:

- `mcp_server/tests/test_canvas_director_templates.py`
  - Pure tests for pack loading, validation, script hashes, naming guards, Pearson leakage, external fixture binding, instantiation call construction, and package-data inclusion.

No `src/RookNative`, `src/Rook`, `mcp_server/src/rook/canvas_director.py`, `mcp_server/src/rook/director.py`, `mcp_server/src/rook/director_compiler.py`, `mcp_server/src/rook/director_video.py`, or `mcp_server/src/rook/server.py` edits are part of this v0 plan.

---

### Task 1: Add Red Tests For Template Pack Contracts

**Files:**
- Create: `mcp_server/tests/test_canvas_director_templates.py`

- [ ] **Step 1: Write the failing test file**

Create `mcp_server/tests/test_canvas_director_templates.py` with this complete content:

```python
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from rook import canvas_director_templates as templates


REQUIRED_TEMPLATE_IDS = {
    "canvas_director.export_marker",
    "canvas_director.clock",
    "canvas_director.timing_gate",
    "canvas_director.oscillator",
    "canvas_director.actors_v2",
    "canvas_director.transform",
    "canvas_director.camera_path",
    "canvas_director.camera_controller",
}


FORBIDDEN_GENERIC_STRINGS = {
    "pearson_animation_test",
    "pearson_v2_smoke",
    "roof_uplift_vertical_test_chunk_001",
    "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
    "C:\\Users\\bring",
    "C:/Users/bring",
    "OneDrive\\Desktop\\Pearson",
    "OneDrive/Desktop/Pearson",
}


PEARSON_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "canvas_director_templates"


def test_template_pack_has_exact_promoted_template_ids() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert ids == REQUIRED_TEMPLATE_IDS


def test_transform_is_promoted_and_band_peel_is_only_strategy() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert "canvas_director.transform" in ids
    assert "canvas_director.band_peel_wave_preview" not in ids

    transform = templates.template_by_id(pack, "canvas_director.transform")
    assert transform["role"] == "transform"
    assert "band_peel_wave" in transform["strategies"]

    serialized = json.dumps(pack, sort_keys=True)
    assert "canvas_director.band_peel_wave_preview" not in serialized


def test_block_piece_preview_is_not_promoted() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert "canvas_director.block_piece_preview" not in ids
    assert all("Block Piece Preview" not in entry.get("display_name", "") for entry in pack["templates"])


def test_template_pack_validates_hashes_and_pin_contracts() -> None:
    pack = templates.load_template_pack()
    assert templates.validate_template_pack(pack) == []

    for template_id in REQUIRED_TEMPLATE_IDS:
        entry = templates.template_by_id(pack, template_id)
        assert entry["template_version"] == "0.1.0"
        assert entry["script"]["language"] == "csharp"
        assert entry["script"]["path"].startswith("scripts/")
        assert entry["script"]["sha256"].startswith("sha256:")
        assert entry["inputs"]
        assert entry["outputs"]


def test_typed_authoring_payload_contracts_are_declared() -> None:
    pack = templates.load_template_pack()
    expected_payloads = {
        "canvas_director.clock": "director_clock_payload",
        "canvas_director.actors_v2": "director_actor_runtime_payload",
        "canvas_director.transform": "director_motion_payload",
        "canvas_director.camera_controller": "director_camera_state",
        "canvas_director.export_marker": "rook.canvas_director.export",
    }
    for template_id, payload_kind in expected_payloads.items():
        entry = templates.template_by_id(pack, template_id)
        assert entry["expected_output_payload_kind"] == payload_kind


def test_generic_template_assets_do_not_leak_pearson_bindings() -> None:
    root = templates.template_root()
    generic_paths = [
        root / "manifest.json",
        *sorted((root / "scripts").glob("*.cs")),
    ]
    for path in generic_paths:
        text = path.read_text(encoding="utf-8")
        leaked = sorted(value for value in FORBIDDEN_GENERIC_STRINGS if value in text)
        assert leaked == [], f"{path} leaked Pearson-only values: {leaked}"


def test_pearson_fixture_contains_project_bindings_and_valid_template_refs() -> None:
    pack = templates.load_template_pack()
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    ids = {entry["template_id"] for entry in pack["templates"]}

    assert fixture["fixture_id"] == "pearson_v2_smoke"
    assert fixture["export_id"] == "pearson_animation_test"
    assert fixture["proposal_id"] == "pearson_v2_smoke"
    assert fixture["templates"] == sorted(REQUIRED_TEMPLATE_IDS)
    assert set(fixture["templates"]) <= ids
    assert fixture["actor_bindings"]["actor_set_ref"].endswith("roof_uplift_vertical_test_chunk_001.json")
    assert fixture["motion"]["strategy"] == "band_peel_wave"
    assert fixture["motion"]["max_height"] == 12000


def test_instantiation_plan_uses_existing_grasshopper_tools_only() -> None:
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    tool_names = [call["tool"] for call in plan["calls"]]

    assert tool_names.count("gh_create_script") == 8
    assert "gh_snapshot" in tool_names
    assert "gh_edit" in tool_names
    assert set(tool_names) <= {"gh_create_script", "gh_snapshot", "gh_edit"}
    assert plan["extract_tool"] == "rhino_director_canvas_extract"


def test_instantiation_plan_connects_typed_payload_outputs_to_export_marker() -> None:
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    connections = plan["deferred_edit"]["connect"]

    assert "actors_v2.O1>export_marker.I0" in connections
    assert "transform.O0>export_marker.I1" in connections
    assert "camera_controller.O1>export_marker.I2" in connections
    assert "TFpsControl.O0>export_marker.I3" in connections
    assert "TFrameCountControl.O0>export_marker.I4" in connections
    assert "TExportIdControl.O0>export_marker.I5" in connections
    assert "TProposalIdControl.O0>export_marker.I6" in connections
    assert "TResolutionControl.O0>export_marker.I7" in connections


def test_gh_edit_temp_ids_are_supported_t_ids() -> None:
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    temp_ids = [entry["temp_id"] for entry in plan["deferred_edit"]["create"]]
    assert temp_ids
    assert all(temp_id.startswith("T") for temp_id in temp_ids)
    assert all(temp_id[1:2].isupper() for temp_id in temp_ids)


@pytest.mark.parametrize(
    "template_id",
    [
        "canvas_director.band_peel_wave_preview",
        "canvas_director.block_piece_preview",
    ],
)
def test_deferred_prototype_ids_are_not_resolvable(template_id: str) -> None:
    pack = templates.load_template_pack()
    with pytest.raises(templates.CanvasDirectorTemplateError, match="template_not_found"):
        templates.template_by_id(pack, template_id)


def test_template_assets_are_present_in_built_wheel(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), "mcp_server"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    wheels = sorted(wheelhouse.glob("rook_mcp-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    assert "rook/canvas_director_templates/manifest.json" in names
    assert "rook/canvas_director_templates/scripts/export_marker.cs" in names
    assert "rook/canvas_director_templates/fixtures/pearson_v2_smoke.json" not in names
```

- [ ] **Step 2: Run the red tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py -q
```

Expected: fails during import with `ImportError` or `ModuleNotFoundError` for `rook.canvas_director_templates`.

- [ ] **Step 3: Commit the red tests**

Run:

```powershell
git add mcp_server/tests/test_canvas_director_templates.py
git commit -m "test(canvas-director): specify template pack contracts"
```

---

### Task 2: Implement Template Loader And Package Surface

**Files:**
- Create: `mcp_server/src/rook/canvas_director_templates/__init__.py`
- Create: `mcp_server/src/rook/canvas_director_templates/loader.py`

- [ ] **Step 1: Create the package init**

Create `mcp_server/src/rook/canvas_director_templates/__init__.py`:

```python
"""Repo-versioned CanvasDirector Grasshopper authoring templates."""

from .loader import (
    CanvasDirectorTemplateError,
    compute_file_sha256,
    load_fixture_binding,
    load_template_pack,
    template_by_id,
    template_root,
    validate_template_pack,
)

__all__ = [
    "CanvasDirectorTemplateError",
    "compute_file_sha256",
    "load_fixture_binding",
    "load_template_pack",
    "template_by_id",
    "template_root",
    "validate_template_pack",
]
```

Task 5 will add `build_instantiation_plan` and `instantiate_fixture` to this package surface after `instantiator.py` exists. Do not import `.instantiator` in Task 2.

- [ ] **Step 2: Create the loader module**

Create `mcp_server/src/rook/canvas_director_templates/loader.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


TEMPLATE_ID_RE = re.compile(r"^canvas_director\.[a-z0-9_]+$")
TEMPLATE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = TEMPLATE_ROOT / "manifest.json"
FIXTURE_ROOT = TEMPLATE_ROOT / "fixtures"
REQUIRED_TEMPLATE_FIELDS = {
    "template_id",
    "template_version",
    "role",
    "display_name",
    "default_nick",
    "script",
    "inputs",
    "outputs",
    "expected_output_payload_kind",
}
REQUIRED_SCRIPT_FIELDS = {"language", "path", "sha256"}
FORBIDDEN_TEMPLATE_IDS = {
    "canvas_director.band_peel_wave_preview",
    "canvas_director.block_piece_preview",
}
FORBIDDEN_GENERIC_STRINGS = {
    "pearson_animation_test",
    "pearson_v2_smoke",
    "roof_uplift_vertical_test_chunk_001",
    "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
    "C:\\Users\\bring",
    "C:/Users/bring",
    "OneDrive\\Desktop\\Pearson",
    "OneDrive/Desktop/Pearson",
}


class CanvasDirectorTemplateError(ValueError):
    """Raised when the CanvasDirector template pack or fixture is invalid."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def template_root() -> Path:
    return TEMPLATE_ROOT


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CanvasDirectorTemplateError("missing_file", str(path)) from exc
    except json.JSONDecodeError as exc:
        raise CanvasDirectorTemplateError("invalid_json", f"{path}:{exc.lineno}") from exc
    if not isinstance(value, dict):
        raise CanvasDirectorTemplateError("invalid_json_type", str(path))
    return value


def load_template_pack(path: Path | str | None = None) -> dict[str, Any]:
    manifest_path = Path(path) if path is not None else MANIFEST_PATH
    return _load_json_object(manifest_path)


def template_by_id(pack: dict[str, Any], template_id: str) -> dict[str, Any]:
    templates = pack.get("templates")
    if not isinstance(templates, list):
        raise CanvasDirectorTemplateError("invalid_manifest", "templates must be a list")
    matches = [
        entry
        for entry in templates
        if isinstance(entry, dict) and entry.get("template_id") == template_id
    ]
    if not matches:
        raise CanvasDirectorTemplateError("template_not_found", template_id)
    if len(matches) > 1:
        raise CanvasDirectorTemplateError("duplicate_template_id", template_id)
    return matches[0]


def _validate_pin_schema(entry: dict[str, Any], field_name: str, errors: list[str]) -> None:
    pins = entry.get(field_name)
    template_id = entry.get("template_id", "<unknown>")
    if not isinstance(pins, list) or not pins:
        errors.append(f"{template_id}:invalid_{field_name}")
        return
    for index, pin in enumerate(pins):
        if not isinstance(pin, dict):
            errors.append(f"{template_id}:invalid_{field_name}_{index}")
            continue
        for required in ("name", "type", "description"):
            if not isinstance(pin.get(required), str) or not pin[required].strip():
                errors.append(f"{template_id}:missing_{field_name}_{index}_{required}")


def _validate_script(entry: dict[str, Any], errors: list[str]) -> None:
    template_id = str(entry.get("template_id", "<unknown>"))
    script = entry.get("script")
    if not isinstance(script, dict):
        errors.append(f"{template_id}:invalid_script")
        return
    missing = sorted(REQUIRED_SCRIPT_FIELDS - set(script))
    for field_name in missing:
        errors.append(f"{template_id}:missing_script_{field_name}")
    if script.get("language") != "csharp":
        errors.append(f"{template_id}:invalid_script_language")
    relative_path = script.get("path")
    if not isinstance(relative_path, str) or not relative_path.startswith("scripts/"):
        errors.append(f"{template_id}:invalid_script_path")
        return
    script_path = (TEMPLATE_ROOT / relative_path).resolve()
    try:
        script_path.relative_to(TEMPLATE_ROOT)
    except ValueError:
        errors.append(f"{template_id}:script_path_escape")
        return
    if not script_path.exists():
        errors.append(f"{template_id}:missing_script_file")
        return
    expected_hash = script.get("sha256")
    actual_hash = compute_file_sha256(script_path)
    if expected_hash != actual_hash:
        errors.append(f"{template_id}:script_hash_mismatch")


def _validate_no_generic_pearson_leak(errors: list[str]) -> None:
    generic_paths = [MANIFEST_PATH, *sorted((TEMPLATE_ROOT / "scripts").glob("*.cs"))]
    for path in generic_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in sorted(FORBIDDEN_GENERIC_STRINGS):
            if forbidden in text:
                errors.append(f"pearson_leak:{path.name}:{forbidden}")


def validate_template_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != 1:
        errors.append("invalid_schema_version")
    if not isinstance(pack.get("template_pack_id"), str) or not pack["template_pack_id"].strip():
        errors.append("missing_template_pack_id")
    templates = pack.get("templates")
    if not isinstance(templates, list) or not templates:
        errors.append("invalid_templates")
        return errors

    seen: set[str] = set()
    for entry in templates:
        if not isinstance(entry, dict):
            errors.append("invalid_template_entry")
            continue
        missing = sorted(REQUIRED_TEMPLATE_FIELDS - set(entry))
        template_id = str(entry.get("template_id", "<unknown>"))
        for field_name in missing:
            errors.append(f"{template_id}:missing_{field_name}")
        if template_id in seen:
            errors.append(f"duplicate_template_id:{template_id}")
        seen.add(template_id)
        if template_id in FORBIDDEN_TEMPLATE_IDS:
            errors.append(f"forbidden_template_id:{template_id}")
        if not TEMPLATE_ID_RE.match(template_id):
            errors.append(f"invalid_template_id:{template_id}")
        if not isinstance(entry.get("template_version"), str) or not entry["template_version"].strip():
            errors.append(f"{template_id}:invalid_template_version")
        _validate_script(entry, errors)
        _validate_pin_schema(entry, "inputs", errors)
        _validate_pin_schema(entry, "outputs", errors)

    _validate_no_generic_pearson_leak(errors)
    return errors


def load_fixture_binding(fixture_id: str, *, fixture_root: Path | str | None = None) -> dict[str, Any]:
    if not isinstance(fixture_id, str) or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$", fixture_id):
        raise CanvasDirectorTemplateError("invalid_fixture_id", str(fixture_id))
    root = Path(fixture_root) if fixture_root is not None else FIXTURE_ROOT
    fixture_path = root / f"{fixture_id}.json"
    fixture = _load_json_object(fixture_path)
    if fixture.get("fixture_id") != fixture_id:
        raise CanvasDirectorTemplateError("fixture_id_mismatch", fixture_id)
    return fixture
```

- [ ] **Step 3: Run a targeted loader import check**

Run:

```powershell
@'
from rook.canvas_director_templates.loader import CanvasDirectorTemplateError, compute_file_sha256, template_root
print(CanvasDirectorTemplateError("ok", "loaded").code)
print(template_root().name)
'@ | mcp_server\.venv\Scripts\python.exe -
```

Expected output includes:

```text
ok
canvas_director_templates
```

- [ ] **Step 4: Commit the loader**

Run:

```powershell
git add mcp_server/src/rook/canvas_director_templates/__init__.py mcp_server/src/rook/canvas_director_templates/loader.py
git commit -m "feat(canvas-director): add template pack loader"
```

---

### Task 3: Promote Generic Script Assets And Manifest

**Files:**
- Create: `mcp_server/src/rook/canvas_director_templates/manifest.json`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/clock.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/timing_gate.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/oscillator.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/actors_v2.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/camera_path.cs`
- Create: `mcp_server/src/rook/canvas_director_templates/scripts/camera_controller.cs`

- [ ] **Step 1: Create script directory**

Run:

```powershell
New-Item -ItemType Directory -Force mcp_server\src\rook\canvas_director_templates\scripts
```

- [ ] **Step 2: Copy generic prototype scripts as starting points**

Copy these files from the prototype capture into the matching promoted script paths:

```powershell
$capture = "C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\prototype_captures\pearson_canvas_director_prototype_20260704_144510\scripts"
Copy-Item "$capture\C37_Director_Clock.cs" mcp_server\src\rook\canvas_director_templates\scripts\clock.cs
Copy-Item "$capture\C27_Director_Timing_Gate.cs" mcp_server\src\rook\canvas_director_templates\scripts\timing_gate.cs
Copy-Item "$capture\C23_Director_Oscillator.cs" mcp_server\src\rook\canvas_director_templates\scripts\oscillator.cs
Copy-Item "$capture\C2_Director_Camera_Path.cs" mcp_server\src\rook\canvas_director_templates\scripts\camera_path.cs
Copy-Item "$capture\C16_Director_Camera_Controller.cs" mcp_server\src\rook\canvas_director_templates\scripts\camera_controller.cs
Copy-Item "$capture\C29_Director_Actors.cs" mcp_server\src\rook\canvas_director_templates\scripts\actors_v2.cs
Copy-Item "$capture\C42_Director_Band_Peel_Wave_Preview.cs" mcp_server\src\rook\canvas_director_templates\scripts\transform.cs
Copy-Item "$capture\C1_CanvasDirector_Export_pearson_animation_test.cs" mcp_server\src\rook\canvas_director_templates\scripts\export_marker.cs
```

- [ ] **Step 3: Normalize `actors_v2.cs`**

Edit `mcp_server/src/rook/canvas_director_templates/scripts/actors_v2.cs` so it satisfies this contract:

```text
Inputs:
- ActorSetPath:string
- ActorGroupingPath:string

Outputs:
- Actors:string
- RuntimePayload:string
- ActorSetId:string
- GroupCount:int
- Info:string

Required behavior:
- If ActorSetPath is blank, Info contains "ActorSetPath is required" and RuntimePayload is empty.
- If ActorGroupingPath is blank, Info contains "ActorGroupingPath is required" and RuntimePayload is empty.
- No default actor-set path is embedded in the script.
- No Pearson object id, Pearson proposal id, Pearson export id, or absolute path is embedded in the script.
- RuntimePayload is JSON with metadata_kind "director_actor_runtime_payload".
```

Retain the prototype script's existing JSON parsing helpers where possible. Remove any fallback literals matching the forbidden generic strings from Task 1.

- [ ] **Step 4: Normalize `transform.cs`**

Edit `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs` so the durable template is a transform primitive and `band_peel_wave` is a strategy:

```text
Inputs:
- Actors:string
- Start:double
- Progress:double
- MaxH:double
- Spread:double
- FastPreview:bool
- Strategy:string

Outputs:
- Motion:string
- G:Geometry
- H:string
- Info:string

Required behavior:
- Strategy defaults to "band_peel_wave" only when blank.
- Motion is JSON with metadata_kind "director_motion_payload".
- Motion includes schema_version 1, strategy, target, keyframes, and preview.
- For band_peel_wave, keyframes include t "0.0" translate [0, 0, 0] and t "1.0" translate [0, 0, MaxH].
- The target comes from the Actors payload; no Pearson actor id is embedded.
- Preview geometry is optional authoring geometry and is not the runtime payload.
```

Use this output shape exactly:

```json
{
  "metadata_kind": "director_motion_payload",
  "schema_version": 1,
  "strategy": "band_peel_wave",
  "target": "actor_set_id_from_Actors_payload",
  "keyframes": [
    {"t": "0.0", "translate": [0, 0, 0]},
    {"t": "1.0", "translate": [0, 0, 12000]}
  ],
  "preview": {
    "start": 0,
    "progress": 1,
    "spread": 16,
    "fast_preview": true
  }
}
```

The numeric values above are examples of runtime values supplied by a fixture or controls. They must not be hard-coded.

- [ ] **Step 5: Normalize `export_marker.cs`**

Edit `mcp_server/src/rook/canvas_director_templates/scripts/export_marker.cs` so the export marker assembles runtime truth from typed upstream payloads plus bound controls:

```text
Inputs:
- Actors:string
- Motion:string
- Camera:string
- FPS:int
- FrameCount:int
- ExportId:string
- ProposalId:string
- Resolution:string

Outputs:
- Json:string
- Info:string

Required behavior:
- Json is empty when Actors or Motion is missing or invalid.
- Json contains metadata_kind "rook.canvas_director.export".
- Json contains schema_version 1.
- Json contains export_id from ExportId and proposal_id from ProposalId.
- Json contains template_id "canvas_director.basic_motion" and template_version "0.1.0" for the existing compiler path.
- Json payload.timeline contains fps and frame_count.
- Json payload.resolution parses "1280x720" into {"width":1280,"height":720}.
- Json payload.groups comes from the Actors payload.
- Json payload.motion comes from the Motion payload's target and keyframes.
- Json payload.camera wraps Camera when Camera has metadata_kind "director_camera_state".
- Json payload.camera falls back to {"strategy":"keyframes","keyframes":[{"frame_index":1,"source":{"kind":"active_view"}}]} when Camera is blank.
```

When wrapping a camera controller payload, use this exact CanvasDirector compiler-compatible source shape:

```json
{
  "strategy": "keyframes",
  "keyframes": [
    {
      "frame_index": 1,
      "source": {
        "kind": "explicit_camera",
        "camera": {
          "projection": "perspective",
          "location": [0, 0, 0],
          "target": [0, 0, 1],
          "up": [0, 0, 1],
          "lens_length": 50
        }
      }
    }
  ]
}
```

The camera values above come from the input payload. They must not be hard-coded beyond the active-view fallback.

- [ ] **Step 6: Keep the remaining scripts generic**

Inspect and edit these scripts to remove any Pearson-only literals from Task 1:

```powershell
rg -n "pearson_animation_test|pearson_v2_smoke|roof_uplift_vertical_test_chunk_001|a28cbdb5-51fa-46b2-b18b-ab880b54ded7|C:\\Users\\bring|OneDrive\\Desktop\\Pearson" mcp_server\src\rook\canvas_director_templates\scripts
```

Expected: no matches.

For `clock.cs`, `timing_gate.cs`, `oscillator.cs`, `camera_path.cs`, and `camera_controller.cs`, retain the prototype logic unless the forbidden-string scan reveals a project binding. Do not add any new file IO, network calls, Native calls, or Director runtime calls.

- [ ] **Step 7: Generate `manifest.json` with computed script hashes**

Run:

```powershell
@'
import json
from pathlib import Path
from rook.canvas_director_templates.loader import compute_file_sha256

root = Path("mcp_server/src/rook/canvas_director_templates")

def script_entry(filename: str) -> dict[str, str]:
    return {
        "language": "csharp",
        "path": f"scripts/{filename}",
        "sha256": compute_file_sha256(root / "scripts" / filename),
    }

manifest = {
    "schema_version": 1,
    "template_pack_id": "canvas_director.core",
    "template_pack_version": "0.1.0",
    "source_capture_id": "pearson_canvas_director_prototype_20260704_144510",
    "templates": [
        {
            "template_id": "canvas_director.export_marker",
            "template_version": "0.1.0",
            "role": "export_marker",
            "display_name": "CanvasDirector Export",
            "default_nick": "CanvasDirector Export",
            "script": script_entry("export_marker.cs"),
            "inputs": [
                {"name": "Actors", "type": "string", "description": "director_actor_runtime_payload JSON"},
                {"name": "Motion", "type": "string", "description": "director_motion_payload JSON"},
                {"name": "Camera", "type": "string", "description": "director_camera_state JSON or blank for active view"},
                {"name": "FPS", "type": "int", "description": "Timeline frames per second"},
                {"name": "FrameCount", "type": "int", "description": "Total frame count"},
                {"name": "ExportId", "type": "string", "description": "CanvasDirector export id"},
                {"name": "ProposalId", "type": "string", "description": "CanvasDirector proposal id"},
                {"name": "Resolution", "type": "string", "description": "Capture resolution such as 1280x720"},
            ],
            "outputs": [
                {"name": "Json", "type": "string", "description": "rook.canvas_director.export JSON"},
                {"name": "Info", "type": "string", "description": "Assembler diagnostics"},
            ],
            "expected_output_payload_kind": "rook.canvas_director.export",
            "fixture_placeholders": ["export_id", "proposal_id", "fps", "frame_count", "resolution"],
            "notes": "Final typed assembler for CanvasDirector extraction. It does not own the animation intent by itself.",
        },
        {
            "template_id": "canvas_director.clock",
            "template_version": "0.1.0",
            "role": "clock",
            "display_name": "Director Clock",
            "default_nick": "Director Clock",
            "script": script_entry("clock.cs"),
            "inputs": [
                {"name": "Frame", "type": "int", "description": "Current frame index"},
                {"name": "FPS", "type": "int", "description": "Frames per second"},
                {"name": "Duration", "type": "double", "description": "Duration in seconds"},
                {"name": "Loop", "type": "bool", "description": "Whether frame wraps"},
                {"name": "Reset", "type": "bool", "description": "Reset request"},
            ],
            "outputs": [
                {"name": "Clock", "type": "string", "description": "director_clock_payload JSON"},
                {"name": "Frame", "type": "int", "description": "Resolved frame index"},
                {"name": "T", "type": "double", "description": "Normalized timeline position"},
                {"name": "Seconds", "type": "double", "description": "Timeline seconds"},
                {"name": "FrameCount", "type": "int", "description": "Total frame count"},
                {"name": "FPS", "type": "int", "description": "Resolved frames per second"},
                {"name": "Info", "type": "string", "description": "Clock diagnostics"},
            ],
            "expected_output_payload_kind": "director_clock_payload",
            "fixture_placeholders": ["fps", "frame_count"],
            "notes": "Timeline authoring payload used by timing gates and controls.",
        },
        {
            "template_id": "canvas_director.timing_gate",
            "template_version": "0.1.0",
            "role": "timing_gate",
            "display_name": "Director Timing Gate",
            "default_nick": "Director Timing Gate",
            "script": script_entry("timing_gate.cs"),
            "inputs": [
                {"name": "Clock", "type": "string", "description": "director_clock_payload JSON"},
                {"name": "Start", "type": "double", "description": "Window start"},
                {"name": "End", "type": "double", "description": "Window end"},
                {"name": "Ease", "type": "string", "description": "Easing name"},
                {"name": "Enabled", "type": "bool", "description": "Gate enabled flag"},
            ],
            "outputs": [
                {"name": "Gate", "type": "string", "description": "director_timing_gate_payload JSON"},
                {"name": "Progress", "type": "double", "description": "Normalized gated progress"},
                {"name": "Active", "type": "bool", "description": "Whether gate is active"},
                {"name": "Ease", "type": "string", "description": "Resolved easing"},
                {"name": "Start", "type": "double", "description": "Resolved start"},
                {"name": "End", "type": "double", "description": "Resolved end"},
                {"name": "T", "type": "double", "description": "Input normalized time"},
                {"name": "Info", "type": "string", "description": "Gate diagnostics"},
            ],
            "expected_output_payload_kind": "director_timing_gate_payload",
            "fixture_placeholders": ["timing_start", "timing_end", "easing"],
            "notes": "Authoring helper; export marker does not read this directly in v0.",
        },
        {
            "template_id": "canvas_director.oscillator",
            "template_version": "0.1.0",
            "role": "oscillator",
            "display_name": "Director Oscillator",
            "default_nick": "Director Oscillator",
            "script": script_entry("oscillator.cs"),
            "inputs": [
                {"name": "Progress", "type": "double", "description": "Normalized progress"},
                {"name": "Amplitude", "type": "double", "description": "Oscillation amplitude"},
                {"name": "Frequency", "type": "double", "description": "Oscillation frequency"},
                {"name": "Phase", "type": "double", "description": "Phase offset"},
                {"name": "Bias", "type": "double", "description": "Value bias"},
                {"name": "Clamp", "type": "bool", "description": "Clamp output to normalized range"},
                {"name": "Enabled", "type": "bool", "description": "Enabled flag"},
            ],
            "outputs": [
                {"name": "Oscillator", "type": "string", "description": "director_oscillator_payload JSON"},
                {"name": "Value", "type": "double", "description": "Oscillator value"},
                {"name": "Wave", "type": "double", "description": "Wave value"},
                {"name": "Progress", "type": "double", "description": "Input progress"},
                {"name": "Amplitude", "type": "double", "description": "Resolved amplitude"},
                {"name": "Frequency", "type": "double", "description": "Resolved frequency"},
                {"name": "Phase", "type": "double", "description": "Resolved phase"},
                {"name": "Bias", "type": "double", "description": "Resolved bias"},
                {"name": "Enabled", "type": "bool", "description": "Resolved enabled flag"},
                {"name": "Info", "type": "string", "description": "Oscillator diagnostics"},
            ],
            "expected_output_payload_kind": "director_oscillator_payload",
            "fixture_placeholders": [],
            "notes": "Reusable curve authoring helper; export marker does not read this directly in v0.",
        },
        {
            "template_id": "canvas_director.actors_v2",
            "template_version": "0.1.0",
            "role": "actors",
            "display_name": "Director Actors",
            "default_nick": "Director Actors",
            "script": script_entry("actors_v2.cs"),
            "inputs": [
                {"name": "ActorSetPath", "type": "string", "description": "Project-relative actor-set .rook path"},
                {"name": "ActorGroupingPath", "type": "string", "description": "Project-relative actor grouping .rook path"},
            ],
            "outputs": [
                {"name": "Actors", "type": "string", "description": "Actor display summary"},
                {"name": "RuntimePayload", "type": "string", "description": "director_actor_runtime_payload JSON"},
                {"name": "ActorSetId", "type": "string", "description": "Resolved actor set id"},
                {"name": "GroupCount", "type": "int", "description": "Resolved group count"},
                {"name": "Info", "type": "string", "description": "Actor diagnostics"},
            ],
            "expected_output_payload_kind": "director_actor_runtime_payload",
            "fixture_placeholders": ["actor_set_ref", "actor_grouping_ref"],
            "notes": "Reads project actor metadata from fixture-bound refs; generic template has no Pearson fallback.",
        },
        {
            "template_id": "canvas_director.transform",
            "template_version": "0.1.0",
            "role": "transform",
            "display_name": "Director Transform",
            "default_nick": "Director Transform",
            "script": script_entry("transform.cs"),
            "inputs": [
                {"name": "Actors", "type": "string", "description": "director_actor_runtime_payload JSON"},
                {"name": "Start", "type": "double", "description": "Local start value"},
                {"name": "Progress", "type": "double", "description": "Normalized progress"},
                {"name": "MaxH", "type": "double", "description": "Maximum Z translation height"},
                {"name": "Spread", "type": "double", "description": "Band spread value"},
                {"name": "FastPreview", "type": "bool", "description": "Preview simplification flag"},
                {"name": "Strategy", "type": "string", "description": "Transform strategy, including band_peel_wave"},
            ],
            "outputs": [
                {"name": "Motion", "type": "string", "description": "director_motion_payload JSON"},
                {"name": "G", "type": "Geometry", "description": "Optional preview geometry"},
                {"name": "H", "type": "string", "description": "Height or preview diagnostics"},
                {"name": "Info", "type": "string", "description": "Transform diagnostics"},
            ],
            "expected_output_payload_kind": "director_motion_payload",
            "strategies": ["band_peel_wave"],
            "fixture_placeholders": ["transform_strategy", "max_height", "spread", "fast_preview"],
            "notes": "Durable transform primitive. The current band peel behavior is a strategy, not the template id.",
        },
        {
            "template_id": "canvas_director.camera_path",
            "template_version": "0.1.0",
            "role": "camera_path",
            "display_name": "Director Camera Path",
            "default_nick": "Director Camera Path",
            "script": script_entry("camera_path.cs"),
            "inputs": [
                {"name": "Path", "type": "Curve", "description": "Camera location path"},
                {"name": "TargetPath", "type": "Curve", "description": "Optional target path"},
                {"name": "Progress", "type": "double", "description": "Path sample progress"},
                {"name": "Up", "type": "Vector3d", "description": "Camera up vector"},
                {"name": "Lens", "type": "double", "description": "Lens length"},
                {"name": "Projection", "type": "string", "description": "Projection mode"},
                {"name": "Distance", "type": "double", "description": "Target offset distance"},
                {"name": "Enabled", "type": "bool", "description": "Enabled flag"},
                {"name": "Preview", "type": "bool", "description": "Preview flag"},
            ],
            "outputs": [
                {"name": "CameraPath", "type": "string", "description": "director_camera_path_payload JSON"},
                {"name": "Camera", "type": "string", "description": "director_camera_state JSON"},
                {"name": "Location", "type": "Point3d", "description": "Sampled camera location"},
                {"name": "Target", "type": "Point3d", "description": "Sampled camera target"},
                {"name": "Direction", "type": "Vector3d", "description": "Camera direction"},
                {"name": "Lens", "type": "double", "description": "Resolved lens length"},
                {"name": "Projection", "type": "string", "description": "Resolved projection mode"},
                {"name": "Info", "type": "string", "description": "Camera path diagnostics"},
            ],
            "expected_output_payload_kind": "director_camera_path_payload",
            "fixture_placeholders": ["camera_path_strategy"],
            "notes": "Authoring helper for camera state; export marker can consume director_camera_state from camera controller.",
        },
        {
            "template_id": "canvas_director.camera_controller",
            "template_version": "0.1.0",
            "role": "camera_controller",
            "display_name": "Director Camera Controller",
            "default_nick": "Director Camera Controller",
            "script": script_entry("camera_controller.cs"),
            "inputs": [
                {"name": "Location", "type": "Point3d", "description": "Camera location"},
                {"name": "Target", "type": "Point3d", "description": "Camera target"},
                {"name": "Direction", "type": "Vector3d", "description": "Camera direction override"},
                {"name": "Up", "type": "Vector3d", "description": "Camera up vector"},
                {"name": "Lens", "type": "double", "description": "Lens length"},
                {"name": "Projection", "type": "string", "description": "Projection mode"},
                {"name": "NearClip", "type": "double", "description": "Near clipping plane"},
                {"name": "FarClip", "type": "double", "description": "Far clipping plane"},
                {"name": "ViewportName", "type": "string", "description": "Optional viewport name"},
                {"name": "Enabled", "type": "bool", "description": "Enabled flag"},
                {"name": "Preview", "type": "bool", "description": "Preview flag"},
                {"name": "Mode", "type": "string", "description": "Target or direction control mode"},
            ],
            "outputs": [
                {"name": "CameraController", "type": "string", "description": "director_camera_controller_payload JSON"},
                {"name": "Camera", "type": "string", "description": "director_camera_state JSON"},
                {"name": "Location", "type": "Point3d", "description": "Resolved camera location"},
                {"name": "Target", "type": "Point3d", "description": "Resolved camera target"},
                {"name": "Direction", "type": "Vector3d", "description": "Resolved camera direction"},
                {"name": "Up", "type": "Vector3d", "description": "Resolved up vector"},
                {"name": "Lens", "type": "double", "description": "Resolved lens length"},
                {"name": "Projection", "type": "string", "description": "Resolved projection mode"},
                {"name": "Info", "type": "string", "description": "Camera diagnostics"},
            ],
            "expected_output_payload_kind": "director_camera_state",
            "fixture_placeholders": ["camera_defaults"],
            "notes": "Camera authoring payload; export marker wraps this into explicit_camera source when present.",
        },
    ],
}

(root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(root / "manifest.json")
for entry in manifest["templates"]:
    print(entry["template_id"], entry["script"]["sha256"])
'@ | mcp_server\.venv\Scripts\python.exe -
```

- [ ] **Step 8: Run validation tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_template_pack_has_exact_promoted_template_ids mcp_server/tests/test_canvas_director_templates.py::test_transform_is_promoted_and_band_peel_is_only_strategy mcp_server/tests/test_canvas_director_templates.py::test_block_piece_preview_is_not_promoted mcp_server/tests/test_canvas_director_templates.py::test_template_pack_validates_hashes_and_pin_contracts mcp_server/tests/test_canvas_director_templates.py::test_typed_authoring_payload_contracts_are_declared mcp_server/tests/test_canvas_director_templates.py::test_generic_template_assets_do_not_leak_pearson_bindings -q
```

Expected: passes after the manifest hashes match the script files and all forbidden strings are removed from generic assets.

- [ ] **Step 9: Commit the template assets**

Run:

```powershell
git add mcp_server/src/rook/canvas_director_templates/manifest.json mcp_server/src/rook/canvas_director_templates/scripts
git commit -m "feat(canvas-director): promote core template scripts"
```

---

### Task 4: Add External Pearson Fixture Binding

**Files:**
- Create: `mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json`

- [ ] **Step 1: Create fixture directory**

Run:

```powershell
New-Item -ItemType Directory -Force mcp_server\tests\fixtures\canvas_director_templates
```

- [ ] **Step 2: Create Pearson fixture binding**

Create `mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json`:

```json
{
  "schema_version": 1,
  "fixture_id": "pearson_v2_smoke",
  "source_capture_id": "pearson_canvas_director_prototype_20260704_144510",
  "project_root": "C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2",
  "export_id": "pearson_animation_test",
  "proposal_id": "pearson_v2_smoke",
  "templates": [
    "canvas_director.actors_v2",
    "canvas_director.camera_controller",
    "canvas_director.camera_path",
    "canvas_director.clock",
    "canvas_director.export_marker",
    "canvas_director.oscillator",
    "canvas_director.timing_gate",
    "canvas_director.transform"
  ],
  "timeline": {
    "fps": 24,
    "frame_count": 240,
    "duration_seconds": 10
  },
  "resolution": {
    "width": 1280,
    "height": 720
  },
  "actor_bindings": {
    "actor_set_ref": ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json",
    "actor_grouping_ref": ".rook/director_planning/actor_groups/roof_uplift_vertical_test_chunk_001.grouping.json",
    "source_object_ids": [
      "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
    ]
  },
  "motion": {
    "strategy": "band_peel_wave",
    "max_height": 12000,
    "spread": 16,
    "fast_preview": true,
    "start": 0,
    "progress": 1
  },
  "timing": {
    "start": 0,
    "end": 1,
    "easing": "ease_in_out"
  },
  "camera": {
    "mode": "target",
    "projection": "perspective",
    "lens_length": 50,
    "near_clip": 0.1,
    "far_clip": 1000000,
    "viewport_name": "Perspective",
    "enabled": true,
    "preview": true
  },
  "layout": {
    "origin": [-1200, -200],
    "x_spacing": 260,
    "y_spacing": 120
  }
}
```

- [ ] **Step 3: Run fixture tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_pearson_fixture_contains_project_bindings_and_valid_template_refs -q
```

Expected: passes.

- [ ] **Step 4: Commit the fixture**

Run:

```powershell
git add mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json
git commit -m "feat(canvas-director): add pearson template fixture"
```

---

### Task 5: Implement Thin Instantiation Plan Builder

**Files:**
- Create: `mcp_server/src/rook/canvas_director_templates/instantiator.py`
- Modify: `mcp_server/src/rook/canvas_director_templates/__init__.py`

- [ ] **Step 1: Create instantiator module**

Create `mcp_server/src/rook/canvas_director_templates/instantiator.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .loader import (
    CanvasDirectorTemplateError,
    load_template_pack,
    template_by_id,
    template_root,
    validate_template_pack,
)


CallTool = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


SCRIPT_ORDER = [
    "canvas_director.clock",
    "canvas_director.timing_gate",
    "canvas_director.oscillator",
    "canvas_director.actors_v2",
    "canvas_director.transform",
    "canvas_director.camera_path",
    "canvas_director.camera_controller",
    "canvas_director.export_marker",
]

NODE_ALIASES = {
    "canvas_director.clock": "clock",
    "canvas_director.timing_gate": "timing_gate",
    "canvas_director.oscillator": "oscillator",
    "canvas_director.actors_v2": "actors_v2",
    "canvas_director.transform": "transform",
    "canvas_director.camera_path": "camera_path",
    "canvas_director.camera_controller": "camera_controller",
    "canvas_director.export_marker": "export_marker",
}


def _pin_definitions(pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(pin["name"]),
            "type": str(pin["type"]),
            "description": str(pin["description"]),
            "optional": True,
        }
        for pin in pins
    ]


def _control_create_ops(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = fixture["timeline"]
    resolution = fixture["resolution"]
    actor_bindings = fixture["actor_bindings"]
    motion = fixture["motion"]
    camera = fixture["camera"]
    x0, y0 = fixture.get("layout", {}).get("origin", [-1200, -200])
    return [
        {"temp_id": "TActorSetControl", "type": "panel", "content": actor_bindings["actor_set_ref"], "pos": [x0, y0 + 220]},
        {"temp_id": "TActorGroupingControl", "type": "panel", "content": actor_bindings["actor_grouping_ref"], "pos": [x0, y0 + 280]},
        {"temp_id": "TFpsControl", "type": "slider", "nick": "FPS", "min": 1, "max": 120, "value": timeline["fps"], "pos": [x0, y0]},
        {"temp_id": "TFrameCountControl", "type": "slider", "nick": "FrameCount", "min": 1, "max": 10000, "value": timeline["frame_count"], "pos": [x0, y0 + 60]},
        {"temp_id": "TExportIdControl", "type": "panel", "content": fixture["export_id"], "pos": [x0, y0 + 420]},
        {"temp_id": "TProposalIdControl", "type": "panel", "content": fixture["proposal_id"], "pos": [x0, y0 + 480]},
        {"temp_id": "TResolutionControl", "type": "panel", "content": f"{resolution['width']}x{resolution['height']}", "pos": [x0, y0 + 540]},
        {"temp_id": "TMotionStrategyControl", "type": "panel", "content": motion["strategy"], "pos": [x0, y0 + 660]},
        {"temp_id": "TMotionMaxHeightControl", "type": "slider", "nick": "MaxH", "min": 0, "max": 50000, "value": motion["max_height"], "pos": [x0, y0 + 720]},
        {"temp_id": "TMotionSpreadControl", "type": "slider", "nick": "Spread", "min": 0, "max": 200, "value": motion["spread"], "pos": [x0, y0 + 780]},
        {"temp_id": "TMotionFastPreviewControl", "type": "toggle", "value": motion["fast_preview"], "pos": [x0, y0 + 840]},
        {"temp_id": "TCameraProjectionControl", "type": "panel", "content": camera["projection"], "pos": [x0, y0 + 960]},
        {"temp_id": "TCameraLensControl", "type": "slider", "nick": "Lens", "min": 1, "max": 200, "value": camera["lens_length"], "pos": [x0, y0 + 1020]}
    ]


def _script_create_calls(pack: dict[str, Any], fixture: dict[str, Any]) -> list[dict[str, Any]]:
    x0, y0 = fixture.get("layout", {}).get("origin", [-1200, -200])
    x_spacing = fixture.get("layout", {}).get("x_spacing", 260)
    y_spacing = fixture.get("layout", {}).get("y_spacing", 120)
    calls: list[dict[str, Any]] = []
    for index, template_id in enumerate(SCRIPT_ORDER):
        entry = template_by_id(pack, template_id)
        script_path = template_root() / entry["script"]["path"]
        calls.append(
            {
                "tool": "gh_create_script",
                "alias": NODE_ALIASES[template_id],
                "arguments": {
                    "language": "csharp",
                    "code": script_path.read_text(encoding="utf-8"),
                    "pins_in": _pin_definitions(entry["inputs"]),
                    "pins_out": _pin_definitions(entry["outputs"]),
                    "name": entry["display_name"],
                    "x": x0 + x_spacing * (index % 4),
                    "y": y0 + y_spacing * (index // 4),
                },
            }
        )
    return calls


def build_instantiation_plan(fixture: dict[str, Any]) -> dict[str, Any]:
    fixture_data = fixture
    pack = load_template_pack()
    errors = validate_template_pack(pack)
    if errors:
        raise CanvasDirectorTemplateError("invalid_template_pack", ";".join(errors))

    calls = _script_create_calls(pack, fixture_data)
    calls.append({"tool": "gh_snapshot", "alias": "snapshot_before_edit", "arguments": {"include_data": False}})

    deferred_edit = {
        "create": _control_create_ops(fixture_data),
        "connect": [
            "TActorSetControl.O0>actors_v2.I0",
            "TActorGroupingControl.O0>actors_v2.I1",
            "actors_v2.O1>transform.I0",
            "TMotionMaxHeightControl.O0>transform.I3",
            "TMotionSpreadControl.O0>transform.I4",
            "TMotionFastPreviewControl.O0>transform.I5",
            "TMotionStrategyControl.O0>transform.I6",
            "TCameraProjectionControl.O0>camera_controller.I5",
            "TCameraLensControl.O0>camera_controller.I4",
            "actors_v2.O1>export_marker.I0",
            "transform.O0>export_marker.I1",
            "camera_controller.O1>export_marker.I2",
            "TFpsControl.O0>export_marker.I3",
            "TFrameCountControl.O0>export_marker.I4",
            "TExportIdControl.O0>export_marker.I5",
            "TProposalIdControl.O0>export_marker.I6",
            "TResolutionControl.O0>export_marker.I7",
        ],
        "groups": [
            {
                "action": "create",
                "nick": "CanvasDirector Template Pack",
                "colour": "#B4D2F596",
                "members": [
                    "clock",
                    "timing_gate",
                    "oscillator",
                    "actors_v2",
                    "transform",
                    "camera_path",
                    "camera_controller",
                    "export_marker",
                ],
            }
        ],
    }
    calls.append({"tool": "gh_edit", "alias": "deferred_wiring", "arguments": {"epoch": "$snapshot_before_edit.epoch", **deferred_edit}})
    return {
        "template_pack_id": pack["template_pack_id"],
        "template_pack_version": pack["template_pack_version"],
        "fixture_id": fixture_data["fixture_id"],
        "calls": calls,
        "deferred_edit": deferred_edit,
        "extract_tool": "rhino_director_canvas_extract",
        "extract_arguments": {
            "project_root": fixture_data["project_root"],
            "export_id": fixture_data["export_id"],
            "solve_mode": "require_fresh_solve",
        },
    }


async def instantiate_fixture(fixture: dict[str, Any], call_tool: CallTool) -> dict[str, Any]:
    plan = build_instantiation_plan(fixture)
    alias_results: dict[str, dict[str, Any]] = {}
    component_aliases: dict[str, str] = {}

    for call in plan["calls"]:
        arguments = dict(call["arguments"])
        if call["tool"] == "gh_edit":
            snapshot = alias_results["snapshot_before_edit"]
            data = snapshot.get("data", snapshot)
            arguments["epoch"] = data["epoch"]
            arguments["connect"] = [
                _resolve_flow_aliases(flow, component_aliases)
                for flow in arguments.get("connect", [])
            ]
            for group in arguments.get("groups", []):
                group["members"] = [component_aliases.get(member, member) for member in group.get("members", [])]

        result = await call_tool(call["tool"], arguments)
        if not isinstance(result, dict) or not result.get("success", False):
            raise CanvasDirectorTemplateError("tool_call_failed", f"{call['tool']}:{result}")
        alias_results[call["alias"]] = result
        if call["tool"] == "gh_create_script":
            data = result.get("data", result)
            component_guid = data.get("component_guid")
            if not isinstance(component_guid, str) or not component_guid:
                raise CanvasDirectorTemplateError("missing_component_guid", call["alias"])
            component_aliases[call["alias"]] = component_guid

    return {"success": True, "plan": plan, "results": alias_results}


def _resolve_flow_aliases(flow: str, component_aliases: dict[str, str]) -> str:
    left, right = flow.split(">", 1)
    source, output = left.split(".", 1)
    target, input_pin = right.split(".", 1)
    resolved_source = component_aliases.get(source, source)
    resolved_target = component_aliases.get(target, target)
    return f"{resolved_source}.{output}>{resolved_target}.{input_pin}"
```

- [ ] **Step 2: Update the package init to expose instantiation helpers**

Replace `mcp_server/src/rook/canvas_director_templates/__init__.py` with:

```python
"""Repo-versioned CanvasDirector Grasshopper authoring templates."""

from .loader import (
    CanvasDirectorTemplateError,
    compute_file_sha256,
    load_fixture_binding,
    load_template_pack,
    template_by_id,
    template_root,
    validate_template_pack,
)
from .instantiator import build_instantiation_plan, instantiate_fixture

__all__ = [
    "CanvasDirectorTemplateError",
    "build_instantiation_plan",
    "compute_file_sha256",
    "instantiate_fixture",
    "load_fixture_binding",
    "load_template_pack",
    "template_by_id",
    "template_root",
    "validate_template_pack",
]
```

- [ ] **Step 3: Run instantiation plan tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_instantiation_plan_uses_existing_grasshopper_tools_only mcp_server/tests/test_canvas_director_templates.py::test_instantiation_plan_connects_typed_payload_outputs_to_export_marker mcp_server/tests/test_canvas_director_templates.py::test_gh_edit_temp_ids_are_supported_t_ids -q
```

Expected: passes.

- [ ] **Step 4: Add fake executor coverage**

Append this test to `mcp_server/tests/test_canvas_director_templates.py`:

```python
@pytest.mark.asyncio
async def test_instantiate_fixture_executes_script_snapshot_and_edit_calls() -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        if tool == "gh_create_script":
            return {"success": True, "data": {"component_guid": f"{arguments['name'].replace(' ', '_')}_guid"}}
        if tool == "gh_snapshot":
            return {"success": True, "data": {"epoch": 17}}
        if tool == "gh_edit":
            assert arguments["epoch"] == 17
            assert arguments["connect"]
            return {"success": True, "data": {"ok": True}}
        raise AssertionError(f"unexpected tool {tool}")

    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    result = await templates.instantiate_fixture(fixture, fake_call_tool)

    assert result["success"] is True
    assert [tool for tool, _ in calls].count("gh_create_script") == 8
    assert [tool for tool, _ in calls][-2:] == ["gh_snapshot", "gh_edit"]

    final_edit = calls[-1][1]
    final_flows = final_edit["connect"]
    joined = "\n".join(final_flows)
    assert "actors_v2." not in joined
    assert "transform." not in joined
    assert "camera_controller." not in joined
    assert "export_marker." not in joined
    assert "Director_Actors_guid.O1>Director_Transform_guid.I0" in final_flows
    assert "Director_Transform_guid.O0>CanvasDirector_Export_guid.I1" in final_flows
    assert "Director_Camera_Controller_guid.O1>CanvasDirector_Export_guid.I2" in final_flows
    assert "TFpsControl.O0>CanvasDirector_Export_guid.I3" in final_flows
    assert "TFrameCountControl.O0>CanvasDirector_Export_guid.I4" in final_flows
```

- [ ] **Step 5: Run fake executor test**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_instantiate_fixture_executes_script_snapshot_and_edit_calls -q
```

Expected: passes.

- [ ] **Step 6: Commit instantiator**

Run:

```powershell
git add mcp_server/src/rook/canvas_director_templates/instantiator.py mcp_server/src/rook/canvas_director_templates/__init__.py mcp_server/tests/test_canvas_director_templates.py
git commit -m "feat(canvas-director): build template instantiation plan"
```

---

### Task 6: Preserve Generic Template Assets In Wheel Packaging

**Files:**
- Modify: `mcp_server/pyproject.toml`

- [ ] **Step 1: Run the package-data test**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_template_assets_are_present_in_built_wheel -q
```

Expected: either passes because Hatch includes package data under `src/rook`, or fails because `manifest.json` or `.cs` assets are missing from the wheel. The external Pearson fixture must not be included in the wheel.

- [ ] **Step 2: Add Hatch force-include only if Step 1 fails**

If the package-data test fails, modify `mcp_server/pyproject.toml` by adding this section after `[tool.hatch.build.targets.wheel]`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/rook/canvas_director_templates/manifest.json" = "rook/canvas_director_templates/manifest.json"
"src/rook/canvas_director_templates/scripts" = "rook/canvas_director_templates/scripts"
```

If the package-data test passes, do not edit `mcp_server/pyproject.toml`.

- [ ] **Step 3: Rerun package-data test**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py::test_template_assets_are_present_in_built_wheel -q
```

Expected: passes.

- [ ] **Step 4: Commit packaging change if there is one**

If `mcp_server/pyproject.toml` changed, run:

```powershell
git add mcp_server/pyproject.toml
git commit -m "build(canvas-director): include template assets in wheel"
```

If `mcp_server/pyproject.toml` did not change, record the passing package-data test in the final task notes and do not make an empty commit.

---

### Task 7: Clean Fixture Extraction Smoke

**Files:**
- No required code changes.
- Optional test note update only if this smoke reveals a contract mismatch in the template scripts or fixture.

- [ ] **Step 1: Confirm no generic script contains Pearson bindings**

Run:

```powershell
rg -n "pearson_animation_test|pearson_v2_smoke|roof_uplift_vertical_test_chunk_001|a28cbdb5-51fa-46b2-b18b-ab880b54ded7|C:\\Users\\bring|OneDrive\\Desktop\\Pearson" mcp_server\src\rook\canvas_director_templates\manifest.json mcp_server\src\rook\canvas_director_templates\scripts
```

Expected: no matches.

- [ ] **Step 2: Generate the fixture instantiation call plan**

Run:

```powershell
@'
import json
from pathlib import Path
from rook import canvas_director_templates as templates
fixture_root = Path("mcp_server/tests/fixtures/canvas_director_templates")
fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=fixture_root)
plan = templates.build_instantiation_plan(fixture)
print(json.dumps({
    "fixture_id": plan["fixture_id"],
    "call_count": len(plan["calls"]),
    "tools": [call["tool"] for call in plan["calls"]],
    "extract_tool": plan["extract_tool"],
    "extract_arguments": plan["extract_arguments"],
}, indent=2, sort_keys=True))
'@ | mcp_server\.venv\Scripts\python.exe -
```

Expected output:

```json
{
  "call_count": 10,
  "extract_arguments": {
    "export_id": "pearson_animation_test",
    "project_root": "C:/Users/bring/OneDrive/Desktop/Pearson/ANIMATION/V2",
    "solve_mode": "require_fresh_solve"
  },
  "extract_tool": "rhino_director_canvas_extract",
  "fixture_id": "pearson_v2_smoke",
  "tools": [
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_create_script",
    "gh_snapshot",
    "gh_edit"
  ]
}
```

- [ ] **Step 3: Run a live clean-canvas smoke when Rhino and Grasshopper are available**

Use existing MCP tools only:

1. Load the external fixture with `templates.load_fixture_binding("pearson_v2_smoke", fixture_root=Path("mcp_server/tests/fixtures/canvas_director_templates"))`.
2. Call `rhino_document`.
3. Read the active Rhino path from `data.documentPath`, `data.path`, or `data.filePath`.
4. Normalize slashes and compare case-insensitively on Windows.
5. Stop unless the active Rhino document path is a saved `.3dm` under or equal to `fixture["project_root"]`.
6. Call `gh_snapshot` with `{"include_data": false}` before any GH mutation.
7. If the snapshot shows the active Pearson prototype definition, any saved non-empty GH document path, or non-empty `components` / `flows`, stop. Do not call `gh_document_new` against the open Pearson prototype definition.
8. Switch to a disposable empty GH document manually, or call `gh_document_new` only after the active GH document is confirmed disposable.
9. Immediately call `gh_snapshot` with `{"include_data": false}` again.
10. Verify the snapshot has `components: []` and `flows: []`. If it is not empty, stop.
11. Apply the eight `gh_create_script` calls from `build_instantiation_plan(fixture)`.
12. Run `gh_snapshot`.
13. Apply the generated `gh_edit` control, wire, and group batch with the returned `epoch`.
14. Run `rhino_director_canvas_extract` with `extract_arguments` from the plan.

This smoke must run in a disposable GH document. Do not run it against the open Pearson prototype definition, even if undo would probably clean up the canvas afterward.

Expected extraction result:

```json
{
  "success": true,
  "data": {
    "canvas_export_state": {
      "metadata_kind": "rook.canvas_director.export",
      "schema_version": 1,
      "export_id": "pearson_animation_test",
      "proposal_id": "pearson_v2_smoke"
    }
  }
}
```

Also inspect the returned payload and verify:

```text
payload.timeline.fps = 24
payload.timeline.frame_count = 240
payload.resolution.width = 1280
payload.resolution.height = 720
payload.motion[0].target is not empty
payload.motion[0].keyframes has t 0.0 and t 1.0 entries
payload.motion[0].keyframes final Z translate is 12000
payload.camera.strategy = keyframes
```

If extraction fails because a promoted script has compile errors, fix the script that failed and rerun Task 3 hash validation before rerunning this smoke. If extraction fails because existing GH tooling cannot create a required native UI control, replace that control with a supported `panel`, `slider`, or `toggle` from the `gh_edit` schema and update the fixture/instantiator tests.

- [ ] **Step 4: Commit any smoke-discovered script corrections**

If the live smoke forced a script correction, run:

```powershell
@'
from pathlib import Path
from rook.canvas_director_templates.loader import compute_file_sha256
root = Path("mcp_server/src/rook/canvas_director_templates/scripts")
for path in sorted(root.glob("*.cs")):
    print(f"{path.name} {compute_file_sha256(path)}")
'@ | mcp_server\.venv\Scripts\python.exe -
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py -q
git add mcp_server/src/rook/canvas_director_templates mcp_server/tests/test_canvas_director_templates.py
git commit -m "fix(canvas-director): stabilize promoted template smoke"
```

If the live smoke passes without code changes, do not create a commit.

---

### Task 8: Final Verification And Self-Review

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_canvas_director_templates.py mcp_server/tests/test_canvas_director.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Verify no disallowed runtime files changed**

Run:

```powershell
git diff --name-only origin/main...HEAD | rg "^(src/RookNative|src/Rook/|mcp_server/src/rook/(canvas_director|director|director_compiler|director_video|server)\\.py)"
```

Expected: no matches for this template-promotion slice. If this command reports files, stop and inspect whether the change violates the non-goals.

- [ ] **Step 3: Verify naming guards from the approved correction**

Run:

```powershell
rg -n "canvas_director\.band_peel_wave_preview|canvas_director\.block_piece_preview|Director Block Piece Preview" mcp_server\src\rook\canvas_director_templates mcp_server\tests\test_canvas_director_templates.py
```

Expected: matches only in tests that assert those names are not promoted. No generic manifest or script match should appear.

- [ ] **Step 4: Verify `band_peel_wave` is only a strategy/preset**

Run:

```powershell
rg -n "band_peel_wave" mcp_server\src\rook\canvas_director_templates mcp_server\tests\fixtures\canvas_director_templates
```

Expected: matches in `mcp_server/src/rook/canvas_director_templates/manifest.json`, `mcp_server/src/rook/canvas_director_templates/scripts/transform.cs`, and `mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json`. No match should contain `template_id` with value `canvas_director.band_peel_wave_preview`.

- [ ] **Step 5: Run formatting/whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 6: Review the final diff**

Run:

```powershell
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected changed files are limited to:

```text
mcp_server/src/rook/canvas_director_templates/__init__.py
mcp_server/src/rook/canvas_director_templates/loader.py
mcp_server/src/rook/canvas_director_templates/instantiator.py
mcp_server/src/rook/canvas_director_templates/manifest.json
mcp_server/src/rook/canvas_director_templates/scripts/*.cs
mcp_server/tests/fixtures/canvas_director_templates/pearson_v2_smoke.json
mcp_server/tests/test_canvas_director_templates.py
mcp_server/pyproject.toml
```

`mcp_server/pyproject.toml` should appear only if Task 6 proved package data needed explicit inclusion.

- [ ] **Step 7: Final commit if needed**

If there are unstaged verification or packaging changes, run:

```powershell
git add mcp_server/src/rook/canvas_director_templates mcp_server/tests/test_canvas_director_templates.py mcp_server/pyproject.toml
git commit -m "test(canvas-director): verify template promotion contracts"
```

If `git status --short` is clean, do not make a commit.

---

## Implementation Notes For Workers

- Do not edit `C:/UDEV/Rook`; use the isolated worktree for this branch.
- Do not add a public MCP tool in this slice. The instantiator is a package helper and can be wired into a public tool later if the template contract proves useful.
- Do not change CanvasDirector extraction, persistence, compile, track, capture, or video code.
- Do not add a Native route or managed Companion public API.
- Do not promote `Director Block Piece Preview`.
- Do not use the Pearson object id or Pearson `.rook` refs in generic scripts or manifest entries.
- Do not convert `band_peel_wave` back into a template id.
- Keep `canvas_director.basic_motion@0.1.0` as the runtime compiler-facing template family emitted by the export marker for v0. `canvas_director.export_marker@0.1.0` is the authoring template id.

## Plan Self-Review

- Spec coverage: tasks cover manifest promotion, typed payload contracts, transform naming correction, deferred block preview, fixture binding separation, thin GH-route instantiation, package-readability, and clean extraction smoke.
- Runtime boundary: no planned edits touch Native, Companion, Director compiler, frame capture, video assembly, or existing CanvasDirector extraction behavior.
- Pearson isolation: tests scan generic scripts and manifest for the known Pearson ids/paths; the fixture is the only approved location for Pearson values.
- v0 size: no new route, graph language, or public tool is introduced.
