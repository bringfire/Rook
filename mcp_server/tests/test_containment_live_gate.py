from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rook.gh_status_contract import normalize_gh_status_result


EXPECTED_RED = "EXPECTED_RED:T8:LIVE_GATE"
RUN_ID = "1" * 32
NONCE = "2" * 32
PROCESS_TOKEN = "3" * 32
SPHERE_ID = "11111111-1111-4111-8111-111111111111"
POINT_ID = "22222222-2222-4222-8222-222222222222"
GH_DOCUMENT_ID = "33333333-3333-4333-8333-333333333333"
GH_BOOTSTRAP_DOCUMENT_ID = "44444444-4444-4444-8444-444444444444"
SPHERE_AREA = 201.0619
SPHERE_VOLUME = 268.0826


class _FinalPairBaseInterrupt(BaseException):
    pass

try:
    live = importlib.import_module("rook.containment_live_gate")
except ModuleNotFoundError as exc:
    if exc.name != "rook.containment_live_gate":
        raise
    live = None


requires_live_gate = pytest.mark.skipif(
    live is None,
    reason="installed containment live gate is not implemented",
)


def _directory_symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks/reparse points unavailable")


def _file_symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks/reparse points unavailable")


@pytest.fixture
def owned_claim_factory(request: pytest.FixtureRequest):
    claims = []

    def create(path: Path):
        claim = live._claim_artifact_directory(path, RUN_ID)
        claims.append(claim)
        return claim

    def reclaim(path: Path):
        leases = live._acquire_retained_path_leases(path, "directory")
        claim = live._ArtifactRootClaim(path, leases)
        claim.verify()
        claims.append(claim)
        return claim

    create.reclaim = reclaim  # type: ignore[attr-defined]

    def release_claims() -> None:
        for claim in reversed(claims):
            if not claim._released:
                claim.release()

    request.addfinalizer(release_claims)
    return create


def test_containment_live_gate_contract_is_available() -> None:
    assert live is not None, f"{EXPECTED_RED} rook.containment_live_gate is not implemented"


@requires_live_gate
def test_literal_contract_tables_are_exact_and_closed() -> None:
    assert live.SCENARIOS == ("rhino", "grasshopper")
    assert live.FAILURE_LABELS == (
        "runtime_origin_invalid",
        "launch_failed",
        "readiness_failed",
        "fixture_invalid",
        "preflight_blocked",
        "authorization_rejected",
        "state_drift",
        "mutation_failed",
        "verification_failed",
        "ownership_ambiguous",
        "restoration_failed",
        "telemetry_changed",
        "cleanup_failed",
    )
    assert live.RHINO_TOOL_ALLOWLIST == frozenset(
        {
            "rhino_ping",
            "rhino_document",
            "rhino_objects",
            "rhino_geometry",
            "rhino_document_ops",
            "rhino_create",
            "rhino_execute",
            "rhino_delete",
        }
    )
    assert live.GRASSHOPPER_TOOL_ALLOWLIST == frozenset(
        {
            "rhino_ping",
            "rhino_document",
            "rhino_command",
            "gh_status",
            "gh_document_open",
            "gh_library",
            "gh_snapshot",
            "gh_edit",
            "gh_errors",
            "gh_undo",
        }
    )
    assert live.SPHERE_COMPONENT_GUID == "dabc854d-f50e-408a-b001-d043c7de151d"
    assert live.FIXTURE_SIZE == 2708
    assert live.FIXTURE_SHA256 == "2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df"
    assert set(live.CONTAINED_IDENTITIES) == {
        "gh_execute_intent",
        "rhino_execute_intent",
        "plan_and_execute",
        "spawn_agent",
        "gh_explore_workflow",
        "gh_replay_recipe",
    }


@requires_live_gate
def test_cli_parser_is_closed_and_has_no_autoauthorization_surface(tmp_path: Path) -> None:
    parser = live._build_parser()
    rhino = tmp_path / "Rhino.exe"
    artifact = tmp_path / "artifacts"
    parsed = parser.parse_args(
        [
            "run",
            "--scenario",
            "rhino",
            "--rhino-exe",
            str(rhino),
            "--artifact-dir",
            str(artifact),
        ]
    )
    assert vars(parsed) == {
        "command": "run",
        "scenario": "rhino",
        "rhino_exe": str(rhino),
        "artifact_dir": str(artifact),
    }
    rejected = (
        ["run", "--scenario", "bogus", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact)],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--yes"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--authorization", "x"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--authorization-env", "X"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino)],
        ["rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact)],
    )
    for argv in rejected:
        with pytest.raises(SystemExit):
            parser.parse_args(argv)

    signature = inspect.signature(live.run_live_scenario)
    assert list(signature.parameters) == ["scenario", "rhino_exe", "artifact_dir"]
    assert all(item.kind is inspect.Parameter.KEYWORD_ONLY for item in signature.parameters.values())
    source = inspect.getsource(live.run_live_scenario)
    for forbidden in ("authorization_reader", "executor=", "autoapprove", "--yes"):
        assert forbidden not in source


@requires_live_gate
def test_authorization_protocol_is_canonical_exact_and_one_shot(tmp_path: Path) -> None:
    target = {
        "label": "Rook containment Rhino scratch document",
        "process_id": 9001,
        "port": 19001,
        "scratch_path": str((tmp_path / f"RookContainmentRhino-{RUN_ID}.3dm").resolve()),
    }
    record = live._build_authorization_challenge(
        scenario="rhino",
        run_id=RUN_ID,
        nonce=NONCE,
        target=target,
    )
    assert set(record) == {
        "type",
        "schema_version",
        "scenario",
        "run_id",
        "nonce",
        "target",
        "target_sha256",
        "mutation",
        "mutation_sha256",
        "verification",
        "verification_sha256",
        "restoration",
        "restoration_sha256",
        "required_response",
    }
    assert record["type"] == "authorization_required"
    assert record["schema_version"] == 1
    assert record["target"] == target
    assert record["required_response"] == (
        f"AUTHORIZE scenario=rhino run={RUN_ID} nonce={NONCE} "
        f"target={record['target_sha256']} mutation={record['mutation_sha256']} "
        f"verify={record['verification_sha256']} restore={record['restoration_sha256']}"
    )
    encoded = live._canonical_json_bytes(record)
    assert encoded == json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert b"\n" not in encoded

    required = record["required_response"].encode("ascii")
    assert live._authorization_matches(record, required + b"\n")
    assert live._authorization_matches(record, required + b"\r\n")
    for rejected in (
        b"",
        required,
        required + b"\r",
        required + b" \n",
        required.lower() + b"\n",
        required + b"\xff\n",
        required + b"\x00\n",
        required + b"\nEXTRA\n",
        record["required_response"] + "\n",
    ):
        assert not live._authorization_matches(record, rejected)


@requires_live_gate
def test_stdin_seam_reads_exactly_one_bounded_line(monkeypatch: pytest.MonkeyPatch) -> None:
    class BinaryOnlyStdin:
        def __init__(self, payload: bytes):
            self.buffer = io.BytesIO(payload)

        def readline(self, *args, **kwargs):
            pytest.fail(f"{EXPECTED_RED}:AUTHORIZATION_BYTES text-mode stdin was read")

    monkeypatch.setattr(
        sys,
        "stdin",
        BinaryOnlyStdin(b"alpha\r\nbeta\xff\n"),
    )
    assert live._read_authorization_line() == b"alpha\r\n"
    assert sys.stdin.buffer.read() == b"beta\xff\n"

    for payload in (b"alpha\n", b"alpha\r", b"\xff\n", b"\x80alternate\n", b""):
        monkeypatch.setattr(sys, "stdin", BinaryOnlyStdin(payload))
        assert live._read_authorization_line() == payload

    monkeypatch.setattr(sys, "stdin", BinaryOnlyStdin(b"x" * 8193 + b"\n"))
    with pytest.raises(live.LiveGateError, match="authorization line"):
        live._read_authorization_line()


@requires_live_gate
def test_fixture_bytes_hash_xml_counts_and_package_lookup() -> None:
    path = live._fixture_resource_path()
    payload = path.read_bytes()
    assert len(payload) == 2708
    assert hashlib.sha256(payload).hexdigest() == live.FIXTURE_SHA256
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in payload
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    root = ET.fromstring(payload.decode("utf-8"))
    assert root.tag == "Archive"
    object_count = root.find("./chunks/chunk[@name='Definition']/chunks/chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']")
    assert object_count is not None and object_count.text == "0"
    definition_objects = root.find("./chunks/chunk[@name='Definition']/chunks/chunk[@name='DefinitionObjects']/chunks")
    assert definition_objects is not None and definition_objects.attrib == {"count": "0"}
    assert live._validate_fixture_bytes(payload) is None
    for corrupt in (payload[:-1], payload + b"\n", b"\xef\xbb\xbf" + payload, payload.replace(b"\n", b"\r\n")):
        with pytest.raises(live.LiveGateError, match="fixture"):
            live._validate_fixture_bytes(corrupt)


@requires_live_gate
def test_fixture_cached_attribute_and_blob_preserve_exact_lf_bytes() -> None:
    root = Path(__file__).resolve().parents[2]
    fixture = "mcp_server/src/rook/resources/containment_empty.ghx"
    attribute_lines = (root / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert attribute_lines == [
        "third_party/ffmpeg/ffmpeg.exe filter=lfs diff=lfs merge=lfs -text",
        f"{fixture} -text",
    ]

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    assert git("check-attr", "--cached", "text", "--", fixture) == (
        f"{fixture}: text: unset"
    )
    assert git("hash-object", "--", fixture) == git("rev-parse", f":{fixture}")
    eol = git("ls-files", "--eol", "--", fixture)
    assert re.search(r"(^|\s)i/lf\s+w/lf\s+attr/-text(\s|$)", eol)


@requires_live_gate
@pytest.mark.parametrize("case", ["missing-parent", "nonempty", "symlink", "owned"])
def test_artifact_preownership_rejection_is_zero_write(
    tmp_path: Path,
    case: str,
) -> None:
    if case == "missing-parent":
        artifact = tmp_path / "missing" / "artifacts"
        before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    elif case == "nonempty":
        artifact = tmp_path / "artifacts"
        artifact.mkdir()
        (artifact / "existing.txt").write_text("keep", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in artifact.iterdir()}
    elif case == "owned":
        artifact = tmp_path / "artifacts"
        artifact.mkdir()
        (artifact / live.OWNERSHIP_MARKER).write_text("owned", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in artifact.iterdir()}
    else:
        target = tmp_path / "target"
        target.mkdir()
        artifact = tmp_path / "artifacts"
        try:
            artifact.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable")
        before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    with pytest.raises(live.PreOwnershipBlocked):
        live._claim_artifact_directory(artifact, RUN_ID)

    if isinstance(before, dict):
        assert {path.name: path.read_bytes() for path in artifact.iterdir()} == before
    else:
        assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == before


@requires_live_gate
def test_artifact_claim_is_atomic_and_marker_is_canonical(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts"
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    try:
        assert claim.path == artifact.resolve()
        marker = artifact / live.OWNERSHIP_MARKER
        payload = marker.read_bytes()
        decoded = json.loads(payload)
        assert decoded == {"process_id": os.getpid(), "run_id": RUN_ID, "schema_version": 1}
        assert payload == live._canonical_json_bytes(decoded)
        with pytest.raises(live.PreOwnershipBlocked):
            live._claim_artifact_directory(artifact, RUN_ID)
    finally:
        claim.release()


@requires_live_gate
def test_artifact_claim_pins_root_before_marker_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts"
    displaced = tmp_path / "displaced-artifacts"
    redirected = tmp_path / "redirected-artifacts"
    redirected.mkdir()
    original_open = live.os.open
    blocked = False
    swapped = False

    def race_marker_open(path: Path, flags: int, mode: int = 0o777) -> int:
        nonlocal blocked, swapped
        if Path(path).name == live.OWNERSHIP_MARKER and not blocked and not swapped:
            try:
                artifact.rename(displaced)
            except PermissionError:
                blocked = True
            else:
                _directory_symlink_or_skip(artifact, redirected)
                swapped = True
        return original_open(path, flags, mode)

    monkeypatch.setattr(live.os, "open", race_marker_open)

    claim = live._claim_artifact_directory(artifact, RUN_ID)
    try:
        assert claim.path == artifact.resolve()
        assert blocked is True
        assert swapped is False, "artifact root was redirected during marker creation"
        assert (artifact / live.OWNERSHIP_MARKER).is_file()
        assert not (redirected / live.OWNERSHIP_MARKER).exists()
    finally:
        claim.release()


@requires_live_gate
def test_producer_retains_root_claim_immediately_after_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    redirected = tmp_path / "redirected-after-claim"
    redirected.mkdir()
    displaced = tmp_path / "displaced-after-claim"
    original_claim = live._claim_artifact_directory
    blocked = False
    swapped = False

    def race_after_claim(path: Path, run_id: str, **kwargs):
        nonlocal blocked, swapped
        claim = original_claim(path, run_id, **kwargs)
        try:
            claim.path.rename(displaced)
        except PermissionError:
            blocked = True
        else:
            _directory_symlink_or_skip(claim.path, redirected)
            swapped = True
        return claim

    monkeypatch.setattr(live, "_claim_artifact_directory", race_after_claim)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True
    assert blocked is True
    assert swapped is False, "producer root was redirected immediately after claim"
    assert not list(redirected.iterdir())


@requires_live_gate
def test_producer_retains_root_claim_through_final_emission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    redirected = tmp_path / "redirected-final"
    redirected.mkdir()
    displaced = tmp_path / "displaced-final"
    original_write_pair = live._write_final_evidence_pair
    blocked = False
    swapped = False

    def race_final_pair(artifact_dir: Path, scenario: str, evidence, *args, **kwargs):
        nonlocal blocked, swapped
        try:
            Path(artifact_dir).rename(displaced)
        except PermissionError:
            blocked = True
        else:
            _directory_symlink_or_skip(Path(artifact_dir), redirected)
            swapped = True
        return original_write_pair(artifact_dir, scenario, evidence, *args, **kwargs)

    monkeypatch.setattr(live, "_write_final_evidence_pair", race_final_pair)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True
    assert blocked is True
    assert swapped is False, "producer root was redirected during final emission"
    assert not list(redirected.iterdir())


@requires_live_gate
def test_producer_releases_root_claim_exactly_once_on_baseexception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_claim = live._claim_artifact_directory
    original_acquire = live._acquire_windows_path_lease
    release_calls = 0
    lease_release_calls: list[int] = []

    def tracked_acquire(*args, **kwargs):
        lease = original_acquire(*args, **kwargs)
        release_index = len(lease_release_calls)
        lease_release_calls.append(0)
        original_release = lease.release

        def tracked_lease_release() -> None:
            lease_release_calls[release_index] += 1
            original_release()

        lease.release = tracked_lease_release
        return lease

    def tracked_claim(path: Path, run_id: str, **kwargs):
        nonlocal release_calls
        claim = original_claim(path, run_id, **kwargs)
        original_release = claim.release

        def tracked_release() -> None:
            nonlocal release_calls
            release_calls += 1
            original_release()

        claim.release = tracked_release
        return claim

    injected = _FinalPairBaseInterrupt("final evidence interrupted")
    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(live, "_claim_artifact_directory", tracked_claim)
    monkeypatch.setattr(
        live,
        "_run_claimed_live_scenario",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(injected),
    )

    with pytest.raises(_FinalPairBaseInterrupt) as caught:
        live.run_live_scenario(
            scenario="rhino",
            rhino_exe=harness.rhino_exe,
            artifact_dir=harness.artifact,
        )

    assert caught.value is injected
    assert release_calls == 1
    assert lease_release_calls
    assert set(lease_release_calls) == {1}
    harness.artifact.rename(tmp_path / "released-artifacts")


@requires_live_gate
def test_producer_root_adoption_failure_releases_unadopted_lease_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts"
    original_acquire = live._acquire_windows_path_lease
    original_adopt_registered = live._RetainedPathLeases._adopt_registered
    acquired: list[tuple[object, list[int], object]] = []
    injected = KeyboardInterrupt("producer root adoption interrupted")

    def tracked_acquire(*args, **kwargs):
        lease = original_acquire(*args, **kwargs)
        calls = [0]
        original_release = lease.release

        def tracked_release() -> None:
            calls[0] += 1
            original_release()

        lease.release = tracked_release
        acquired.append((lease, calls, original_release))
        return lease

    def interrupt_root_adoption(retained, lease) -> None:
        if lease.path == artifact:
            raise injected
        original_adopt_registered(retained, lease)

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(
        live._RetainedPathLeases,
        "_adopt_registered",
        interrupt_root_adoption,
    )

    with pytest.raises(KeyboardInterrupt) as caught:
        live._claim_artifact_directory(artifact, RUN_ID)

    observed = [calls[0] for _lease, calls, _release in acquired]
    for lease, calls, original_release in acquired:
        if calls[0] == 0:
            original_release()
    assert caught.value is injected
    assert observed and set(observed) == {1}


@requires_live_gate
@pytest.mark.parametrize("terminal", ["success", "ordinary_failure", "baseexception"])
def test_producer_releases_every_acquired_lease_once_on_all_terminal_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    terminal: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_acquire = live._acquire_windows_path_lease
    release_calls: list[int] = []

    def tracked_acquire(*args, **kwargs):
        lease = original_acquire(*args, **kwargs)
        release_index = len(release_calls)
        release_calls.append(0)
        original_release = lease.release

        def tracked_release() -> None:
            release_calls[release_index] += 1
            original_release()

        lease.release = tracked_release
        return lease

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    if terminal != "success":
        injected = (
            OSError("ordinary final interruption")
            if terminal == "ordinary_failure"
            else _FinalPairBaseInterrupt("base final interruption")
        )
        monkeypatch.setattr(
            live,
            "_write_final_evidence_pair",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(injected),
        )

    if terminal == "success":
        assert live.run_live_scenario(
            scenario="rhino",
            rhino_exe=harness.rhino_exe,
            artifact_dir=harness.artifact,
        ).success
    else:
        with pytest.raises(type(injected)) as caught:
            live.run_live_scenario(
                scenario="rhino",
                rhino_exe=harness.rhino_exe,
                artifact_dir=harness.artifact,
            )
        assert caught.value is injected

    assert len(release_calls) > 1
    assert set(release_calls) == {1}


@requires_live_gate
def test_retained_directory_handles_pin_each_writable_path_until_reverse_release(
    tmp_path: Path,
) -> None:
    ancestor = tmp_path / "retained-ancestor"
    descendant = ancestor / "retained-descendant"
    descendant.mkdir(parents=True)
    leases = [
        live._acquire_windows_directory_lease(path, path.lstat())
        for path in (ancestor, descendant)
    ]
    try:
        assert all(lease.rename_pinned is True for lease in leases)
        for path in (descendant, ancestor):
            with pytest.raises(PermissionError):
                path.rename(path.with_name(f"{path.name}-while-retained"))
    finally:
        for lease in reversed(leases):
            lease.release()

    descendant.rename(ancestor / "descendant-after-release")
    ancestor.rename(tmp_path / "ancestor-after-release")


@requires_live_gate
def test_directory_sharing_violation_never_falls_back_to_weak_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import ctypes

    target = tmp_path / "sharing-conflict"
    target.mkdir()
    create_calls = 0

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel32:
        def __init__(self):
            self.CreateFileW = FakeFunction(self._create)
            self.GetFileInformationByHandle = FakeFunction(lambda *_args: 0)
            self.CloseHandle = FakeFunction(lambda *_args: 1)

        def _create(self, *_args):
            nonlocal create_calls
            create_calls += 1
            ctypes.set_last_error(32)
            return ctypes.c_void_p(-1).value

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: FakeKernel32(),
    )

    with pytest.raises(OSError) as caught:
        live._acquire_windows_directory_lease(target, target.lstat())

    assert caught.value.errno == 32
    assert create_calls == 1


@requires_live_gate
@pytest.mark.parametrize("acquisition", ["terminal_chain", "direct_descendant"])
def test_sensitive_directory_use_rejects_weak_handle_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    acquisition: str,
) -> None:
    target = tmp_path / "weak-terminal"
    target.mkdir()
    original_acquire = live._acquire_windows_path_lease
    weak_lease = None
    release_calls = 0
    original_release = None

    def inject_weak_lease(path: Path, *args, **kwargs):
        nonlocal weak_lease, release_calls, original_release
        lease = original_acquire(path, *args, **kwargs)
        if Path(path) != target:
            return lease
        lease.rename_pinned = False
        weak_lease = lease
        original_release = lease.release

        def tracked_release() -> None:
            nonlocal release_calls
            release_calls += 1
            original_release()

        lease.release = tracked_release
        return lease

    monkeypatch.setattr(live, "_acquire_windows_path_lease", inject_weak_lease)
    caught = None
    retained = None
    try:
        try:
            if acquisition == "terminal_chain":
                retained = live._acquire_retained_path_leases(target, "directory")
            else:
                retained = live._acquire_windows_directory_lease(
                    target,
                    target.lstat(),
                )
        except live.LiveGateError as exc:
            caught = exc
        observed_releases = release_calls
    finally:
        if retained is not None:
            if isinstance(retained, live._RetainedPathLeases):
                if not retained.released:
                    retained.release()
            elif not retained._released:
                retained.release()
        elif weak_lease is not None and not weak_lease._released:
            original_release()

    assert caught is not None and "rename-pinned" in str(caught)
    assert observed_releases == 1


