from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

SCHEMA_VERSION = 1
GENERATOR_VERSION = "rookvisiondirector_prepare_take_metadata_only_v1"
PREPARE_STATUS_COMPLETE = "complete"
VALIDATION_STATUS_VALID = "valid"
NATIVE_MAX_INVENTORY_PAGE_SIZE = 1000
APPROVED_ERROR_CODES = {
    "missing_source_selection",
    "unsupported_scope",
    "invalid_source_object_ids",
    "invalid_storage_options",
    "source_document_unsaved",
    "invalid_page_size",
    "inventory_stale",
    "inventory_session_invalid",
    "inventory_cursor_missing",
    "native_response_invalid",
    "invalid_output_root",
    "missing_unsaved_document_session",
    "missing_source_top_level_object_id",
    "missing_source_object_id",
    "missing_source_snapshot_fact",
    "provenance_hash_mismatch",
    "take_already_exists",
}
IDENTITY_TRANSFORM = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_RESERVED_WINDOWS_DEVICE_RE = re.compile(
    r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE
)
_UNSAVED_SESSION_TOKENS: dict[str, str] = {}


class DirectorPrepareError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.extra = extra

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


@dataclass(frozen=True)
class SourceDocumentKey:
    value: str
    scope: str


@dataclass(frozen=True)
class PrepareTakeRequest:
    take_id: str
    scope: str = "selected_occurrences"
    source_object_ids: list[str] = field(default_factory=list)
    use_current_selection: bool = False
    page_size: int = 500
    write_markdown_audit: bool = True
    classify_nested: bool = False
    output_root: str | None = None
    portable: bool = False
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PrepareTakeRequest":
        if not isinstance(payload, dict):
            raise DirectorPrepareError(
                "invalid_source_object_ids", "prepare_take payload must be an object"
            )

        scope = payload.get("scope", "selected_occurrences")
        if scope != "selected_occurrences":
            raise DirectorPrepareError(
                "unsupported_scope",
                "prepare_take only supports scope='selected_occurrences'",
                scope=scope,
            )

        page_size = payload.get("page_size", 500)
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
            or page_size > NATIVE_MAX_INVENTORY_PAGE_SIZE
        ):
            raise DirectorPrepareError(
                "invalid_page_size",
                f"page_size must be an integer between 1 and {NATIVE_MAX_INVENTORY_PAGE_SIZE}",
            )

        portable = bool(payload.get("portable", False))
        output_root = payload.get("output_root")
        if output_root is not None and portable:
            raise DirectorPrepareError(
                "invalid_storage_options",
                "output_root and portable storage cannot both be set",
            )

        take_id = payload.get("take_id") or f"take_{uuid.uuid4().hex}"
        if not _is_safe_take_id(take_id):
            raise DirectorPrepareError(
                "invalid_source_object_ids",
                "take_id must be 1..128 chars using letters, digits, '.', '_' or '-'",
            )

        source_ids = _coerce_string_list(payload.get("source_object_ids") or [])
        use_current_selection = bool(payload.get("use_current_selection", False))
        warnings: list[dict[str, Any]] = []
        if source_ids and use_current_selection:
            warnings.append(
                {
                    "code": "explicit_source_ids_override_selection",
                    "message": "source_object_ids override use_current_selection",
                }
            )
            use_current_selection = False

        write_markdown_audit = payload.get("write_markdown_audit", True)
        if not isinstance(write_markdown_audit, bool):
            raise DirectorPrepareError(
                "invalid_source_object_ids", "write_markdown_audit must be boolean"
            )

        classify_nested = payload.get("classify_nested", False)
        if not isinstance(classify_nested, bool):
            raise DirectorPrepareError(
                "invalid_source_object_ids", "classify_nested must be boolean"
            )

        return cls(
            take_id=take_id,
            scope=scope,
            source_object_ids=source_ids,
            use_current_selection=use_current_selection,
            page_size=page_size,
            write_markdown_audit=write_markdown_audit,
            classify_nested=classify_nested,
            output_root=output_root,
            portable=portable,
            warnings=warnings,
        )


