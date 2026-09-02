from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from rook.agent.chat import acp_storage
from rook.agent.chat.acp_storage import (
    AssociationAlreadyExists,
    AssociationStore,
    OpenClaim,
    PrimeSessionHeader,
    PublicationAlreadyExists,
    PublicationUnsupported,
    RookBinding,
    SessionRecoveryRequired,
    SessionUnavailable,
    atomic_publish_noreplace,
    validate_prime_session_header,
)
from rook.runtime_paths import AcpDataPaths, RuntimePaths


def _runtime_paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(
        mode="dev",
        install_root=tmp_path / "app",
        data_root=tmp_path / "data",
        logs_root=tmp_path / "logs",
        runtime_root=tmp_path,
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        repo_root=tmp_path / "app",
    )


@pytest.fixture
def paths(tmp_path: Path) -> AcpDataPaths:
    value = AcpDataPaths.from_runtime_paths(_runtime_paths(tmp_path))
    value.create_roots()
    return value


@pytest.fixture
def binding() -> RookBinding:
    return RookBinding(
        profile="full",
        host_generation_id=str(uuid.UUID("a66f624c-cc08-4c76-a8f9-cd999b11b7a4")),
        rhino_document_serial=17,
        route_process_id=4242,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rhino_document_serial", True),
        ("rhino_document_serial", 1.5),
        ("route_process_id", True),
        ("route_process_id", 1.5),
    ],
)
def test_rook_binding_requires_exact_positive_integer_fields(field: str, value: object) -> None:
    values = {
        "profile": "full",
        "host_generation_id": "a66f624c-cc08-4c76-a8f9-cd999b11b7a4",
        "rhino_document_serial": 17,
        "route_process_id": 4242,
    }
    values[field] = value
    with pytest.raises(ValueError):
        RookBinding(**values)


def _write_header(
    path: Path,
    *,
    session_id: str = "01a05a98-7598-76e2-a251-58aaac4d80e1",
    cwd: Path,
    version: int = 3,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "session", "version": version, "id": session_id, "cwd": str(cwd)}
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


@pytest.mark.parametrize(
    "bad_first_line",
    [b"", b"[]\n", b'{"type":"other"}\n', b"{not-json}\n"],
)
def test_header_envelope_refuses_invalid_first_line(
    paths: AcpDataPaths,
    tmp_path: Path,
    bad_first_line: bytes,
) -> None:
    session = paths.sessions_root / "one.jsonl"
    session.write_bytes(bad_first_line)

    with pytest.raises(SessionUnavailable, match="session_unavailable"):
        validate_prime_session_header(
            session,
            expected_id=None,
            expected_cwd=tmp_path,
            sessions_root=paths.sessions_root,
        )