@requires_live_gate
def test_acl_identity_anchor_drift_is_rejected_before_dependent_use(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "anchor-parent"
    anchor = parent / "acl-anchor"
    child = anchor / "child"
    child.mkdir(parents=True)

    def fake_directory_lease(path: Path):
        info = path.lstat()
        attributes = 0x0010
        return live._WindowsPathLease(
            path=path,
            kind="directory",
            rename_pinned=True,
            device_id=info.st_dev,
            volume_serial=info.st_dev & 0xFFFFFFFF,
            file_id=info.st_ino,
            inspect_handle=lambda: (
                attributes,
                info.st_dev & 0xFFFFFFFF,
                info.st_ino,
                0,
            ),
            read_handle=None,
            close_handle=lambda: None,
        )

    anchor_info = anchor.lstat()
    retained = live._RetainedPathLeases()
    retained.adopt(fake_directory_lease(parent))
    retained.adopt(
        live._RetainedPathIdentity(
            path=anchor,
            kind="directory",
            device_id=anchor_info.st_dev,
            file_id=anchor_info.st_ino,
        )
    )
    retained.adopt(fake_directory_lease(child))
    retained.verify()
    displaced = parent / "displaced-anchor"
    anchor.rename(displaced)
    (anchor / "child").mkdir(parents=True)
    dependent_used = False
    try:
        with pytest.raises(live.LiveGateError, match="identity"):
            retained.verify()
    finally:
        retained.release()
    assert dependent_used is False


@requires_live_gate
def test_machine_profile_acl_anchor_and_writable_descendant_modes(
    tmp_path: Path,
) -> None:
    profile = Path.home()
    if profile not in tmp_path.parents:
        pytest.skip("temporary directory is not below the machine profile")
    retained = live._acquire_retained_path_leases(tmp_path, "directory")
    try:
        profile_entry = retained.lease_for(profile)
        writable_entry = retained.lease_for(tmp_path)
        assert isinstance(profile_entry, live._RetainedPathIdentity)
        assert isinstance(writable_entry, live._WindowsPathLease)
        assert writable_entry.rename_pinned is True
    finally:
        retained.release()


@requires_live_gate
def test_overlapping_path_views_share_handles_and_close_at_last_reverse_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    child = shared / "child"
    child.mkdir(parents=True)
    original_acquire = live._acquire_windows_path_lease
    releases: dict[Path, int] = {}

    def tracked_acquire(path: Path, *args, **kwargs):
        lease = original_acquire(path, *args, **kwargs)
        original_release = lease.release
        releases[Path(path)] = 0

        def tracked_release() -> None:
            releases[Path(path)] += 1
            original_release()

        lease.release = tracked_release
        return lease

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    registry = live._RetainedLeaseRegistry()
    first = live._acquire_retained_path_leases(
        shared,
        "directory",
        registry=registry,
    )
    second = live._acquire_retained_path_leases(
        child,
        "directory",
        registry=registry,
    )
    try:
        assert releases[shared] == 0
        second.release()
        assert releases[child] == 1
        assert releases[shared] == 0
        with pytest.raises(PermissionError):
            shared.rename(tmp_path / "shared-while-first-view-live")
    finally:
        if not second.released:
            second.release()
        first.release()
    assert releases and set(releases.values()) == {1}
    shared.rename(tmp_path / "shared-after-last-view")


@requires_live_gate
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_overlapping_partial_view_failure_decrements_only_its_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_type: type[BaseException],
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    failing = shared / "failing"
    failing.mkdir()
    original_acquire = live._acquire_windows_path_lease
    releases: dict[Path, int] = {}
    injected = error_type("overlap acquisition interrupted")

    def tracked_acquire(path: Path, *args, **kwargs):
        if Path(path) == failing:
            raise injected
        lease = original_acquire(path, *args, **kwargs)
        original_release = lease.release
        releases[Path(path)] = 0

        def tracked_release() -> None:
            releases[Path(path)] += 1
            original_release()

        lease.release = tracked_release
        return lease

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    registry = live._RetainedLeaseRegistry()
    first = live._acquire_retained_path_leases(
        shared,
        "directory",
        registry=registry,
    )
    try:
        with pytest.raises(error_type) as caught:
            live._acquire_retained_path_leases(
                failing,
                "directory",
                registry=registry,
            )
        assert caught.value is injected
        assert releases[shared] == 0
        first.verify()
    finally:
        first.release()
    assert releases and set(releases.values()) == {1}


@requires_live_gate
@pytest.mark.parametrize("failure_site", ["read_api_setup", "expected_stat"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_raw_windows_handle_closes_once_when_post_create_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_site: str,
    error_type: type[BaseException],
) -> None:
    import ctypes

    target = tmp_path / "raw-handle.json"
    target.write_bytes(b"{}")
    expected = target.lstat()
    injected = error_type(f"injected {failure_site} failure")
    close_calls = 0

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel32:
        def __init__(self):
            self.CreateFileW = FakeFunction(lambda *_args: 7331)
            self.GetFileInformationByHandle = FakeFunction(lambda *_args: 1)
            self.CloseHandle = FakeFunction(self._close)
            self.ReadFile = FakeFunction(lambda *_args: 1)
            self._set_pointer = FakeFunction(lambda *_args: 1)

        def _close(self, _handle):
            nonlocal close_calls
            close_calls += 1
            return 1

        @property
        def SetFilePointerEx(self):
            if failure_site == "read_api_setup":
                raise injected
            return self._set_pointer

    fake_kernel = FakeKernel32()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: fake_kernel)
    original_kind = live._filesystem_entry_kind

    def fail_expected_stat(info):
        if failure_site == "expected_stat" and info is expected:
            raise injected
        return original_kind(info)

    monkeypatch.setattr(live, "_filesystem_entry_kind", fail_expected_stat)

    with pytest.raises(error_type) as caught:
        live._acquire_windows_path_lease(target, expected, "file")

    assert caught.value is injected
    assert close_calls == 1


@requires_live_gate
def test_child_tree_adoption_failure_releases_unadopted_lease_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "capture-root"
    root.mkdir()
    child = root / "child.json"
    child.write_bytes(b"{}")
    original_acquire = live._acquire_windows_path_lease
    original_add = live._ProtectedArtifactTree.add_lease
    acquired: list[tuple[object, list[int], object]] = []

    def tracked_acquire(*args, **kwargs):
        lease = original_acquire(*args, **kwargs)
        calls = [0]
        original_release = lease.release

        def tracked_release() -> None:
            calls[0] += 1
            original_release()

        lease.release = tracked_release
        acquired.append((lease, calls, original_release))
        return lease

    def reject_child_adoption(tree, relative: str, lease) -> None:
        if relative == "child.json":
            raise KeyboardInterrupt("child adoption interrupted")
        original_add(tree, relative, lease)

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(live._ProtectedArtifactTree, "add_lease", reject_child_adoption)

    with pytest.raises(KeyboardInterrupt, match="adoption"):
        live._scan_artifact_tree_nonfollowing(root)

    observed = [calls[0] for _lease, calls, _release in acquired]
    for lease, calls, original_release in acquired:
        if calls[0] == 0:
            original_release()
    assert observed and set(observed) == {1}


@requires_live_gate
def test_consumer_root_capture_failure_releases_every_retained_lease_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    original_acquire = live._acquire_windows_path_lease
    acquired: list[tuple[object, list[int], object]] = []

    def tracked_acquire(*args, **kwargs):
        lease = original_acquire(*args, **kwargs)
        calls = [0]
        original_release = lease.release

        def tracked_release() -> None:
            calls[0] += 1
            original_release()

        lease.release = tracked_release
        acquired.append((lease, calls, original_release))
        return lease

    injected = KeyboardInterrupt("consumer root capture interrupted")
    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(
        live,
        "_capture_protected_artifact_tree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(injected),
    )

    with pytest.raises(KeyboardInterrupt) as caught:
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    observed = [calls[0] for _lease, calls, _release in acquired]
    for lease, calls, original_release in acquired:
        if calls[0] == 0:
            original_release()
    assert caught.value is injected
    assert observed and set(observed) == {1}


@requires_live_gate
def test_producer_rejects_active_child_reparse_before_any_external_write(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    outside.mkdir()
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    try:
        _directory_symlink_or_skip(artifact / "operations", outside)
        with pytest.raises((live.LiveGateError, live.OwnershipAmbiguous)):
            live._atomic_write_bytes(
                artifact / "operations" / "001-rhino_ping-arguments.json",
                b"{}",
                root_claim=claim,
            )
        assert list(outside.iterdir()) == []
    finally:
        claim.release()


@requires_live_gate
@pytest.mark.parametrize(
    "replacement_payload",
    [b'{"attacker":true}', b"{}"],
    ids=["different-payload", "same-payload"],
)
def test_atomic_write_rejects_same_kind_target_replacement_before_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement_payload: bytes,
) -> None:
    artifact = tmp_path / "artifacts"
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    target = artifact / "operations" / "001-rhino_ping-arguments.json"
    displaced = artifact / "displaced-arguments.json"
    original_replace = live.os.replace
    swapped = False

    def replace_then_swap(source: Path, destination: Path) -> None:
        nonlocal swapped
        original_replace(source, destination)
        if Path(destination) == target and not swapped:
            target.rename(displaced)
            target.write_bytes(replacement_payload)
            swapped = True

    monkeypatch.setattr(live.os, "replace", replace_then_swap)
    result = live._new_result("rhino", RUN_ID, live._utc_now())
    failure = None
    completed = False
    try:
        try:
            captured = live._atomic_write_bytes(target, b"{}", root_claim=claim)
            live._register_artifact(
                result,
                captured,
                artifact,
                "operation_arguments",
            )
            completed = True
        except (live.LiveGateError, live.OwnershipAmbiguous) as exc:
            failure = exc
        assert swapped is True
    finally:
        claim.release()
    assert failure is not None
    assert completed is False
    assert result.artifacts == []


@requires_live_gate
@pytest.mark.parametrize("failure_site", ["directory", "file"])
def test_producer_path_capture_preserves_nonexception_baseexception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_site: str,
) -> None:
    artifact = tmp_path / "artifacts"
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    target = artifact / ("operations" if failure_site == "directory" else "owned.json")
    injected = _FinalPairBaseInterrupt(f"{failure_site} capture interrupted")
    if failure_site == "directory":
        target.mkdir()
        original = live._acquire_windows_directory_lease

        def interrupt(path: Path, *args, **kwargs):
            if Path(path) == target:
                raise injected
            return original(path, *args, **kwargs)

        monkeypatch.setattr(live, "_acquire_windows_directory_lease", interrupt)
    else:
        target.write_bytes(b"{}")
        original = live._acquire_windows_path_lease

        def interrupt(path: Path, *args, **kwargs):
            if Path(path) == target:
                raise injected
            return original(path, *args, **kwargs)

        monkeypatch.setattr(live, "_acquire_windows_path_lease", interrupt)

    try:
        with pytest.raises(_FinalPairBaseInterrupt) as caught:
            if failure_site == "directory":
                claim.ensure_directory(target)
            else:
                claim.capture_file(target)
    finally:
        claim.release()

    assert caught.value is injected