@dataclass(frozen=True)
class StorageResolution:
    storage_mode: str
    final_dir: Path


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise DirectorPrepareError(
            "invalid_source_object_ids", "source_object_ids must be an array"
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise DirectorPrepareError(
                "invalid_source_object_ids", "source_object_ids must contain strings"
            )
        out.append(canonical_source_object_id(item))
    return out


def canonical_source_object_id(value: Any) -> str:
    text = str(value).strip()
    uuid_text = text[1:-1] if text.startswith("{") and text.endswith("}") else text
    try:
        return str(uuid.UUID(uuid_text))
    except (AttributeError, TypeError, ValueError):
        return text


def _is_safe_take_id(value: Any) -> bool:
    if not isinstance(value, str) or _SAFE_SEGMENT_RE.match(value) is None:
        return False
    if value in {".", ".."}:
        return False
    if value.endswith(".") or value.endswith(" "):
        return False
    return _RESERVED_WINDOWS_DEVICE_RE.match(value) is None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_payload(value: Any) -> str:
    return _hash_text(_canonical_json(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_path(document: dict[str, Any]) -> str | None:
    for key in (
        "path",
        "file_path",
        "filePath",
        "full_path",
        "fullPath",
        "document_path",
        "documentPath",
    ):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _is_saved_document(document: dict[str, Any]) -> bool:
    if document.get("is_saved") is False or document.get("isSaved") is False:
        return False
    if document.get("is_unsaved") is True or document.get("isUnsaved") is True:
        return False
    if document.get("is_saved") is True or document.get("isSaved") is True:
        return True
    return _document_path(document) is not None


def _normalized_saved_path(document: dict[str, Any]) -> str:
    path = _document_path(document)
    if path is None:
        raise DirectorPrepareError(
            "native_response_invalid", "saved document facts are missing a path"
        )
    resolved = Path(path).expanduser().resolve(strict=False)
    return str(resolved).replace("\\", "/").lower()


def source_document_key_from_facts(
    document: dict[str, Any], unsaved_session_token: str | None = None
) -> SourceDocumentKey:
    if not isinstance(document, dict):
        raise DirectorPrepareError(
            "native_response_invalid", "document facts must be an object"
        )
    if _is_saved_document(document):
        normalized_path = _normalized_saved_path(document)
        return SourceDocumentKey(
            value=f"saved_document_{_hash_text(normalized_path)[:32]}",
            scope="saved_document",
        )
    token = unsaved_session_token or get_unsaved_session_token(document)
    return SourceDocumentKey(value=token, scope="unsaved_session")


def _unsaved_session_handle(document: dict[str, Any]) -> str | None:
    for key in (
        "documentSessionId",
        "document_session_id",
        "sessionId",
        "session_id",
        "documentHandle",
        "document_handle",
    ):
        value = document.get(key)
        if value is not None and str(value):
            return str(value)
    return None


def get_unsaved_session_token(document: dict[str, Any]) -> str:
    handle = _unsaved_session_handle(document)
    if handle is None:
        raise DirectorPrepareError(
            "missing_unsaved_document_session",
            "unsaved document facts must include a document session handle",
        )
    token = _UNSAVED_SESSION_TOKENS.get(handle)
    if token is None:
        token = f"unsaved_session_{_hash_text(handle)[:32]}"
        _UNSAVED_SESSION_TOKENS[handle] = token
    return token


def resolve_storage(
    *,
    document: dict[str, Any],
    source_document_key: SourceDocumentKey,
    take_id: str,
    output_root: str | None = None,
    portable: bool = False,
) -> StorageResolution:
    if output_root is not None and portable:
        raise DirectorPrepareError(
            "invalid_storage_options",
            "output_root and portable storage cannot both be set",
        )
    if not _is_safe_take_id(take_id):
        raise DirectorPrepareError(
            "invalid_source_object_ids", "take_id is not a valid path segment"
        )

    if portable:
        if not _is_saved_document(document):
            raise DirectorPrepareError(
                "source_document_unsaved",
                "portable storage requires a saved source document",
            )
        document_path = _document_path(document)
        if document_path is None:
            raise DirectorPrepareError(
                "source_document_unsaved",
                "portable storage requires a saved source document path",
            )
        final_dir = (
            Path(document_path).expanduser().resolve(strict=False).parent
            / ".rook"
            / "director_takes"
            / take_id
        ).resolve(strict=False)
        return StorageResolution(storage_mode="document_local", final_dir=final_dir)

    if output_root is not None:
        if not isinstance(output_root, str) or not output_root.strip():
            raise DirectorPrepareError("invalid_output_root", "output_root must be a path")
        root = Path(output_root).expanduser()
        if not root.is_absolute():
            raise DirectorPrepareError(
                "invalid_output_root", "output_root must be an absolute path"
            )
        final_dir = (root.resolve(strict=False) / source_document_key.value / take_id).resolve(
            strict=False
        )
        return StorageResolution(storage_mode="custom_output_root", final_dir=final_dir)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorPrepareError(
            "invalid_output_root",
            "LOCALAPPDATA is required for default director take storage",
        )
    final_dir = (
        Path(local_app_data).expanduser().resolve(strict=False)
        / "Rook"
        / "director_takes"
        / source_document_key.value
        / take_id
    ).resolve(strict=False)
    return StorageResolution(storage_mode="global", final_dir=final_dir)


def _stable_document_facts(
    document: dict[str, Any], source_document_key: SourceDocumentKey
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "source_document_key": source_document_key.value,
        "source_document_key_scope": source_document_key.scope,
        "saved": _is_saved_document(document),
    }
    if _is_saved_document(document):
        normalized_path = _normalized_saved_path(document)
        facts["normalized_path_hash"] = _hash_text(normalized_path)
        facts["file_name"] = Path(normalized_path).name
    else:
        facts["unsaved_session_token_hash"] = _hash_text(source_document_key.value)
    for key in ("document_id", "documentId", "model_id", "modelId"):
        if document.get(key) is not None:
            facts["document_id"] = str(document[key])
            break
    return facts


def build_source_document_fingerprint(
    document: dict[str, Any],
    source_document_key: SourceDocumentKey,
    source_object_ids: list[str],
    inventory_context: dict[str, Any],
    evidence_summary: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "schema_version": SCHEMA_VERSION,
        "stable_document_facts": _stable_document_facts(document, source_document_key),
        "selected_roots": list(source_object_ids),
        "inventory_context": _bounded_stable_copy(inventory_context),
        "provenance_summary": _bounded_stable_copy(evidence_summary),
    }
    body["hash"] = _hash_payload(body)
    return body


def _bounded_stable_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _canonical_segment(segment: Any) -> str:
    if isinstance(segment, dict):
        return _canonical_json(segment)
    return str(segment)


def _path_segments(record: dict[str, Any]) -> list[Any]:
    path = record.get("source_occurrence_path")
    if not isinstance(path, list) or not path:
        raise DirectorPrepareError(
            "missing_source_top_level_object_id",
            "source_occurrence_path must be a non-empty array",
        )
    return path


def _canonical_occurrence_path(record: dict[str, Any]) -> list[str]:
    return [_canonical_segment(segment) for segment in _path_segments(record)]


def path_hash(record: dict[str, Any]) -> str:
    return _hash_payload(_canonical_occurrence_path(record))


def source_occurrence_key(record: dict[str, Any]) -> str:
    return f"occ_{path_hash(record)[:32]}"


def _segment_identity(segment: Any) -> str | None:
    if isinstance(segment, dict):
        for key in (
            "source_top_level_object_id",
            "source_object_id",
            "object_id",
            "objectId",
            "id",
            "instance_object_id",
            "definition_object_id",
        ):
            value = segment.get(key)
            if value is not None and str(value):
                return str(value)
        return None
    if segment is not None and str(segment):
        return str(segment)
    return None


def source_top_level_object_id_from_record(record: dict[str, Any]) -> str:
    value = record.get("source_top_level_object_id")
    if value is not None and str(value):
        return canonical_source_object_id(value)
    path = record.get("source_occurrence_path")
    if isinstance(path, list) and path:
        root = _segment_identity(path[0])
        if root is not None:
            return canonical_source_object_id(root)
    raise DirectorPrepareError(
        "missing_source_top_level_object_id",
        "inventory record must include source_top_level_object_id or a top path root",
    )


def source_object_id_or_definition_object_id(record: dict[str, Any]) -> str:
    for key in (
        "source_object_id_or_definition_object_id",
        "source_object_id",
        "object_id",
        "objectId",
        "definition_object_id",
        "definitionObjectId",
    ):
        value = record.get(key)
        if value is not None and str(value):
            return canonical_source_object_id(value)
    raise DirectorPrepareError(
        "missing_source_object_id",
        "inventory record is missing source or definition object id",
    )


def source_snapshot_from_record(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source_snapshot")
    if not isinstance(source, dict):
        source = record
    required = (
        "object_type",
        "object_name",
        "layer_path",
        "material_ref",
        "local_bbox",
        "world_bbox",
        "world_transform",
    )
    snapshot: dict[str, Any] = {}
    for fact in required:
        if fact not in source or source[fact] is None:
            raise DirectorPrepareError(
                "missing_source_snapshot_fact",
                f"inventory record is missing required source snapshot fact: {fact}",
                fact=fact,
            )
        snapshot[fact] = copy.deepcopy(source[fact])
    return snapshot


_ROLE_BY_KIND = {
    "actor_root": "actor_root",
    "nested_instance": "nested_instance",
    "definition_object": "definition_object",
}
_RELEVANCE_BY_KIND = {
    "actor_root": "direct",
    "nested_instance": "inherited",
    "definition_object": "definition_reference",
}
_SEMANTIC_KEYWORDS = {
    "bridge": ("bridge", "span", "pier", "abutment", "viaduct", "girder"),
    "roof": ("roof", "canopy", "skylight"),
    "facade": ("facade", "curtain wall", "cladding", "storefront"),
    "structure": ("beam", "column", "truss", "slab", "foundation"),
    "site": ("terrain", "road", "pavement", "landscape"),
}


def _text_chunks(value: Any) -> list[str]:
    if isinstance(value, dict):
        chunks: list[str] = []
        for item in value.values():
            chunks.extend(_text_chunks(item))
        return chunks
    if isinstance(value, list):
        chunks = []
        for item in value:
            chunks.extend(_text_chunks(item))
        return chunks
    if value is None:
        return []
    return [str(value)]


def _classify_semantics(
    record_kind: str,
    snapshot: dict[str, Any],
    record: dict[str, Any],
    *,
    classify_nested: bool,
) -> dict[str, Any]:
    text_parts = (
        _text_chunks(snapshot.get("object_name"))
        + _text_chunks(snapshot.get("layer_path"))
        + _text_chunks(snapshot.get("material_ref"))
        + _text_chunks(record.get("semantic_hints"))
        + _text_chunks(record.get("user_strings"))
    )
    text = " ".join(text_parts).lower()
    evidence: dict[str, list[str]] = {}
    for group, keywords in _SEMANTIC_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in text]
        if hits:
            evidence[group] = hits

    candidates = [
        {
            "semantic_group": group,
            "score": len(hits),
            "evidence": hits,
        }
        for group, hits in evidence.items()
    ]
    candidates.sort(key=lambda item: (-item["score"], item["semantic_group"]))

    if not candidates:
        return {
            "semantic_group": None,
            "classification_status": "unclassified",
            "candidate_groups": [],
            "classification_evidence": [],
            "classification_conflicts": [],
        }

    top_score = candidates[0]["score"]
    tied = [candidate for candidate in candidates if candidate["score"] == top_score]
    should_classify_nested = (
        record_kind == "actor_root" or classify_nested or top_score >= 2
    )
    if record_kind != "actor_root" and not should_classify_nested:
        return {
            "semantic_group": None,
            "classification_status": "unclassified",
            "candidate_groups": candidates,
            "classification_evidence": [
                {"semantic_group": group, "matched_terms": terms}
                for group, terms in sorted(evidence.items())
            ],
            "classification_conflicts": [],
        }

    if len(tied) > 1:
        conflict_groups = [candidate["semantic_group"] for candidate in tied]
        return {
            "semantic_group": None,
            "classification_status": "ambiguous",
            "candidate_groups": candidates,
            "classification_evidence": [
                {"semantic_group": group, "matched_terms": terms}
                for group, terms in sorted(evidence.items())
            ],
            "classification_conflicts": [
                {
                    "reason": "strong_evidence_tie",
                    "semantic_groups": conflict_groups,
                }
            ],
        }

    return {
        "semantic_group": candidates[0]["semantic_group"],
        "classification_status": "classified",
        "candidate_groups": candidates,
        "classification_evidence": [
            {"semantic_group": group, "matched_terms": terms}
            for group, terms in sorted(evidence.items())
        ],
        "classification_conflicts": [],
    }


def _actor_id_for(take_id: str, source_top_level_object_id: str) -> str:
    return f"actor_{_hash_text(take_id + '|' + source_top_level_object_id)[:16]}"


def build_provenance_record(
    native_record: dict[str, Any],
    *,
    take_id: str,
    actor_id: str,
    classify_nested: bool = False,
) -> dict[str, Any]:
    if not isinstance(native_record, dict):
        raise DirectorPrepareError(
            "native_response_invalid", "inventory record must be an object"
        )
    source_top_level_object_id = source_top_level_object_id_from_record(native_record)
    occurrence_key = source_occurrence_key(native_record)
    snapshot = source_snapshot_from_record(native_record)
    record_kind = str(native_record.get("record_kind") or native_record.get("kind") or "source_occurrence")
    source_object = source_object_id_or_definition_object_id(native_record)
    classification = _classify_semantics(
        record_kind, snapshot, native_record, classify_nested=classify_nested
    )
    object_role = str(native_record.get("object_role") or _ROLE_BY_KIND.get(record_kind, "source_occurrence"))
    animation_relevance = str(
        native_record.get("animation_relevance")
        or _RELEVANCE_BY_KIND.get(record_kind, "referenced")
    )
    warnings = copy.deepcopy(native_record.get("warnings") or [])
    out = {
        "schema_version": SCHEMA_VERSION,
        "record_kind": record_kind,
        "take_id": take_id,
        "actor_id": actor_id,
        "provenance_id": f"prov_{_hash_text(take_id + '|' + occurrence_key + '|' + source_object)[:32]}",
        "source_occurrence_key": occurrence_key,
        "path_hash": path_hash(native_record),
        "source_occurrence_path": copy.deepcopy(native_record["source_occurrence_path"]),
        "source_top_level_object_id": source_top_level_object_id,
        "source_object_id_or_definition_object_id": source_object,
        "source_snapshot": snapshot,
        "object_role": object_role,
        "animation_relevance": animation_relevance,
        "materialization_status": "referenced_only",
        "semantic_group": classification["semantic_group"],
        "classification_status": classification["classification_status"],
        "candidate_groups": classification["candidate_groups"],
        "classification_evidence": classification["classification_evidence"],
        "classification_conflicts": classification["classification_conflicts"],
        "warnings": warnings,
        "audit": {
            "evidence_authority": "python",
            "native_fact_scope": "transient_inventory_page",
            "representation": "metadata_only",
        },
    }
    return out


class PrepareEvidenceWriter:
    def __init__(
        self,
        *,
        take_id: str,
        run_dir: Path,
        classify_nested: bool,
        selected_root_ids: list[str] | None = None,
    ):
        self.take_id = take_id
        self.run_dir = run_dir
        self.provenance_path = run_dir / "provenance_records.jsonl"
        self.classify_nested = classify_nested
        self.selected_root_ids = set(selected_root_ids) if selected_root_ids is not None else None
        self._fh = None
        self._stream_hash = hashlib.sha256()
        self.provenance_record_count = 0
        self.page_count = 0
        self.role_counts: Counter[str] = Counter()
        self.animation_relevance_counts: Counter[str] = Counter()
        self.materialization_status_counts: Counter[str] = Counter()
        self.warning_counts: Counter[str] = Counter()
        self.actor_summaries: list[dict[str, Any]] = []
        self.root_actor_ids: dict[str, str] = {}
        self._actor_summary_ids: set[str] = set()

    def __enter__(self) -> "PrepareEvidenceWriter":
        self.provenance_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.provenance_path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _actor_id(self, source_top_level_object_id: str) -> str:
        actor_id = self.root_actor_ids.get(source_top_level_object_id)
        if actor_id is None:
            actor_id = _actor_id_for(self.take_id, source_top_level_object_id)
            self.root_actor_ids[source_top_level_object_id] = actor_id
        return actor_id

    def append_page(self, records: list[dict[str, Any]]) -> None:
        if self._fh is None:
            raise DirectorPrepareError(
                "native_response_invalid", "evidence writer is closed"
            )
        if not isinstance(records, list):
            raise DirectorPrepareError(
                "native_response_invalid", "inventory page records must be an array"
            )
        self.page_count += 1
        for native_record in records:
            if not isinstance(native_record, dict):
                raise DirectorPrepareError(
                    "native_response_invalid", "inventory record must be an object"
                )
            source_top_level_object_id = source_top_level_object_id_from_record(native_record)
            if (
                self.selected_root_ids is not None
                and source_top_level_object_id not in self.selected_root_ids
            ):
                raise DirectorPrepareError(
                    "native_response_invalid",
                    "inventory record source root was not in selected source_object_ids",
                )
            actor_id = self._actor_id(source_top_level_object_id)
            payload = build_provenance_record(
                native_record,
                take_id=self.take_id,
                actor_id=actor_id,
                classify_nested=self.classify_nested,
            )
            try:
                line = _canonical_json(payload) + "\n"
            except (TypeError, ValueError) as exc:
                raise DirectorPrepareError(
                    "native_response_invalid",
                    "inventory record could not be serialized as strict JSON",
                ) from exc
            encoded = line.encode("utf-8")
            self._fh.write(line)
            self._fh.flush()
            self._stream_hash.update(encoded)
            self._index_payload(payload)

    def _index_payload(self, payload: dict[str, Any]) -> None:
        self.provenance_record_count += 1
        self.role_counts[payload["object_role"]] += 1
        self.animation_relevance_counts[payload["animation_relevance"]] += 1
        self.materialization_status_counts[payload["materialization_status"]] += 1
        for warning in payload.get("warnings") or []:
            code = warning.get("code") if isinstance(warning, dict) else str(warning)
            self.warning_counts[str(code)] += 1
        if payload["record_kind"] == "actor_root" and payload["actor_id"] not in self._actor_summary_ids:
            self._actor_summary_ids.add(payload["actor_id"])
            self.actor_summaries.append(
                {
                    "take_id": payload["take_id"],
                    "actor_id": payload["actor_id"],
                    "actor_kind": "source_occurrence",
                    "representation": "metadata_only",
                    "source_top_level_object_id": payload["source_top_level_object_id"],
                    "source_occurrence_key": payload["source_occurrence_key"],
                    "source_occurrence_path": copy.deepcopy(payload["source_occurrence_path"]),
                    "semantic_group": payload["semantic_group"],
                    "classification_status": payload["classification_status"],
                }
            )

    def finalize(self) -> dict[str, Any]:
        self.close()
        streaming_hash = self._stream_hash.hexdigest()
        file_hash = _sha256_file(self.provenance_path)
        if streaming_hash != file_hash:
            raise DirectorPrepareError(
                "provenance_hash_mismatch",
                "streaming provenance hash did not match finalized file hash",
            )
        materialized = sum(
            count
            for status, count in self.materialization_status_counts.items()
            if status != "referenced_only"
        )
        return {
            "provenance_record_count": self.provenance_record_count,
            "page_count": self.page_count,
            "actor_count": len(self.actor_summaries),
            "role_counts": dict(sorted(self.role_counts.items())),
            "animation_relevance_counts": dict(sorted(self.animation_relevance_counts.items())),
            "warning_counts": dict(sorted(self.warning_counts.items())),
            "materialization_status_counts": dict(
                sorted(self.materialization_status_counts.items())
            ),
            "referenced_record_count": self.materialization_status_counts.get(
                "referenced_only", 0
            ),
            "materialized_record_count": materialized,
            "provenance_jsonl_sha256": file_hash,
            "actors": copy.deepcopy(self.actor_summaries),
            "root_actor_ids": dict(sorted(self.root_actor_ids.items())),
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def _native_data(
    call_native,
    endpoint: str,
    *,
    method: str = "POST",
    data: Any = None,
    port: int | None = None,
) -> Any:
    result = await call_native(endpoint, method=method, data=data, port=port)
    if not isinstance(result, dict) or not result.get("success"):
        payload = result.get("data") if isinstance(result, dict) else None
        code = "native_response_invalid"
        message = f"native call failed: {endpoint}"
        if isinstance(payload, dict):
            native_code = str(payload.get("code") or code)
            code = native_code if native_code in APPROVED_ERROR_CODES else "native_response_invalid"
            message = str(payload.get("message") or message)
        raise DirectorPrepareError(code, message, endpoint=endpoint)
    return result.get("data")


async def resolve_source_object_ids(
    call_native,
    request: PrepareTakeRequest,
    *,
    port: int | None = None,
) -> list[str]:
    if request.source_object_ids:
        return list(request.source_object_ids)
    if not request.use_current_selection:
        raise DirectorPrepareError(
            "missing_source_selection",
            "source_object_ids or use_current_selection is required",
        )
    selection = await _native_data(
        call_native, "/selection", method="GET", data=None, port=port
    )
    source_ids = _selection_ids(selection)
    if not source_ids:
        raise DirectorPrepareError(
            "missing_source_selection", "current Rhino selection is empty"
        )
    return source_ids


def _selection_ids(selection: Any) -> list[str]:
    if isinstance(selection, dict):
        explicit = selection.get("object_ids") or selection.get("objectIds")
        if isinstance(explicit, list):
            return [
                canonical_source_object_id(item)
                for item in explicit
                if item is not None and str(item)
            ]
        objects = selection.get("objects")
        if isinstance(objects, list):
            out: list[str] = []
            for obj in objects:
                if isinstance(obj, dict):
                    value = obj.get("id") or obj.get("object_id") or obj.get("objectId")
                else:
                    value = obj
                if value is not None and str(value):
                    out.append(canonical_source_object_id(value))
            return out
    if isinstance(selection, list):
        return [
            canonical_source_object_id(item)
            for item in selection
            if item is not None and str(item)
        ]
    return []


def _document_from_native(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("document"), dict):
        return data["document"]
    if isinstance(data, dict):
        return data
    raise DirectorPrepareError(
        "native_response_invalid", "native /document response must be an object"
    )


def _inventory_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    if "records" not in page:
        raise DirectorPrepareError(
            "native_response_invalid", "inventory page is missing a records array"
        )
    page_records = page["records"]
    if not isinstance(page_records, list):
        raise DirectorPrepareError(
            "native_response_invalid", "inventory page records must be an array"
        )
    return page_records


def _page_complete(page: dict[str, Any], next_cursor: Any) -> bool:
    if isinstance(page.get("complete"), bool):
        return bool(page["complete"])
    if isinstance(page.get("is_complete"), bool):
        return bool(page["is_complete"])
    if isinstance(page.get("has_more"), bool):
        return not bool(page["has_more"])
    return next_cursor is None


def _next_cursor(page: dict[str, Any]) -> Any:
    return page.get("next_cursor", page.get("nextCursor"))


def _inventory_context_from_page(page: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if page.get("inventory_session_id") is not None:
        context["inventory_session_id"] = page["inventory_session_id"]
    if isinstance(page.get("inventory_context_fingerprint"), dict):
        context["inventory_context_fingerprint"] = copy.deepcopy(
            page["inventory_context_fingerprint"]
        )
    if isinstance(page.get("inventory_context"), dict):
        context.update(copy.deepcopy(page["inventory_context"]))
    for key in ("schema_version", "native_schema", "traversal_mode"):
        if page.get(key) is not None:
            context[key] = page[key]
    return context


def _warnings_from_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = page.get("warnings")
    if warnings is None:
        return []
    if not isinstance(warnings, list):
        return [{"code": "native_warning", "message": str(warnings)}]

    normalized: list[dict[str, Any]] = []
    for item in warnings:
        if isinstance(item, dict):
            normalized.append(copy.deepcopy(item))
            continue
        message = str(item)
        code = message.split(":", 1)[0].strip() or "native_warning"
        normalized.append({"code": code, "message": message})
    return normalized


def _dedupe_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for warning in warnings:
        key = _canonical_json(warning)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def _merge_warning_counts(
    summary: dict[str, Any], warnings: list[dict[str, Any]]
) -> dict[str, Any]:
    counts = Counter(summary.get("warning_counts") or {})
    for warning in warnings:
        counts[str(warning.get("code", "warning"))] += 1
    merged = dict(summary)
    merged["warning_counts"] = dict(sorted(counts.items()))
    return merged


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _audit_markdown(take_id: str, evidence_summary: dict[str, Any]) -> str:
    return (
        f"# RookVisionDirector Prepare Take Audit\n\n"
        f"- Take ID: `{take_id}`\n"
        f"- Provenance records: {evidence_summary['provenance_record_count']}\n"
        f"- Actor count: {evidence_summary['actor_count']}\n"
        f"- Page count: {evidence_summary['page_count']}\n"
        f"- Validation: valid\n"
    )


async def prepare_take(
    payload: dict[str, Any],
    *,
    call_native=None,
    port: int | None = None,
) -> dict[str, Any]:
    request = PrepareTakeRequest.from_payload(payload)
    if not request.source_object_ids and not request.use_current_selection:
        raise DirectorPrepareError(
            "missing_source_selection",
            "source_object_ids or use_current_selection is required",
        )

    call_native = call_native or call_rhino
    document = _document_from_native(
        await _native_data(call_native, "/document", method="GET", data=None, port=port)
    )
    source_document_key = source_document_key_from_facts(document)
    source_object_ids = await resolve_source_object_ids(call_native, request, port=port)
    storage = resolve_storage(
        document=document,
        source_document_key=source_document_key,
        take_id=request.take_id,
        output_root=request.output_root,
        portable=request.portable,
    )

    final_dir = storage.final_dir
    if final_dir.exists():
        raise DirectorPrepareError(
            "take_already_exists", f"take directory already exists: {final_dir}"
        )
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = final_dir.parent / f".{request.take_id}.tmp.{uuid.uuid4().hex}"
    if temp_dir.exists():
        raise DirectorPrepareError(
            "take_already_exists", f"temporary take directory already exists: {temp_dir}"
        )
    temp_dir.mkdir(parents=True)

    try:
        inventory_context: dict[str, Any] = {
            "page_size": request.page_size,
            "scope": request.scope,
        }
        inventory_warnings: list[dict[str, Any]] = []
        with PrepareEvidenceWriter(
            take_id=request.take_id,
            run_dir=temp_dir,
            classify_nested=request.classify_nested,
            selected_root_ids=source_object_ids,
        ) as writer:
            cursor = None
            inventory_session_id = None
            first_page = True
            while True:
                if first_page:
                    inventory_payload = {
                        "source_object_ids": list(source_object_ids),
                        "page_size": request.page_size,
                        "cursor": None,
                    }
                else:
                    inventory_payload = {
                        "inventory_session_id": inventory_session_id,
                        "page_size": request.page_size,
                        "cursor": cursor,
                    }
                page_data = await _native_data(
                    call_native,
                    "/director/occurrence-inventory",
                    method="POST",
                    data=inventory_payload,
                    port=port,
                )
                if not isinstance(page_data, dict):
                    raise DirectorPrepareError(
                        "native_response_invalid", "inventory page must be an object"
                    )
                if page_data.get("inventory_session_id") is not None:
                    inventory_session_id = page_data["inventory_session_id"]
                inventory_context.update(_inventory_context_from_page(page_data))
                inventory_warnings.extend(_warnings_from_page(page_data))
                writer.append_page(_inventory_items(page_data))
                next_cursor = _next_cursor(page_data)
                complete = _page_complete(page_data, next_cursor)
                if not complete and next_cursor is None:
                    raise DirectorPrepareError(
                        "inventory_cursor_missing",
                        "incomplete inventory page did not include next_cursor",
                    )
                if complete:
                    break
                cursor = next_cursor
                first_page = False
            evidence_summary = writer.finalize()

        actor_root_ids = {
            actor["source_top_level_object_id"]
            for actor in evidence_summary["actors"]
            if actor.get("source_top_level_object_id") is not None
        }
        missing_actor_roots = [
            source_id
            for source_id in source_object_ids
            if source_id not in actor_root_ids
        ]
        if missing_actor_roots:
            raise DirectorPrepareError(
                "native_response_invalid",
                "inventory did not include actor_root records for every selected source object",
                missing_source_object_ids=missing_actor_roots,
            )

        combined_warnings = _dedupe_warnings(
            copy.deepcopy(request.warnings) + inventory_warnings
        )
        evidence_summary = _merge_warning_counts(evidence_summary, combined_warnings)
        evidence_summary["selected_roots"] = list(source_object_ids)
        fingerprint = build_source_document_fingerprint(
            document,
            source_document_key,
            source_object_ids,
            inventory_context,
            evidence_summary,
        )

        final_paths = _final_paths(final_dir, request.write_markdown_audit)
        audit = {
            "schema_version": SCHEMA_VERSION,
            "take_id": request.take_id,
            "prepare_status": PREPARE_STATUS_COMPLETE,
            "validation_status": VALIDATION_STATUS_VALID,
            "source_document_key": source_document_key.value,
            "source_document_key_scope": source_document_key.scope,
            "source_document_fingerprint": fingerprint,
            "evidence_summary": evidence_summary,
            "warnings": copy.deepcopy(combined_warnings),
            "created_at": _utc_now(),
        }
        audit_json_path = temp_dir / "audit_report.json"
        _write_json(audit_json_path, audit)
        audit_json_sha = _sha256_file(audit_json_path)

        audit_markdown_sha = None
        if request.write_markdown_audit:
            audit_markdown_path = temp_dir / "audit_report.md"
            _write_text(audit_markdown_path, _audit_markdown(request.take_id, evidence_summary))
            audit_markdown_sha = _sha256_file(audit_markdown_path)

        manifest = _build_manifest(
            request=request,
            storage=storage,
            source_document_key=source_document_key,
            source_document_fingerprint=fingerprint,
            source_object_ids=source_object_ids,
            inventory_context=inventory_context,
            evidence_summary=evidence_summary,
            paths=final_paths,
            audit_json_sha=audit_json_sha,
            audit_markdown_sha=audit_markdown_sha,
            warnings=combined_warnings,
        )
        _write_json(temp_dir / "take_manifest.json", manifest)

        if final_dir.exists():
            raise DirectorPrepareError(
                "take_already_exists", f"take directory already exists: {final_dir}"
            )
        temp_dir.rename(final_dir)
        return {
            "take_id": request.take_id,
            "prepare_status": PREPARE_STATUS_COMPLETE,
            "storage_mode": storage.storage_mode,
            "source_document_key": source_document_key.value,
            "source_document_key_scope": source_document_key.scope,
            "source_document_fingerprint": fingerprint,
            "actor_count": evidence_summary["actor_count"],
            "provenance_record_count": evidence_summary["provenance_record_count"],
            "validation_status": VALIDATION_STATUS_VALID,
            "paths": final_paths,
            "warnings": copy.deepcopy(combined_warnings),
        }
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _final_paths(final_dir: Path, markdown_enabled: bool) -> dict[str, Any]:
    return {
        "provenance_records": str(final_dir / "provenance_records.jsonl"),
        "audit_report_json": str(final_dir / "audit_report.json"),
        "audit_report_markdown": str(final_dir / "audit_report.md")
        if markdown_enabled
        else None,
        "take_manifest": str(final_dir / "take_manifest.json"),
    }


def _build_manifest(
    *,
    request: PrepareTakeRequest,
    storage: StorageResolution,
    source_document_key: SourceDocumentKey,
    source_document_fingerprint: dict[str, Any],
    source_object_ids: list[str],
    inventory_context: dict[str, Any],
    evidence_summary: dict[str, Any],
    paths: dict[str, Any],
    audit_json_sha: str,
    audit_markdown_sha: str | None,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    files: dict[str, Any] = {
        "provenance_records": {
            "path": paths["provenance_records"],
            "sha256": evidence_summary["provenance_jsonl_sha256"],
            "line_count": evidence_summary["provenance_record_count"],
        },
        "audit_report_json": {
            "path": paths["audit_report_json"],
            "sha256": audit_json_sha,
        },
        "audit_report_markdown": {
            "enabled": request.write_markdown_audit,
            "path": paths["audit_report_markdown"],
            "sha256": None,
        },
    }
    if request.write_markdown_audit:
        files["audit_report_markdown"]["sha256"] = audit_markdown_sha
    inventory_summary = _inventory_summary(evidence_summary, source_object_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "take_id": request.take_id,
        "prepare_status": PREPARE_STATUS_COMPLETE,
        "created_at": _utc_now(),
        "generator_version": GENERATOR_VERSION,
        "storage_mode": storage.storage_mode,
        "source_document_key": source_document_key.value,
        "source_document_key_scope": source_document_key.scope,
        "source_document_fingerprint": source_document_fingerprint,
        "input": _manifest_input(request, source_object_ids),
        "inventory_context": _bounded_stable_copy(inventory_context),
        "inventory_summary": inventory_summary,
        "actors": copy.deepcopy(evidence_summary["actors"]),
        "root_actor_ids": copy.deepcopy(evidence_summary["root_actor_ids"]),
        "files": files,
        "warnings": copy.deepcopy(warnings),
        "validation_status": VALIDATION_STATUS_VALID,
    }


def _manifest_input(
    request: PrepareTakeRequest, source_object_ids: list[str]
) -> dict[str, Any]:
    return {
        "scope": request.scope,
        "source_object_ids": list(source_object_ids),
        "use_current_selection": request.use_current_selection,
        "page_size": request.page_size,
        "classify_nested": request.classify_nested,
        "write_markdown_audit": request.write_markdown_audit,
        "portable": request.portable,
        "output_root": request.output_root,
    }


def _inventory_summary(
    evidence_summary: dict[str, Any], source_object_ids: list[str]
) -> dict[str, Any]:
    provenance_record_count = evidence_summary["provenance_record_count"]
    referenced_count = evidence_summary["referenced_record_count"]
    materialized_count = evidence_summary["materialized_record_count"]
    return {
        "total_records": provenance_record_count,
        "provenance_record_count": provenance_record_count,
        "actor_count": evidence_summary["actor_count"],
        "page_count": evidence_summary["page_count"],
        "selected_root_ids": list(source_object_ids),
        "selected_roots": list(source_object_ids),
        "role_counts": evidence_summary["role_counts"],
        "animation_relevance_counts": evidence_summary["animation_relevance_counts"],
        "warning_counts": evidence_summary["warning_counts"],
        "provenance_jsonl_sha256": evidence_summary["provenance_jsonl_sha256"],
        "materialization_status_counts": evidence_summary[
            "materialization_status_counts"
        ],
        "referenced_record_count": referenced_count,
        "referenced_only_count": referenced_count,
        "materialized_record_count": materialized_count,
        "materialized_count": materialized_count,
    }
