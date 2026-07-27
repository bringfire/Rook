#!/usr/bin/env python3
"""Bounded governed-resolution checkpoint orchestration."""

from __future__ import annotations

import copy
import base64
import json
import sys
import threading
import time
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_c_compiler_sufficiency_probe as PROVIDER_ADAPTER
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_probe as PLANNER_PROBE
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9b_p_readiness_contract as READINESS


@dataclass(frozen=True)
class ResolutionAttemptResult:
    classification: str | None
    planner_session: PLANNER_SUPPORT.PlannerSessionResult | None
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None
    isolation_result: SUPPORT.IsolationGateResult | None
    sealed_checkpoint: ARTIFACTS.SealedResolutionCheckpoint | None
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult | None
    candidate_recipe_bytes: bytes | None
    call_ledger: tuple[Mapping[str, object], ...]
    derived_stop_cause: str
    state: str
    finalization_indeterminate: ARTIFACTS.FinalizationIndeterminate | None = None


class _AdapterIdentityMismatch(RuntimeError):
    pass


class _AdapterEvidenceMismatch(RuntimeError):
    pass


def _construct_resolution_role_provider(
    *, role: str, model: str, temperature: float
) -> object:
    if role not in {"planner", "planner_evaluator"}:
        raise ValueError("resolution cannot construct an unregistered role adapter")
    return PLANNER_PROBE.build_planner_evaluator_provider(
        model=model,
        temperature=temperature,
    )


def _resolution_role_adapter_api() -> tuple[Callable[..., object], Callable[..., object]]:
    registry: weakref.WeakKeyDictionary[object, object] = weakref.WeakKeyDictionary()
    registry_lock = threading.Lock()

    class IssuedResolutionRoleAdapters:
        __slots__ = ("__weakref__",)

    def derive(
        *,
        preflight: ARTIFACTS.VerifiedResolutionPreflight,
        readiness_manifest: READINESS.RouteManifest,
    ) -> object:
        if type(preflight) is not ARTIFACTS.VerifiedResolutionPreflight:
            raise TypeError("verified resolution preflight is required")
        expected_projection = preflight.record["instrument_contracts"]["readiness"][
            "route_identity_projection"
        ]
        actual_projection = ARTIFACTS.readiness_route_identity_projection(
            readiness_manifest
        )
        if actual_projection != expected_projection:
            raise ValueError("role-adapter route differs from resolution preflight")
        providers: dict[str, object] = {}
        expected_response_identities: dict[str, Mapping[str, object]] = {}
        provider_snapshots: dict[str, Mapping[str, object]] = {}
        for role, contract_key in (
            ("planner", "planner"),
            ("planner_evaluator", "evaluator"),
        ):
            matching_routes = [
                route for route in readiness_manifest.routes if role in route.member_roles
            ]
            if len(matching_routes) != 1:
                raise ValueError("resolution role has no unique readiness route")
            route = matching_routes[0]
            contract = preflight.record["instrument_contracts"][contract_key]
            if (
                route.model != contract["model"]
                or route.adapter_path != "litellm.completion"
                or contract["provider_profile"]
                != "litellm.completion.tool_calling.no_parallel:v1"
                or contract["temperature"] != 0.0
            ):
                raise ValueError("resolution role configuration differs from route")
            provider = _construct_resolution_role_provider(
                role=role,
                model=route.model,
                temperature=contract["temperature"],
            )
            identity = getattr(provider, "identity", None)
            expected_adapter_identity = {
                "adapter_path": route.adapter_path,
                "model": route.model,
                "profile_identity": contract["provider_profile"],
                "temperature": contract["temperature"],
            }
            if (
                not isinstance(identity, Mapping)
                or dict(identity) != expected_adapter_identity
                or getattr(provider, "model", None) != route.model
                or getattr(provider, "temperature", None) != contract["temperature"]
                or getattr(provider, "profile_identity", None)
                != contract["provider_profile"]
            ):
                raise ValueError("constructed resolution role adapter identity mismatch")
            providers[role] = provider
            expected_response_identities[role] = MappingProxyType(
                {
                    "requested_model": route.model,
                    "requested_profile": contract["provider_profile"],
                }
            )
            provider_snapshots[role] = MappingProxyType(
                {
                    "provider": provider,
                    "adapter_identity": MappingProxyType(expected_adapter_identity),
                    "route_fingerprint": route.route_fingerprint,
                }
            )
        issued = IssuedResolutionRoleAdapters()
        with registry_lock:
            registry[issued] = (
                MappingProxyType(providers),
                MappingProxyType(expected_response_identities),
                MappingProxyType(provider_snapshots),
            )
        return issued

    def consume(issued: object, *, role: str) -> tuple[object, Mapping[str, object]]:
        if type(issued) is not IssuedResolutionRoleAdapters:
            raise TypeError("closure-issued resolution role adapters are required")
        with registry_lock:
            snapshot = registry.get(issued)
        if snapshot is None:
            raise ValueError("resolution role-adapter issuance is unknown")
        providers, expected_response_identities, provider_snapshots = snapshot
        if role not in providers:
            raise ValueError("resolution role adapter is not registered")
        provider = providers[role]
        provider_snapshot = provider_snapshots[role]
        if (
            provider_snapshot["provider"] is not provider
            or dict(getattr(provider, "identity", {}))
            != dict(provider_snapshot["adapter_identity"])
        ):
            raise ValueError("resolution role adapter changed after issuance")
        return provider, expected_response_identities[role]

    return derive, consume