def test_header_envelope_binds_id_cwd_version_and_product_root(paths: AcpDataPaths, tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    session = paths.sessions_root / "one.jsonl"
    _write_header(session, cwd=cwd)

    header = validate_prime_session_header(
        session,
        expected_id="01a05a98-7598-76e2-a251-58aaac4d80e1",
        expected_cwd=cwd,
        sessions_root=paths.sessions_root,
    )

    assert header == PrimeSessionHeader(
        version=3,
        session_id="01a05a98-7598-76e2-a251-58aaac4d80e1",
        working_directory=str(cwd.resolve()),
    )

    outside = tmp_path / "outside.jsonl"
    _write_header(outside, cwd=cwd)
    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(
            outside,
            expected_id=None,
            expected_cwd=cwd,
            sessions_root=paths.sessions_root,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("version", 2), ("version", True), ("id", ""), ("id", "different"), ("cwd", "C:/wrong")],
)
def test_header_envelope_refuses_identity_drift(
    paths: AcpDataPaths,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    session = paths.sessions_root / "one.jsonl"
    payload: dict[str, object] = {
        "type": "session",
        "version": 3,
        "id": "durable-id",
        "cwd": str(cwd),
    }
    payload[field] = value
    session.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(
            session,
            expected_id="durable-id",
            expected_cwd=cwd,
            sessions_root=paths.sessions_root,
        )


def test_header_envelope_refuses_non_utf8_and_oversized_first_line(
    paths: AcpDataPaths,
    tmp_path: Path,
) -> None:
    session = paths.sessions_root / "one.jsonl"
    session.write_bytes(b"\xff\n")
    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(
            session,
            expected_id=None,
            expected_cwd=tmp_path,
            sessions_root=paths.sessions_root,
        )

    session.write_bytes(b"{" + b"x" * acp_storage.MAX_SESSION_HEADER_BYTES + b"\n")
    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(
            session,
            expected_id=None,
            expected_cwd=tmp_path,
            sessions_root=paths.sessions_root,
        )


def test_header_envelope_refuses_symlink_or_reparse_escape(paths: AcpDataPaths, tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    outside = tmp_path / "outside.jsonl"
    _write_header(outside, cwd=cwd)
    alias = paths.sessions_root / "alias.jsonl"
    try:
        alias.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")

    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(
            alias,
            expected_id=None,
            expected_cwd=cwd,
            sessions_root=paths.sessions_root,
        )


def test_open_claim_is_non_expiring_and_create_exclusive(paths: AcpDataPaths) -> None:
    session = paths.canonical_session("one.jsonl")
    first = OpenClaim.acquire(paths.claims_root, session)

    with pytest.raises(SessionRecoveryRequired, match="session_recovery_required"):
        OpenClaim.acquire(paths.claims_root, session)

    assert first.path.read_bytes() == b""
    first.release_no_child_created()
    assert not first.path.exists()


def test_crashed_claim_owner_is_never_reclaimed(paths: AcpDataPaths, tmp_path: Path) -> None:
    session = paths.canonical_session("crashed.jsonl")
    script = (
        "from pathlib import Path; "
        "from rook.agent.chat.acp_storage import OpenClaim; "
        "OpenClaim.acquire(Path(__import__('sys').argv[1]), __import__('sys').argv[2])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(paths.claims_root), session],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    with pytest.raises(SessionRecoveryRequired):
        OpenClaim.acquire(paths.claims_root, session)


def test_atomic_publish_noreplace_preserves_existing_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "association.json"
    destination.write_bytes(b"original")

    with pytest.raises(PublicationAlreadyExists):
        atomic_publish_noreplace(destination, b"replacement")

    assert destination.read_bytes() == b"original"


def test_atomic_publish_refuses_unsupported_platform_before_temp_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "association.json"
    monkeypatch.setattr(acp_storage, "_WINDOWS_ATOMIC_PUBLISH", False)

    with pytest.raises(PublicationUnsupported, match="publication_unsupported"):
        atomic_publish_noreplace(destination, b"payload")

    assert list(tmp_path.iterdir()) == []


def test_atomic_publish_two_processes_create_exactly_one_file(tmp_path: Path) -> None:
    destination = tmp_path / "association.json"
    gate = tmp_path / "go"
    outcomes = [tmp_path / "one.out", tmp_path / "two.out"]
    script = """
import sys, time
from pathlib import Path
from rook.agent.chat.acp_storage import PublicationAlreadyExists, atomic_publish_noreplace
destination, gate, outcome, payload = map(Path, sys.argv[1:])
while not gate.exists():
    time.sleep(0.005)
try:
    atomic_publish_noreplace(destination, payload.name.encode('ascii'))
except PublicationAlreadyExists:
    outcome.write_text('exists', encoding='utf-8')
else:
    outcome.write_text('created', encoding='utf-8')
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(destination), str(gate), str(outcome), name],
            cwd=tmp_path,
        )
        for outcome, name in zip(outcomes, ("one", "two"), strict=True)
    ]
    gate.touch()
    for child in children:
        assert child.wait(timeout=10) == 0

    assert sorted(path.read_text(encoding="utf-8") for path in outcomes) == ["created", "exists"]
    assert destination.read_bytes() in {b"one", b"two"}


def test_association_publication_is_complete_and_create_only(
    paths: AcpDataPaths,
    binding: RookBinding,
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    store = AssociationStore(paths)
    provisional = store.reserve_provisional(
        binding=binding,
        runtime_id="prime-runtime-1",
        working_directory=cwd,
        requested_model="anthropic/claude-x",
        requested_reasoning="high",
    )
    session = Path(provisional.session_path)
    _write_header(session, cwd=cwd, session_id="durable-prime-id")
    header = validate_prime_session_header(
        session,
        expected_id=None,
        expected_cwd=cwd,
        sessions_root=paths.sessions_root,
    )

    published = store.publish(provisional, header)
    with pytest.raises(AssociationAlreadyExists):
        store.publish(provisional, header)

    assert store.get(published.conversation_id) == published
    assert store.list() == (published,)
    assert published.prime_session_id == "durable-prime-id"
    assert published.binding == binding
    assert Path(published.session_path) == session.resolve()


def test_provisional_reservation_refuses_owned_path_collisions(
    paths: AcpDataPaths,
    binding: RookBinding,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    store = AssociationStore(paths)
    fixed = uuid.UUID("11743f23-c588-4535-b70c-2243d60daa29")
    monkeypatch.setattr(acp_storage.uuid, "uuid4", lambda: fixed)
    paths.session_path(fixed.hex).touch()

    with pytest.raises(AssociationAlreadyExists):
        store.reserve_provisional(
            binding=binding,
            runtime_id="prime-runtime-1",
            working_directory=cwd,
            requested_model=None,
            requested_reasoning=None,
        )
