from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from rook.agent.chat.prime_registry import (
    LifecycleRecord,
    PrimeConversationRecord,
    PrimeConversationRegistry,
    PrimeModelSelection,
    RegistryLockError,
    RegistryValidationError,
    TargetFingerprint,
)


PID = 1234
START_TICKS = "638918000000000000"


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