@requires_live_gate
@pytest.mark.parametrize("error_type", [OSError, _FinalPairBaseInterrupt])
def test_atomic_write_fdopen_failure_closes_raw_descriptor_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_type: type[BaseException],
) -> None:
    artifact = tmp_path / "artifacts"
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    target = artifact / "operations" / "owned.json"
    original_mkstemp = live.tempfile.mkstemp
    original_close = live.os.close
    descriptors: list[int] = []
    close_calls = 0
    injected = error_type("fdopen ownership transfer interrupted")

    def tracked_mkstemp(*args, **kwargs):
        descriptor, path = original_mkstemp(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor, path

    def tracked_close(descriptor: int) -> None:
        nonlocal close_calls
        close_calls += 1
        original_close(descriptor)

    monkeypatch.setattr(live.tempfile, "mkstemp", tracked_mkstemp)
    monkeypatch.setattr(live.os, "close", tracked_close)
    monkeypatch.setattr(
        live.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(injected),
    )

    try:
        with pytest.raises(error_type) as caught:
            live._atomic_write_bytes(target, b"{}", root_claim=claim)
        observed_close_calls = close_calls
    finally:
        for descriptor in descriptors:
            try:
                original_close(descriptor)
            except OSError:
                pass
        claim.release()

    assert caught.value is injected
    assert descriptors
    assert observed_close_calls == 1


@requires_live_gate
def test_producer_never_rereads_owned_artifacts_by_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_read_bytes = Path.read_bytes

    def reject_owned_path_read(path: Path) -> bytes:
        if path == harness.artifact or harness.artifact in path.parents:
            raise AssertionError(f"producer reread owned artifact by path: {path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_owned_path_read)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True


@requires_live_gate
def test_producer_holds_parent_ancestor_chain_before_missing_leaf_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ancestor = tmp_path / "claim-ancestor"
    parent = ancestor / "claim-parent"
    parent.mkdir(parents=True)
    artifact = parent / "artifacts"
    displaced = tmp_path / "displaced-claim-ancestor"
    redirected = tmp_path / "redirected-claim-ancestor"
    (redirected / "claim-parent").mkdir(parents=True)
    original_mkdir = Path.mkdir
    blocked = False
    swapped = False

    def race_before_leaf_creation(path: Path, *args, **kwargs) -> None:
        nonlocal blocked, swapped
        if path == artifact and not blocked and not swapped:
            try:
                ancestor.rename(displaced)
            except PermissionError:
                blocked = True
            else:
                _directory_symlink_or_skip(ancestor, redirected)
                swapped = True
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", race_before_leaf_creation)

    claim = live._claim_artifact_directory(artifact, RUN_ID)
    try:
        assert blocked is True
        assert swapped is False
        assert claim.path == artifact
    finally:
        claim.release()


@requires_live_gate
def test_rhino_executable_ancestor_chain_is_held_through_process_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    install = tmp_path / "install"
    system = install / "System"
    system.mkdir(parents=True)
    rhino_exe = system / "Rhino.exe"
    rhino_exe.write_bytes(b"fake-rhino")
    redirected = tmp_path / "redirected-install"
    (redirected / "System").mkdir(parents=True)
    (redirected / "System" / "Rhino.exe").write_bytes(b"external-rhino")
    displaced = tmp_path / "displaced-install"
    original_start = live._start_owned_rhino
    blocked = False
    swapped = False

    def race_at_process_creation(*, rhino_exe: Path, launch):
        nonlocal blocked, swapped
        try:
            install.rename(displaced)
        except PermissionError:
            blocked = True
        else:
            _directory_symlink_or_skip(install, redirected)
            swapped = True
        return original_start(rhino_exe=rhino_exe, launch=launch)

    monkeypatch.setattr(live, "_start_owned_rhino", race_at_process_creation)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True
    assert blocked is True
    assert swapped is False
    install.rename(tmp_path / "install-after-release")


@requires_live_gate
def test_consumer_holds_ancestor_chain_before_root_handle_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    container = tmp_path / "consumer-container"
    container.mkdir()
    harness = _install_fake_scenario(monkeypatch, container, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    redirected = tmp_path / "redirected-consumer-container"
    shutil.copytree(container, redirected)
    displaced = tmp_path / "displaced-consumer-container"
    original_acquire = live._acquire_windows_path_lease
    blocked = False
    swapped = False

    def race_before_root_acquire(path: Path, expected, kind):
        nonlocal blocked, swapped
        if Path(path) == harness.artifact and not blocked and not swapped:
            try:
                container.rename(displaced)
            except PermissionError:
                blocked = True
            else:
                _directory_symlink_or_skip(container, redirected)
                swapped = True
        return original_acquire(path, expected, kind)

    monkeypatch.setattr(live, "_acquire_windows_path_lease", race_before_root_acquire)

    evidence = live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    assert evidence["success"] is True
    assert blocked is True
    assert swapped is False


@requires_live_gate
def test_artifact_claim_rejects_reparse_in_any_existing_ancestor(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    (target / "nested").mkdir(parents=True)
    linked = tmp_path / "linked"
    _directory_symlink_or_skip(linked, target)
    artifact = linked / "nested" / "artifacts"

    with pytest.raises(live.PreOwnershipBlocked, match="reparse"):
        live._claim_artifact_directory(artifact, RUN_ID)

    assert not (target / "nested" / "artifacts").exists()


@requires_live_gate
def test_run_rejects_relative_rhino_path_before_resolution_or_artifact_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(live.PreOwnershipBlocked, match="absolute"):
        live.run_live_scenario(
            scenario="rhino",
            rhino_exe=Path(harness.rhino_exe.name),
            artifact_dir=harness.artifact,
        )

    assert not harness.artifact.exists()


@requires_live_gate
def test_run_checks_raw_rhino_absoluteness_before_expanduser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw = Path("~") / "Rhino.exe"
    original_expanduser = Path.expanduser

    def reject_early_expansion(path: Path) -> Path:
        if path == raw:
            raise AssertionError("relative Rhino path was expanded before rejection")
        return original_expanduser(path)

    monkeypatch.setattr(Path, "expanduser", reject_early_expansion)

    with pytest.raises(live.PreOwnershipBlocked, match="absolute"):
        live.run_live_scenario(
            scenario="rhino",
            rhino_exe=raw,
            artifact_dir=tmp_path / "artifacts",
        )


@requires_live_gate
def test_claim_checks_raw_artifact_absoluteness_before_expanduser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = Path("~") / "artifacts"
    original_expanduser = Path.expanduser

    def reject_early_expansion(path: Path) -> Path:
        if path == raw:
            raise AssertionError("relative artifact path was expanded before rejection")
        return original_expanduser(path)

    monkeypatch.setattr(Path, "expanduser", reject_early_expansion)

    with pytest.raises(live.PreOwnershipBlocked, match="absolute"):
        live._claim_artifact_directory(raw, RUN_ID)


@requires_live_gate
def test_consumer_checks_raw_artifact_absoluteness_before_expanduser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = Path("~") / "artifacts"
    original_expanduser = Path.expanduser

    def reject_early_expansion(path: Path) -> Path:
        if path == raw:
            raise AssertionError("relative artifact path was expanded before rejection")
        return original_expanduser(path)

    monkeypatch.setattr(Path, "expanduser", reject_early_expansion)

    with pytest.raises(live.LiveGateError, match="absolute"):
        live._validate_scenario_artifacts(raw, scenario="rhino")


@requires_live_gate
def test_run_rejects_reparse_in_rhino_executable_ancestor_before_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    target = tmp_path / "installed"
    (target / "System").mkdir(parents=True)
    (target / "System" / "Rhino.exe").write_bytes(b"fake")
    linked = tmp_path / "linked-install"
    _directory_symlink_or_skip(linked, target)

    with pytest.raises(live.PreOwnershipBlocked, match="reparse"):
        live.run_live_scenario(
            scenario="rhino",
            rhino_exe=linked / "System" / "Rhino.exe",
            artifact_dir=harness.artifact,
        )

    assert not harness.artifact.exists()


@requires_live_gate
@pytest.mark.parametrize("preexisting", [False, True])
@pytest.mark.parametrize("failure_site", ["write", "fsync", "close"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_artifact_claim_failure_removes_partial_marker_and_only_created_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    preexisting: bool,
    failure_site: str,
    error_type: type[BaseException],
) -> None:
    artifact = tmp_path / "artifacts"
    if preexisting:
        artifact.mkdir()
    original_close = live.os.close
    close_calls = 0

    def fail(*_args, **_kwargs):
        raise error_type(f"claim {failure_site} interrupted")

    def close_then_fail(descriptor: int) -> None:
        nonlocal close_calls
        close_calls += 1
        original_close(descriptor)
        fail()

    with monkeypatch.context() as scoped:
        scoped.setattr(
            live.os,
            failure_site,
            close_then_fail if failure_site == "close" else fail,
        )
        with pytest.raises(error_type, match=failure_site):
            live._claim_artifact_directory(artifact, RUN_ID)

    if failure_site == "close":
        assert close_calls == 1
    assert not (artifact / live.OWNERSHIP_MARKER).exists()
    if preexisting:
        assert artifact.is_dir()
        assert list(artifact.iterdir()) == []
    else:
        assert not artifact.exists()


@requires_live_gate
@pytest.mark.parametrize("rmdir_outcome", ["success", "exception", "baseexception"])
def test_created_claim_failure_pins_parent_between_leaf_release_and_rmdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rmdir_outcome: str,
) -> None:
    container = tmp_path / "claim-container"
    parent = container / "claim-parent"
    parent.mkdir(parents=True)
    artifact = parent / "artifacts"
    displaced_parent = container / "displaced-claim-parent"
    external_parent = tmp_path / "external-claim-parent"
    external_artifact = external_parent / "artifacts"
    external_artifact.mkdir(parents=True)
    original_acquire = live._acquire_windows_path_lease
    original_scandir = live.os.scandir
    original_rmdir = Path.rmdir
    releases: list[tuple[Path, list[int]]] = []
    raw_scans = 0
    blocked = False
    swapped = False
    rmdir_calls = 0
    injected = RuntimeError("claim failed after marker capture")

    def tracked_acquire(path: Path, *args, **kwargs):
        lease = original_acquire(path, *args, **kwargs)
        calls = [0]
        original_release = lease.release

        def tracked_release() -> None:
            calls[0] += 1
            original_release()

        lease.release = tracked_release
        releases.append((Path(path), calls))
        return lease

    def fail_final_inventory(path: Path):
        nonlocal raw_scans
        if Path(path) == artifact:
            raw_scans += 1
            if raw_scans == 2:
                raise injected
        return original_scandir(path)

    def race_at_rmdir(path: Path) -> None:
        nonlocal blocked, swapped, rmdir_calls
        if Path(path) != artifact:
            return original_rmdir(path)
        rmdir_calls += 1
        leaf_releases = [calls[0] for lease_path, calls in releases if lease_path == artifact]
        parent_releases = [calls[0] for lease_path, calls in releases if lease_path == parent]
        assert leaf_releases == [1], "created leaf handle was not released before rmdir"
        assert parent_releases == [0], "parent handle was released before leaf rmdir"
        try:
            parent.rename(displaced_parent)
        except PermissionError:
            blocked = True
        else:
            _directory_symlink_or_skip(parent, external_parent)
            swapped = True
        if rmdir_outcome == "exception":
            raise OSError("created leaf rmdir failed")
        if rmdir_outcome == "baseexception":
            raise _FinalPairBaseInterrupt("created leaf rmdir interrupted")
        return original_rmdir(path)

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(live.os, "scandir", fail_final_inventory)
    monkeypatch.setattr(Path, "rmdir", race_at_rmdir)

    with pytest.raises(RuntimeError) as caught:
        live._claim_artifact_directory(artifact, RUN_ID)

    assert caught.value is injected
    assert raw_scans == 2
    assert rmdir_calls == 1
    assert blocked is True
    assert swapped is False
    assert external_artifact.is_dir(), "claim cleanup removed an external directory"
    assert releases and {calls[0] for _path, calls in releases} == {1}


@requires_live_gate
def test_ownership_marker_capture_rejects_same_payload_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts"
    marker = artifact / live.OWNERSHIP_MARKER
    displaced = tmp_path / "displaced-marker"
    payload = live._canonical_json_bytes(
        {
            "process_id": os.getpid(),
            "run_id": RUN_ID,
            "schema_version": live.SCHEMA_VERSION,
        }
    )
    original_close = live.os.close
    swapped = False

    def close_then_swap(descriptor: int) -> None:
        nonlocal swapped
        original_close(descriptor)
        if not swapped:
            marker.rename(displaced)
            marker.write_bytes(payload)
            swapped = True

    monkeypatch.setattr(live.os, "close", close_then_swap)
    claim = None
    failure = None
    try:
        try:
            claim = live._claim_artifact_directory(artifact, RUN_ID)
        except (live.LiveGateError, live.OwnershipAmbiguous) as exc:
            failure = exc
    finally:
        if claim is not None:
            claim.release()

    assert swapped is True
    assert failure is not None


@requires_live_gate
@pytest.mark.parametrize("failure_site", ["registration", "hash"])
def test_post_claim_marker_failure_emits_canonical_failure_without_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_site: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    failed = False
    original_register = live._register_artifact
    original_hash = live._sha256_bytes

    if failure_site == "registration":
        def fail_once_register(result, path, root, kind):
            nonlocal failed
            if kind == "ownership_marker" and not failed:
                failed = True
                raise OSError("one-shot marker registration failure")
            return original_register(result, path, root, kind)

        monkeypatch.setattr(live, "_register_artifact", fail_once_register)
    else:
        def fail_once_hash(payload: bytes):
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("one-shot marker hash failure")
            return original_hash(payload)

        monkeypatch.setattr(live, "_sha256_bytes", fail_once_hash)

    try:
        result = live.run_live_scenario(
            scenario="rhino",
            rhino_exe=harness.rhino_exe,
            artifact_dir=harness.artifact,
        )
    except Exception as exc:
        pytest.fail(
            f"{EXPECTED_RED}:POST_CLAIM_MARKER:{failure_site} "
            f"failure escaped final evidence state machine: {exc!r}"
        )

    assert failed is True
    assert harness.trace == [], (
        f"{EXPECTED_RED}:POST_CLAIM_MARKER:{failure_site} host launch occurred"
    )
    assert result.success is False
    assert result.failure_label in live.FAILURE_LABELS
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["success"] is False
    assert evidence["failure_label"] == result.failure_label
    assert any(
        item["kind"] == "ownership_marker"
        and item["relative_path"] == live.OWNERSHIP_MARKER
        for item in evidence["artifacts"]
    )
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(records) == 1
    assert records[0]["type"] == "scenario_result"
    assert records[0]["success"] is False


@requires_live_gate
def test_runtime_serial_and_point_parsers_require_one_exact_line() -> None:
    assert live._parse_runtime_serial("ROOK_DOC_RUNTIME_SERIAL=17\n") == 17
    assert live._parse_point_id(f"ROOK_POINT_ID={POINT_ID}\n") == POINT_ID
    for output in (
        "",
        "ROOK_DOC_RUNTIME_SERIAL=0",
        "ROOK_DOC_RUNTIME_SERIAL=-1",
        "x ROOK_DOC_RUNTIME_SERIAL=2",
        "ROOK_DOC_RUNTIME_SERIAL=2\nROOK_DOC_RUNTIME_SERIAL=3",
    ):
        with pytest.raises(live.LiveGateError):
            live._parse_runtime_serial(output)
    for output in (
        "",
        "ROOK_POINT_ID=not-a-guid",
        f"ROOK_POINT_ID={POINT_ID}\nROOK_POINT_ID={POINT_ID}",
    ):
        with pytest.raises(live.LiveGateError):
            live._parse_point_id(output)


@dataclass
class _Record:
    pid: int
    port: int
    path: Path
    raw: dict[str, Any]
    host: str = "127.0.0.1"


class _Discovery:
    def __init__(self, record: _Record):
        self.record = record
        self.discovery_dir = record.path.parent
        self.removed = False
        self.read_count = 0

    def read_owned_record(self, pid: int) -> _Record:
        self.read_count += 1
        if self.removed or pid != self.record.pid:
            raise RuntimeError("discovery missing")
        return self.record


class _AdapterProcess:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode: int | None = None

    def poll(self):
        return self.returncode


def _install_bound_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dispatch,
    request: pytest.FixtureRequest,
):
    process = _AdapterProcess(9001)
    started = SimpleNamespace(process=process, pid=process.pid, started_wall=100.0)
    record_path = tmp_path / "instance-9001-native.json"
    record_bytes = b'{"pluginType":"native","port":19001,"processId":9001}'
    record_path.write_bytes(record_bytes)
    record = _Record(
        9001,
        19001,
        record_path,
        {"processId": 9001, "port": 19001, "pluginType": "native"},
    )
    discovery = _Discovery(record)
    process_token = live._owned_process_start_token(started)
    discovery_leases = live._acquire_retained_path_leases(
        record_path.parent,
        "directory",
    )
    request.addfinalizer(
        lambda: (
            discovery_leases.release()
            if not discovery_leases.released
            else None
        )
    )
    monkeypatch.setattr(live, "_new_owned_discovery", lambda: discovery)
    monkeypatch.setattr(live, "_dispatch_installed_tool", dispatch)
    adapter = live.BoundInstalledToolAdapter(
        port=19001,
        process_id=9001,
        started=started,
        record=record,
        process_start_token=process_token,
        record_bytes=record_bytes,
        record_device_id=record_path.stat().st_dev,
        record_file_id=record_path.stat().st_ino,
        discovery_leases=discovery_leases,
    )
    return SimpleNamespace(
        adapter=adapter,
        process=process,
        started=started,
        record=record,
        record_path=record_path,
        record_bytes=record_bytes,
        discovery=discovery,
        discovery_leases=discovery_leases,
        process_token=process_token,
    )


@requires_live_gate
def test_bound_adapter_constructor_reuses_captured_bytes_without_path_reread(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    process = _AdapterProcess(9001)
    started = SimpleNamespace(process=process, pid=process.pid, started_wall=100.0)
    record_path = tmp_path / "instance-9001-native.json"
    record_bytes = b'{"pluginType":"native","port":19001,"processId":9001}'
    record_path.write_bytes(record_bytes)
    record = _Record(
        9001,
        19001,
        record_path,
        {"pluginType": "native", "port": 19001, "processId": 9001},
    )
    original_read = Path.read_bytes

    def reject_record_reread(path: Path) -> bytes:
        if path == record_path:
            raise AssertionError("accepted discovery bytes were reread before binding")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", reject_record_reread)

    discovery_leases = live._acquire_retained_path_leases(
        record_path.parent,
        "directory",
    )
    request.addfinalizer(
        lambda: (
            discovery_leases.release()
            if not discovery_leases.released
            else None
        )
    )

    adapter = live.BoundInstalledToolAdapter(
        port=record.port,
        process_id=record.pid,
        started=started,
        record=record,
        process_start_token=live._owned_process_start_token(started),
        record_bytes=record_bytes,
        record_device_id=record_path.stat().st_dev,
        record_file_id=record_path.stat().st_ino,
        discovery_leases=discovery_leases,
    )

    assert adapter._record_bytes is record_bytes


@requires_live_gate
def test_bound_adapter_rechecks_pid_port_preserves_envelope_and_injects_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    seen: list[tuple[str, dict[str, Any], dict[str, int | None]]] = []
    envelope = {"success": True, "data": {"pong": True}}

    async def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from rook.bridge import get_rhino_request_context

        seen.append((name, dict(arguments), get_rhino_request_context()))
        return envelope

    harness = _install_bound_adapter(monkeypatch, tmp_path, dispatch, request)
    result = asyncio.run(harness.adapter.call("rhino_ping", {}))
    assert result is envelope
    assert harness.discovery.read_count == 2
    assert seen == [
        (
            "rhino_ping",
            {"port": 19001},
            {"port": 19001, "process_id": 9001, "document_serial_number": None},
        )
    ]
    with pytest.raises(live.LiveGateError, match="allowlist"):
        asyncio.run(harness.adapter.call("gh_execute_intent", {}))
    with pytest.raises(live.LiveGateError, match="argument"):
        asyncio.run(harness.adapter.call("rhino_ping", {"port": 9}))
    harness.discovery.record = _Record(
        9001,
        19002,
        harness.record_path,
        {"processId": 9001, "port": 19002},
    )
    with pytest.raises(live.OwnershipAmbiguous):
        asyncio.run(harness.adapter.call("rhino_ping", {}))


@requires_live_gate
@pytest.mark.parametrize(
    "drift_case",
    [
        "started_process_replaced",
        "process_exited_before",
        "process_exited_after",
        "start_token_changed",
        "record_path_replaced",
        "record_bytes_changed",
    ],
)
def test_bound_adapter_rejects_process_or_discovery_continuity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift_case: str,
    request: pytest.FixtureRequest,
) -> None:
    dispatched: list[str] = []
    holder: dict[str, Any] = {}

    async def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        dispatched.append(name)
        if drift_case == "process_exited_after":
            holder["harness"].process.returncode = 0
        return _success({"pong": True})

    harness = _install_bound_adapter(monkeypatch, tmp_path, dispatch, request)
    holder["harness"] = harness
    if drift_case == "started_process_replaced":
        harness.started.process = _AdapterProcess(harness.process.pid)
    elif drift_case == "process_exited_before":
        harness.process.returncode = 0
    elif drift_case == "start_token_changed":
        harness.started.started_wall = 101.0
    elif drift_case == "record_path_replaced":
        replacement_path = tmp_path / "replacement-instance.json"
        replacement_path.write_bytes(harness.record_bytes)
        harness.discovery.record = _Record(
            9001,
            19001,
            replacement_path,
            dict(harness.record.raw),
        )
    elif drift_case == "record_bytes_changed":
        harness.record_path.write_bytes(b'{"processId":9001,"port":19001}')

    with pytest.raises(live.OwnershipAmbiguous):
        asyncio.run(harness.adapter.call("rhino_ping", {}))

    assert dispatched == (["rhino_ping"] if drift_case == "process_exited_after" else [])


@requires_live_gate
@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("rhino_delete", {"ids": [SPHERE_ID]}),
        ("gh_undo", {}),
    ],
)
def test_bound_adapter_rechecks_process_after_restoration_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    arguments: dict[str, Any],
    request: pytest.FixtureRequest,
) -> None:
    holder: dict[str, Any] = {}

    async def exit_after_dispatch(
        tool_name: str, tool_arguments: dict[str, Any]
    ) -> dict[str, Any]:
        holder["harness"].process.returncode = 0
        return _success({})

    harness = _install_bound_adapter(
        monkeypatch,
        tmp_path,
        exit_after_dispatch,
        request,
    )
    holder["harness"] = harness

    with pytest.raises(live.OwnershipAmbiguous):
        asyncio.run(harness.adapter.call(name, arguments))


class _Store:
    def __init__(self, *, events: list[dict[str, Any]] | None = None):
        self.events = list(events or [])
        self.token = "a" * 32

    def get_containment_denials_snapshot(self) -> dict[str, Any]:
        return {
            "process_id": os.getpid(),
            "process_start_token": self.token,
            "events": copy.deepcopy(self.events),
        }


class _TelemetryDict(dict):
    pass


class _TelemetryList(list):
    pass


class _TelemetryInt(int):
    pass


class _TelemetryToken(str):
    pass


@requires_live_gate
@pytest.mark.parametrize(
    "drift",
    ["mapping_subclass", "pid_subclass", "token_subclass", "events_subclass", "oversized_ring"],
)
def test_runtime_telemetry_snapshot_requires_exact_contract_types(
    drift: str,
) -> None:
    snapshot: dict[str, Any] = {
        "process_id": os.getpid(),
        "process_start_token": "a" * 32,
        "events": [],
    }
    candidate: Any = snapshot
    if drift == "mapping_subclass":
        candidate = _TelemetryDict(snapshot)
    elif drift == "pid_subclass":
        snapshot["process_id"] = _TelemetryInt(os.getpid())
    elif drift == "token_subclass":
        snapshot["process_start_token"] = _TelemetryToken("a" * 32)
    elif drift == "events_subclass":
        snapshot["events"] = _TelemetryList()
    else:
        snapshot["events"] = [{} for _ in range(51)]

    with pytest.raises(live.LiveGateError, match="telemetry"):
        live._validate_snapshot(candidate)


@requires_live_gate
def test_final_telemetry_events_require_an_exact_list() -> None:
    telemetry = {
        "process_id": os.getpid(),
        "process_start_token": "a" * 32,
        "before_sha256": "b" * 64,
        "after_sha256": "c" * 64,
        "delta_count": 0,
        "events_added": _TelemetryList(),
    }

    with pytest.raises(live.LiveGateError, match="telemetry"):
        live._validate_telemetry_result(telemetry)


class _Process:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self.killed = False
        self.closed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.closed = True
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True
        self.returncode = -9


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


class _RhinoAdapter:
    def __init__(self, scratch_path: Path):
        self.scratch_path = scratch_path
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.serial = 41
        self.saved = False
        self.objects: dict[str, dict[str, Any]] = {}
        self.modified = False
        self.sphere_geometry_overrides: dict[str, Any] = {}

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "rhino_ping":
            return _success({"pong": True})
        if name == "rhino_execute" and arguments == {"code": live.RUNTIME_SERIAL_CODE}:
            return _success({"output": f"ROOK_DOC_RUNTIME_SERIAL={self.serial}\n"})
        if name == "rhino_document":
            return _success(
                {
                    "name": self.scratch_path.name if self.saved else "Untitled",
                    "path": str(self.scratch_path) if self.saved else "",
                    "objectCount": len(self.objects),
                    "modified": self.modified,
                }
            )
        if name == "rhino_objects":
            return _success({"objects": list(self.objects.values()), "count": len(self.objects)})
        if name == "rhino_document_ops":
            assert arguments == {"action": "save", "path": str(self.scratch_path)}
            self.saved = True
            self.modified = False
            self.scratch_path.write_bytes(b"fake-3dm")
            return _success({"saved": True, "path": str(self.scratch_path)})
        if name == "rhino_create":
            expected = live._rhino_sphere_arguments(RUN_ID)
            assert arguments == expected
            self.objects[SPHERE_ID] = {
                "id": SPHERE_ID,
                "name": expected["name"],
                "type": "Brep",
            }
            self.modified = True
            return _success({"id": SPHERE_ID})
        if name == "rhino_execute":
            assert arguments == {"code": live._rhino_point_script(RUN_ID)}
            self.objects[POINT_ID] = {
                "id": POINT_ID,
                "name": f"RookContainmentPoint-{RUN_ID}",
                "type": "Point",
            }
            self.modified = True
            return _success({"output": f"ROOK_POINT_ID={POINT_ID}\n"})
        if name == "rhino_geometry":
            object_id = arguments["id"]
            if object_id == SPHERE_ID:
                projection = {
                    "id": SPHERE_ID,
                    "name": f"RookContainmentSphere-{RUN_ID}",
                    "type": "Brep",
                    "bbox": {"min": [-4, -4, -4], "max": [4, 4, 4]},
                    "geometry": {
                        "type": "Brep",
                        "faceCount": 1,
                        "edgeCount": 1,
                        "vertexCount": 2,
                        "isSolid": True,
                        "isManifold": True,
                        "area": SPHERE_AREA,
                        "volume": SPHERE_VOLUME,
                    },
                }
                projection["geometry"].update(self.sphere_geometry_overrides)
                return _success(projection)
            return _success(
                {
                    "id": POINT_ID,
                    "name": f"RookContainmentPoint-{RUN_ID}",
                    "type": "Point",
                    "bbox": {"min": [10, 0, 0], "max": [10, 0, 0]},
                    "geometry": {"type": "Point", "location": [10, 0, 0]},
                }
            )
        if name == "rhino_delete":
            assert arguments["ids"] and set(arguments["ids"]).issubset({SPHERE_ID, POINT_ID})
            for object_id in arguments["ids"]:
                self.objects.pop(object_id, None)
            self.modified = True
            return _success({"deleted": 2})
        raise AssertionError((name, arguments))


