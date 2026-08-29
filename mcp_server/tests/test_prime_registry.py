from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from rook.agent.chat.prime_registry import (
    LifecycleRecord,
    PrimeConversationRecord,
    PrimeConversationRecordV2,
    PrimeConversationRegistry,
    PrimeModelSelection,
    PrimeRuntimeContractRef,
    RegistryLockError,
    RegistryValidationError,
    RuntimePreparation,
    TargetFingerprint,
    TargetFingerprintV2,
)


PID = 1234
START_TICKS = "638918000000000000"
CONTRACT_SHA256 = "A" * 64
GH_DOCUMENT_ID = "01234567-89ab-cdef-0123-456789abcdef"


def record(
    conversation_id: str = "conv_aaaaaaaaaaaa",
    *,
    state: str = "idle",
    reason: str | None = None,
    target: TargetFingerprint | None = None,
) -> PrimeConversationRecord:
    return PrimeConversationRecord(
        schema_version=1,
        conversation_id=conversation_id,
        prime_session_id=f"session-{conversation_id}",
        prime_session_path=f"sessions/{conversation_id}.jsonl",
        model=PrimeModelSelection(
            provider="openai-codex",
            id="gpt-5.6-sol",
            thinking="xhigh",
        ),
        target=target
        or TargetFingerprint(
            rhino_pid=PID,
            rhino_process_start_utc_ticks=START_TICKS,
            document_runtime_serial=42,
        ),
        last_lifecycle=LifecycleRecord(
            state=state,
            reason=reason,
            updated_at_utc="2026-08-26T12:00:00Z",
        ),
    )


def record_v2(
    tmp_path: Path,
    conversation_id: str = "conv_v2_aaaaaaaa",
    *,
    profile: str = "readonly",
    preparation: RuntimePreparation | None = None,
    state: str = "idle",
    reason: str | None = None,
) -> PrimeConversationRecordV2:
    environment = tmp_path / "kernels" / CONTRACT_SHA256
    return PrimeConversationRecordV2(
        schema_version=2,
        conversation_id=conversation_id,
        prime_session_id=f"session-{conversation_id}",
        prime_session_path=str(tmp_path / "sessions" / f"{conversation_id}.jsonl"),
        model=PrimeModelSelection(
            provider="openai-codex",
            id="gpt-5.6-sol",
            thinking="xhigh",
        ),
        runtime=PrimeRuntimeContractRef(
            contract_fingerprint_sha256=CONTRACT_SHA256,
            capability_profile=profile,
            kernel_environment_path=str(environment),
            preparation=preparation
            or RuntimePreparation(
                status="pending",
                interpreter_path=None,
                prepared_at_utc=None,
            ),
        ),
        target=TargetFingerprintV2(
            rhino_pid=PID,
            rhino_process_start_utc_ticks=START_TICKS,
            document_runtime_serial=42,
            grasshopper_document_id=GH_DOCUMENT_ID,
        ),
        last_lifecycle=LifecycleRecord(
            state=state,
            reason=reason,
            updated_at_utc="2026-08-29T12:00:00Z",
        ),
    )


@pytest.fixture
def registry(tmp_path: Path):
    owner = PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    try:
        yield owner
    finally:
        owner.close()


def test_round_trip_uses_closed_camel_case_record_and_absolute_session_path(
    registry: PrimeConversationRegistry,
) -> None:
    path = registry.write(record())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schemaVersion",
        "conversationId",
        "primeSessionId",
        "primeSessionPath",
        "model",
        "target",
        "lastLifecycle",
    }
    assert set(payload["model"]) == {"provider", "id", "thinking"}
    assert set(payload["target"]) == {
        "rhinoPid",
        "rhinoProcessStartUtcTicks",
        "documentRuntimeSerial",
    }
    assert set(payload["lastLifecycle"]) == {
        "state",
        "reason",
        "updatedAtUtc",
    }
    assert Path(payload["primeSessionPath"]).is_absolute()
    assert registry.load("conv_aaaaaaaaaaaa") == replace(
        record(),
        prime_session_path=str(Path("sessions/conv_aaaaaaaaaaaa.jsonl").resolve()),
    )


