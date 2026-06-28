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
