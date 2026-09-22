"""Backend-only Vertex provider operations."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import httpx

from .vertex_auth import (
    VERTEX_SCHEMA_VERSION,
    VertexAuthError,
    VertexMode,
    VertexRecord,
    VertexRuntimeArguments,
    VertexStore,
    _UNSUPPORTED_MODEL_MESSAGE,
    _WindowsNamedMutex,
    vertex_gemini_model_name,
)
from .vertex_oauth import (
    DesktopOAuthClient,
    _OAuthDependencies,
    authorize_desktop,
)
from .vertex_token_lease import (
    TOKEN_ISSUANCE_TIMEOUT_SECONDS,
    refresh_access_token,
)


_READINESS_TIMEOUT_SECONDS = 30
_READINESS_TEXT = "Rook Vertex readiness probe"
_EMPTY_GENERATION = "0" * 32
_MESSAGES = {
    "vertex_project_inaccessible": "The configured Google Cloud project is inaccessible.",
    "vertex_api_disabled": "The Vertex AI API is not enabled for the project.",
    "vertex_billing_unavailable": "Billing is unavailable for the Vertex AI request.",
    "vertex_permission_missing": "The identity lacks Vertex AI inference permission.",
    "vertex_region_invalid": "The configured Vertex AI region is invalid.",
    "vertex_model_unavailable": (
        "The selected Gemini model is unavailable in this project and region."
    ),
    "vertex_request_failed": "The Vertex AI request failed without a safely classifiable cause.",
}


@dataclass(frozen=True)
class VertexOperationResult:
    success: bool
    code: str | None
    message: str
    generation: str | None
    revocation: str | None = None
    local_deletion: str | None = None


def _result_from_error(error: VertexAuthError) -> VertexOperationResult:
    return VertexOperationResult(
        success=False,
        code=error.code,
        message=error.public_message,
        generation=None,
    )


def _generic_failure() -> VertexOperationResult:
    return VertexOperationResult(
        success=False,
        code="vertex_request_failed",
        message=_MESSAGES["vertex_request_failed"],
        generation=None,
    )


def _success(generation: str, message: str) -> VertexOperationResult:
    return VertexOperationResult(
        success=True,
        code=None,
        message=message,
        generation=generation,
    )


def _restart_required(
    generation: str | None,
    *,
    revocation: str | None = None,
    local_deletion: str | None = None,
) -> VertexOperationResult:
    return VertexOperationResult(
        success=False,
        code="vertex_restart_required",
        message="Vertex authorization changed, but a managed process could not be retired.",
        generation=generation,
        revocation=revocation,
        local_deletion=local_deletion,
    )


def _validate_project_region(project_id: object, region: object) -> None:
    try:
        VertexRecord(
            schema_version=VERTEX_SCHEMA_VERSION,
            generation=_EMPTY_GENERATION,
            mode=VertexMode.ADC,
            project_id=project_id,
            region="us-central1",
            oauth_ciphertext=None,
            service_account_path=None,
        )
    except VertexAuthError as exc:
        raise VertexAuthError(
            "vertex_project_required",
            "A valid Google Cloud project ID is required for Vertex AI.",
        ) from exc
    try:
        VertexRecord(
            schema_version=VERTEX_SCHEMA_VERSION,
            generation=_EMPTY_GENERATION,
            mode=VertexMode.ADC,
            project_id=project_id,
            region=region,
            oauth_ciphertext=None,
            service_account_path=None,
        )
    except VertexAuthError as exc:
        raise VertexAuthError(
            "vertex_region_required",
            "A valid Google Cloud region is required for Vertex AI.",
        ) from exc


def _mutation_lock(store: VertexStore) -> _WindowsNamedMutex:
    return _WindowsNamedMutex(store._mutex_name, store._mutex_timeout_ms)


def _replace_and_recycle(
    store: VertexStore,
    record: VertexRecord,
    recycler: Callable[[str | None], None],
    *,
    message: str,
) -> VertexOperationResult:
    committed = store.replace(record)
    try:
        recycler(committed.generation)
    except Exception:
        return _restart_required(committed.generation)
    return _success(committed.generation, message)


def _managed_chirp_recycler(generation: str | None) -> None:
    from ..chirp_manager import recycle_after_vertex_commit

    recycle_after_vertex_commit(generation)


def _select_recycler(
    recycler: Callable[[str | None], None] | None,
) -> Callable[[str | None], None]:
    if recycler is None:
        return _managed_chirp_recycler
    if not callable(recycler):
        raise VertexAuthError(
            "vertex_request_failed",
            _MESSAGES["vertex_request_failed"],
        )
    return recycler


def _default_token_loader(runtime: VertexRuntimeArguments) -> str:
    deadline = time.monotonic() + TOKEN_ISSUANCE_TIMEOUT_SECONDS
    return refresh_access_token(runtime, deadline, time.monotonic).access_token


def _post_json(
    url: str,
    body: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, object]:
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, json=body, headers=headers)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


def _error_info(details: list[object]) -> list[dict[str, object]]:
    return [
        item
        for item in details
        if isinstance(item, dict)
        and item.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo"
    ]


def _classify_readiness(payload: object) -> str | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None
    error = payload["error"]
    status = error.get("status")
    details = error.get("details")
    if not isinstance(status, str) or not isinstance(details, list):
        return None

    for info in _error_info(details):
        reason = info.get("reason")
        domain = info.get("domain")
        metadata = info.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if (
            status == "PERMISSION_DENIED"
            and domain == "googleapis.com"
            and reason in {"CONSUMER_INVALID", "RESOURCE_PROJECT_INVALID"}
            and isinstance(metadata.get("consumer"), str)
        ):
            return "vertex_project_inaccessible"
        if (
            status == "PERMISSION_DENIED"
            and domain == "googleapis.com"
            and reason == "SERVICE_DISABLED"
            and metadata.get("service") == "aiplatform.googleapis.com"
        ):
            return "vertex_api_disabled"
        if (
            status == "PERMISSION_DENIED"
            and domain == "googleapis.com"
            and reason == "BILLING_DISABLED"
            and metadata.get("service") == "aiplatform.googleapis.com"
        ):
            return "vertex_billing_unavailable"
        if (
            status == "PERMISSION_DENIED"
            and domain == "aiplatform.googleapis.com"
            and reason == "IAM_PERMISSION_DENIED"
            and metadata.get("permission") == "aiplatform.endpoints.predict"
        ):
            return "vertex_permission_missing"

    if status == "INVALID_ARGUMENT":
        for detail in details:
            if (
                isinstance(detail, dict)
                and detail.get("@type")
                == "type.googleapis.com/google.rpc.BadRequest"
                and isinstance(detail.get("fieldViolations"), list)
                and any(
                    isinstance(violation, dict)
                    and violation.get("field") == "location"
                    for violation in detail["fieldViolations"]
                )
            ):
                return "vertex_region_invalid"

    if status == "NOT_FOUND":
        for detail in details:
            if (
                isinstance(detail, dict)
                and detail.get("@type")
                == "type.googleapis.com/google.rpc.ResourceInfo"
                and detail.get("resourceType")
                == "aiplatform.googleapis.com/PublisherModel"
                and isinstance(detail.get("resourceName"), str)
            ):
                return "vertex_model_unavailable"
    return None


def probe_vertex_readiness(
    model: object,
    *,
    store: VertexStore | None = None,
    token_loader: Callable[[VertexRuntimeArguments], str] | None = None,
    post_json: Callable[
        [str, dict[str, object], dict[str, str], float], tuple[int, object]
    ]
    | None = None,
) -> VertexOperationResult:
    """Perform the explicit, non-generating Vertex readiness request."""

    try:
        publisher_model = vertex_gemini_model_name(model)
        if publisher_model is None:
            raise VertexAuthError(
                "vertex_model_family_unsupported",
                _UNSUPPORTED_MODEL_MESSAGE,
            )
        runtime = (store or VertexStore.production()).resolve_runtime()
        token = (token_loader or _default_token_loader)(runtime)
        if not isinstance(token, str) or not token:
            raise VertexAuthError(
                "vertex_request_failed",
                _MESSAGES["vertex_request_failed"],
            )
        host = (
            "aiplatform.googleapis.com"
            if runtime.region == "global"
            else f"{runtime.region}-aiplatform.googleapis.com"
        )
        url = (
            f"https://{host}/v1/"
            f"projects/{runtime.project_id}/locations/{runtime.region}/"
            f"publishers/google/models/{publisher_model}:countTokens"
        )
        body: dict[str, object] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _READINESS_TEXT}],
                }
            ]
        }
        status_code, payload = (post_json or _post_json)(
            url,
            body,
            {"Authorization": f"Bearer {token}"},
            _READINESS_TIMEOUT_SECONDS,
        )
        if (
            status_code == 200
            and isinstance(payload, dict)
            and type(payload.get("totalTokens")) is int
            and payload["totalTokens"] >= 0
        ):
            return VertexOperationResult(
                success=True,
                code=None,
                message="Vertex AI readiness passed.",
                generation=runtime.generation,
            )
        code = _classify_readiness(payload)
        if code is None:
            return _generic_failure()
        return VertexOperationResult(
            success=False,
            code=code,
            message=_MESSAGES[code],
            generation=runtime.generation,
        )
    except VertexAuthError as exc:
        return _result_from_error(exc)
    except Exception:
        return _generic_failure()


def connect_vertex_oauth(
    client: DesktopOAuthClient,
    project_id: object,
    region: object,
    *,
    recycler: Callable[[str | None], None] | None = None,
    store: VertexStore | None = None,
    authorize: Callable[[DesktopOAuthClient], dict[str, str]] | None = None,
    oauth_dependencies: _OAuthDependencies | None = None,
) -> VertexOperationResult:
    """Authorize and atomically commit one Rook-owned desktop OAuth record."""

    selected_store = store or VertexStore.production()
    try:
        selected_recycler = _select_recycler(recycler)
        _validate_project_region(project_id, region)
        with _mutation_lock(selected_store):
            selected_store.read()
            credentials = (
                authorize(client)
                if authorize is not None
                else authorize_desktop(client, dependencies=oauth_dependencies)
            )
            ciphertext = selected_store.protect_authorized_user(credentials)
            requested = VertexRecord(
                schema_version=VERTEX_SCHEMA_VERSION,
                generation=_EMPTY_GENERATION,
                mode=VertexMode.OAUTH,
                project_id=project_id,
                region=region,
                oauth_ciphertext=ciphertext,
                service_account_path=None,
            )
            return _replace_and_recycle(
                selected_store,
                requested,
                selected_recycler,
                message="Google authorization was saved for Vertex AI.",
            )
    except VertexAuthError as exc:
        return _result_from_error(exc)
    except Exception:
        return _generic_failure()


def save_vertex_configuration(
    mode: VertexMode | str,
    project_id: object,
    region: object,
    *,
    recycler: Callable[[str | None], None] | None = None,
    service_account_path: str | None = None,
    store: VertexStore | None = None,
) -> VertexOperationResult:
    """Select one explicit Vertex mode without falling through to another."""

    selected_store = store or VertexStore.production()
    try:
        selected_recycler = _select_recycler(recycler)
        _validate_project_region(project_id, region)
        try:
            selected_mode = mode if isinstance(mode, VertexMode) else VertexMode(mode)
        except (TypeError, ValueError) as exc:
            raise VertexAuthError(
                "vertex_request_failed",
                "The selected Vertex authorization mode is invalid.",
            ) from exc
        with _mutation_lock(selected_store):
            prior = selected_store.read()
            ciphertext = None
            path = None
            if selected_mode is VertexMode.OAUTH:
                if prior is None or prior.mode is not VertexMode.OAUTH:
                    raise VertexAuthError(
                        "vertex_signed_out",
                        "Sign in with Google before selecting Rook desktop OAuth.",
                    )
                ciphertext = prior.oauth_ciphertext
            elif selected_mode is VertexMode.SERVICE_ACCOUNT:
                path = service_account_path
            try:
                requested = VertexRecord(
                    schema_version=VERTEX_SCHEMA_VERSION,
                    generation=_EMPTY_GENERATION,
                    mode=selected_mode,
                    project_id=project_id,
                    region=region,
                    oauth_ciphertext=ciphertext,
                    service_account_path=path,
                )
            except VertexAuthError as exc:
                if selected_mode is VertexMode.SERVICE_ACCOUNT:
                    raise VertexAuthError(
                        "vertex_service_account_unavailable",
                        "The selected service-account file is unavailable.",
                    ) from exc
                raise
            return _replace_and_recycle(
                selected_store,
                requested,
                selected_recycler,
                message="Vertex AI configuration was saved.",
            )
    except VertexAuthError as exc:
        return _result_from_error(exc)
    except Exception:
        return _generic_failure()


def _revoke_token(refresh_token: str) -> bool:
    with httpx.Client(timeout=10) as client:
        response = client.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": refresh_token},
        )
    return response.status_code == 200


def disconnect_vertex(
    *,
    recycler: Callable[[str | None], None] | None = None,
    store: VertexStore | None = None,
    revoke: Callable[[str], bool] | None = None,
) -> VertexOperationResult:
    """Best-effort revoke OAuth and exact-delete only the Vertex record."""

    selected_store = store or VertexStore.production()
    try:
        selected_recycler = _select_recycler(recycler)
        with _mutation_lock(selected_store):
            record = selected_store.read()
            if record is None:
                return VertexOperationResult(
                    success=True,
                    code=None,
                    message="Vertex AI was already disconnected.",
                    generation=None,
                    revocation="not_applicable",
                    local_deletion="absent",
                )
            revocation = "not_applicable"
            if record.mode is VertexMode.OAUTH:
                revocation = "failed"
                try:
                    runtime = selected_store.resolve_runtime()
                    credentials = runtime.vertex_credentials
                    if isinstance(credentials, dict):
                        refresh_token = credentials.get("refresh_token")
                        if isinstance(refresh_token, str) and refresh_token:
                            revocation = (
                                "revoked"
                                if (revoke or _revoke_token)(refresh_token)
                                else "failed"
                            )
                except Exception:
                    revocation = "failed"
            try:
                selected_store.path.unlink()
            except FileNotFoundError:
                local_deletion = "absent"
            except OSError:
                return VertexOperationResult(
                    success=False,
                    code="vertex_request_failed",
                    message="The local Vertex authorization could not be removed.",
                    generation=record.generation,
                    revocation=revocation,
                    local_deletion="failed",
                )
            else:
                local_deletion = "deleted"
            try:
                selected_recycler(None)
            except Exception:
                return _restart_required(
                    None,
                    revocation=revocation,
                    local_deletion=local_deletion,
                )
            return VertexOperationResult(
                success=True,
                code=None,
                message="Vertex AI was disconnected locally.",
                generation=None,
                revocation=revocation,
                local_deletion=local_deletion,
            )
    except VertexAuthError as exc:
        return _result_from_error(exc)
    except Exception:
        return _generic_failure()