(
    _derive_resolution_role_adapters,
    _consume_resolution_role_adapter,
) = _resolution_role_adapter_api()


class _StagedCallLedger:
    """Persist immutable adapter-boundary requests before each dispatch."""

    def __init__(
        self,
        *,
        preflight: ARTIFACTS.VerifiedResolutionPreflight,
        invocation_binding: Mapping[str, object],
        readiness_record: Mapping[str, object],
        readiness_verified_at: str,
    ) -> None:
        self._preflight = preflight
        self._runtime = preflight.attempt.staging_path / ".resolution-runtime"
        self._calls = self._runtime / "calls"
        self._runtime.mkdir(parents=False, exist_ok=False)
        self._calls.mkdir(parents=False, exist_ok=False)
        self._rows: list[Mapping[str, object]] = []
        self._active_calls: set[int] = set()
        self._pending_terminal_rows: dict[int, Mapping[str, object]] = {}
        self._adapter_identity_failures: set[int] = set()
        self._adapter_evidence_failures: dict[int, str] = {}
        self._response_capture_failures: dict[int, str] = {}
        self._planner_call_plans: list[
            PLANNER_SUPPORT.PlannerProviderCallPlan
        ] = []
        self._dispatch_lock = threading.Lock()
        self._role_open = {"planner": True, "planner_evaluator": True}
        attempt = {
            "schema": "rook.lm9b_p.governed_resolution_staged_attempt:v1",
            "attempt_id": preflight.attempt.attempt_id,
            "attempt_fingerprint": preflight.attempt.attempt_fingerprint,
            "canonical_destination": str(preflight.attempt.destination),
            "staging_path": str(preflight.attempt.staging_path),
        }
        readiness = {
            "schema": "rook.lm9b_p.governed_resolution_staged_readiness:v1",
            "record": PLANNER_SUPPORT._json_builtins(readiness_record),
            "verified_at": readiness_verified_at,
        }
        self._persist_and_reread(
            self._runtime / "preflight.json",
            (preflight.archive_dir / "record.json").read_bytes(),
        )
        self._persist_and_reread(
            self._runtime / "attempt.json", _canonical_bytes(attempt)
        )
        self._persist_and_reread(
            self._runtime / "invocation.json",
            _canonical_bytes(invocation_binding),
        )
        self._persist_and_reread(
            self._runtime / "readiness.json", _canonical_bytes(readiness)
        )
        self._persist_and_reread(
            self._runtime / "initial-request.json",
            preflight.instrument.initial_request.raw_bytes,
        )

    @property
    def has_unjoined_dispatch(self) -> bool:
        with self._dispatch_lock:
            return bool(self._active_calls)

    @property
    def has_adapter_identity_failure(self) -> bool:
        with self._dispatch_lock:
            return bool(self._adapter_identity_failures)

    def adapter_evidence_failure_for_role(self, role: str) -> str | None:
        with self._dispatch_lock:
            failures = [
                failure
                for index, failure in self._adapter_evidence_failures.items()
                if self._rows[index]["role"] == role
            ]
            if len(failures) > 1:
                raise ValueError("multiple adapter evidence failures were recorded")
            return None if not failures else failures[0]

    def response_capture_failure_for_role(self, role: str) -> str | None:
        with self._dispatch_lock:
            failures = [
                failure
                for index, failure in self._response_capture_failures.items()
                if self._rows[index]["role"] == role
            ]
            if len(failures) > 1:
                raise ValueError("multiple response capture failures were recorded")
            return None if not failures else failures[0]

    def role_dispatch_complete(self, role: str) -> bool:
        with self._dispatch_lock:
            rows = [row for row in self._rows if row["role"] == role]
            return bool(rows) and not any(
                index in self._active_calls
                for index, row in enumerate(self._rows)
                if row["role"] == role
            )

    def record_planner_call_plan(
        self, plan: PLANNER_SUPPORT.PlannerProviderCallPlan
    ) -> None:
        if type(plan) is not PLANNER_SUPPORT.PlannerProviderCallPlan:
            raise TypeError("controller-issued Planner call plan is required")
        with self._dispatch_lock:
            expected_turn = len(self._planner_call_plans) + 1
            if plan.turn_index != expected_turn:
                raise ValueError("Planner call plans are not contiguous")
            self._planner_call_plans.append(plan)

    def complete_quiescent_call(self, role: str, quiescent: bool) -> None:
        if type(quiescent) is not bool:
            raise TypeError("provider call quiescence must be Boolean")
        with self._dispatch_lock:
            active = [
                index
                for index in sorted(self._active_calls)
                if self._rows[index]["role"] == role
            ]
            if len(active) != 1:
                raise ValueError("provider call completion has no unique dispatch")
            if not quiescent:
                return
            call_index = active[0]
            terminal = self._pending_terminal_rows.pop(call_index, None)
            if terminal is None:
                if call_index in self._response_capture_failures:
                    self._active_calls.remove(call_index)
                    return
                raise ValueError("provider call completed before evidence capture")
            self._rows[call_index] = terminal
            self._active_calls.remove(call_index)

    def close_role(self, role: str) -> None:
        with self._dispatch_lock:
            self._role_open[role] = False

    def wrap(
        self,
        provider: Callable[[dict[str, object]], object],
        *,
        role: str,
        materialize: Callable[[bytes], dict[str, object]],
        expected_response_identity: Mapping[str, object],
    ) -> Callable[[dict[str, object]], object]:
        if role not in {"planner", "planner_evaluator"}:
            raise ValueError("unregistered resolution provider role")

        def invoke(request: dict[str, object]) -> object:
            request_bytes = _canonical_bytes(copy.deepcopy(request))
            # The role-specific materializer replays the code-owned builder and
            # rejects drift before the irreversible dispatch marker.
            materialize(request_bytes)
            role_contract = self._preflight.record["instrument_contracts"][
                "planner" if role == "planner" else "evaluator"
            ]
            with self._dispatch_lock:
                if not self._role_open[role]:
                    raise RuntimeError("resolution role dispatch is closed")
                call_index = len(self._rows)
                prefix = f"{call_index:02d}-{role}"
                request_path = self._calls / f"{prefix}-request.json"
                self._persist_and_reread(request_path, request_bytes)
                request_value = materialize(request_path.read_bytes())
                deadline_state = None
                if role == "planner":
                    if len(self._planner_call_plans) != call_index + 1:
                        raise ValueError(
                            "Planner dispatch lacks its controller call plan"
                        )
                    plan = self._planner_call_plans[call_index]
                    if (
                        plan.request_bytes != request_bytes
                        or plan.request_raw_sha256
                        != PLANNER_SUPPORT.sha256_prefixed(request_bytes)
                    ):
                        raise ValueError(
                            "Planner request differs from controller call plan"
                        )
                    deadline_state = {
                        "turn_index": plan.turn_index,
                        "session_started_monotonic_s": (
                            plan.session_started_monotonic_s
                        ),
                        "call_started_monotonic_s": plan.call_started_monotonic_s,
                        "elapsed_before_call_s": plan.elapsed_before_call_s,
                        "remaining_before_call_s": plan.remaining_before_call_s,
                    }
                marker = {
                    "schema": "rook.lm9b_p.governed_resolution_dispatch_started:v1",
                    "call_index": call_index,
                    "role": role,
                    "request_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(request_bytes),
                    "preceding_transcript_fingerprint": PLANNER_SUPPORT.fingerprint(
                        request_value["messages"]
                    ),
                    "provider_timeout_s": request_value["provider_timeout_s"],
                    "controller_deadline_state": deadline_state,
                    "role_contract_fingerprint": PLANNER_SUPPORT.fingerprint(
                        role_contract
                    ),
                }
                marker_raw = _canonical_bytes(marker)
                self._persist_and_reread(
                    self._calls / f"{prefix}-dispatch_started.json", marker_raw
                )
                row: dict[str, object] = {
                    **marker,
                    "dispatch_marker_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
                        marker_raw
                    ),
                    "canonical_request_json": request_bytes.decode("utf-8"),
                    "provider_claimed_raw_request_b64": None,
                    "provider_claimed_raw_request_sha256": None,
                    "provider_raw_error_b64": None,
                    "provider_raw_error_sha256": None,
                    "raw_response_b64": None,
                    "raw_response_sha256": None,
                    "assistant_message": None,
                    "usage": None,
                    "provider_metadata": None,
                    "outcome": "dispatch_started",
                    "exception_type": None,
                    "failure_type": None,
                    "elapsed_ms": None,
                    "terminal": False,
                }
                self._rows.append(MappingProxyType(copy.deepcopy(row)))
                self._active_calls.add(call_index)
            started = time.monotonic()
            try:
                response = provider(request_value)
            except BaseException as exc:
                terminal = {
                    **row,
                    "outcome": "raised",
                    "exception_type": type(exc).__name__,
                    "failure_type": getattr(exc, "failure_type", None),
                    "elapsed_ms": max(
                        0, int((time.monotonic() - started) * 1000)
                    ),
                    "terminal": True,
                }
                evidence_failure = "adapter_evidence_incomplete"
                if isinstance(exc, PLANNER_SUPPORT.ProviderCallFailure):
                    raw_request = exc.raw_request
                    raw_error = exc.raw_error
                    if type(raw_request) is bytes and type(raw_error) is bytes:
                        terminal.update(
                            {
                                "provider_claimed_raw_request_b64": (
                                    base64.b64encode(raw_request).decode("ascii")
                                ),
                                "provider_claimed_raw_request_sha256": (
                                    PLANNER_SUPPORT.sha256_prefixed(raw_request)
                                ),
                                "provider_raw_error_b64": (
                                    base64.b64encode(raw_error).decode("ascii")
                                ),
                                "provider_raw_error_sha256": (
                                    PLANNER_SUPPORT.sha256_prefixed(raw_error)
                                ),
                            }
                        )
                        try:
                            self._persist_and_reread(
                                self._calls / f"{prefix}-adapter-request.json",
                                raw_request,
                            )
                            self._persist_and_reread(
                                self._calls / f"{prefix}-adapter-error.bin",
                                raw_error,
                            )
                        except (OSError, ValueError):
                            evidence_failure = "adapter_failure_capture_failure"
                        expected_request = (
                            PROVIDER_ADAPTER.build_litellm_completion_request_bytes(
                                model=role_contract["model"],
                                temperature=role_contract["temperature"],
                                provider_request=request_value,
                            )
                        )
                        if evidence_failure != "adapter_failure_capture_failure":
                            evidence_failure = (
                                "adapter_request_mismatch"
                                if raw_request != expected_request
                                else ""
                            )
                with self._dispatch_lock:
                    if evidence_failure:
                        self._adapter_evidence_failures[call_index] = evidence_failure
                    self._pending_terminal_rows[call_index] = MappingProxyType(
                        copy.deepcopy(terminal)
                    )
                raise
            terminal = {
                **row,
                "outcome": "returned",
                "elapsed_ms": max(
                    0, int((time.monotonic() - started) * 1000)
                ),
                "terminal": True,
            }
            if type(response) is PLANNER_SUPPORT.ProviderTurn:
                try:
                    self._persist_and_reread(
                        self._calls / f"{prefix}-adapter-request.json",
                        response.raw_request,
                    )
                    self._persist_and_reread(
                        self._calls / f"{prefix}-adapter-response.bin",
                        response.raw_response,
                    )
                    captured = {
                        "provider_claimed_raw_request_b64": base64.b64encode(
                            response.raw_request
                        ).decode("ascii"),
                        "provider_claimed_raw_request_sha256": (
                            PLANNER_SUPPORT.sha256_prefixed(response.raw_request)
                        ),
                        "raw_response_b64": base64.b64encode(
                            response.raw_response
                        ).decode("ascii"),
                        "raw_response_sha256": PLANNER_SUPPORT.sha256_prefixed(
                            response.raw_response
                        ),
                        "assistant_message": PLANNER_SUPPORT._json_builtins(
                            response.assistant_message
                        ),
                        "usage": PLANNER_SUPPORT._json_builtins(response.usage),
                        "provider_metadata": PLANNER_SUPPORT._json_builtins(
                            response.provider_metadata
                        ),
                    }
                except BaseException:
                    failure_locus = (
                        "planner_response_capture_failure"
                        if role == "planner"
                        else "evaluator_response_capture_failure"
                    )
                    with self._dispatch_lock:
                        self._response_capture_failures[call_index] = failure_locus
                    raise
                terminal.update(captured)
                try:
                    projected_message = (
                        PROVIDER_ADAPTER.project_litellm_assistant_message(
                            response.raw_response
                        )
                    )
                except (TypeError, ValueError):
                    projected_message = None
                if projected_message != response.assistant_message:
                    terminal.update(
                        {
                            "outcome": "raised",
                            "exception_type": "_AdapterEvidenceMismatch",
                            "failure_type": "AdapterEvidenceMismatch",
                        }
                    )
                    with self._dispatch_lock:
                        self._adapter_evidence_failures[call_index] = (
                            "adapter_response_projection_mismatch"
                        )
                        self._pending_terminal_rows[call_index] = MappingProxyType(
                            copy.deepcopy(terminal)
                        )
                    raise _AdapterEvidenceMismatch(
                        "adapter assistant differs from raw response projection"
                    )
                metadata = response.provider_metadata
                if (
                    not isinstance(metadata, Mapping)
                    or metadata.get("requested_model")
                    != expected_response_identity["requested_model"]
                    or metadata.get("requested_profile")
                    != expected_response_identity["requested_profile"]
                ):
                    terminal.update(
                        {
                            "outcome": "raised",
                            "exception_type": "_AdapterIdentityMismatch",
                            "failure_type": "AdapterIdentityMismatch",
                        }
                    )
                    with self._dispatch_lock:
                        self._adapter_identity_failures.add(call_index)
                        self._pending_terminal_rows[call_index] = MappingProxyType(
                            copy.deepcopy(terminal)
                        )
                    raise _AdapterIdentityMismatch(
                        "adapter-authored requested identity differs from authorized role"
                    )
            with self._dispatch_lock:
                self._pending_terminal_rows[call_index] = MappingProxyType(
                    copy.deepcopy(terminal)
                )
            return response

        return invoke

    def frozen_rows(self) -> tuple[Mapping[str, object], ...]:
        with self._dispatch_lock:
            return tuple(
                PLANNER_SUPPORT._json_builtins(row) for row in self._rows
            )

    @staticmethod
    def _persist_and_reread(path: Path, raw: bytes) -> None:
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise ValueError("staged resolution evidence write verification failed")