class _GrasshopperAdapter:
    def __init__(self, scratch_path: Path):
        self.scratch_path = scratch_path
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.bootstrapped = False
        self.opened = False
        self.edited = False
        self.undo_count = 0
        self.open_status_overrides: dict[str, Any] = {}

    def _status(self) -> dict[str, Any]:
        if not self.bootstrapped:
            raw = {
                "available": False,
                "assemblyVersion": "",
                "hasActiveCanvas": False,
                "hasActiveDocument": False,
                "documentId": None,
                "documentPath": "",
                "objectCount": 0,
                "readyForEdit": False,
                "warnings": ["Grasshopper assembly is not loaded."],
                "solverEnabled": None,
                "solverStateKnown": False,
                "solutionState": None,
            }
        else:
            raw = {
                "available": True,
                "assemblyVersion": "8.0",
                "hasActiveCanvas": True,
                "hasActiveDocument": True,
                "documentId": GH_DOCUMENT_ID if self.opened else GH_BOOTSTRAP_DOCUMENT_ID,
                "documentPath": str(self.scratch_path) if self.opened else "",
                "objectCount": 2 if self.edited else 0,
                "readyForEdit": True,
                "warnings": [],
                "solverEnabled": True,
                "solverStateKnown": True,
                "solutionState": "PostProcess",
            }
            if self.opened and not self.edited:
                raw.update(self.open_status_overrides)
        normalized = normalize_gh_status_result(_success(raw))
        assert normalized["success"] is True and isinstance(normalized["data"], dict)
        return normalized["data"]

    def _snapshot(self) -> dict[str, Any]:
        if not self.edited:
            return {
                "version": "1.0.0",
                "document": {"name": self.scratch_path.name, "path": str(self.scratch_path)},
                "epoch": 7 + self.undo_count,
                "components": [],
                "flows": [],
                "diagnostics": {"total": 0, "errors": 0, "warnings": 0, "error_ids": None, "warning_ids": None},
            }
        return {
            "version": "1.0.0",
            "document": {"name": self.scratch_path.name, "path": str(self.scratch_path)},
            "epoch": 8,
            "components": [
                {
                    "id": "C1",
                    "type": "NumberSlider",
                    "nick": f"RookContainmentRadius-{RUN_ID}",
                    "pos": [100, 100],
                    "is_param": True,
                    "value": {"type": "slider", "val": 4, "min": 1, "max": 9},
                },
                {
                    "id": "C2",
                    "type": "Component",
                    "name": "Sphere",
                    "componentGuid": live.SPHERE_COMPONENT_GUID,
                    "pos": [400, 100],
                    "inputs": [{"idx": 0, "name": "Base"}, {"idx": 1, "name": "Radius", "sources": 1}],
                    "outputs": [
                        {
                            "idx": 0,
                            "name": "Sphere",
                            "type": "Sphere",
                            "data": {
                                "structure": "single",
                                "count": 1,
                                "preview": ["Sphere"],
                            },
                        }
                    ],
                },
            ],
            "flows": ["C1.O0>C2.I1"],
            "diagnostics": {"total": 2, "errors": 0, "warnings": 0, "error_ids": None, "warning_ids": None},
        }

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "rhino_ping":
            return _success({"pong": True})
        if name == "rhino_document":
            return _success({"name": "Untitled", "path": "", "objectCount": 0, "modified": False})
        if name == "gh_status":
            return _success(self._status())
        if name == "rhino_command":
            assert arguments == {"command": "_Grasshopper", "echo": False}
            self.bootstrapped = True
            return _success({"executed": True})
        if name == "gh_document_open":
            assert arguments == {"path": str(self.scratch_path)}
            assert self.scratch_path.read_bytes() == live._fixture_resource_path().read_bytes()
            self.opened = True
            return _success({"opened": True, "path": str(self.scratch_path), "fileName": self.scratch_path.name, "objectCount": 0})
        if name == "gh_snapshot":
            return _success(self._snapshot())
        if name == "gh_errors":
            return _success({"totalComponents": 2 if self.edited else 0, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []})
        if name == "gh_library":
            assert arguments == {"search": "Sphere", "exact": True}
            return _success({"count": 1, "components": [{"name": "Sphere", "guid": live.SPHERE_COMPONENT_GUID}]})
        if name == "gh_edit":
            assert arguments == live._grasshopper_edit_arguments(RUN_ID, 7)
            self.edited = True
            result = self._snapshot()
            result["edit_summary"] = {
                "created": 2,
                "connected": 1,
                "solve_scheduled": True,
                "solver_locked": False,
                "solver_state_known": True,
                "verification_deferred": True,
                "errors": None,
            }
            return _success(result)
        if name == "gh_undo":
            self.undo_count += 1
            self.edited = False
            return _success({"message": "Undo successful", "epoch": 8 + self.undo_count, "snapshot": self._snapshot()})
        raise AssertionError((name, arguments))


@requires_live_gate
def test_gh_status_projection_consumes_exact_server_normalized_wire_shape() -> None:
    normalized = normalize_gh_status_result(
        _success(
            {
                "available": True,
                "assemblyVersion": "8.0",
                "hasActiveCanvas": True,
                "hasActiveDocument": True,
                "documentId": GH_DOCUMENT_ID,
                "documentPath": r"C:\scratch\containment.ghx",
                "objectCount": 2,
                "readyForEdit": True,
                "warnings": [],
                "solverEnabled": True,
                "solverStateKnown": True,
                "solutionState": "PostProcess",
            }
        )
    )
    data = normalized["data"]
    assert "hasActiveCanvas" not in data and data["has_active_canvas"] is True
    assert "documentId" not in data and data["document_id"] == GH_DOCUMENT_ID
    assert data["solverEnabled"] is True
    assert data["solverStateKnown"] is True
    assert data["solutionState"] == "PostProcess"
    assert live._gh_status_projection(data) == {
        "available": True,
        "has_active_canvas": True,
        "has_active_document": True,
        "document_id": GH_DOCUMENT_ID,
        "document_path": r"C:\scratch\containment.ghx",
        "object_count": 2,
        "ready_for_edit": True,
        "solver_enabled": True,
        "solver_state_known": True,
        "solution_state": "PostProcess",
    }


@requires_live_gate
@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("objectCount", False),
        ("available", 1),
        ("hasActiveCanvas", 1),
        ("hasActiveDocument", 1),
        ("readyForEdit", 1),
        ("solverEnabled", 1),
        ("solverStateKnown", 1),
    ],
)
def test_gh_status_rejects_boolean_counts_and_numeric_boolean_flags(
    field: str,
    invalid: object,
) -> None:
    data = {
        "available": True,
        "hasActiveCanvas": True,
        "hasActiveDocument": True,
        "documentId": GH_DOCUMENT_ID,
        "documentPath": r"C:\scratch\containment.ghx",
        "objectCount": 0,
        "readyForEdit": True,
        "solverEnabled": True,
        "solverStateKnown": True,
        "solutionState": "PostProcess",
    }
    data[field] = invalid

    with pytest.raises(live.LiveGateError, match="status"):
        live._gh_status_projection(data)


@requires_live_gate
@pytest.mark.parametrize("field", ["total", "errors", "warnings"])
def test_snapshot_projection_rejects_boolean_diagnostic_counts(
    tmp_path: Path,
    field: str,
) -> None:
    adapter = _GrasshopperAdapter(tmp_path / "scratch.ghx")
    snapshot = adapter._snapshot()
    snapshot["diagnostics"][field] = False

    with pytest.raises(live.LiveGateError, match="snapshot"):
        live._snapshot_projection(
            snapshot,
            process_id=9002,
            process_token=PROCESS_TOKEN,
            port=19002,
            document_id=GH_DOCUMENT_ID,
            has_active_canvas=True,
        )


@requires_live_gate
@pytest.mark.parametrize(
    "field", ["totalComponents", "errorCount", "warningCount"]
)
def test_gh_errors_rejects_boolean_counts(field: str) -> None:
    data = {
        "totalComponents": 0,
        "errorCount": 0,
        "warningCount": 0,
        "errors": [],
        "warnings": [],
    }
    data[field] = False

    with pytest.raises(live.LiveGateError, match="error projection"):
        live._errors_projection(data)


@requires_live_gate
@pytest.mark.parametrize(
    ("field", "numeric"),
    [
        ("solve_scheduled", 1),
        ("solver_locked", 0),
        ("solver_state_known", 1),
        ("verification_deferred", 1),
    ],
)
def test_gh_edit_solve_projection_keeps_flags_exactly_boolean(
    field: str,
    numeric: int,
) -> None:
    summary = {
        "solve_scheduled": True,
        "solver_locked": False,
        "solver_state_known": True,
        "verification_deferred": True,
    }
    summary[field] = numeric

    with pytest.raises(live._ScenarioFailure, match="solve"):
        live._gh_edit_solve_projection({"edit_summary": summary})


def _runtime_evidence(tmp_path: Path) -> dict[str, Any]:
    root = (tmp_path / "installed").resolve()
    root.mkdir(exist_ok=True)
    return {
        "python_executable": str((root / "python.exe").resolve()),
        "installed_root": str(root),
        "cwd": str((tmp_path / "run").resolve()),
        "sys_path": [str(root)],
        "rook_origins": {
            "rook": str(root / "rook" / "__init__.py"),
            "rook.containment_live_gate": str(root / "rook" / "containment_live_gate.py"),
        },
    }


def _install_fake_scenario(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    scenario: str,
    store: _Store | None = None,
    authorization: str = "valid",
    drift: bool = False,
    graceful_forced: bool = False,
    discovery_mode: str = "fresh",
    discovery_dir: Path | None = None,
):
    artifact = tmp_path / f"artifacts-{scenario}"
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_bytes(b"fake")
    process = _Process(9001 if scenario == "rhino" else 9002)
    record_directory = discovery_dir or tmp_path
    record_directory.mkdir(parents=True, exist_ok=True)
    record_path = record_directory / f"instance-{process.pid}-native.json"
    record_raw = {
        "processId": process.pid,
        "port": 19001 if scenario == "rhino" else 19002,
        "pluginType": "native",
    }
    record_bytes = json.dumps(record_raw).encode("utf-8")
    if discovery_mode == "stale_unchanged":
        record_path.write_bytes(record_bytes)
    record_sha256 = hashlib.sha256(record_bytes).hexdigest()
    record = _Record(
        process.pid,
        19001 if scenario == "rhino" else 19002,
        record_path,
        dict(record_raw),
    )
    discovery = _Discovery(record)
    scratch_suffix = "3dm" if scenario == "rhino" else "ghx"
    scratch_prefix = "RookContainmentRhino" if scenario == "rhino" else "RookContainmentGH"
    scratch = (artifact / f"{scratch_prefix}-{RUN_ID}.{scratch_suffix}").resolve()
    adapter = _RhinoAdapter(scratch) if scenario == "rhino" else _GrasshopperAdapter(scratch)
    store = store or _Store()
    trace: list[str] = []

    monkeypatch.setattr(live, "_new_run_id", lambda: RUN_ID)
    monkeypatch.setattr(live, "_new_nonce", lambda: NONCE)
    monkeypatch.setattr(live, "_collect_and_validate_runtime_evidence", lambda: _runtime_evidence(tmp_path))
    monkeypatch.setattr(live, "_get_metrics_store", lambda: store)
    monkeypatch.setattr(live, "_build_launch_environment", lambda: {"env": {}, "report": {}})

    def start(*, rhino_exe: Path, launch: dict[str, Any]):
        assert store.get_containment_denials_snapshot()
        trace.append("launch")
        if discovery_mode != "stale_unchanged":
            replacement = record_path.with_suffix(".json.tmp")
            replacement.write_bytes(record_bytes)
            os.replace(replacement, record_path)
            if discovery_mode == "changed_but_old":
                os.utime(record_path, (0.0, 0.0))
        return SimpleNamespace(process=process, pid=process.pid, started_wall=100.0)

    monkeypatch.setattr(live, "_start_owned_rhino", start)
    monkeypatch.setattr(live, "_new_owned_discovery", lambda: discovery)
    monkeypatch.setattr(live, "_wait_for_owned_readiness", lambda started, owned: record)
    monkeypatch.setattr(live, "_owned_process_start_token", lambda started: PROCESS_TOKEN)
    accepted_record_bytes: list[bytes | None] = []

    def new_adapter(
        *,
        started,
        record,
        process_start_token,
        record_bytes=None,
        record_device_id=None,
        record_file_id=None,
        discovery_leases=None,
    ):
        accepted_record_bytes.append(record_bytes)
        return adapter

    monkeypatch.setattr(live, "_new_bound_adapter", new_adapter)

    close_calls: list[int] = []

    def close(proc, diagnostics):
        close_calls.append(proc.pid)
        proc.wait()
        discovery.removed = True
        try:
            record_path.unlink()
        except FileNotFoundError:
            pass
        return graceful_forced

    monkeypatch.setattr(live, "_request_graceful_close", close)
    monkeypatch.setattr(live, "_force_owned_cleanup", lambda proc, diagnostics: False)
    fake_clock = {"now": 0.0}
    monkeypatch.setattr(live, "_monotonic", lambda: fake_clock["now"])
    monkeypatch.setattr(
        live,
        "_sleep",
        lambda seconds: fake_clock.__setitem__(
            "now", fake_clock["now"] + seconds
        ),
    )

    challenge_target = {
        "label": live.AUTHORIZATION_LABELS[scenario],
        "process_id": process.pid,
        "port": record.port,
        "scratch_path": str(scratch),
    }
    expected_challenge = live._build_authorization_challenge(
        scenario=scenario,
        run_id=RUN_ID,
        nonce=NONCE,
        target=challenge_target,
    )
    if authorization == "valid":
        line = expected_challenge["required_response"].encode("ascii") + b"\n"
    elif authorization == "eof":
        line = b""
    else:
        line = b"WRONG\n"
    monkeypatch.setattr(live, "_read_authorization_line", lambda: line)

    if drift:
        original = adapter.call
        drift_name = "rhino_document" if scenario == "rhino" else "gh_status"
        seen_preflight = 0

        async def drifting_call(name, arguments):
            nonlocal seen_preflight
            result = await original(name, arguments)
            if name == drift_name:
                seen_preflight += 1
                if seen_preflight >= 2 and result["success"]:
                    result = copy.deepcopy(result)
                    result["data"][
                        "objectCount" if scenario == "rhino" else "object_count"
                    ] = 99
            return result

        adapter.call = drifting_call

    return SimpleNamespace(
        artifact=artifact,
        rhino_exe=rhino_exe,
        process=process,
        record=record,
        record_sha256=record_sha256,
        record_bytes=record_bytes,
        accepted_record_bytes=accepted_record_bytes,
        discovery=discovery,
        adapter=adapter,
        store=store,
        trace=trace,
        close_calls=close_calls,
        scratch=scratch,
        challenge=expected_challenge,
    )


def _load_final_artifact(artifact: Path, scenario: str) -> dict[str, Any]:
    path = artifact / f"{scenario}-scenario.json"
    payload = path.read_bytes()
    assert payload == live._canonical_json_bytes(json.loads(payload))
    digest = hashlib.sha256(payload).hexdigest()
    assert (artifact / f"{scenario}-scenario.sha256").read_bytes() == f"{digest}\n".encode()
    return json.loads(payload)


@requires_live_gate
def test_grasshopper_output_contract_uses_structured_fields_not_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()

    projection = live._verify_gh_edit(snapshot, RUN_ID)

    output = projection["components"][1]["outputs"][0]
    assert output["idx"] == 0
    assert output["name"] == "Sphere"
    assert output["type"] == "Sphere"
    assert output["data"]["structure"] == "single"
    assert output["data"]["count"] == 1
    assert output["data"]["preview"] == ["Sphere"]


@requires_live_gate
def test_grasshopper_output_contract_rejects_misleading_digit_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()
    output = snapshot["components"][1]["outputs"][0]
    output["type"] = "Integer"
    output["data"]["preview"] = ["misleading radius 4"]

    with pytest.raises(live._ScenarioFailure, match="output"):
        live._verify_gh_edit(snapshot, RUN_ID)


@requires_live_gate
@pytest.mark.parametrize("case", ["wrong_slider_value", "empty_output"])
def test_grasshopper_output_contract_rejects_wrong_value_or_empty_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()
    if case == "wrong_slider_value":
        snapshot["components"][0]["value"]["val"] = 5
    else:
        snapshot["components"][1]["outputs"][0]["data"] = {
            "structure": "empty",
            "count": 0,
            "preview": ["misleading radius 4"],
        }

    with pytest.raises(live._ScenarioFailure):
        live._verify_gh_edit(snapshot, RUN_ID)


@requires_live_gate
@pytest.mark.parametrize(
    "integer_field",
    [
        "slider_min",
        "slider_max",
        "slider_value",
        "input_index",
        "source_count",
        "output_index",
        "output_count",
        "diagnostic_total",
        "diagnostic_errors",
        "diagnostic_warnings",
    ],
)
def test_grasshopper_edit_verification_rejects_boolean_integer_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    integer_field: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()
    slider = snapshot["components"][0]
    sphere = snapshot["components"][1]
    if integer_field == "slider_min":
        slider["value"]["min"] = True
    elif integer_field == "slider_max":
        slider["value"]["max"] = True
    elif integer_field == "slider_value":
        slider["value"]["val"] = True
    elif integer_field == "input_index":
        sphere["inputs"][1]["idx"] = True
    elif integer_field == "source_count":
        sphere["inputs"][1]["sources"] = True
    elif integer_field == "output_index":
        sphere["outputs"][0]["idx"] = False
    elif integer_field == "output_count":
        sphere["outputs"][0]["data"]["count"] = True
    elif integer_field == "diagnostic_total":
        snapshot["diagnostics"]["total"] = False
    elif integer_field == "diagnostic_errors":
        snapshot["diagnostics"]["errors"] = False
    else:
        snapshot["diagnostics"]["warnings"] = False

    with pytest.raises(live._ScenarioFailure):
        live._verify_gh_edit(snapshot, RUN_ID)


@requires_live_gate
def test_grasshopper_library_count_rejects_boolean_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def boolean_library_count(name: str, arguments: dict[str, Any]):
        result = await original(name, arguments)
        if name == "gh_library":
            result = copy.deepcopy(result)
            result["data"]["count"] = True
        return result

    harness.adapter.call = boolean_library_count
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "verification_failed"


@requires_live_gate
@pytest.mark.parametrize(
    "discovery_mode",
    ["stale_unchanged", "changed_but_old"],
)
def test_owned_discovery_record_must_be_new_or_changed_and_launch_fresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    discovery_mode: str,
) -> None:
    harness = _install_fake_scenario(
        monkeypatch,
        tmp_path,
        scenario="rhino",
        discovery_mode=discovery_mode,
    )

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "readiness_failed"
    assert harness.accepted_record_bytes == []


@requires_live_gate
def test_discovery_rejects_same_identity_after_same_byte_fresh_touch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "instance-7001-native.json"
    raw = {"pid": 7001, "port": 17001}
    payload = live._canonical_json_bytes(raw)
    path.write_bytes(payload)
    before = live._capture_discovery_record(path)
    os.utime(path, None)
    record = SimpleNamespace(pid=7001, port=17001, path=path, raw=raw)
    started = SimpleNamespace(
        pid=7001,
        started_wall=path.stat().st_mtime_ns / 1_000_000_000,
    )

    with pytest.raises(live.LiveGateError, match="prelaunch|identity|unchanged"):
        live._accept_fresh_owned_discovery_record(
            started=started,
            record=record,
            prelaunch={path: before},
        )


@requires_live_gate
def test_discovery_rejects_prelaunch_identity_renamed_to_accepted_pid_path(
    tmp_path: Path,
) -> None:
    old_path = tmp_path / "instance-7000-native.json"
    accepted_path = tmp_path / "instance-7001-native.json"
    raw = {"pid": 7001, "port": 17001}
    old_path.write_bytes(live._canonical_json_bytes(raw))
    before = live._capture_discovery_record(old_path)
    old_path.rename(accepted_path)
    os.utime(accepted_path, None)
    record = SimpleNamespace(pid=7001, port=17001, path=accepted_path, raw=raw)
    started = SimpleNamespace(
        pid=7001,
        started_wall=accepted_path.stat().st_mtime_ns / 1_000_000_000,
    )

    with pytest.raises(live.LiveGateError, match="prelaunch|identity|unchanged"):
        live._accept_fresh_owned_discovery_record(
            started=started,
            record=record,
            prelaunch={old_path: before},
        )