def test_v1_bytes_remain_frozen(registry: PrimeConversationRegistry) -> None:
    path = registry.write(record())
    expected = {
        "conversationId": "conv_aaaaaaaaaaaa",
        "lastLifecycle": {
            "reason": None,
            "state": "idle",
            "updatedAtUtc": "2026-08-26T12:00:00Z",
        },
        "model": {
            "id": "gpt-5.6-sol",
            "provider": "openai-codex",
            "thinking": "xhigh",
        },
        "primeSessionId": "session-conv_aaaaaaaaaaaa",
        "primeSessionPath": str(
            Path("sessions/conv_aaaaaaaaaaaa.jsonl").resolve()
        ),
        "schemaVersion": 1,
        "target": {
            "documentRuntimeSerial": 42,
            "rhinoPid": PID,
            "rhinoProcessStartUtcTicks": START_TICKS,
        },
    }
    golden = (
        json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")

    assert path.read_bytes() == golden
    assert registry.load("conv_aaaaaaaaaaaa") == replace(
        record(),
        prime_session_path=str(Path("sessions/conv_aaaaaaaaaaaa.jsonl").resolve()),
    )


def test_v2_round_trip_uses_closed_shape(
    registry: PrimeConversationRegistry, tmp_path: Path
) -> None:
    expected = record_v2(tmp_path)

    path = registry.write_new_v2(expected)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schemaVersion",
        "conversationId",
        "primeSessionId",
        "primeSessionPath",
        "model",
        "runtime",
        "target",
        "lastLifecycle",
    }
    assert set(payload["runtime"]) == {
        "contractFingerprintSha256",
        "capabilityProfile",
        "kernelEnvironmentPath",
        "preparation",
    }
    assert set(payload["runtime"]["preparation"]) == {
        "status",
        "interpreterPath",
        "preparedAtUtc",
    }
    assert set(payload["target"]) == {
        "rhinoPid",
        "rhinoProcessStartUtcTicks",
        "documentRuntimeSerial",
        "grasshopperDocumentId",
    }
    assert registry.load(expected.conversation_id) == expected


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.pop("runtime"), "v2 record keys"),
        (lambda value: value.update({"authority": {}}), "v2 record keys"),
        (lambda value: value["runtime"].pop("capabilityProfile"), "runtime keys"),
        (lambda value: value["runtime"].update({"profile": "full"}), "runtime keys"),
        (
            lambda value: value["runtime"]["preparation"].pop("status"),
            "preparation keys",
        ),
        (
            lambda value: value["runtime"]["preparation"].update({"ready": True}),
            "preparation keys",
        ),
        (
            lambda value: value["target"].pop("grasshopperDocumentId"),
            "v2 target keys",
        ),
        (lambda value: value["target"].update({"documentId": None}), "v2 target keys"),
    ],
)
def test_v2_load_rejects_missing_or_unknown_keys(
    registry: PrimeConversationRegistry,
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    path = registry.write_new_v2(record_v2(tmp_path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RegistryValidationError, match=message):
        registry.load("conv_v2_aaaaaaaa")


def test_v2_load_rejects_duplicate_keys(
    registry: PrimeConversationRegistry, tmp_path: Path
) -> None:
    path = registry.write_new_v2(record_v2(tmp_path))
    raw = path.read_text(encoding="utf-8")
    path.write_text(
        raw.replace(
            '"schemaVersion":2,',
            '"schemaVersion":2,"schemaVersion":2,',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="duplicate JSON key"):
        registry.load("conv_v2_aaaaaaaa")


@pytest.mark.parametrize("fingerprint", ["a" * 64, "A" * 63, "G" * 64, ""])
def test_v2_requires_canonical_uppercase_sha256(
    tmp_path: Path, fingerprint: str
) -> None:
    with pytest.raises(RegistryValidationError, match="SHA-256"):
        replace(
            record_v2(tmp_path).runtime,
            contract_fingerprint_sha256=fingerprint,
        )


@pytest.mark.parametrize(
    "document_id",
    [
        "01234567-89AB-CDEF-0123-456789ABCDEF",
        "{01234567-89ab-cdef-0123-456789abcdef}",
        "0123456789abcdef0123456789abcdef",
        "not-a-guid",
        "00000000-0000-0000-0000-000000000000",
    ],
)
def test_v2_requires_canonical_nonempty_guid(document_id: str) -> None:
    with pytest.raises(RegistryValidationError, match="Grasshopper document ID"):
        TargetFingerprintV2(
            rhino_pid=PID,
            rhino_process_start_utc_ticks=START_TICKS,
            document_runtime_serial=42,
            grasshopper_document_id=document_id,
        )


@pytest.mark.parametrize("profile", ["read", "write", "FULL", ""])
def test_v2_requires_closed_capability_profile(tmp_path: Path, profile: str) -> None:
    with pytest.raises(RegistryValidationError, match="capability profile"):
        record_v2(tmp_path, profile=profile)


def test_v2_pending_and_prepared_fields_are_paired(tmp_path: Path) -> None:
    environment = tmp_path / "kernels" / CONTRACT_SHA256
    interpreter = environment / "Scripts" / "python.exe"

    with pytest.raises(RegistryValidationError, match="pending preparation"):
        RuntimePreparation(
            status="pending",
            interpreter_path=str(interpreter),
            prepared_at_utc=None,
        )
    with pytest.raises(RegistryValidationError, match="prepared preparation"):
        RuntimePreparation(
            status="prepared",
            interpreter_path=None,
            prepared_at_utc="2026-08-29T12:00:01Z",
        )
    with pytest.raises(RegistryValidationError, match="contract environment"):
        PrimeRuntimeContractRef(
            contract_fingerprint_sha256=CONTRACT_SHA256,
            capability_profile="readonly",
            kernel_environment_path=str(environment),
            preparation=RuntimePreparation(
                status="prepared",
                interpreter_path=str(tmp_path / "other" / "python.exe"),
                prepared_at_utc="2026-08-29T12:00:01Z",
            ),
        )


def test_v2_transition_changes_only_preparation_triple(
    registry: PrimeConversationRegistry, tmp_path: Path
) -> None:
    pending = record_v2(tmp_path)
    registry.write_new_v2(pending)
    interpreter = Path(pending.runtime.kernel_environment_path) / "Scripts/python.exe"

    prepared = registry.mark_runtime_prepared(
        pending.conversation_id,
        str(interpreter),
        "2026-08-29T12:00:01Z",
    )

    assert prepared.runtime.preparation == RuntimePreparation(
        status="prepared",
        interpreter_path=str(interpreter),
        prepared_at_utc="2026-08-29T12:00:01Z",
    )
    assert replace(prepared, runtime=pending.runtime) == pending


def test_v2_rejects_rewriting_immutable_contract_or_preparation(
    registry: PrimeConversationRegistry, tmp_path: Path
) -> None:
    pending = record_v2(tmp_path)
    registry.write_new_v2(pending)

    with pytest.raises(RegistryValidationError, match="immutable"):
        registry.write(
            replace(
                pending,
                runtime=replace(pending.runtime, capability_profile="full"),
            )
        )

    interpreter = Path(pending.runtime.kernel_environment_path) / "Scripts/python.exe"
    registry.mark_runtime_prepared(
        pending.conversation_id,
        str(interpreter),
        "2026-08-29T12:00:01Z",
    )
    with pytest.raises(RegistryValidationError, match="already prepared"):
        registry.mark_runtime_prepared(
            pending.conversation_id,
            str(interpreter),
            "2026-08-29T12:00:02Z",
        )
    with pytest.raises(RegistryValidationError, match="preparation"):
        registry.write(pending)


def test_restart_marks_pending_v2_runtime_unavailable(
    registry: PrimeConversationRegistry, tmp_path: Path
) -> None:
    pending = record_v2(tmp_path)
    registry.write_new_v2(pending)

    changed = registry.reconcile_interrupted_records()

    assert changed == (pending.conversation_id,)
    loaded = registry.load(pending.conversation_id)
    assert isinstance(loaded, PrimeConversationRecordV2)
    assert loaded.runtime.preparation.status == "pending"
    assert loaded.last_lifecycle.state == "failed"
    assert loaded.last_lifecycle.reason == "runtime_contract_unavailable"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.pop("model"), "record keys"),
        (lambda value: value.update({"credential": "secret"}), "record keys"),
        (lambda value: value["model"].pop("provider"), "model keys"),
        (lambda value: value["model"].update({"temperature": 0}), "model keys"),
        (lambda value: value["target"].pop("rhinoPid"), "target keys"),
        (lambda value: value["target"].update({"pid": PID}), "target keys"),
        (lambda value: value["lastLifecycle"].pop("state"), "lifecycle keys"),
        (lambda value: value["lastLifecycle"].update({"pid": 7}), "lifecycle keys"),
    ],
)
def test_load_rejects_missing_or_unknown_keys_at_every_level(
    registry: PrimeConversationRegistry,
    mutate,
    message: str,
) -> None:
    path = registry.write(record())
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RegistryValidationError, match=message):
        registry.load("conv_aaaaaaaaaaaa")