def run_resolution_attempt(**_kwargs: object) -> ResolutionAttemptResult:
    required = {
        "preflight",
        "invocation_binding",
        "readiness_record",
        "readiness_manifest",
        "head_sha",
        "now_iso",
        "credential_present",
    }
    if set(_kwargs) != required:
        raise ValueError("resolution attempt arguments are incomplete or contain extras")
    supplied = _kwargs["preflight"]
    if type(supplied) is not ARTIFACTS.VerifiedResolutionPreflight:
        raise TypeError("verified resolution preflight is required")
    preflight = ARTIFACTS.verify_resolution_preflight(
        supplied.archive_dir,
        expected_fingerprint=supplied.preflight_fingerprint,
    )
    head_sha = _kwargs["head_sha"]
    if head_sha != preflight.record["reviewed_commit_sha"]:
        raise ValueError("execution commit differs from resolution preflight")
    readiness_record = _kwargs["readiness_record"]
    readiness_manifest = _kwargs["readiness_manifest"]
    if type(readiness_record) is not dict:
        raise TypeError("readiness record must be an object")
    expected_manifest_fingerprint = preflight.record["instrument_contracts"][
        "readiness"
    ]["route_manifest_fingerprint"]
    expected_route_identity = preflight.record["instrument_contracts"]["readiness"][
        "route_identity_projection"
    ]
    if (
        type(readiness_manifest) is not READINESS.RouteManifest
        or readiness_manifest.manifest_fingerprint
        != expected_manifest_fingerprint
        or ARTIFACTS.readiness_route_identity_projection(readiness_manifest)
        != expected_route_identity
    ):
        raise ValueError(
            "resolution readiness route or role membership differs from preflight"
        )
    decision = READINESS.verify_launch_readiness(
        record=readiness_record,
        manifest=readiness_manifest,
        head_sha=head_sha,
        now_iso=_kwargs["now_iso"],
        credential_present=_kwargs["credential_present"],
    )
    if not decision.ok:
        raise ValueError("resolution readiness refused: " + "; ".join(decision.failures))
    expected_invocation = ARTIFACTS.build_resolution_invocation_binding(
        supplied_preflight_fingerprint=preflight.preflight_fingerprint,
        transmit=True,
        reviewed_commit_sha=head_sha,
        readiness_identity=readiness_record.get("record_fingerprint"),
        attempt_id=preflight.attempt.attempt_id,
        attempt_fingerprint=preflight.attempt.attempt_fingerprint,
    )
    ARTIFACTS.verify_resolution_invocation_binding(
        _kwargs["invocation_binding"], expected=expected_invocation
    )
    ARTIFACTS.require_clean_reviewed_checkout(
        ARTIFACTS._REPO_ROOT, preflight.record["reviewed_commit_sha"]
    )
    if preflight.attempt.destination.exists() or preflight.attempt.staging_path.exists():
        raise FileExistsError("resolution destination or staging already exists")
    role_adapters = _derive_resolution_role_adapters(
        preflight=preflight,
        readiness_manifest=readiness_manifest,
    )
    planner_adapter, planner_response_identity = _consume_resolution_role_adapter(
        role_adapters, role="planner"
    )
    evaluator_adapter, evaluator_response_identity = (
        _consume_resolution_role_adapter(
            role_adapters, role="planner_evaluator"
        )
    )
    ARTIFACTS.reserve_resolution_staging(preflight)
    ledger = _StagedCallLedger(
        preflight=preflight,
        invocation_binding=expected_invocation,
        readiness_record=readiness_record,
        readiness_verified_at=_kwargs["now_iso"],
    )
    planner_provider = ledger.wrap(
        planner_adapter,
        role="planner",
        materialize=PLANNER_SUPPORT.materialize_planner_provider_call_request,
        expected_response_identity=planner_response_identity,
    )
    inputs = preflight.instrument.inputs
    planner_session = PLANNER_SUPPORT.run_planner_session(
        provider=planner_provider,
        system_prompt=SUPPORT.REVISION_SYSTEM_PROMPT,
        user_prompt=preflight.instrument.initial_request.raw_bytes.decode("utf-8"),
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
        call_plan_observer=ledger.record_planner_call_plan,
        call_completion_observer=lambda quiescent: ledger.complete_quiescent_call(
            "planner", quiescent
        ),
    )
    ledger.close_role("planner")
    planner_stop = _planner_stop_cause(planner_session)
    if ledger.has_adapter_identity_failure:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="planner_adapter_identity_mismatch",
            state="post_dispatch_unsealed",
        )
    planner_capture_failure = ledger.response_capture_failure_for_role("planner")
    if planner_capture_failure is not None:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=planner_capture_failure,
            state="post_dispatch_unsealed",
        )
    planner_evidence_failure = ledger.adapter_evidence_failure_for_role("planner")
    if planner_evidence_failure is not None:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=f"planner_{planner_evidence_failure}",
            state="post_dispatch_unsealed",
        )
    if planner_session.termination in {"provider_failure", "timeout"}:
        if (
            ledger.has_unjoined_dispatch
            or not ledger.role_dispatch_complete("planner")
        ):
            return _attempt_result(
                preflight=preflight,
                classification=None,
                planner_session=planner_session,
                evaluator_result=None,
                isolation_result=None,
                checkpoint_gate=None,
                candidate_recipe_bytes=None,
                call_ledger=ledger.frozen_rows(),
                derived_stop_cause="ambiguous_planner_dispatch",
                state="post_dispatch_unsealed",
            )
        return _attempt_result(
            preflight=preflight,
            classification="probe_inconclusive",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=planner_stop,
        )
    if planner_session.termination == "mechanically_rejected":
        return _attempt_result(
            preflight=preflight,
            classification="probe_mechanically_rejected",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=planner_stop,
        )
    if planner_session.termination != "mechanically_accepted":
        raise ValueError("Planner session returned an unknown termination")
    candidate_raw = planner_session.final_recipe_bytes
    assert candidate_raw is not None
    checkpoint_gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=candidate_raw,
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    accepted_turns = tuple(
        turn.gate_result
        for turn in planner_session.turns
        if turn.gate_result is not None
        and turn.gate_result.status == "mechanically_accepted"
    )
    if (
        checkpoint_gate.status != "mechanically_accepted"
        or checkpoint_gate.final_recipe_bytes != candidate_raw
        or len(accepted_turns) != 1
        or checkpoint_gate != accepted_turns[0]
    ):
        raise ValueError("independent checkpoint gate differs from Planner session")
    isolation = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    if isolation.status == "isolation_rejected":
        return _attempt_result(
            preflight=preflight,
            classification="probe_resolution_isolation_failure",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="isolation_rejected",
        )
    if isolation.status != "isolated":
        raise ValueError("resolution isolation returned an unknown status")

    rendered_evaluator = SUPPORT.render_planner_revision_evaluation_request(
        inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    evaluator_request_bytes = (
        PLANNER_SUPPORT.build_planner_evaluator_provider_call_request(
            system_prompt=PLANNER_SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
            user_prompt=rendered_evaluator.raw_bytes.decode("utf-8"),
        )
    )
    def evaluator_provider(request: dict[str, object]) -> object:
        return evaluator_adapter(request)

    staged_evaluator_provider = ledger.wrap(
        evaluator_provider,
        role="planner_evaluator",
        materialize=(
            PLANNER_SUPPORT.materialize_planner_evaluator_provider_call_request
        ),
        expected_response_identity=evaluator_response_identity,
    )
    evaluator_result = PLANNER_SUPPORT.run_planner_evaluation(
        provider=staged_evaluator_provider,
        provider_call_request_bytes=evaluator_request_bytes,
    )
    ledger.complete_quiescent_call(
        "planner_evaluator", evaluator_result.quiescent
    )
    ledger.close_role("planner_evaluator")
    if ledger.has_adapter_identity_failure:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="evaluator_adapter_identity_mismatch",
            state="post_dispatch_unsealed",
        )
    evaluator_capture_failure = ledger.response_capture_failure_for_role(
        "planner_evaluator"
    )
    if evaluator_capture_failure is not None:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=evaluator_capture_failure,
            state="post_dispatch_unsealed",
        )
    evaluator_evidence_failure = ledger.adapter_evidence_failure_for_role(
        "planner_evaluator"
    )
    if evaluator_evidence_failure is not None:
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=f"evaluator_{evaluator_evidence_failure}",
            state="post_dispatch_unsealed",
        )
    if (
        not evaluator_result.quiescent
        or ledger.has_unjoined_dispatch
        or not ledger.role_dispatch_complete("planner_evaluator")
    ):
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="ambiguous_evaluator_dispatch",
            state="post_dispatch_unsealed",
        )
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator_result,
        final_recipe_bytes=candidate_raw,
    )
    if classification == "probe_candidate_blocked":
        raise ValueError("isolation-passing candidate retained an explicit blocker")
    if classification not in {
        "probe_candidate_ready",
        "probe_planner_failure",
        "probe_inconclusive",
    }:
        raise ValueError("shared classifier returned an invalid resolution outcome")
    stop_cause = _evaluator_stop_cause(evaluator_result)
    call_ledger = ledger.frozen_rows()
    return _attempt_result(
        preflight=preflight,
        classification=classification,
        planner_session=planner_session,
        evaluator_result=evaluator_result,
        isolation_result=isolation,
        checkpoint_gate=checkpoint_gate,
        candidate_recipe_bytes=candidate_raw,
        call_ledger=call_ledger,
        derived_stop_cause=stop_cause,
    )