@requires_live_gate
def test_discovery_rejects_nonmatching_prelaunch_identity_renamed_to_accepted_path(
    tmp_path: Path,
) -> None:
    stale_path = tmp_path / "stale-native-publication.tmp"
    accepted_path = tmp_path / "instance-7001-native.json"
    raw = {"pid": 7001, "port": 17001}
    stale_path.write_bytes(live._canonical_json_bytes(raw))
    prelaunch = live._snapshot_prelaunch_discovery_records(
        SimpleNamespace(discovery_dir=tmp_path)
    )
    stale_path.rename(accepted_path)
    os.utime(accepted_path, None)
    record = SimpleNamespace(pid=7001, port=17001, path=accepted_path, raw=raw)
    started = SimpleNamespace(
        pid=7001,
        started_wall=accepted_path.stat().st_mtime_ns / 1_000_000_000,
    )

    assert stale_path in prelaunch
    with pytest.raises(live.LiveGateError, match="prelaunch|identity|unchanged"):
        live._accept_fresh_owned_discovery_record(
            started=started,
            record=record,
            prelaunch=prelaunch,
        )


@requires_live_gate
def test_discovery_binds_direntry_identity_through_prelaunch_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    discovery_dir = tmp_path / "discovery"
    discovery_dir.mkdir()
    stale_path = discovery_dir / "a-stale.tmp"
    accepted_path = discovery_dir / "instance-7001-native.json"
    replacement = tmp_path / "replacement.tmp"
    stale_raw = {"pid": 7001, "port": 17001}
    stale_path.write_bytes(live._canonical_json_bytes(stale_raw))
    replacement.write_bytes(b'{"replacement":true}')
    original_capture = live._capture_discovery_record
    swapped = False

    def swap_after_entry_inspection(path: Path, *args, **kwargs):
        nonlocal swapped
        if Path(path) == stale_path and not swapped:
            stale_path.rename(accepted_path)
            replacement.rename(stale_path)
            swapped = True
        return original_capture(path, *args, **kwargs)

    monkeypatch.setattr(
        live,
        "_capture_discovery_record",
        swap_after_entry_inspection,
    )
    record = SimpleNamespace(
        pid=7001,
        port=17001,
        path=accepted_path,
        raw=stale_raw,
    )

    with pytest.raises(live.LiveGateError, match="identity|changed|prelaunch"):
        prelaunch = live._snapshot_prelaunch_discovery_records(
            SimpleNamespace(discovery_dir=discovery_dir)
        )
        os.utime(accepted_path, None)
        live._accept_fresh_owned_discovery_record(
            started=SimpleNamespace(
                pid=7001,
                started_wall=accepted_path.stat().st_mtime_ns / 1_000_000_000,
            ),
            record=record,
            prelaunch=prelaunch,
        )

    assert swapped is True


@requires_live_gate
def test_discovery_accepts_same_bytes_from_fresh_atomic_replacement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "instance-7001-native.json"
    temp = tmp_path / "instance-7001-native.json.tmp"
    raw = {"pid": 7001, "port": 17001}
    payload = live._canonical_json_bytes(raw)
    path.write_bytes(payload)
    before = live._capture_discovery_record(path)
    temp.write_bytes(payload)
    os.replace(temp, path)
    os.utime(path, None)
    record = SimpleNamespace(pid=7001, port=17001, path=path, raw=raw)
    started = SimpleNamespace(
        pid=7001,
        started_wall=path.stat().st_mtime_ns / 1_000_000_000,
    )

    accepted = live._accept_fresh_owned_discovery_record(
        started=started,
        record=record,
        prelaunch={path: before},
    )

    assert accepted.payload == payload
    assert (accepted.device_id, accepted.file_id) != (
        before.device_id,
        before.file_id,
    )


@requires_live_gate
@pytest.mark.parametrize("race_phase", ["accepted_capture", "adapter_continuity"])
def test_postlaunch_discovery_ancestry_stays_pinned_through_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    race_phase: str,
) -> None:
    discovery_container = tmp_path / "owned-discovery-container"
    discovery_dir = discovery_container / "discovery"
    harness = _install_fake_scenario(
        monkeypatch,
        tmp_path,
        scenario="rhino",
        discovery_dir=discovery_dir,
    )
    displaced_container = tmp_path / "displaced-discovery-container"
    attacker_container = tmp_path / "attacker-discovery-container"
    attacker_dir = attacker_container / "discovery"
    attacker_dir.mkdir(parents=True)
    attacker_record = attacker_dir / harness.record.path.name
    attacker_record.write_bytes(
        live._canonical_json_bytes(
            {
                "processId": harness.process.pid,
                "port": 29999,
                "pluginType": "native",
            }
        )
    )
    original_capture = live._capture_discovery_record
    original_acquire = live._acquire_windows_path_lease
    original_close = live._request_graceful_close
    original_force = live._force_owned_cleanup
    original_final_pair = live._write_final_evidence_pair
    capture_calls = 0
    blocked = False
    swapped = False
    external_record_opened = False
    cleanup_finished = False
    released_before_cleanup = False
    bound_ports: list[int] = []
    host_dispatches: list[str] = []
    cleanup_calls: list[str] = []
    releases: dict[Path, list[int]] = {}
    tracked_directories = {discovery_container, discovery_dir}
    target_capture = 1 if race_phase == "accepted_capture" else 2

    def tracked_acquire(path: Path, *args, **kwargs):
        nonlocal external_record_opened, released_before_cleanup
        candidate = Path(path)
        if swapped:
            try:
                external_record_opened = (
                    external_record_opened
                    or candidate.resolve() == attacker_record.resolve()
                )
            except OSError:
                pass
        lease = original_acquire(path, *args, **kwargs)
        if candidate in tracked_directories:
            calls = [0]
            releases[candidate] = calls
            original_release = lease.release

            def tracked_release() -> None:
                nonlocal released_before_cleanup
                calls[0] += 1
                if not cleanup_finished:
                    released_before_cleanup = True
                original_release()

            lease.release = tracked_release
        return lease

    def race_capture(path: Path, *args, **kwargs):
        nonlocal capture_calls, blocked, swapped
        if Path(path) == harness.record.path:
            capture_calls += 1
            if capture_calls == target_capture:
                try:
                    discovery_container.rename(displaced_container)
                except PermissionError:
                    blocked = True
                else:
                    _directory_symlink_or_skip(
                        discovery_container,
                        attacker_container,
                    )
                    swapped = True
                snapshot = original_capture(path, *args, **kwargs)
                raise live.LiveGateError("stop after protected discovery capture")
        return original_capture(path, *args, **kwargs)

    def new_bound_adapter(**kwargs):
        bound_ports.append(kwargs["record"].port)
        constructor = {
            "port": kwargs["record"].port,
            "process_id": kwargs["record"].pid,
            "started": kwargs["started"],
            "record": kwargs["record"],
            "process_start_token": kwargs["process_start_token"],
            "record_bytes": kwargs["record_bytes"],
            "record_file_id": kwargs["record_file_id"],
        }
        for name in ("record_device_id", "discovery_leases"):
            if name in kwargs:
                constructor[name] = kwargs[name]
        return live.BoundInstalledToolAdapter(**constructor)

    async def track_dispatch(name: str, arguments: dict[str, Any]):
        host_dispatches.append(name)
        forwarded = dict(arguments)
        forwarded.pop("port", None)
        return await harness.adapter.call(name, forwarded)

    def close_before_release(process, diagnostics):
        nonlocal cleanup_finished
        cleanup_calls.append("graceful")
        result = original_close(process, diagnostics)
        cleanup_finished = True
        return result

    def force_before_release(process, diagnostics):
        nonlocal cleanup_finished
        cleanup_calls.append("forced")
        result = original_force(process, diagnostics)
        cleanup_finished = True
        return result

    def final_pair_before_release(*args, **kwargs):
        nonlocal cleanup_finished
        result = original_final_pair(*args, **kwargs)
        cleanup_finished = True
        return result

    monkeypatch.setattr(live, "_acquire_windows_path_lease", tracked_acquire)
    monkeypatch.setattr(live, "_capture_discovery_record", race_capture)
    monkeypatch.setattr(live, "_new_bound_adapter", new_bound_adapter)
    monkeypatch.setattr(live, "_dispatch_installed_tool", track_dispatch)
    monkeypatch.setattr(live, "_request_graceful_close", close_before_release)
    monkeypatch.setattr(live, "_force_owned_cleanup", force_before_release)
    monkeypatch.setattr(live, "_write_final_evidence_pair", final_pair_before_release)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert capture_calls == target_capture
    assert blocked is True
    assert swapped is False
    assert external_record_opened is False
    assert 29999 not in bound_ports
    assert host_dispatches == []
    assert harness.adapter.calls == []
    assert cleanup_finished is True
    if race_phase == "accepted_capture":
        assert cleanup_calls == ["graceful"]
        assert not harness.record.path.exists(), "normal plugin record deletion was blocked"
    else:
        assert cleanup_calls == []
        assert harness.record.path.is_file(), "forced cleanup removed the discovery record"
    assert attacker_record.is_file(), "cleanup removed an external discovery record"
    assert released_before_cleanup is False
    assert set(releases) == tracked_directories
    assert {calls[0] for calls in releases.values()} == {1}


def _tracked_claim_and_unadopted_view(tmp_path: Path) -> SimpleNamespace:
    artifact = tmp_path / "retain-view-artifacts"
    discovery = tmp_path / "retain-view-discovery"
    artifact.mkdir()
    discovery.mkdir()
    root_leases = live._acquire_retained_path_leases(artifact, "directory")
    try:
        incoming = live._acquire_retained_path_leases(
            discovery,
            "directory",
            registry=root_leases._registry,
        )
    except BaseException:
        root_leases.release()
        raise
    claim = live._ArtifactRootClaim(artifact, root_leases)
    claim.verify()
    incoming.verify()

    underlying_release_calls: dict[Path, list[int]] = {}
    for _identity, lease, _references in root_leases._registry._entries.values():
        calls = [0]
        underlying_release_calls[lease.path] = calls
        original_release = lease.release

        def tracked_release(
            *,
            _calls: list[int] = calls,
            _original_release=original_release,
        ) -> None:
            _calls[0] += 1
            _original_release()

        lease.release = tracked_release

    incoming_release_calls = [0]
    original_incoming_release = incoming.release

    def tracked_incoming_release() -> None:
        incoming_release_calls[0] += 1
        original_incoming_release()

    incoming.release = tracked_incoming_release
    return SimpleNamespace(
        claim=claim,
        incoming=incoming,
        registry=root_leases._registry,
        incoming_release_calls=incoming_release_calls,
        underlying_release_calls=underlying_release_calls,
    )


@requires_live_gate
@pytest.mark.parametrize("validation_site", ["claim", "incoming_view"])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_retain_view_validation_failure_releases_unadopted_view_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    validation_site: str,
    error_type: type[BaseException],
) -> None:
    tracked = _tracked_claim_and_unadopted_view(tmp_path)
    injected = error_type(f"{validation_site} validation interrupted")

    def fail_validation() -> None:
        raise injected

    target = tracked.claim if validation_site == "claim" else tracked.incoming
    monkeypatch.setattr(target, "verify", fail_validation)
    caught: BaseException | None = None
    observed_view_releases = -1
    observed_underlying_releases: set[int] = set()
    observed_registry_empty = False
    try:
        with pytest.raises(error_type) as raised:
            tracked.claim.retain_view(tracked.incoming)
        caught = raised.value
    finally:
        try:
            if not tracked.claim._released:
                tracked.claim.release()
        finally:
            observed_view_releases = tracked.incoming_release_calls[0]
            observed_underlying_releases = {
                calls[0] for calls in tracked.underlying_release_calls.values()
            }
            observed_registry_empty = not tracked.registry._entries
            if not tracked.incoming.released:
                tracked.incoming.release()

    assert caught is injected
    assert tracked.claim._retained_views == []
    assert observed_view_releases == 1
    assert observed_underlying_releases == {1}
    assert observed_registry_empty is True


@requires_live_gate
def test_retain_view_success_transfers_release_ownership_once(
    tmp_path: Path,
) -> None:
    tracked = _tracked_claim_and_unadopted_view(tmp_path)
    try:
        tracked.claim.retain_view(tracked.incoming)
        assert tracked.claim._retained_views == [tracked.incoming]
        assert tracked.incoming_release_calls == [0]
        tracked.claim.release()
    finally:
        if not tracked.claim._released:
            tracked.claim.release()
        if not tracked.incoming.released:
            tracked.incoming.release()

    assert tracked.incoming_release_calls == [1]
    assert {
        calls[0] for calls in tracked.underlying_release_calls.values()
    } == {1}
    assert tracked.registry._entries == {}


@requires_live_gate
def test_target_and_adapter_share_exact_fresh_discovery_record_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True
    assert harness.accepted_record_bytes == [harness.record_bytes]
    assert result.target is not None
    assert result.target["discovery_record_sha256"] == hashlib.sha256(
        harness.accepted_record_bytes[0]
    ).hexdigest()


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_successful_fake_host_scenarios_emit_exact_evidence_and_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is True
    assert result.failure_label is None
    stdout = capsys.readouterr().out.encode("utf-8")
    lines = stdout.splitlines(keepends=True)
    assert len(lines) == 2 and all(line.endswith(b"\n") for line in lines)
    records = [json.loads(line) for line in lines]
    assert records[0] == harness.challenge
    assert records[1]["type"] == "scenario_result"
    assert records[1]["success"] is True and records[1]["failure_label"] is None
    assert set(records[1]) == {
        "type", "schema_version", "scenario", "run_id", "success", "failure_label", "evidence_path", "evidence_sha256"
    }

    artifact = _load_final_artifact(harness.artifact, scenario)
    assert set(artifact) == set(live.RESULT_FIELDS)
    assert artifact["success"] is True
    assert artifact["runtime"] == _runtime_evidence(tmp_path)
    assert artifact["target"]["process_id"] == harness.process.pid
    assert artifact["target"]["port"] == harness.record.port
    assert artifact["target"]["process_start_token"] == PROCESS_TOKEN
    assert artifact["target"]["discovery_record_sha256"] == harness.record_sha256
    assert artifact["authorization"]["state_unchanged"] is True
    assert artifact["verification"]["passed"] is True
    assert artifact["restoration"] == {
        "ownership_certain": True,
        "attempted": True,
        "verified": True,
        "in_process_projection_matches_declared": True,
        "prior_identity_or_absence_restored": True,
        "scratch_disposed": True,
        "discovery_removed": True,
    }
    assert artifact["telemetry"]["delta_count"] == 0
    assert artifact["telemetry"]["events_added"] == []
    assert not harness.scratch.exists()
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert artifact["operations"]
    assert not any(item["name"] in live.CONTAINED_IDENTITIES for item in artifact["operations"])
    for operation in artifact["operations"]:
        for kind in ("arguments", "result"):
            path = harness.artifact / operation[f"{kind}_path"]
            payload = path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == operation[f"{kind}_sha256"]
            assert payload == live._canonical_json_bytes(json.loads(payload))
            assert any(item["relative_path"] == operation[f"{kind}_path"] for item in artifact["artifacts"])
    live._validate_scenario_artifacts(harness.artifact, scenario=scenario)

    names = [name for name, _ in harness.adapter.calls]
    if scenario == "rhino":
        assert ("rhino_create", live._rhino_sphere_arguments(RUN_ID)) in harness.adapter.calls
        assert ("rhino_execute", {"code": live._rhino_point_script(RUN_ID)}) in harness.adapter.calls
        sphere = artifact["verification"]["projection"]["objects"]["sphere"]
        assert sphere == {
            "id": SPHERE_ID,
            "name": f"RookContainmentSphere-{RUN_ID}",
            "type": "Brep",
            "center": [0.0, 0.0, 0.0],
            "radius": 4.0,
            "bbox": {"min": [-4, -4, -4], "max": [4, 4, 4]},
            "face_count": 1,
            "edge_count": 1,
            "vertex_count": 2,
            "is_solid": True,
            "is_manifold": True,
            "area": SPHERE_AREA,
            "volume": SPHERE_VOLUME,
        }
        assert names.index("rhino_delete") < names.index("rhino_document_ops", names.index("rhino_delete"))
        dirty_checks = [
            args for name, args in harness.adapter.calls if name == "rhino_document"
        ]
        assert dirty_checks
    else:
        assert ("rhino_command", {"command": "_Grasshopper", "echo": False}) in harness.adapter.calls
        assert ("gh_library", {"search": "Sphere", "exact": True}) in harness.adapter.calls
        edit_calls = [args for name, args in harness.adapter.calls if name == "gh_edit"]
        assert edit_calls == [live._grasshopper_edit_arguments(RUN_ID, 7)]
        assert 1 <= names.count("gh_undo") <= 4
        assert "gh_solve" not in names and "gh_document_new" not in names


@requires_live_gate
def test_rhino_uses_only_the_plan_sanctioned_point_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is True
    script_bodies = [
        arguments["code"]
        for name, arguments in harness.adapter.calls
        if name == "rhino_execute"
        and arguments != {"code": live.RUNTIME_SERIAL_CODE}
    ]
    assert script_bodies == [live._rhino_point_script(RUN_ID)], (
        f"{EXPECTED_RED}:RHINO_SOLE_SCRIPT the gate executed a code body not "
        "sanctioned by the frozen Task 8 plan"
    )


@requires_live_gate
@pytest.mark.parametrize(
    "geometry_override",
    [
        {"faceCount": 2},
        {"edgeCount": 0},
        {"vertexCount": 0},
        {"isManifold": False},
        {"area": 200.0},
        {"volume": 267.0},
    ],
    ids=[
        "wrong_face_count",
        "wrong_edge_count",
        "wrong_vertex_count",
        "non_manifold",
        "wrong_area",
        "wrong_volume",
    ],
)
def test_rhino_rejects_same_bbox_brep_signature_impostors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    geometry_override: dict[str, Any],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    harness.adapter.sphere_geometry_overrides = geometry_override

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False, (
        f"{EXPECTED_RED}:RHINO_BREP_SIGNATURE a same-bbox topology or mass "
        "properties impostor was accepted"
    )
    assert result.failure_label == "verification_failed"
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["verification"]["passed"] is False
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_sphere_center_and_radius_are_derived_from_equal_axis_bbox() -> None:
    observed = live._sphere_observation_from_bbox(
        {"min": [-3, -2, -1], "max": [5, 6, 7]}
    )
    assert observed == {"center": [1.0, 2.0, 3.0], "radius": 4.0}

    with pytest.raises(live._ScenarioFailure, match="equal-axis"):
        live._sphere_observation_from_bbox(
            {"min": [-3, -2, -1], "max": [5, 6, 6]}
        )


