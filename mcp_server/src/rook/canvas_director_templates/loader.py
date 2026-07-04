from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


TEMPLATE_ID_RE = re.compile(r"^canvas_director\.[a-z0-9_]+$")
FIXTURE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
TEMPLATE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = TEMPLATE_ROOT / "manifest.json"
FIXTURE_ROOT = TEMPLATE_ROOT / "fixtures"
TEMPLATE_ROOT_KEY = "__template_root__"
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
    if manifest_path.is_dir():
        manifest_path = manifest_path / "manifest.json"
    pack = _load_json_object(manifest_path)
    pack[TEMPLATE_ROOT_KEY] = str(manifest_path.parent.resolve())
    return pack


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


def validate_template_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pack_root = _template_root_for_pack(pack)

    if pack.get("schema_version") != 1:
        errors.append("invalid_schema_version")
    if not _nonempty_string(pack.get("template_pack_id")):
        errors.append("missing_template_pack_id")

    templates = pack.get("templates")
    if not isinstance(templates, list) or not templates:
        errors.append("invalid_templates")
        _validate_generic_leakage(pack, [], pack_root, errors)
        return errors

    seen_template_ids: set[str] = set()
    script_paths: list[Path] = []
    for index, entry in enumerate(templates):
        if not isinstance(entry, dict):
            errors.append(f"template_{index}:invalid_template")
            continue

        _validate_template_entry(entry, seen_template_ids, script_paths, pack_root, errors)

    _validate_generic_leakage(pack, script_paths, pack_root, errors)
    return errors


def load_fixture_binding(
    fixture_id: str,
    *,
    fixture_root: Path | str | None = None,
) -> dict[str, Any]:
    if not FIXTURE_ID_RE.fullmatch(fixture_id):
        raise CanvasDirectorTemplateError("invalid_fixture_id", fixture_id)

    root = Path(fixture_root) if fixture_root is not None else FIXTURE_ROOT
    fixture = _load_json_object(root / f"{fixture_id}.json")
    if fixture.get("fixture_id") != fixture_id:
        raise CanvasDirectorTemplateError("fixture_id_mismatch", fixture_id)
    return fixture


def _validate_template_entry(
    entry: dict[str, Any],
    seen_template_ids: set[str],
    script_paths: list[Path],
    pack_root: Path,
    errors: list[str],
) -> None:
    template_id = entry.get("template_id")
    label = template_id if isinstance(template_id, str) else "<unknown>"

    for field_name in sorted(REQUIRED_TEMPLATE_FIELDS - set(entry)):
        errors.append(f"{label}:missing_{field_name}")

    if not isinstance(template_id, str) or not template_id.strip():
        errors.append(f"{label}:invalid_template_id")
    else:
        if template_id in seen_template_ids:
            errors.append(f"{template_id}:duplicate_template_id")
        seen_template_ids.add(template_id)
        if template_id in FORBIDDEN_TEMPLATE_IDS:
            errors.append(f"{template_id}:forbidden_template_id")
        if not TEMPLATE_ID_RE.fullmatch(template_id):
            errors.append(f"{template_id}:invalid_template_id")

    for field_name in (
        "template_version",
        "role",
        "display_name",
        "default_nick",
        "expected_output_payload_kind",
    ):
        if field_name in entry and not _nonempty_string(entry.get(field_name)):
            errors.append(f"{label}:invalid_{field_name}")

    _validate_script(entry, script_paths, pack_root, errors)
    _validate_pin_schema(entry, "inputs", errors)
    _validate_pin_schema(entry, "outputs", errors)


def _validate_script(
    entry: dict[str, Any],
    script_paths: list[Path],
    pack_root: Path,
    errors: list[str],
) -> None:
    template_id = str(entry.get("template_id", "<unknown>"))
    script = entry.get("script")
    if not isinstance(script, dict):
        errors.append(f"{template_id}:invalid_script")
        return

    for field_name in sorted(REQUIRED_SCRIPT_FIELDS - set(script)):
        errors.append(f"{template_id}:missing_script_{field_name}")

    if script.get("language") != "csharp":
        errors.append(f"{template_id}:invalid_script_language")

    relative_path = script.get("path")
    if not isinstance(relative_path, str) or not relative_path.startswith("scripts/"):
        errors.append(f"{template_id}:invalid_script_path")
        return

    script_root = (pack_root / "scripts").resolve()
    script_path = (pack_root / relative_path).resolve()
    if not script_path.is_relative_to(script_root):
        errors.append(f"{template_id}:script_path_escape")
        return

    script_paths.append(script_path)
    if not script_path.exists():
        errors.append(f"{template_id}:missing_script_file")
        return
    if not script_path.is_file():
        errors.append(f"{template_id}:script_not_file")
        return

    expected_sha = script.get("sha256")
    if not isinstance(expected_sha, str) or not expected_sha.startswith("sha256:"):
        errors.append(f"{template_id}:invalid_script_sha256")
        return

    try:
        actual_sha = compute_file_sha256(script_path)
    except OSError:
        errors.append(f"{template_id}:unreadable_script_file")
        return
    if expected_sha != actual_sha:
        errors.append(f"{template_id}:script_sha256_mismatch")


def _validate_pin_schema(entry: dict[str, Any], field_name: str, errors: list[str]) -> None:
    pins = entry.get(field_name)
    template_id = str(entry.get("template_id", "<unknown>"))
    if not isinstance(pins, list) or not pins:
        errors.append(f"{template_id}:invalid_{field_name}")
        return

    for index, pin in enumerate(pins):
        if not isinstance(pin, dict):
            errors.append(f"{template_id}:invalid_{field_name}_{index}")
            continue
        for required in ("name", "type", "description"):
            if not _nonempty_string(pin.get(required)):
                errors.append(f"{template_id}:missing_{field_name}_{index}_{required}")


def _validate_generic_leakage(
    pack: dict[str, Any],
    referenced_script_paths: list[Path],
    pack_root: Path,
    errors: list[str],
) -> None:
    manifest_text = json.dumps(_public_manifest_payload(pack), sort_keys=True)
    for leaked in _find_forbidden_generic_strings(manifest_text):
        errors.append(f"manifest:forbidden_generic_string:{leaked}")

    paths_to_scan = set(referenced_script_paths)
    scripts_root = pack_root / "scripts"
    if scripts_root.exists():
        paths_to_scan.update(path.resolve() for path in scripts_root.glob("*.cs"))

    for script_path in sorted(paths_to_scan):
        if not script_path.exists():
            continue
        try:
            script_text = script_path.read_text(encoding="utf-8")
        except OSError:
            errors.append(f"{script_path.name}:unreadable_script")
            continue
        for leaked in _find_forbidden_generic_strings(script_text):
            errors.append(f"{script_path.name}:forbidden_generic_string:{leaked}")


def _template_root_for_pack(pack: dict[str, Any]) -> Path:
    root = pack.get(TEMPLATE_ROOT_KEY)
    if isinstance(root, str) and root.strip():
        return Path(root)
    return TEMPLATE_ROOT


def _public_manifest_payload(pack: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in pack.items() if key != TEMPLATE_ROOT_KEY}


def _find_forbidden_generic_strings(text: str) -> list[str]:
    return sorted(
        {
            raw_value
            for variant, raw_value in _forbidden_generic_string_variants().items()
            if variant in text
        }
    )


def _forbidden_generic_string_variants() -> dict[str, str]:
    variants: dict[str, str] = {}
    for value in FORBIDDEN_GENERIC_STRINGS:
        variants[value] = value
        variants[json.dumps(value)[1:-1]] = value
    return variants


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