def _attempt_result(
    *,
    preflight: ARTIFACTS.VerifiedResolutionPreflight,
    classification: str | None,
    planner_session: PLANNER_SUPPORT.PlannerSessionResult,
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None,
    isolation_result: SUPPORT.IsolationGateResult | None,
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult | None,
    candidate_recipe_bytes: bytes | None,
    call_ledger: tuple[Mapping[str, object], ...],
    derived_stop_cause: str,
    state: str = "terminal_evidence_complete",
    sealed_checkpoint: ARTIFACTS.SealedResolutionCheckpoint | None = None,
) -> ResolutionAttemptResult:
    if state != "post_dispatch_unsealed":
        ARTIFACTS.verify_resolution_call_ledger(
            preflight=preflight,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation_result,
            classification=classification,
            candidate_recipe_bytes=candidate_recipe_bytes,
            call_ledger=call_ledger,
            derived_stop_cause=derived_stop_cause,
        )
        runtime = preflight.attempt.staging_path / ".resolution-runtime"
        invocation_binding = json.loads((runtime / "invocation.json").read_bytes())
        readiness = json.loads((runtime / "readiness.json").read_bytes())
        try:
            finalized = ARTIFACTS.seal_resolution_checkpoint(
                preflight=preflight,
                invocation_binding=invocation_binding,
                readiness_record=readiness["record"],
                readiness_verified_at=readiness["verified_at"],
                planner_session=planner_session,
                evaluator_result=evaluator_result,
                isolation_result=isolation_result,
                checkpoint_gate=checkpoint_gate,
                candidate_recipe_bytes=candidate_recipe_bytes,
                call_ledger=call_ledger,
                derived_stop_cause=derived_stop_cause,
                classification=classification,
            )
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            locus = f"checkpoint_seal_failure:{type(exc).__name__}"
            ARTIFACTS.retain_post_dispatch_unsealed(
                evidence_dir=preflight.attempt.staging_path,
                preflight=preflight,
                failure_locus=locus,
            )
            return ResolutionAttemptResult(
                classification=None,
                planner_session=planner_session,
                evaluator_result=evaluator_result,
                isolation_result=isolation_result,
                sealed_checkpoint=None,
                checkpoint_gate=checkpoint_gate,
                candidate_recipe_bytes=candidate_recipe_bytes,
                call_ledger=call_ledger,
                derived_stop_cause=locus,
                state="post_dispatch_unsealed",
            )
        if type(finalized) is ARTIFACTS.FinalizationIndeterminate:
            return ResolutionAttemptResult(
                classification=None,
                planner_session=planner_session,
                evaluator_result=evaluator_result,
                isolation_result=isolation_result,
                sealed_checkpoint=None,
                checkpoint_gate=checkpoint_gate,
                candidate_recipe_bytes=candidate_recipe_bytes,
                call_ledger=call_ledger,
                derived_stop_cause=finalized.failure_locus,
                state="finalization_indeterminate",
                finalization_indeterminate=finalized,
            )
        if type(finalized) is ARTIFACTS.PostDispatchUnsealed:
            return ResolutionAttemptResult(
                classification=None,
                planner_session=planner_session,
                evaluator_result=evaluator_result,
                isolation_result=isolation_result,
                sealed_checkpoint=None,
                checkpoint_gate=checkpoint_gate,
                candidate_recipe_bytes=candidate_recipe_bytes,
                call_ledger=call_ledger,
                derived_stop_cause=finalized.failure_locus,
                state="post_dispatch_unsealed",
                finalization_indeterminate=None,
            )
        sealed_checkpoint = finalized
        state = "sealed"
    else:
        ARTIFACTS.retain_post_dispatch_unsealed(
            evidence_dir=preflight.attempt.staging_path,
            preflight=preflight,
            failure_locus=derived_stop_cause,
        )
    return ResolutionAttemptResult(
        classification=classification,
        planner_session=planner_session,
        evaluator_result=evaluator_result,
        isolation_result=isolation_result,
        sealed_checkpoint=sealed_checkpoint,
        checkpoint_gate=checkpoint_gate,
        candidate_recipe_bytes=candidate_recipe_bytes,
        call_ledger=call_ledger,
        derived_stop_cause=derived_stop_cause,
        state=state,
        finalization_indeterminate=None,
    )