@requires_live_gate
@pytest.mark.parametrize(
    "status_override",
    [
        {"hasActiveCanvas": False},
        {"hasActiveCanvas": None},
        {"hasActiveDocument": False},
        {"hasActiveDocument": None},
        {"documentPath": r"C:\wrong\not-the-owned-scratch.ghx"},
        {"readyForEdit": False},
        {"readyForEdit": None},
    ],
    ids=[
        "canvas_false",
        "canvas_unknown",
        "document_false",
        "document_unknown",
        "wrong_path",
        "not_ready",
        "readiness_unknown",
    ],
)
def test_grasshopper_rejects_unready_or_wrong_post_open_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status_override: dict[str, Any],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.open_status_overrides = status_override

    with redirect_stdout(io.StringIO()):
        result = live.run_live_scenario(
            scenario="grasshopper",
            rhino_exe=harness.rhino_exe,
            artifact_dir=harness.artifact,
        )

    assert result.success is False, (
        f"{EXPECTED_RED}:GH_POST_OPEN_STATUS an inactive, unknown, unready, or "
        "wrong-path canvas was projected as the owned scratch canvas"
    )
    names = [name for name, _ in harness.adapter.calls]
    assert "gh_document_open" in names
    assert "gh_library" not in names and "gh_edit" not in names
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["pre_state"]["scratch_projection"] is None
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
def test_grasshopper_settle_waits_past_real_deferred_dispatch_delay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    clock = {"now": 0.0}
    edited_status_times: list[float] = []

    async def delayed_settle(name, arguments):
        result = await original_call(name, arguments)
        if name == "gh_status" and harness.adapter.edited:
            edited_status_times.append(clock["now"])
            if clock["now"] < 5.25:
                result = copy.deepcopy(result)
                result["data"]["solutionState"] = "PreProcess"
        return result

    harness.adapter.call = delayed_settle
    monkeypatch.setattr(live, "_monotonic", lambda: clock["now"], raising=False)
    monkeypatch.setattr(
        live,
        "_sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert live.GH_SOLVE_SETTLE_TIMEOUT_SECONDS > 5.0
    assert result.success is True
    assert edited_status_times[0] == 0.0
    assert max(edited_status_times) >= 5.25
    assert max(edited_status_times) <= live.GH_SOLVE_SETTLE_TIMEOUT_SECONDS


@requires_live_gate
def test_keyboard_interrupt_before_authorization_closes_owned_target_and_exits_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    def interrupt_authorization() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(live, "_read_authorization_line", interrupt_authorization)
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "rhino",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    names = [name for name, _ in harness.adapter.calls]
    assert exit_code == 130
    assert not {
        "rhino_document_ops",
        "rhino_create",
        "rhino_delete",
    }.intersection(names)
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert not Path(harness.record.path).exists()
    assert not harness.scratch.exists()
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "authorization_rejected"
    assert evidence["restoration"]["attempted"] is False
    assert evidence["restoration"]["verified"] is False
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_keyboard_interrupt_during_restoration_retries_safely_then_exits_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    undo_attempts = 0

    async def interrupt_first_undo(name, arguments):
        nonlocal undo_attempts
        if name == "gh_undo":
            undo_attempts += 1
            if undo_attempts == 1:
                raise KeyboardInterrupt
        return await original_call(name, arguments)

    harness.adapter.call = interrupt_first_undo
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "grasshopper",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    assert exit_code == 130
    assert undo_attempts == 2
    assert harness.adapter.undo_count == 1
    assert harness.adapter.edited is False
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert not Path(harness.record.path).exists()
    assert not harness.scratch.exists()
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "mutation_failed"
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["verified"] is True
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
def test_keyboard_interrupt_retry_never_exceeds_total_four_undo_attempts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    undo_attempts = 0

    async def interrupt_fourth_undo(name, arguments):
        nonlocal undo_attempts
        if name == "gh_undo":
            undo_attempts += 1
            if undo_attempts < 4:
                harness.adapter.calls.append((name, copy.deepcopy(arguments)))
                return _success(
                    {
                        "message": "Undo reported without restoration",
                        "epoch": 8 + undo_attempts,
                        "snapshot": harness.adapter._snapshot(),
                    }
                )
            if undo_attempts == 4:
                raise KeyboardInterrupt
        return await original_call(name, arguments)

    harness.adapter.call = interrupt_fourth_undo
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "grasshopper",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    assert exit_code == 130
    assert undo_attempts == 4
    assert harness.adapter.edited is True
    assert harness.process.closed and not harness.process.killed
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "restoration_failed"
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["verified"] is False
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_keyboard_interrupt_during_restoration_validation_preserves_exit_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    original = harness.adapter.call
    observed = 0

    async def interrupt_first_restoration_validation(name, arguments):
        nonlocal observed
        is_validation_probe = (
            scenario == "rhino"
            and name == "rhino_execute"
            and arguments == {"code": live.RUNTIME_SERIAL_CODE}
        ) or (scenario == "grasshopper" and name == "gh_snapshot")
        if is_validation_probe:
            observed += 1
            if observed == 4:
                raise KeyboardInterrupt
        return await original(name, arguments)

    harness.adapter.call = interrupt_first_restoration_validation
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                scenario,
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    assert exit_code == 130, (
        f"{EXPECTED_RED}:RESTORE_VALIDATION_INTERRUPT:{scenario} "
        "KeyboardInterrupt was converted into an ordinary failure"
    )
    evidence = _load_final_artifact(harness.artifact, scenario)
    assert evidence["success"] is False
    assert evidence["restoration"]["verified"] is True


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
@pytest.mark.parametrize("authorization", ["eof", "wrong"])
def test_authorization_rejection_blocks_all_forward_mutation_and_is_not_green(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    authorization: str,
) -> None:
    harness = _install_fake_scenario(
        monkeypatch,
        tmp_path,
        scenario=scenario,
        authorization=authorization,
    )
    result = live.run_live_scenario(scenario=scenario, rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "authorization_rejected"
    artifact = _load_final_artifact(harness.artifact, scenario)
    names = [name for name, _ in harness.adapter.calls]
    mutation_names = {"rhino_document_ops", "rhino_create", "rhino_delete", "rhino_command", "gh_document_open", "gh_edit", "gh_undo"}
    assert not mutation_names.intersection(names)
    assert artifact["operations"] == []
    assert not any(item["kind"].startswith("operation_") for item in artifact["artifacts"])
    assert artifact["authorization"]["authorized_at"] is None
    assert artifact["restoration"]["attempted"] is False
    assert artifact["success"] is False


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_preflight_blocked_has_no_operation_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    original = harness.adapter.call

    async def block_preflight(name, arguments):
        result = await original(name, arguments)
        if scenario == "rhino" and name == "rhino_document":
            result = copy.deepcopy(result)
            result["data"]["objectCount"] = 1
        if scenario == "grasshopper" and name == "gh_status":
            result = copy.deepcopy(result)
            result["data"].update(
                {
                    "available": True,
                    "has_active_canvas": True,
                    "has_active_document": True,
                    "document_id": GH_BOOTSTRAP_DOCUMENT_ID,
                    "ready_for_edit": True,
                    "object_count": 1,
                }
            )
        return result

    harness.adapter.call = block_preflight
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "preflight_blocked"
    artifact = _load_final_artifact(harness.artifact, scenario)
    assert artifact["authorization"] is None
    assert artifact["operations"] == []
    assert not any(item["kind"].startswith("operation_") for item in artifact["artifacts"])


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_malformed_preflight_is_classified_as_blocked_without_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    original = harness.adapter.call

    async def malformed_preflight(name, arguments):
        if (scenario == "rhino" and name == "rhino_document") or (
            scenario == "grasshopper" and name == "gh_status"
        ):
            harness.adapter.calls.append((name, copy.deepcopy(arguments)))
            return {"success": True, "data": []}
        return await original(name, arguments)

    harness.adapter.call = malformed_preflight
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "preflight_blocked"
    evidence = _load_final_artifact(harness.artifact, scenario)
    assert evidence["operations"] == []
    assert evidence["authorization"] is None


@requires_live_gate
def test_invalid_packaged_fixture_is_classified_before_authorization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    invalid = tmp_path / "invalid.ghx"
    invalid.write_bytes(b"not-the-approved-fixture\n")
    monkeypatch.setattr(live, "_fixture_resource_path", lambda: invalid)
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "fixture_invalid"
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["authorization"] is None
    assert evidence["pre_state"] is None
    assert evidence["operations"] == []


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_pre_mutation_state_drift_invalidates_authorization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario, drift=True)
    result = live.run_live_scenario(scenario=scenario, rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "state_drift"
    names = [name for name, _ in harness.adapter.calls]
    assert not {"rhino_document_ops", "rhino_create", "rhino_command", "gh_document_open", "gh_edit"}.intersection(names)


@requires_live_gate
def test_telemetry_baseline_precedes_launch_seed_before_allowed_seed_after_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_event = {"tool": "spawn_agent", "disposition": "suspended", "origin": "rook_agent", "timestamp": "2026-07-16T00:00:00.000000Z"}
    store = _Store(events=[old_event])
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", store=store)
    passed = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert passed.success is True

    second_root = tmp_path / "second"
    second_root.mkdir()
    store2 = _Store(events=[old_event])
    harness2 = _install_fake_scenario(monkeypatch, second_root, scenario="rhino", store=store2)
    original_close = live._request_graceful_close

    def close_and_add(proc, diagnostics):
        value = original_close(proc, diagnostics)
        store2.events.append({**old_event, "tool": "gh_execute_intent"})
        return value

    monkeypatch.setattr(live, "_request_graceful_close", close_and_add)
    failed = live.run_live_scenario(scenario="rhino", rhino_exe=harness2.rhino_exe, artifact_dir=harness2.artifact)
    assert failed.success is False and failed.failure_label == "telemetry_changed"


@requires_live_gate
@pytest.mark.parametrize("drift", ["reset", "truncated", "nonprefix"])
def test_telemetry_requires_before_events_as_exact_after_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift: str,
) -> None:
    first = {
        "tool": "spawn_agent",
        "disposition": "suspended",
        "origin": "rook_agent",
        "timestamp": "2026-07-16T00:00:00.000000Z",
    }
    second = {**first, "tool": "gh_execute_intent"}
    store = _Store(events=[first, second])
    harness = _install_fake_scenario(
        monkeypatch, tmp_path, scenario="rhino", store=store
    )
    original_close = live._request_graceful_close

    def close_and_drift(proc, diagnostics):
        value = original_close(proc, diagnostics)
        if drift == "reset":
            store.events.clear()
        elif drift == "truncated":
            store.events.pop()
        else:
            store.events[0] = {**first, "tool": "nonprefix_replacement"}
        return value

    monkeypatch.setattr(live, "_request_graceful_close", close_and_drift)
    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "telemetry_changed"


@requires_live_gate
def test_telemetry_process_token_or_accessor_replacement_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _Store()
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", store=store)
    original_close = live._request_graceful_close

    def close_and_drift(proc, diagnostics):
        value = original_close(proc, diagnostics)
        store.token = "b" * 32
        return value

    monkeypatch.setattr(live, "_request_graceful_close", close_and_drift)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "telemetry_changed"


@requires_live_gate
def test_force_cleanup_can_never_turn_success_green(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", graceful_forced=True)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert _load_final_artifact(harness.artifact, "rhino")["restoration"]["verified"] is False


@requires_live_gate
@pytest.mark.parametrize("returncode", [0, 7])
def test_cleanup_requires_process_live_at_entry_and_confirmed_graceful_close(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_restore = live._restore_rhino

    async def restore_then_process_exits(state, recorder):
        restored = await original_restore(state, recorder)
        harness.process.returncode = returncode
        harness.discovery.removed = True
        Path(harness.record.path).unlink()
        return restored

    monkeypatch.setattr(live, "_restore_rhino", restore_then_process_exits)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False, (
        f"{EXPECTED_RED}:CLEANUP_LIVE_ENTRY:returncode={returncode} "
        "an already-exited process was accepted as graceful cleanup"
    )
    assert result.failure_label == "cleanup_failed"
    assert result.restoration["verified"] is False
    assert harness.close_calls == []
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["restoration"]["verified"] is False


@requires_live_gate
@pytest.mark.parametrize("returncode", [0, 7])
def test_already_exited_cleanup_label_overrides_prior_restoration_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    async def restoration_fails_then_process_exits(state, recorder):
        state.result.restoration["attempted"] = True
        state.result.restoration["in_process_projection_matches_declared"] = False
        harness.process.returncode = returncode
        harness.discovery.removed = True
        Path(harness.record.path).unlink()
        return False

    monkeypatch.setattr(live, "_restore_rhino", restoration_fails_then_process_exits)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "cleanup_failed", (
        f"{EXPECTED_RED}:CLEANUP_EXIT_LABEL:returncode={returncode} "
        "an already-exited process did not take cleanup-failure precedence"
    )
    assert result.restoration["verified"] is False


@requires_live_gate
def test_stale_discovery_record_is_not_deleted_or_reported_as_restored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    def close_without_discovery_cleanup(proc, diagnostics):
        proc.wait()
        return False

    monkeypatch.setattr(live, "_request_graceful_close", close_without_discovery_cleanup)
    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert Path(harness.record.path).is_file()
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["restoration"]["discovery_removed"] is False
    assert evidence["restoration"]["verified"] is False


@requires_live_gate
@pytest.mark.parametrize("broken_path", ["scratch", "discovery"])
def test_cleanup_rejects_broken_scratch_or_discovery_link_as_successful_disposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    broken_path: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_close = live._request_graceful_close

    def close_then_install_broken_link(proc, diagnostics):
        result = original_close(proc, diagnostics)
        target = harness.scratch if broken_path == "scratch" else Path(harness.record.path)
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        _file_symlink_or_skip(target, tmp_path / f"missing-{broken_path}")
        return result

    monkeypatch.setattr(live, "_request_graceful_close", close_then_install_broken_link)

    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "cleanup_failed"
    assert result.restoration[
        "scratch_disposed" if broken_path == "scratch" else "discovery_removed"
    ] is False
    assert live._is_reparse(
        harness.scratch if broken_path == "scratch" else Path(harness.record.path)
    ) is True


@requires_live_gate
def test_cleanup_exception_uses_force_only_as_failed_diagnostic_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    force_calls: list[int] = []

    def close_raises(proc, diagnostics):
        raise RuntimeError("close transport failed")

    def force_cleanup(proc, diagnostics):
        force_calls.append(proc.pid)
        proc.kill()
        harness.discovery.removed = True
        Path(harness.record.path).unlink()
        return True

    monkeypatch.setattr(live, "_request_graceful_close", close_raises)
    monkeypatch.setattr(live, "_force_owned_cleanup", force_cleanup)
    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert force_calls == [harness.process.pid]
    assert harness.process.killed
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["restoration"]["verified"] is False


@requires_live_gate
def test_rhino_restoration_refuses_unvalidated_object_id_without_deletion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    unexpected_id = "55555555-5555-4555-8555-555555555555"
    root_claim = owned_claim_factory(harness.artifact)
    live._atomic_write_bytes(
        harness.scratch,
        b"fake-3dm",
        root_claim=root_claim,
    )
    harness.adapter.saved = True
    harness.adapter.modified = True
    harness.adapter.objects = {
        SPHERE_ID: {
            "id": SPHERE_ID,
            "name": f"RookContainmentSphere-{RUN_ID}",
            "type": "Brep",
        },
        unexpected_id: {
            "id": unexpected_id,
            "name": "Unexpected",
            "type": "Point",
        },
    }
    result = live._new_result("rhino", RUN_ID, live._utc_now())
    result.pre_state = {
        "host_projection": None,
        "host_sha256": None,
        "scratch_projection": {
            "runtime_serial": 41,
            "path": str(harness.scratch),
            "modified": False,
            "object_count": 0,
            "object_ids": [],
        },
        "scratch_sha256": None,
    }
    state = live._RunState(
        scenario="rhino",
        run_id=RUN_ID,
        artifact_dir=harness.artifact,
        rhino_exe=harness.rhino_exe,
        started_at=result.started_at,
        result=result,
        adapter=harness.adapter,
        scratch_path=harness.scratch,
        created_rhino_ids=[SPHERE_ID],
        root_claim=root_claim,
    )

    with pytest.raises(live.OwnershipAmbiguous, match="object"):
        asyncio.run(live._restore_rhino(state, live._OperationRecorder(state)))

    assert "rhino_delete" not in [name for name, _ in harness.adapter.calls]
    assert set(harness.adapter.objects) == {SPHERE_ID, unexpected_id}


def _direct_rhino_restoration_state(harness: Any, owned_claim_factory):
    root_claim = owned_claim_factory(harness.artifact)
    live._atomic_write_bytes(
        harness.scratch,
        b"fake-3dm",
        root_claim=root_claim,
    )
    harness.adapter.saved = True
    harness.adapter.modified = True
    harness.adapter.objects = {
        SPHERE_ID: {
            "id": SPHERE_ID,
            "name": f"RookContainmentSphere-{RUN_ID}",
            "type": "Brep",
        },
        POINT_ID: {
            "id": POINT_ID,
            "name": f"RookContainmentPoint-{RUN_ID}",
            "type": "Point",
        },
    }
    result = live._new_result("rhino", RUN_ID, live._utc_now())
    scratch_projection = {
        "runtime_serial": 41,
        "path": str(harness.scratch),
        "modified": False,
        "object_count": 0,
        "object_ids": [],
    }
    result.pre_state = {
        "host_projection": {
            "prior_active_document_runtime_serial": 41,
            "prior_path": "",
            "prior_modified": False,
        },
        "host_sha256": live._sha256_value(
            {
                "prior_active_document_runtime_serial": 41,
                "prior_path": "",
                "prior_modified": False,
            }
        ),
        "scratch_projection": scratch_projection,
        "scratch_sha256": live._sha256_value(scratch_projection),
    }
    return live._RunState(
        scenario="rhino",
        run_id=RUN_ID,
        artifact_dir=harness.artifact,
        rhino_exe=harness.rhino_exe,
        started_at=result.started_at,
        result=result,
        adapter=harness.adapter,
        scratch_path=harness.scratch,
        created_rhino_ids=[SPHERE_ID, POINT_ID],
        root_claim=root_claim,
    )


@requires_live_gate
@pytest.mark.parametrize("drift_phase", ["before_delete", "before_save"])
def test_rhino_restoration_revalidates_exact_scratch_identity_before_each_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift_phase: str,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    state = _direct_rhino_restoration_state(harness, owned_claim_factory)
    original = harness.adapter.call

    if drift_phase == "before_delete":
        harness.adapter.serial = 99

    async def drift_after_delete(name, arguments):
        result = await original(name, arguments)
        if drift_phase == "before_save" and name == "rhino_delete":
            harness.adapter.serial = 99
        return result

    harness.adapter.call = drift_after_delete

    try:
        asyncio.run(live._restore_rhino(state, live._OperationRecorder(state)))
    except live.OwnershipAmbiguous:
        pass
    else:
        pytest.fail(
            f"{EXPECTED_RED}:RHINO_RESTORE_REVALIDATE:{drift_phase} "
            "drifted scratch identity was not classified as ambiguous"
        )

    mutation_names = [
        name
        for name, _ in harness.adapter.calls
        if name in {"rhino_delete", "rhino_document_ops"}
    ]
    expected = [] if drift_phase == "before_delete" else ["rhino_delete"]
    assert mutation_names == expected, (
        f"{EXPECTED_RED}:RHINO_RESTORE_REVALIDATE:{drift_phase} "
        f"unexpected restorative mutation sequence: {mutation_names}"
    )


def _direct_grasshopper_restoration_state(harness: Any, owned_claim_factory):
    root_claim = owned_claim_factory(harness.artifact)
    harness.adapter.bootstrapped = True
    harness.adapter.opened = True
    harness.adapter.edited = False
    empty_snapshot = harness.adapter._snapshot()
    expected = live._snapshot_projection(
        empty_snapshot,
        process_id=harness.record.pid,
        process_token=PROCESS_TOKEN,
        port=harness.record.port,
        document_id=GH_DOCUMENT_ID,
        has_active_canvas=True,
    )
    harness.adapter.edited = True
    result = live._new_result("grasshopper", RUN_ID, live._utc_now())
    result.target = {
        "process_id": harness.record.pid,
        "port": harness.record.port,
        "process_start_token": PROCESS_TOKEN,
        "discovery_record_sha256": harness.record_sha256,
        "scratch_path": str(harness.scratch),
        "ownership_certain": True,
    }
    host_projection = {"has_active_canvas": False, "document_id": None}
    result.pre_state = {
        "host_projection": host_projection,
        "host_sha256": live._sha256_value(host_projection),
        "scratch_projection": expected,
        "scratch_sha256": live._sha256_value(expected),
    }
    state = live._RunState(
        scenario="grasshopper",
        run_id=RUN_ID,
        artifact_dir=harness.artifact,
        rhino_exe=harness.rhino_exe,
        started_at=result.started_at,
        result=result,
        record=harness.record,
        adapter=harness.adapter,
        scratch_path=harness.scratch,
        gh_edit_may_have_applied=True,
        root_claim=root_claim,
    )
    return state


@requires_live_gate
@pytest.mark.parametrize("observed_empty", [True, False])
def test_grasshopper_restoration_observes_once_when_edit_not_known_applied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    observed_empty: bool,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    state = _direct_grasshopper_restoration_state(harness, owned_claim_factory)
    state.gh_edit_may_have_applied = False
    harness.adapter.edited = not observed_empty

    restored = asyncio.run(
        live._restore_grasshopper(state, live._OperationRecorder(state))
    )

    assert restored is observed_empty
    assert state.result.restoration["in_process_projection_matches_declared"] is (
        observed_empty
    )
    assert [name for name, _ in harness.adapter.calls] == [
        "gh_snapshot",
        "gh_errors",
        "gh_status",
    ]
    assert harness.adapter.undo_count == 0


@requires_live_gate
@pytest.mark.parametrize(
    "integer_field",
    [
        "slider_min",
        "input_index",
        "source_count",
        "output_index",
        "output_count",
    ],
)
def test_grasshopper_restoration_rejects_boolean_integer_fields_before_undo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    integer_field: str,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    state = _direct_grasshopper_restoration_state(harness, owned_claim_factory)
    original = harness.adapter.call

    async def boolean_integer_observation(name, arguments):
        result = await original(name, arguments)
        if name != "gh_snapshot" or not harness.adapter.edited:
            return result
        result = copy.deepcopy(result)
        slider = result["data"]["components"][0]
        sphere = result["data"]["components"][1]
        if integer_field == "slider_min":
            slider["value"]["min"] = True
        elif integer_field == "input_index":
            sphere["inputs"][1]["idx"] = True
        elif integer_field == "source_count":
            sphere["inputs"][1]["sources"] = True
        elif integer_field == "output_index":
            sphere["outputs"][0]["idx"] = False
        else:
            sphere["outputs"][0]["data"]["count"] = True
        return result

    harness.adapter.call = boolean_integer_observation

    with pytest.raises(live.OwnershipAmbiguous):
        asyncio.run(
            live._restore_grasshopper(state, live._OperationRecorder(state))
        )

    assert harness.adapter.undo_count == 0
    assert "gh_undo" not in [name for name, _ in harness.adapter.calls]


@requires_live_gate
@pytest.mark.parametrize(
    "drift_case",
    [
        "different_document",
        "different_path",
        "different_canvas_token",
        "unexpected_component",
        "altered_component",
        "unexpected_wire",
        "object_count_bool",
        "expected_object_count_bool",
    ],
)
def test_grasshopper_restoration_revalidates_target_and_owned_state_before_undo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift_case: str,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    state = _direct_grasshopper_restoration_state(harness, owned_claim_factory)
    original = harness.adapter.call
    if drift_case == "different_canvas_token":
        state.result.pre_state["scratch_projection"]["gate_canvas_token"] = "f" * 64
    if drift_case == "expected_object_count_bool":
        state.result.pre_state["scratch_projection"]["object_count"] = False

    async def drift_restoration_observation(name, arguments):
        result = await original(name, arguments)
        if name == "gh_status" and drift_case == "different_document":
            result = copy.deepcopy(result)
            result["data"]["document_id"] = "55555555-5555-4555-8555-555555555555"
        if name == "gh_status" and drift_case == "object_count_bool":
            result = copy.deepcopy(result)
            result["data"]["object_count"] = True
        if name == "gh_snapshot" and harness.adapter.edited:
            result = copy.deepcopy(result)
            if drift_case == "different_path":
                result["data"]["document"]["path"] = str(tmp_path / "other.ghx")
            elif drift_case == "unexpected_component":
                result["data"]["components"].append(
                    {"id": "C9", "type": "Panel", "nick": "Unexpected", "pos": [0, 0]}
                )
            elif drift_case == "altered_component":
                result["data"]["components"][0]["value"]["val"] = 5
            elif drift_case == "unexpected_wire":
                result["data"]["flows"] = ["C1.O0>C2.I0"]
            elif drift_case == "object_count_bool":
                result["data"]["components"] = [result["data"]["components"][0]]
                result["data"]["flows"] = []
        return result

    harness.adapter.call = drift_restoration_observation

    try:
        asyncio.run(live._restore_grasshopper(state, live._OperationRecorder(state)))
    except live.OwnershipAmbiguous:
        pass
    else:
        pytest.fail(
            f"{EXPECTED_RED}:GH_RESTORE_REVALIDATE:{drift_case} "
            "unknown restoration target/state was not classified as ambiguous"
        )

    assert harness.adapter.undo_count == 0, (
        f"{EXPECTED_RED}:GH_RESTORE_REVALIDATE:{drift_case} "
        "gh_undo ran after ownership became ambiguous"
    )
    assert "gh_undo" not in [name for name, _ in harness.adapter.calls]


@requires_live_gate
@pytest.mark.parametrize("owned_subset", ["slider", "sphere", "components", "full"])
def test_grasshopper_restoration_allows_exact_code_owned_partial_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    owned_subset: str,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    state = _direct_grasshopper_restoration_state(harness, owned_claim_factory)
    original_snapshot = harness.adapter._snapshot
    original_status = harness.adapter._status

    def partial_snapshot():
        snapshot = original_snapshot()
        if not harness.adapter.edited:
            return snapshot
        components = snapshot["components"]
        if owned_subset == "slider":
            snapshot["components"] = [components[0]]
            snapshot["flows"] = []
        elif owned_subset == "sphere":
            snapshot["components"] = [components[1]]
            snapshot["components"][0]["inputs"][1]["sources"] = 0
            snapshot["flows"] = []
        elif owned_subset == "components":
            snapshot["components"][1]["inputs"][1]["sources"] = 0
            snapshot["flows"] = []
        return snapshot

    harness.adapter._snapshot = partial_snapshot

    def partial_status():
        status = original_status()
        if harness.adapter.edited and owned_subset in {"slider", "sphere"}:
            status["object_count"] = 1
        return status

    harness.adapter._status = partial_status

    restored = asyncio.run(
        live._restore_grasshopper(state, live._OperationRecorder(state))
    )

    assert restored is True
    assert harness.adapter.undo_count == 1


@requires_live_gate
def test_grasshopper_restoration_never_exceeds_four_undo_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def undo_without_restoring(name, arguments):
        if name == "gh_undo":
            harness.adapter.calls.append((name, copy.deepcopy(arguments)))
            harness.adapter.undo_count += 1
            return _success(
                {
                    "message": "Undo successful",
                    "epoch": 8 + harness.adapter.undo_count,
                    "snapshot": harness.adapter._snapshot(),
                }
            )
        return await original(name, arguments)

    harness.adapter.call = undo_without_restoring
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "restoration_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert names.count("gh_undo") == 4


@requires_live_gate
def test_grasshopper_requires_a_fresh_post_edit_epoch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_snapshot = harness.adapter._snapshot

    def stale_snapshot():
        snapshot = original_snapshot()
        if harness.adapter.edited:
            snapshot["epoch"] = 7
        return snapshot

    harness.adapter._snapshot = stale_snapshot
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"


@requires_live_gate
@pytest.mark.parametrize(
    "case",
    ["solve_not_scheduled", "deferred_false", "deferred_missing"],
)
def test_grasshopper_requires_exact_deferred_edit_solve_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def invalid_edit_solve_evidence(name, arguments):
        result = await original(name, arguments)
        if name == "gh_edit":
            result = copy.deepcopy(result)
            summary = result["data"]["edit_summary"]
            if case == "solve_not_scheduled":
                summary["solve_scheduled"] = False
            elif case == "deferred_false":
                summary["verification_deferred"] = False
            else:
                summary.pop("verification_deferred")
        return result

    harness.adapter.call = invalid_edit_solve_evidence
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"
    undo_count = [name for name, _ in harness.adapter.calls].count("gh_undo")
    assert 1 <= undo_count <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False


@requires_live_gate
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("solverEnabled", False),
        ("solverStateKnown", False),
        ("solutionState", "PreProcess"),
    ],
)
def test_grasshopper_requires_known_enabled_postprocess_solver_after_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def non_solved_status(name, arguments):
        result = await original(name, arguments)
        if name == "gh_status" and harness.adapter.edited:
            result = copy.deepcopy(result)
            result["data"][field] = value
        return result

    harness.adapter.call = non_solved_status
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"


@requires_live_gate
def test_partial_successful_gh_edit_is_undone_before_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def partial_edit(name, arguments):
        result = await original(name, arguments)
        if name == "gh_edit":
            result = copy.deepcopy(result)
            result["success"] = False
            result["partial_success"] = True
            result["verified"] = False
            result["data"]["edit_summary"]["errors"] = ["bounded edit partially applied"]
        return result

    harness.adapter.call = partial_edit
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "mutation_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert 1 <= names.count("gh_undo") <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False
    edit_operation = next(item for item in evidence["operations"] if item["name"] == "gh_edit")
    assert edit_operation["success"] is False


@requires_live_gate
def test_post_dispatch_gh_edit_result_write_failure_inspects_and_undoes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_write = live._atomic_write_bytes

    def fail_edit_result(path: Path, payload: bytes, **kwargs):
        if path.name.endswith("-gh_edit-result.json"):
            raise OSError("result evidence disk failure")
        return original_write(path, payload, **kwargs)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_edit_result)
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "mutation_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert "gh_edit" in names
    assert 1 <= names.count("gh_undo") <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False
    assert not any(item["name"] == "gh_edit" for item in evidence["operations"])
    orphan_arguments = [
        item
        for item in evidence["artifacts"]
        if item["relative_path"].endswith("-gh_edit-arguments.json")
    ]
    assert len(orphan_arguments) == 1
    assert not any(
        item["relative_path"].endswith("-gh_edit-result.json")
        for item in evidence["artifacts"]
    )