@pytest.mark.parametrize(
    "conversation_id",
    ["../escape", "conv/slash", "conv\\slash", ".hidden", "has space", ""],
)
def test_conversation_ids_are_path_safe(
    registry: PrimeConversationRegistry,
    conversation_id: str,
) -> None:
    with pytest.raises(RegistryValidationError, match="conversation_id"):
        registry.write(record(conversation_id))


@pytest.mark.parametrize("ticks", ["0638918000000000000", "+638918", "638_918", "", "-1"])
def test_process_start_ticks_are_canonical_decimal(tmp_path: Path, ticks: str) -> None:
    with pytest.raises(RegistryValidationError, match="process start ticks"):
        PrimeConversationRegistry(tmp_path, PID, ticks)


def test_record_target_must_match_registry_namespace(
    registry: PrimeConversationRegistry,
) -> None:
    wrong_target = TargetFingerprint(
        rhino_pid=PID + 1,
        rhino_process_start_utc_ticks=START_TICKS,
        document_runtime_serial=42,
    )

    with pytest.raises(RegistryValidationError, match="target does not match"):
        registry.write(record(target=wrong_target))


def test_independent_updates_do_not_rewrite_sibling(
    registry: PrimeConversationRegistry,
) -> None:
    registry.write(record("conv_aaaaaaaaaaaa"))
    sibling = registry.write(record("conv_bbbbbbbbbbbb"))
    sibling_bytes = sibling.read_bytes()

    registry.write(record("conv_aaaaaaaaaaaa", state="failed", reason="test"))

    assert sibling.read_bytes() == sibling_bytes