def _planner_stop_cause(
    session: PLANNER_SUPPORT.PlannerSessionResult,
) -> str:
    if session.termination == "mechanically_accepted":
        return "mechanically_accepted"
    if session.termination == "provider_failure":
        return "planner_provider_failure"
    if session.termination == "timeout":
        return "planner_terminal_timeout"
    if session.termination != "mechanically_rejected":
        raise ValueError("unknown Planner termination")
    total_tokens = 0
    total_cost = 0.0
    cost_complete = True
    for turn in session.turns:
        tokens, cost, complete = PLANNER_SUPPORT._planner_usage_values(turn.usage)
        total_tokens += tokens
        total_cost += cost
        cost_complete = cost_complete and complete
    if total_tokens >= PLANNER_SUPPORT.PLANNER_TOKEN_STOP_THRESHOLD:
        return "token_stop"
    if cost_complete and total_cost >= PLANNER_SUPPORT.PLANNER_COST_STOP_THRESHOLD_USD:
        return "cost_stop"
    if len(session.turns) == PLANNER_SUPPORT.PLANNER_MAX_TURNS:
        return "max_turns"
    raise ValueError("mechanically rejected session has no derivable stop cause")


def _evaluator_stop_cause(
    result: PLANNER_SUPPORT.PlannerEvaluationResult,
) -> str:
    if result.termination == "valid_recommendation":
        if result.recommendation == "semantically_faithful":
            return "semantic_faithful"
        if result.recommendation == "semantically_unfaithful":
            return "semantic_unfaithful"
        if result.recommendation == "evaluation_inconclusive":
            return "evaluation_inconclusive"
    if result.termination == "malformed":
        return "evaluator_malformed"
    if result.termination == "provider_failure":
        return "evaluator_provider_failure"
    if result.termination == "timeout":
        return "evaluator_terminal_timeout"
    raise ValueError("unknown evaluator termination")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        PLANNER_SUPPORT._json_builtins(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = ("ResolutionAttemptResult", "run_resolution_attempt")