@requires_live_gate
def test_forward_mutation_failure_restores_only_when_ownership_is_certain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = harness.adapter.call

    async def fail_point(name, arguments):
        if name == "rhino_execute" and arguments != {"code": live.RUNTIME_SERIAL_CODE}:
            return {"success": False, "data": "point failed"}
        return await original(name, arguments)

    harness.adapter.call = fail_point
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label in {"mutation_failed", "restoration_failed"}
    names = [name for name, _ in harness.adapter.calls]
    assert "rhino_delete" in names
    assert "rhino_document_ops" in names

    second = tmp_path / "ambiguous"
    second.mkdir()
    harness2 = _install_fake_scenario(monkeypatch, second, scenario="rhino")
    original2 = harness2.adapter.call

    async def ambiguous(name, arguments):
        if name == "rhino_create":
            harness2.discovery.removed = True
            raise live.OwnershipAmbiguous("lost owned discovery")
        return await original2(name, arguments)

    harness2.adapter.call = ambiguous
    result2 = live.run_live_scenario(scenario="rhino", rhino_exe=harness2.rhino_exe, artifact_dir=harness2.artifact)
    assert result2.success is False and result2.failure_label == "ownership_ambiguous"
    names2 = [name for name, _ in harness2.adapter.calls]
    assert "rhino_delete" not in names2


@requires_live_gate
def test_operation_artifact_write_failure_stops_forward_work_and_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = live._atomic_write_bytes

    def fail_on_create(path: Path, payload: bytes, **kwargs):
        if "rhino_create-arguments" in path.name:
            raise OSError("disk full")
        return original(path, payload, **kwargs)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_on_create)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False
    names = [name for name, _ in harness.adapter.calls]
    assert "rhino_create" not in names