def test_atomic_replace_failure_preserves_previous_record(
    registry: PrimeConversationRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = registry.write(record())
    before = path.read_bytes()

    def fail_replace(_source: str | os.PathLike[str], _target: str | os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("rook.agent.chat.prime_registry.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        registry.write(record(state="failed", reason="not published"))

    assert path.read_bytes() == before
    assert list(path.parent.glob("*.tmp")) == []


def test_second_writer_refuses_same_process_generation(tmp_path: Path) -> None:
    first = PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    try:
        with pytest.raises(RegistryLockError, match="already has a writer"):
            PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    finally:
        first.close()


def test_different_process_generations_have_independent_writers(tmp_path: Path) -> None:
    first = PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    second = PrimeConversationRegistry(tmp_path, PID, str(int(START_TICKS) + 1))
    try:
        assert first.namespace != second.namespace
    finally:
        first.close()
        second.close()


def test_restart_reconciliation_changes_only_interrupted_states(
    registry: PrimeConversationRegistry,
) -> None:
    registry.write(record("conv_aaaaaaaaaaaa", state="running"))
    registry.write(record("conv_bbbbbbbbbbbb", state="cancel_requested"))
    registry.write(record("conv_cccccccccccc", state="idle"))
    registry.write(record("conv_dddddddddddd", state="failed", reason="existing"))
    registry.write(record("conv_eeeeeeeeeeee", state="closed", reason="user"))

    changed = registry.reconcile_interrupted_records()

    assert changed == ("conv_aaaaaaaaaaaa", "conv_bbbbbbbbbbbb")
    for conversation_id in changed:
        assert registry.load(conversation_id).last_lifecycle.state == "failed"
        assert (
            registry.load(conversation_id).last_lifecycle.reason
            == "broker_restart_interrupted"
        )
    assert registry.load("conv_cccccccccccc").last_lifecycle.state == "idle"
    assert registry.load("conv_dddddddddddd").last_lifecycle.reason == "existing"
    assert registry.load("conv_eeeeeeeeeeee").last_lifecycle.state == "closed"
