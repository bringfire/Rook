"""Immutable lifecycle authority for contained legacy semantic tools."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class LifecycleDisposition(str, Enum):
    RETIRED = "retired"
    SUSPENDED = "suspended"


class DispatchOrigin(str, Enum):
    PUBLIC_MCP = "public_mcp"
    PROGRESSIVE_META = "progressive_meta"
    SERVER_DISPATCH = "server_dispatch"
    ROOK_AGENT = "rook_agent"
    ROOK_CHAT = "rook_chat"
    PLAN_GRAPH = "plan_graph"
    TOOL_DISPATCHER = "tool_dispatcher"
    INTERNAL_HANDLER = "internal_handler"


@dataclass(frozen=True)
class LifecycleEntry:
    name: str
    disposition: LifecycleDisposition
    recovery: str
    restoration_criteria: tuple[str, ...]
    aliases: tuple[str, ...]


_IDENTITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$", re.ASCII)


def _validate_identity(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    if not value.isascii() or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must match {_IDENTITY_PATTERN.pattern}")
    if len(value.encode("ascii")) > 128:
        raise ValueError(f"{label} exceeds 128 bytes")
    return value


def _validate_text(
    value: object,
    label: str,
    *,
    maximum_utf8_bytes: int,
) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    byte_count = len(value.encode("utf-8"))
    if byte_count < 1 or byte_count > maximum_utf8_bytes:
        raise ValueError(
            f"{label} must be 1-{maximum_utf8_bytes} UTF-8 bytes"
        )
    if value.splitlines() != [value]:
        raise ValueError(f"{label} must be single-line")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _validate_entry(entry: LifecycleEntry) -> None:
    if type(entry) is not LifecycleEntry:
        raise ValueError("manifest entries must be LifecycleEntry instances")
    _validate_identity(entry.name, "canonical name")
    if type(entry.disposition) is not LifecycleDisposition:
        raise ValueError("disposition must be a LifecycleDisposition")
    _validate_text(entry.recovery, "recovery", maximum_utf8_bytes=512)

    if type(entry.aliases) is not tuple:
        raise ValueError("aliases must be a tuple")
    if len(entry.aliases) > 16:
        raise ValueError("an entry may have at most 16 aliases")
    for alias in entry.aliases:
        _validate_identity(alias, "alias")

    if type(entry.restoration_criteria) is not tuple:
        raise ValueError("restoration_criteria must be a tuple")
    if entry.disposition is LifecycleDisposition.RETIRED:
        if entry.restoration_criteria:
            raise ValueError("retired entries must have no restoration criteria")
        return

    if not 1 <= len(entry.restoration_criteria) <= 16:
        raise ValueError("suspended entries require 1-16 restoration criteria")
    for criterion in entry.restoration_criteria:
        _validate_text(
            criterion,
            "restoration criterion",
            maximum_utf8_bytes=256,
        )


def _build_manifest(
    entries: Iterable[LifecycleEntry],
) -> tuple[Mapping[str, LifecycleEntry], Mapping[str, LifecycleEntry]]:
    manifest: dict[str, LifecycleEntry] = {}
    identity_index: dict[str, LifecycleEntry] = {}

    for entry in entries:
        _validate_entry(entry)
        if entry.name in manifest:
            raise ValueError(f"duplicate canonical name: {entry.name}")
        manifest[entry.name] = entry

        for identity in (entry.name, *entry.aliases):
            if identity in identity_index:
                raise ValueError(f"lifecycle identity collision: {identity}")
            identity_index[identity] = entry

    return MappingProxyType(manifest), MappingProxyType(identity_index)


_ENTRIES = (
    LifecycleEntry(
        name="gh_execute_intent",
        disposition=LifecycleDisposition.RETIRED,
        recovery=(
            "Rediscover the current Grasshopper surface; inspect state and "
            "components, then use explicit gh_edit or supported script tools "
            "and verify solve state, outputs, and errors."
        ),
        restoration_criteria=(),
        aliases=(),
    ),
    LifecycleEntry(
        name="rhino_execute_intent",
        disposition=LifecycleDisposition.RETIRED,
        recovery=(
            "Rediscover the current Rhino surface; use explicit typed Rhino "
            "tools, rhino_execute, or a sanctioned preflighted rhino_command, "
            "then verify the host result."
        ),
        restoration_criteria=(),
        aliases=(),
    ),
    LifecycleEntry(
        name="plan_and_execute",
        disposition=LifecycleDisposition.SUSPENDED,
        recovery=(
            "Rediscover the current surface and perform bounded steps through "
            "explicit admitted tools; autonomous plan execution is suspended."
        ),
        restoration_criteria=(
            "A bounded plan contract limits admitted node identities, call "
            "counts, targets, and mutation scope.",
            "Every live node re-enters lifecycle and profile guards before "
            "parameters are copied or execution begins.",
            "Readiness, host verification, failure, and restoration evidence "
            "are deterministic and independently reviewed.",
        ),
        aliases=(),
    ),
    LifecycleEntry(
        name="spawn_agent",
        disposition=LifecycleDisposition.SUSPENDED,
        recovery=(
            "Rediscover the current surface and use the connected model to call "
            "explicit admitted tools directly; autonomous agent spawning is "
            "suspended."
        ),
        restoration_criteria=(
            "Agent authority is bounded by admitted tool identities, explicit "
            "targets, deterministic call budgets, and stop conditions.",
            "Injected and local registries are filtered and every invocation "
            "independently re-enters lifecycle and profile guards.",
            "Live readiness, verification, restoration, and runaway-control "
            "evidence is recorded and independently approved.",
        ),
        aliases=(),
    ),
    LifecycleEntry(
        name="gh_explore_workflow",
        disposition=LifecycleDisposition.SUSPENDED,
        recovery=(
            "Rediscover the current Grasshopper inspection surface and use "
            "explicit snapshot, component, or knowledge tools; semantic "
            "workflow exploration is suspended."
        ),
        restoration_criteria=(
            "The contract is proven host-read-only or every possible mutation "
            "is explicit, bounded, authorized, and verified.",
            "Knowledge or model output cannot directly carry mutation authority "
            "into a hidden executor.",
            "Deterministic tests and live evidence prove the bounded contract "
            "and absence of undeclared host mutation.",
        ),
        aliases=(),
    ),
    LifecycleEntry(
        name="gh_replay_recipe",
        disposition=LifecycleDisposition.SUSPENDED,
        recovery=(
            "Rediscover the current Grasshopper surface and apply reviewed "
            "explicit gh_edit operations; recipe replay is suspended."
        ),
        restoration_criteria=(
            "Recipes use a versioned bounded schema containing only explicit "
            "admitted operations and validated arguments.",
            "Preflight establishes target ownership, readiness, mutation bounds, "
            "and a restoration plan before execution.",
            "Execution produces deterministic host verification and verified "
            "restoration or an approved durable recovery receipt.",
        ),
        aliases=(),
    ),
)

_MANIFEST, _IDENTITY_INDEX = _build_manifest(_ENTRIES)
_CONTAINED_NAMES = frozenset(_IDENTITY_INDEX)


def lifecycle_manifest() -> Mapping[str, LifecycleEntry]:
    return _MANIFEST


def contained_names() -> frozenset[str]:
    return _CONTAINED_NAMES


def resolve_contained_identity(raw_name: object) -> LifecycleEntry | None:
    if type(raw_name) is not str:
        return None
    return _IDENTITY_INDEX.get(raw_name)


def _canonical_manifest_json(
    manifest: Mapping[str, LifecycleEntry],
) -> str:
    records = [
        {
            "name": entry.name,
            "disposition": entry.disposition.value,
            "recovery": entry.recovery,
            "restoration_criteria": list(entry.restoration_criteria),
            "aliases": sorted(entry.aliases),
        }
        for entry in sorted(manifest.values(), key=lambda item: item.name)
    ]
    return json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_CANONICAL_MANIFEST_JSON = _canonical_manifest_json(_MANIFEST)
_LIFECYCLE_FINGERPRINT = hashlib.sha256(
    _CANONICAL_MANIFEST_JSON.encode("utf-8")
).hexdigest()


def canonical_manifest_json() -> str:
    return _CANONICAL_MANIFEST_JSON


def lifecycle_fingerprint() -> str:
    return _LIFECYCLE_FINGERPRINT


def containment_payload(entry: LifecycleEntry) -> dict[str, object]:
    return {
        "code": "legacy_semantic_tool_contained",
        "tool": entry.name,
        "disposition": entry.disposition.value,
        "retryable": False,
        "verified": False,
        "recovery": entry.recovery,
    }


def containment_envelope(entry: LifecycleEntry) -> dict[str, object]:
    return {
        "success": False,
        "data": containment_payload(entry),
    }


def _mcp_record_name(raw_record: object) -> object:
    if isinstance(raw_record, Mapping):
        return raw_record.get("name")
    return getattr(raw_record, "name", None)


def _litellm_schema_name(raw_record: object) -> object:
    function = raw_record.get("function") if isinstance(raw_record, Mapping) else None
    return function.get("name") if isinstance(function, Mapping) else None


def filter_mcp_records(records: Iterable[object]) -> list[object]:
    return [
        record
        for record in records
        if resolve_contained_identity(_mcp_record_name(record)) is None
    ]


def filter_litellm_catalog(
    catalog: Mapping[object, object],
) -> dict[object, object]:
    admitted: dict[object, object] = {}
    for raw_key, raw_record in catalog.items():
        function = (
            raw_record.get("function")
            if isinstance(raw_record, Mapping)
            else None
        )
        embedded = (
            function.get("name") if isinstance(function, Mapping) else None
        )
        if (
            resolve_contained_identity(raw_key)
            or resolve_contained_identity(embedded)
        ):
            continue
        admitted[raw_key] = raw_record
    return admitted


def filter_litellm_schemas(schemas: Iterable[object]) -> list[object]:
    return [
        schema
        for schema in schemas
        if resolve_contained_identity(_litellm_schema_name(schema)) is None
    ]


def filter_local_registrations(
    registrations: Mapping[object, object],
) -> dict[object, object]:
    return {
        raw_name: registration
        for raw_name, registration in registrations.items()
        if resolve_contained_identity(raw_name) is None
    }