@requires_live_gate
def test_ownership_ambiguous_preserves_and_enumerates_grasshopper_scratch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def lose_ownership_after_scratch_copy(name, arguments):
        if name == "rhino_command":
            raise live.OwnershipAmbiguous("lost owned Grasshopper target")
        return await original(name, arguments)

    harness.adapter.call = lose_ownership_after_scratch_copy
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert result.success is False
    assert result.failure_label == "ownership_ambiguous"
    assert harness.scratch.is_file()
    scratch_items = [
        item
        for item in result.artifacts
        if item["relative_path"] == harness.scratch.name
    ]
    assert scratch_items == [
        {
            "kind": "scratch",
            "relative_path": harness.scratch.name,
            "sha256": live.FIXTURE_SHA256,
            "size": live.FIXTURE_SIZE,
        }
    ], f"{EXPECTED_RED}:SCRATCH_INVENTORY retained GHX was not hash-bound"
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
def test_consumer_rejects_missing_tampered_noncanonical_and_escaping_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    owned_claim_factory,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact).success
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    evidence_path = harness.artifact / "rhino-scenario.json"
    evidence = json.loads(evidence_path.read_bytes())
    operation_path = harness.artifact / evidence["operations"][0]["arguments_path"]
    original = operation_path.read_bytes()

    operation_path.unlink()
    with pytest.raises(live.LiveGateError, match="artifact"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    operation_path.write_bytes(original + b" ")
    with pytest.raises(live.LiveGateError, match="artifact"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    operation_path.write_bytes(original)

    evidence["operations"][0]["arguments_path"] = "../escape.json"
    root_claim = owned_claim_factory.reclaim(harness.artifact)
    live._write_final_evidence_pair(
        harness.artifact,
        "rhino",
        evidence,
        root_claim=root_claim,
    )
    with pytest.raises(live.LiveGateError, match="path"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_consumer_rejects_unenumerated_artifact_directory_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    (harness.artifact / "undeclared.bin").write_bytes(b"not inventoried")
    with pytest.raises(
        live.LiveGateError,
        match="inventory|enumerated",
    ):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_consumer_rejects_relative_root_before_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    monkeypatch.chdir(tmp_path)

    with pytest.raises(live.LiveGateError, match="absolute"):
        live._validate_scenario_artifacts(
            harness.artifact.relative_to(tmp_path), scenario="rhino"
        )


@requires_live_gate
def test_consumer_rejects_reparse_in_root_ancestor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    harness = _install_fake_scenario(monkeypatch, real, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    linked = tmp_path / "linked"
    _directory_symlink_or_skip(linked, real)

    with pytest.raises(live.LiveGateError, match="reparse"):
        live._validate_scenario_artifacts(
            linked / harness.artifact.relative_to(real), scenario="rhino"
        )


@requires_live_gate
def test_consumer_nonfollowing_walk_rejects_broken_reparse_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    broken = harness.artifact / "broken-entry"
    try:
        broken.symlink_to(harness.artifact / "missing-target")
    except OSError:
        pytest.skip("file symlinks/reparse points unavailable")
    assert live._is_reparse(broken) is True

    with pytest.raises(live.LiveGateError, match="reparse"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_consumer_nonfollowing_walk_rejects_directory_swapped_to_reparse_before_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    outside = tmp_path / "outside"
    nested.mkdir(parents=True)
    outside.mkdir()
    (outside / "payload.json").write_bytes(b"{}")
    original_scandir = live.os.scandir
    swapped = False

    def swapping_scandir(path: Path):
        nonlocal swapped
        if Path(path) == nested and not swapped:
            nested.rename(tmp_path / "original-nested")
            _directory_symlink_or_skip(nested, outside)
            swapped = True
        return original_scandir(path)

    monkeypatch.setattr(live.os, "scandir", swapping_scandir)

    with pytest.raises(live.LiveGateError, match="reparse|changed"):
        live._scan_artifact_tree_nonfollowing(root)
    assert swapped is False, "the swapped reparse target was traversed before drift detection"


@requires_live_gate
def test_consumer_holds_root_lease_before_first_artifact_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    redirected = tmp_path / "redirected-artifacts"
    shutil.copytree(harness.artifact, redirected)
    displaced = tmp_path / "displaced-artifacts"
    original_capture = live._capture_protected_artifact_tree
    blocked = False
    swapped = False

    def race_before_capture(root: Path, root_lease):
        nonlocal blocked, swapped
        try:
            root.rename(displaced)
        except PermissionError:
            blocked = True
        else:
            _directory_symlink_or_skip(root, redirected)
            swapped = True
        return original_capture(root, root_lease)

    monkeypatch.setattr(live, "_capture_protected_artifact_tree", race_before_capture)

    evidence = live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    assert evidence["success"] is True
    assert blocked is True
    assert swapped is False, "consumer root was redirected before its first read"


@requires_live_gate
def test_consumer_validates_only_from_handle_captured_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    original_read_bytes = Path.read_bytes

    def reject_artifact_path_read(path: Path) -> bytes:
        if path == harness.artifact or harness.artifact in path.parents:
            raise AssertionError(f"consumer fell back to a path read: {path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_artifact_path_read)

    evidence = live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    assert evidence["success"] is True


@requires_live_gate
def test_consumer_rejects_child_swap_immediately_after_entry_snapshot_without_traversal_or_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    operations = harness.artifact / "operations"
    displaced = tmp_path / "displaced-operations"
    redirected = tmp_path / "redirected-operations"
    shutil.copytree(operations, redirected)
    original_scandir = live.os.scandir
    original_inspect = live._inspect_directory_entry
    original_read_bytes = Path.read_bytes
    swapped = False
    traversed = False
    operation_path_reads: list[Path] = []

    def track_scandir(path: Path):
        nonlocal traversed
        if Path(path) == operations and swapped:
            traversed = True
        return original_scandir(path)

    def race_after_entry_snapshot(entry, candidate: Path, *args):
        nonlocal swapped
        snapshot = original_inspect(entry, candidate, *args)
        if Path(candidate) == operations and not swapped:
            operations.rename(displaced)
            _directory_symlink_or_skip(operations, redirected)
            swapped = True
        return snapshot

    def track_operation_path_reads(path: Path) -> bytes:
        if operations in path.parents:
            operation_path_reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(live.os, "scandir", track_scandir)
    monkeypatch.setattr(live, "_inspect_directory_entry", race_after_entry_snapshot)
    monkeypatch.setattr(Path, "read_bytes", track_operation_path_reads)

    with pytest.raises(
        live.LiveGateError,
        match="reparse|changed|identity",
    ) as caught:
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    assert swapped is True, f"race hook did not fire: {caught.value}"
    assert traversed is False, "consumer traversed the swapped child target"
    assert operation_path_reads == [], "consumer read child paths before protected capture"


@requires_live_gate
def test_consumer_entry_snapshot_binds_device_and_file_identity_before_open() -> None:
    entry_info = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_file_attributes=0,
        st_dev=101,
        st_ino=909,
    )
    replacement_info = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_file_attributes=0,
        st_dev=202,
        st_ino=909,
    )
    entry = SimpleNamespace(
        stat=lambda *, follow_symlinks: entry_info,
        inode=lambda: entry_info.st_ino,
    )
    candidate = SimpleNamespace(lstat=lambda: replacement_info)

    with pytest.raises(live.LiveGateError, match="identity"):
        live._inspect_directory_entry(entry, candidate)


@requires_live_gate
@pytest.mark.parametrize("kind", ["file", "directory"])
def test_consumer_rejects_same_kind_swap_at_fresh_lstat_gap_before_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
) -> None:
    root = tmp_path / "snapshot-root"
    root.mkdir()
    candidate = root / "candidate"
    replacement = root / "replacement"
    displaced = root / "displaced"
    if kind == "file":
        candidate.write_bytes(b"owned")
        replacement.write_bytes(b"replacement")
    else:
        candidate.mkdir()
        replacement.mkdir()
        (replacement / "external.json").write_bytes(b"external")
    with os.scandir(root) as iterator:
        entry = next(item for item in iterator if item.name == "candidate")
    original_lstat = Path.lstat
    original_acquire = live._acquire_windows_path_lease
    swapped = False
    opened_replacement = False

    def swap_before_fresh_lstat(path: Path):
        nonlocal swapped
        if path == candidate and not swapped:
            candidate.rename(displaced)
            replacement.rename(candidate)
            swapped = True
        return original_lstat(path)

    def track_open(path: Path, expected, expected_kind):
        nonlocal opened_replacement
        if Path(path) == candidate and swapped:
            opened_replacement = True
        return original_acquire(path, expected, expected_kind)

    monkeypatch.setattr(Path, "lstat", swap_before_fresh_lstat)
    monkeypatch.setattr(live, "_acquire_windows_path_lease", track_open)

    with pytest.raises(live.LiveGateError, match="identity"):
        live._inspect_directory_entry(entry, candidate)

    assert swapped is True
    assert opened_replacement is False


@requires_live_gate
def test_consumer_rejects_undeclared_directory_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    (harness.artifact / "undeclared-directory").mkdir()

    with pytest.raises(live.LiveGateError, match="directory|enumerated"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
@pytest.mark.parametrize(
    "mode",
    [stat.S_IFCHR | 0o600, stat.S_IFIFO | 0o600, stat.S_IFSOCK | 0o600],
)
def test_filesystem_entry_classifier_rejects_device_and_nonregular_modes(
    mode: int,
) -> None:
    info = SimpleNamespace(st_mode=mode, st_file_attributes=0)

    with pytest.raises(live.LiveGateError, match="non-regular"):
        live._filesystem_entry_kind(info)


@requires_live_gate
def test_safe_relative_rejects_reparse_traversal_before_resolving_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.json").write_bytes(b"{}")
    linked = root / "junction-like"
    _directory_symlink_or_skip(linked, outside)

    with pytest.raises(live.LiveGateError, match="reparse"):
        live._safe_relative(root, "junction-like/payload.json")


def _rewrite_final_evidence(
    artifact: Path,
    scenario: str,
    evidence: dict[str, Any],
) -> None:
    payload = live._canonical_json_bytes(evidence)
    (artifact / f"{scenario}-scenario.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (artifact / f"{scenario}-scenario.sha256").write_bytes(
        f"{digest}\n".encode("ascii")
    )


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_consumer_rejects_closed_nested_schema_tampering_with_valid_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    assert live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    evidence_path = harness.artifact / f"{scenario}-scenario.json"
    baseline = json.loads(evidence_path.read_bytes())
    host_wrong_field = (
        "prior_modified" if scenario == "rhino" else "has_active_canvas"
    )
    scratch_wrong_field = "object_count"

    def add_extra(section: str):
        return lambda item: item[section].__setitem__("unexpected", True)

    def remove_key(section: str, key: str):
        return lambda item: item[section].pop(key)

    def wrong_field(section: str, key: str, value: object):
        return lambda item: item[section].__setitem__(key, value)

    cases = [
        ("schema_version_bool", lambda item: item.__setitem__("schema_version", True)),
        ("run_id_wrong_type", lambda item: item.__setitem__("run_id", 1)),
        ("started_at_wrong_type", lambda item: item.__setitem__("started_at", None)),
        ("runtime_extra", add_extra("runtime")),
        ("runtime_missing", remove_key("runtime", "cwd")),
        ("runtime_wrong_type", wrong_field("runtime", "sys_path", "not-an-array")),
        ("target_extra", add_extra("target")),
        ("target_missing", remove_key("target", "port")),
        ("target_wrong_type", wrong_field("target", "process_id", "9001")),
        ("authorization_extra", add_extra("authorization")),
        ("authorization_missing", remove_key("authorization", "nonce")),
        ("authorization_wrong_type", wrong_field("authorization", "state_unchanged", 1)),
        ("pre_state_extra", add_extra("pre_state")),
        ("pre_state_missing", remove_key("pre_state", "host_sha256")),
        ("pre_state_wrong_type", wrong_field("pre_state", "host_sha256", None)),
        (
            "host_projection_extra",
            lambda item: item["pre_state"]["host_projection"].__setitem__(
                "unexpected", True
            ),
        ),
        (
            "host_projection_missing",
            lambda item: item["pre_state"]["host_projection"].pop(
                host_wrong_field
            ),
        ),
        (
            "host_projection_wrong_type",
            lambda item: item["pre_state"]["host_projection"].__setitem__(
                host_wrong_field, 1
            ),
        ),
        (
            "scratch_projection_extra",
            lambda item: item["pre_state"]["scratch_projection"].__setitem__(
                "unexpected", True
            ),
        ),
        (
            "scratch_projection_missing",
            lambda item: item["pre_state"]["scratch_projection"].pop("path"),
        ),
        (
            "scratch_projection_wrong_type",
            lambda item: item["pre_state"]["scratch_projection"].__setitem__(
                scratch_wrong_field, True
            ),
        ),
        ("verification_extra", add_extra("verification")),
        ("verification_missing", remove_key("verification", "warnings")),
        ("verification_wrong_type", wrong_field("verification", "passed", 1)),
        ("restoration_extra", add_extra("restoration")),
        ("restoration_missing", remove_key("restoration", "discovery_removed")),
        ("restoration_wrong_type", wrong_field("restoration", "verified", 1)),
        ("telemetry_extra", add_extra("telemetry")),
        ("telemetry_missing", remove_key("telemetry", "events_added")),
        ("telemetry_wrong_type", wrong_field("telemetry", "delta_count", False)),
        ("diagnostics_wrong_type", lambda item: item.__setitem__("diagnostics", {})),
        (
            "diagnostic_entry_extra",
            lambda item: item.__setitem__(
                "diagnostics",
                [
                    {
                        "stage": "scenario",
                        "label": "verification_failed",
                        "relative_path": "diagnostics/001.json",
                        "sha256": "0" * 64,
                        "unexpected": True,
                    }
                ],
            ),
        ),
        (
            "diagnostic_entry_missing",
            lambda item: item.__setitem__(
                "diagnostics",
                [
                    {
                        "stage": "scenario",
                        "label": "verification_failed",
                        "relative_path": "diagnostics/001.json",
                    }
                ],
            ),
        ),
        ("success_runtime_null", lambda item: item.__setitem__("runtime", None)),
        ("success_target_null", lambda item: item.__setitem__("target", None)),
        ("success_authorization_null", lambda item: item.__setitem__("authorization", None)),
        ("success_pre_state_null", lambda item: item.__setitem__("pre_state", None)),
        ("success_telemetry_null", lambda item: item.__setitem__("telemetry", None)),
        (
            "success_authorized_at_null",
            lambda item: item["authorization"].__setitem__("authorized_at", None),
        ),
        (
            "success_pre_mutation_null",
            lambda item: item["authorization"].__setitem__(
                "pre_mutation_sha256", None
            ),
        ),
        (
            "success_verification_projection_null",
            lambda item: item["verification"].update(
                {"projection": None, "projection_sha256": None}
            ),
        ),
        (
            "success_restoration_unverified",
            lambda item: item["restoration"].__setitem__("verified", False),
        ),
        (
            "success_telemetry_final_null",
            lambda item: item["telemetry"].update(
                {"after_sha256": None, "delta_count": None, "events_added": None}
            ),
        ),
    ]
    accepted: list[str] = []
    for label, mutate in cases:
        tampered = copy.deepcopy(baseline)
        mutate(tampered)
        _rewrite_final_evidence(harness.artifact, scenario, tampered)
        try:
            live._validate_scenario_artifacts(
                harness.artifact,
                scenario=scenario,
            )
        except live.LiveGateError:
            pass
        else:
            accepted.append(label)

    _rewrite_final_evidence(harness.artifact, scenario, baseline)
    assert accepted == [], (
        f"{EXPECTED_RED}:CLOSED_NESTED_SCHEMA:{scenario} accepted={accepted}"
    )
    live._validate_scenario_artifacts(harness.artifact, scenario=scenario)


@requires_live_gate
def test_consumer_rejects_failure_stage_fabrication_with_valid_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    baseline = _load_final_artifact(harness.artifact, "rhino")

    def failure_shape(label: str) -> dict[str, Any]:
        evidence = copy.deepcopy(baseline)
        evidence["success"] = False
        evidence["failure_label"] = label
        evidence["operations"] = []
        if label == "runtime_origin_invalid":
            for field in ("target", "authorization", "pre_state", "telemetry"):
                evidence[field] = None
        elif label == "launch_failed":
            for field in ("target", "authorization", "pre_state"):
                evidence[field] = None
        elif label == "readiness_failed":
            evidence["authorization"] = None
            evidence["pre_state"] = None
        elif label == "preflight_blocked":
            evidence["authorization"] = None
            evidence["pre_state"] = None
        elif label == "authorization_rejected":
            evidence["authorization"].update(
                {
                    "authorized_at": None,
                    "pre_mutation_sha256": None,
                    "state_unchanged": False,
                }
            )
        return evidence

    cases = [
        ("runtime_target", "runtime_origin_invalid", ("target",)),
        ("runtime_pre_state", "runtime_origin_invalid", ("target", "pre_state")),
        (
            "runtime_authorization",
            "runtime_origin_invalid",
            ("target", "pre_state", "authorization"),
        ),
        ("runtime_telemetry", "runtime_origin_invalid", ("telemetry",)),
        ("launch_target", "launch_failed", ("target",)),
        ("launch_pre_state", "launch_failed", ("target", "pre_state")),
        (
            "launch_authorization",
            "launch_failed",
            ("target", "pre_state", "authorization"),
        ),
        ("readiness_pre_state", "readiness_failed", ("pre_state",)),
        (
            "readiness_authorization",
            "readiness_failed",
            ("pre_state", "authorization"),
        ),
        ("preflight_operations", "preflight_blocked", ("operations",)),
        (
            "authorization_operations",
            "authorization_rejected",
            ("operations",),
        ),
    ]
    accepted: list[str] = []
    for case, label, fabricated_fields in cases:
        tampered = failure_shape(label)
        for field in fabricated_fields:
            tampered[field] = copy.deepcopy(baseline[field])
        if label == "authorization_rejected":
            tampered["authorization"].update(
                {
                    "authorized_at": None,
                    "pre_mutation_sha256": None,
                    "state_unchanged": False,
                }
            )
        _rewrite_final_evidence(harness.artifact, "rhino", tampered)
        try:
            live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
        except live.LiveGateError:
            pass
        else:
            accepted.append(case)

    _rewrite_final_evidence(harness.artifact, "rhino", baseline)
    assert accepted == [], (
        f"{EXPECTED_RED}:FAILURE_STAGE_INVARIANTS accepted={accepted}"
    )


@requires_live_gate
def test_consumer_reconstructs_authorization_and_rejects_impossible_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    baseline = _load_final_artifact(harness.artifact, "rhino")

    def failed_evidence() -> dict[str, Any]:
        evidence = copy.deepcopy(baseline)
        evidence["success"] = False
        evidence["failure_label"] = "cleanup_failed"
        return evidence

    cases: list[tuple[str, dict[str, Any]]] = []
    wrong_challenge = failed_evidence()
    wrong_challenge["authorization"]["challenge_sha256"] = "f" * 64
    cases.append(("challenge_sha256", wrong_challenge))

    missing_authorized_at = failed_evidence()
    missing_authorized_at["authorization"].update(
        {"authorized_at": None, "state_unchanged": False}
    )
    cases.append(("pre_mutation_without_authorized_at", missing_authorized_at))

    unchanged_without_projection = failed_evidence()
    unchanged_without_projection["authorization"].update(
        {"pre_mutation_sha256": None, "state_unchanged": True}
    )
    cases.append(("unchanged_without_pre_mutation", unchanged_without_projection))

    equal_but_claimed_changed = failed_evidence()
    equal_but_claimed_changed["authorization"]["state_unchanged"] = False
    cases.append(("equal_hashes_claimed_changed", equal_but_claimed_changed))

    mismatched_but_claimed_unchanged = copy.deepcopy(baseline)
    mismatched_but_claimed_unchanged["authorization"]["pre_mutation_sha256"] = "f" * 64
    cases.append(("different_hashes_claimed_unchanged", mismatched_but_claimed_unchanged))

    accepted: list[str] = []
    for case, tampered in cases:
        _rewrite_final_evidence(harness.artifact, "rhino", tampered)
        try:
            live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
        except live.LiveGateError:
            pass
        else:
            accepted.append(case)
    assert accepted == [], (
        f"{EXPECTED_RED}:AUTHORIZATION_STATE_MACHINE accepted={accepted}"
    )

    interrupted_revalidation = failed_evidence()
    interrupted_revalidation["failure_label"] = "state_drift"
    interrupted_revalidation["operations"] = []
    interrupted_revalidation["authorization"].update(
        {"pre_mutation_sha256": None, "state_unchanged": False}
    )
    _rewrite_final_evidence(harness.artifact, "rhino", interrupted_revalidation)
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")

    _rewrite_final_evidence(harness.artifact, "rhino", baseline)
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_consumer_requires_canonical_bound_ownership_marker_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    ).success
    baseline = _load_final_artifact(harness.artifact, "rhino")
    marker_path = harness.artifact / live.OWNERSHIP_MARKER
    baseline_marker = marker_path.read_bytes()
    expected_marker = json.loads(baseline_marker)

    def marker_item(evidence: dict[str, Any]) -> dict[str, Any]:
        return next(
            item
            for item in evidence["artifacts"]
            if item["relative_path"] == live.OWNERSHIP_MARKER
        )

    cases: list[tuple[str, dict[str, Any], bytes]] = []
    missing = copy.deepcopy(baseline)
    missing["artifacts"] = [
        item
        for item in missing["artifacts"]
        if item["relative_path"] != live.OWNERSHIP_MARKER
    ]
    cases.append(("missing_inventory", missing, baseline_marker))

    wrong_kind = copy.deepcopy(baseline)
    marker_item(wrong_kind)["kind"] = "diagnostic"
    cases.append(("wrong_kind", wrong_kind, baseline_marker))

    for case, updates in (
        ("wrong_run_id", {"run_id": "f" * 32}),
        ("wrong_process_id", {"process_id": expected_marker["process_id"] + 1}),
        ("wrong_schema_version", {"schema_version": live.SCHEMA_VERSION + 1}),
        ("extra_key", {"unexpected": True}),
    ):
        evidence = copy.deepcopy(baseline)
        payload = live._canonical_json_bytes({**expected_marker, **updates})
        item = marker_item(evidence)
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["size"] = len(payload)
        cases.append((case, evidence, payload))

    noncanonical = json.dumps(expected_marker, indent=2).encode("utf-8")
    noncanonical_evidence = copy.deepcopy(baseline)
    item = marker_item(noncanonical_evidence)
    item["sha256"] = hashlib.sha256(noncanonical).hexdigest()
    item["size"] = len(noncanonical)
    cases.append(("noncanonical_content", noncanonical_evidence, noncanonical))

    accepted: list[str] = []
    for case, tampered, marker_payload in cases:
        marker_path.write_bytes(marker_payload)
        _rewrite_final_evidence(harness.artifact, "rhino", tampered)
        try:
            live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
        except live.LiveGateError:
            pass
        else:
            accepted.append(case)

    marker_path.write_bytes(baseline_marker)
    _rewrite_final_evidence(harness.artifact, "rhino", baseline)
    assert accepted == [], (
        f"{EXPECTED_RED}:OWNERSHIP_MARKER_BINDING accepted={accepted}"
    )
    monkeypatch.setattr(
        live.os,
        "getpid",
        lambda: expected_marker["process_id"] + 1000,
    )
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
@pytest.mark.parametrize("failure_site", ["payload", "sidecar", "registration"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_diagnostic_persistence_failure_cleans_owned_host_and_suppresses_final_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_site: str,
    error_type: type[BaseException],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original_call = harness.adapter.call
    original_write = live._atomic_write_bytes
    original_register = live._register_artifact
    injected = error_type(f"diagnostic {failure_site} persistence failure")

    async def fail_after_mutation(name: str, arguments: dict[str, Any]):
        if name == "rhino_geometry":
            raise RuntimeError("post-mutation verification failure")
        return await original_call(name, arguments)

    def fail_diagnostic_write(path: Path, payload: bytes, **kwargs):
        is_diagnostic = path.parent.name == "diagnostics"
        if is_diagnostic and (
            (failure_site == "payload" and path.suffix == ".json")
            or (failure_site == "sidecar" and path.name.endswith(".json.sha256"))
        ):
            raise injected
        return original_write(path, payload, **kwargs)

    def fail_diagnostic_registration(result, path, root, kind):
        if failure_site == "registration" and kind == "diagnostic":
            raise injected
        return original_register(result, path, root, kind)

    harness.adapter.call = fail_after_mutation
    monkeypatch.setattr(live, "_atomic_write_bytes", fail_diagnostic_write)
    monkeypatch.setattr(live, "_register_artifact", fail_diagnostic_registration)

    if isinstance(injected, Exception):
        with pytest.raises(live.FinalEvidenceWriteError, match="diagnostic"):
            live.run_live_scenario(
                scenario="rhino",
                rhino_exe=harness.rhino_exe,
                artifact_dir=harness.artifact,
            )
    else:
        with pytest.raises(error_type) as caught:
            live.run_live_scenario(
                scenario="rhino",
                rhino_exe=harness.rhino_exe,
                artifact_dir=harness.artifact,
            )
        assert caught.value is injected

    assert harness.close_calls == [harness.process.pid]
    assert harness.process.poll() is not None
    assert harness.adapter.objects == {}
    assert not harness.scratch.exists()
    assert not Path(harness.record.path).exists()
    assert not (harness.artifact / "rhino-scenario.json").exists()
    assert not (harness.artifact / "rhino-scenario.sha256").exists()
    diagnostics = harness.artifact / "diagnostics"
    assert not diagnostics.exists() or list(diagnostics.iterdir()) == []
    assert "scenario_result" not in capsys.readouterr().out


@requires_live_gate
def test_final_evidence_write_failure_emits_no_fabricated_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = live._atomic_write_bytes

    def fail_final(path: Path, payload: bytes, **kwargs):
        if path.name == "rhino-scenario.json":
            raise OSError("final disk failure")
        return original(path, payload, **kwargs)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_final)
    with pytest.raises(live.FinalEvidenceWriteError):
        live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    stdout = capsys.readouterr().out
    assert "scenario_result" not in stdout
    assert not (harness.artifact / "rhino-scenario.json").exists()
    assert not (harness.artifact / "rhino-scenario.sha256").exists()


@requires_live_gate
@pytest.mark.parametrize("failure_site", ["evidence", "sidecar"])
@pytest.mark.parametrize(
    "error_type", [OSError, _FinalPairBaseInterrupt, KeyboardInterrupt]
)
def test_final_evidence_pair_cleans_both_paths_and_preserves_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_site: str,
    error_type: type[BaseException],
    owned_claim_factory,
) -> None:
    artifact = tmp_path / "artifacts"
    root_claim = owned_claim_factory(artifact)
    evidence_path = artifact / "rhino-scenario.json"
    sidecar = artifact / "rhino-scenario.sha256"
    live._atomic_write_bytes(
        evidence_path,
        b"stale-evidence",
        root_claim=root_claim,
    )
    live._atomic_write_bytes(
        sidecar,
        b"stale-sidecar",
        root_claim=root_claim,
    )
    original = live._atomic_write_bytes
    injected = error_type(f"final {failure_site} write interrupted")

    def fail_selected(path: Path, payload: bytes, **kwargs):
        if (
            failure_site == "evidence"
            and path == evidence_path
            or failure_site == "sidecar"
            and path == sidecar
        ):
            raise injected
        return original(path, payload, **kwargs)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_selected)
    if isinstance(injected, Exception):
        with pytest.raises(live.FinalEvidenceWriteError):
            live._write_final_evidence_pair(
                artifact,
                "rhino",
                {"schema_version": live.SCHEMA_VERSION},
                root_claim=root_claim,
            )
    else:
        with pytest.raises(error_type) as caught:
            live._write_final_evidence_pair(
                artifact,
                "rhino",
                {"schema_version": live.SCHEMA_VERSION},
                root_claim=root_claim,
            )
        assert caught.value is injected

    assert not evidence_path.exists()
    assert not sidecar.exists()


@requires_live_gate
def test_main_exit_codes_and_bounded_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rhino = tmp_path / "Rhino.exe"
    rhino.write_bytes(b"fake")
    missing_parent = tmp_path / "missing" / "artifacts"
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(missing_parent)]) == 2
    assert 0 < len(stderr.getvalue()) <= 1200

    success_root = tmp_path / "success"
    success_root.mkdir()
    harness = _install_fake_scenario(monkeypatch, success_root, scenario="rhino")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(harness.rhino_exe), "--artifact-dir", str(harness.artifact)]) == 0

    blocked_root = tmp_path / "blocked"
    blocked_root.mkdir()
    harness2 = _install_fake_scenario(monkeypatch, blocked_root, scenario="rhino", authorization="wrong")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(harness2.rhino_exe), "--artifact-dir", str(harness2.artifact)]) == 2


@requires_live_gate
def test_early_failure_null_invariants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rhino = tmp_path / "Rhino.exe"
    rhino.write_bytes(b"fake")
    artifact = tmp_path / "origin"
    monkeypatch.setattr(live, "_new_run_id", lambda: RUN_ID)
    monkeypatch.setattr(live, "_collect_and_validate_runtime_evidence", lambda: (_ for _ in ()).throw(live.LiveGateError("bad origin")))
    result = live.run_live_scenario(scenario="rhino", rhino_exe=rhino, artifact_dir=artifact)
    evidence = _load_final_artifact(artifact, "rhino")
    assert result.failure_label == "runtime_origin_invalid"
    assert evidence["target"] is None
    assert evidence["authorization"] is None
    assert evidence["pre_state"] is None
    assert evidence["telemetry"] is None
    live._validate_scenario_artifacts(artifact, scenario="rhino")


@requires_live_gate
def test_cli_is_absent_from_mcp_model_and_contained_surfaces() -> None:
    from rook import server

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert "containment_live_gate" not in names
    assert "run_live_scenario" not in names
    assert not hasattr(server, "containment_live_gate")
    source = Path(live.__file__).read_text(encoding="utf-8")
    for contained in live.CONTAINED_IDENTITIES:
        assert re.search(rf"[\"']{re.escape(contained)}[\"']", source) is None
    for forbidden in ("gh_solve", "gh_document_new"):
        assert re.search(rf"[\"']{re.escape(forbidden)}[\"']", source) is None
