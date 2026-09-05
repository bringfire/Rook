from __future__ import annotations

import importlib.util
import asyncio
import json
import sys
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "vertex_oauth_acceptance.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("vertex_oauth_acceptance", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        pytest.fail("Vertex acceptance harness is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path: Path):
    local_app_data = tmp_path / "LocalAppData"
    installed_python = local_app_data / "Rook" / "venv" / "Scripts" / "python.exe"
    installed_python.parent.mkdir(parents=True)
    installed_python.write_text("", encoding="utf-8")
    temp_root = tmp_path / "Temp"
    temp_root.mkdir()
    evidence_root = temp_root / "rook-vertex-acceptance-0123456789abcdef"
    evidence_root.mkdir()
    client_path = tmp_path / "desktop-client.json"
    client_path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "client-secret-sentinel",
                }
            }
        ),
        encoding="utf-8",
    )
    boundary = SimpleNamespace(
        executable=installed_python,
        local_app_data=local_app_data,
        temp_root=temp_root,
        script_path=SCRIPT_PATH,
        expected_rook_commit="a" * 40,
        expected_chirp_commit="b" * 40,
    )
    argv = [
        "--acceptance-level",
        "technical",
        "--project",
        "company-ai-project",
        "--region",
        "us-central1",
        "--model",
        "vertex_ai/gemini-2.5-pro",
        "--desktop-client-json",
        str(client_path),
        "--evidence-root",
        str(evidence_root),
        "--watchdog-seconds",
        "900",
        "--run-consumers",
    ]
    return boundary, argv, evidence_root


def _passing_operations(module, calls: list[str] | None = None):
    calls = calls if calls is not None else []

    def provenance():
        calls.append("provenance")
        return {
            "rook_commit": "a" * 40,
            "chirp_commit": "b" * 40,
            "installed_versions": {
                "rook-mcp": "1.5.18",
                "chirp": "0.1.0",
                "google-auth": "2.56.3",
            },
        }

    def connect(_client, _project, _region):
        calls.append("connect")
        return SimpleNamespace(success=True, code=None)

    def readiness(_model):
        calls.append("readiness")
        return SimpleNamespace(success=True, code=None)

    async def dspy(_model, _marker):
        calls.append("dspy")

    async def chirp(_model, _marker, _evidence_root):
        calls.append("chirp")
        return {
            "chirp": "passed",
            "canvas_cleanup": "passed",
            "process_cleanup": "passed",
        }

    def disconnect():
        calls.append("disconnect")
        return SimpleNamespace(success=True, code=None)

    return module.AcceptanceOperations(
        provenance=provenance,
        connect=connect,
        readiness=readiness,
        dspy=dspy,
        chirp=chirp,
        disconnect=disconnect,
    )


def test_requires_exact_installed_interpreter_before_connect(tmp_path):
    module = _load_harness()
    boundary, argv, _evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    boundary.executable = tmp_path / "source" / ".venv" / "Scripts" / "python.exe"

    result = module.run(
        argv,
        boundary=boundary,
        operations=_passing_operations(module, calls),
    )

    assert result == 1
    assert calls == []


@pytest.mark.parametrize(
    "replacement",
    [
        ["--model", "vertex_ai/claude-opus-5"],
        ["--model", "gemini/gemini-2.5-pro"],
        ["--watchdog-seconds", "0"],
    ],
)
def test_invalid_model_or_watchdog_fails_before_connect(tmp_path, replacement):
    module = _load_harness()
    boundary, argv, _evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    option = replacement[0]
    index = argv.index(option)
    argv[index : index + 2] = replacement

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    assert calls == []


def test_live_call_acknowledgement_is_required_before_connect(tmp_path):
    module = _load_harness()
    boundary, argv, _evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    argv.remove("--run-consumers")

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    assert calls == []


def test_evidence_root_must_be_owned_temp_child(tmp_path):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    outside = tmp_path / "arbitrary-output"
    outside.mkdir()
    index = argv.index(str(evidence_root))
    argv[index] = str(outside)

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    assert calls == []
    assert not (outside / "result.json").exists()


def test_nonempty_evidence_root_without_ownership_sentinel_is_refused(tmp_path):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    (evidence_root / "foreign.txt").write_text("keep", encoding="utf-8")

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    assert calls == []
    assert (evidence_root / "foreign.txt").read_text(encoding="utf-8") == "keep"


def test_production_readiness_requires_all_four_acknowledgements(tmp_path):
    module = _load_harness()
    boundary, argv, _evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    argv[argv.index("technical")] = "production"

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    assert calls == []


def test_technical_run_writes_only_redacted_allowlisted_evidence(tmp_path):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    calls: list[str] = []

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 0
    payload = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert set(payload) == module.RESULT_KEYS
    assert payload["success"] is True
    assert payload["acceptance_level"] == "technical_pass"
    assert payload["stages"] == {
        "installed_provenance": "passed",
        "oauth": "passed",
        "readiness": "passed",
        "dspy": "passed",
        "chirp": "passed",
        "canvas_cleanup": "passed",
        "process_cleanup": "passed",
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "company-ai-project",
        "us-central1",
        "gemini-2.5-pro",
        "client-id.apps.googleusercontent.com",
        "client-secret-sentinel",
    ):
        assert forbidden not in serialized
    assert calls == ["provenance", "connect", "readiness", "dspy", "chirp"]


def test_production_run_can_report_production_ready(tmp_path):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    argv[argv.index("technical")] = "production"
    argv.extend(
        [
            "--production-client-ready",
            "--google-verification-complete",
            "--enterprise-admin-guidance-published",
            "--managed-business-production-validated",
        ]
    )

    assert module.run(argv, boundary=boundary, operations=_passing_operations(module)) == 0

    payload = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert payload["acceptance_level"] == "production_ready"


def test_body_and_cleanup_failures_are_preserved_as_stage_statuses(tmp_path):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    operations = _passing_operations(module)

    async def fail_chirp(_model, _marker, _root):
        raise module.AcceptanceFailure(
            "vertex_chirp_and_cleanup_failed",
            stages={
                "chirp": "failed",
                "canvas_cleanup": "failed",
                "process_cleanup": "failed",
            },
        )

    operations = module.AcceptanceOperations(
        provenance=operations.provenance,
        connect=operations.connect,
        readiness=operations.readiness,
        dspy=operations.dspy,
        chirp=fail_chirp,
        disconnect=operations.disconnect,
    )

    assert module.run(argv, boundary=boundary, operations=operations) == 1

    payload = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["acceptance_level"] == "failed"
    assert payload["error_code"] == "vertex_chirp_and_cleanup_failed"
    assert payload["stages"]["chirp"] == "failed"
    assert payload["stages"]["canvas_cleanup"] == "failed"
    assert payload["stages"]["process_cleanup"] == "failed"


def test_dspy_predicate_requires_marker():
    module = _load_harness()
    marker = "rook-vertex-marker-01234567"

    module.validate_dspy_result(SimpleNamespace(echoed_marker=marker), marker)

    with pytest.raises(module.AcceptanceFailure):
        module.validate_dspy_result(SimpleNamespace(echoed_marker="wrong"), marker)


def test_provenance_reads_chirp_from_its_separate_installed_runtime(
    monkeypatch,
    tmp_path,
):
    module = _load_harness()
    boundary, _argv, _evidence_root = _fixture(tmp_path)
    rook_module_path = (
        boundary.local_app_data
        / "Rook"
        / "venv"
        / "Lib"
        / "site-packages"
        / "rook"
        / "__init__.py"
    )
    rook_module_path.parent.mkdir(parents=True)
    rook_module_path.write_text("", encoding="utf-8")
    manifest_path = (
        boundary.local_app_data / "Rook" / "app" / "python-runtime-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"rook_git_sha": "a" * 40, "chirp_git_sha": "b" * 40}),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "rook", SimpleNamespace(__file__=rook_module_path))
    monkeypatch.setattr(
        module.metadata,
        "version",
        lambda name: {
            "rook-mcp": "1.5.18",
            "google-auth": "2.56.3",
            "mcp": "1.28.1",
        }[name],
    )
    monkeypatch.setattr(
        module,
        "_read_installed_chirp_version",
        lambda _boundary: "0.1.0",
    )

    result = module._verify_installed_provenance(boundary)

    assert result["installed_versions"]["chirp"] == "0.1.0"


def test_chirp_child_receives_scoped_model_and_marker_without_persisting_them(
    monkeypatch,
    tmp_path,
):
    module = _load_harness()
    boundary, _argv, evidence_root = _fixture(tmp_path)
    model = "vertex_ai/gemini-2.5-pro"
    marker = "rook-vertex-marker-01234567"
    captured = {}

    class CleanupStatus(Enum):
        GRACEFUL_EXIT = "graceful_exit"

    def fake_harness(**_kwargs):
        captured["model"] = module.os.environ.get("ROOK_VERTEX_ACCEPTANCE_MODEL")
        captured["marker"] = module.os.environ.get("ROOK_VERTEX_ACCEPTANCE_MARKER")
        return SimpleNamespace(
            smoke=SimpleNamespace(
                stdout=json.dumps(
                    {
                        "schema_version": 1,
                        "chirp": "passed",
                        "canvas_cleanup": "passed",
                    }
                )
            ),
            cleanup_status=CleanupStatus.GRACEFUL_EXIT,
            success=True,
        )

    monkeypatch.setitem(
        sys.modules,
        "rook.runtime_harness",
        SimpleNamespace(
            CleanupStatus=CleanupStatus,
            run_rhino_runtime_harness=fake_harness,
        ),
    )
    monkeypatch.delenv("ROOK_VERTEX_ACCEPTANCE_MODEL", raising=False)
    monkeypatch.delenv("ROOK_VERTEX_ACCEPTANCE_MARKER", raising=False)

    stages = asyncio.run(
        module._run_chirp(model, marker, evidence_root, boundary)
    )

    assert stages == {
        "chirp": "passed",
        "canvas_cleanup": "passed",
        "process_cleanup": "passed",
    }
    assert captured == {"model": model, "marker": marker}
    assert "ROOK_VERTEX_ACCEPTANCE_MODEL" not in module.os.environ
    assert "ROOK_VERTEX_ACCEPTANCE_MARKER" not in module.os.environ


@pytest.mark.parametrize(
    "expected_field",
    ["expected_rook_commit", "expected_chirp_commit"],
)
def test_valid_but_wrong_installed_commits_fail_before_oauth(
    tmp_path,
    expected_field,
):
    module = _load_harness()
    boundary, argv, evidence_root = _fixture(tmp_path)
    calls: list[str] = []
    setattr(boundary, expected_field, "c" * 40)

    result = module.run(argv, boundary=boundary, operations=_passing_operations(module, calls))

    assert result == 1
    payload = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert payload["error_code"] == "vertex_acceptance_provenance_mismatch"
    assert payload["stages"] == {}
    assert calls == ["provenance"]


def test_dspy_timeout_cancels_async_prediction_without_starting_sync_worker(
    monkeypatch,
):
    module = _load_harness()
    marker = "rook-vertex-marker-01234567"
    state = {"sync_called": False, "async_started": False, "async_cancelled": False}

    class FakeSignature:
        pass

    class FakePrediction:
        def __call__(self, **_kwargs):
            state["sync_called"] = True
            time.sleep(0.4)
            return SimpleNamespace(echoed_marker=marker)

        async def acall(self, **_kwargs):
            state["async_started"] = True
            try:
                await asyncio.Event().wait()
            finally:
                state["async_cancelled"] = True

    fake_lm = SimpleNamespace(
        model="vertex_ai/gemini-2.5-pro",
        kwargs={},
    )
    monkeypatch.setitem(
        sys.modules,
        "dspy",
        SimpleNamespace(
            Signature=FakeSignature,
            InputField=lambda: None,
            OutputField=lambda: None,
            Predict=lambda _signature: FakePrediction(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "rook.learning.dspy_config",
        SimpleNamespace(configure_dspy=lambda **_kwargs: fake_lm),
    )
    monkeypatch.setattr(module, "_DSPY_TIMEOUT_SECONDS", 0.01)

    started = time.monotonic()
    with pytest.raises(Exception) as caught:
        asyncio.run(module._run_dspy(fake_lm.model, marker))
    elapsed = time.monotonic() - started

    assert isinstance(caught.value, module.AcceptanceFailure)
    assert caught.value.code == "vertex_dspy_timeout"
    assert elapsed < 0.2
    assert state == {
        "sync_called": False,
        "async_started": True,
        "async_cancelled": True,
    }


def _install_chirp_child_fakes(
    monkeypatch,
    module,
    *,
    record,
    inspect_responses=None,
):
    calls: list[tuple[str, object]] = []
    inspect_responses = list(inspect_responses or [])
    context_state = {"active": False}

    class FakeProofFailure(RuntimeError):
        def __init__(self, details=None):
            super().__init__("proof failed")
            self.details = details or {}

    class FakeDiscovery:
        def read_owned_record(self, pid):
            calls.append(("read_owned_record", pid))
            if isinstance(record, BaseException):
                raise record
            return record

    @contextmanager
    def request_context(*, port, process_id):
        calls.append(("context", (port, process_id)))
        context_state["active"] = True
        try:
            yield
        finally:
            context_state["active"] = False

    async def ensure_ready(args):
        assert context_state["active"] is True
        calls.append(("ensure_ready", dict(args)))
        return {"status": {"success": True}}

    async def capture_state(args, **_kwargs):
        assert context_state["active"] is True
        calls.append(("capture_state", dict(args)))
        return {"object_count": 0, "instance_guids": []}

    async def dispatch(name, arguments):
        assert context_state["active"] is True
        calls.append((name, dict(arguments)))
        if name == "gh_inspect_output":
            return inspect_responses.pop(0)
        return {"success": True}

    async def mutation(*_args, verify_created_fn, **_kwargs):
        assert context_state["active"] is True
        calls.append(("mutation", None))
        await verify_created_fn("owned-component-guid", {"success": True})
        return {}

    monkeypatch.setitem(
        sys.modules,
        "rook.runtime_harness",
        SimpleNamespace(OwnedRhinoDiscovery=FakeDiscovery),
    )
    monkeypatch.setitem(
        sys.modules,
        "rook.bridge",
        SimpleNamespace(
            call_rhino=object(),
            rhino_request_context=request_context,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "rook.local_testing_proof",
        SimpleNamespace(
            ProofFailure=FakeProofFailure,
            _capture_chirp_cleanup_state=capture_state,
            _ensure_grasshopper_ready=ensure_ready,
            _is_retryable_slow_inspection_timeout=(
                lambda response: response
                == {"success": False, "data": "GH callback request timed out."}
            ),
            _run_chirp_smoke_mutation=mutation,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "rook.server",
        SimpleNamespace(_call_tool_dispatch=dispatch),
    )
    monkeypatch.setenv("ROOK_VERTEX_ACCEPTANCE_MODEL", "vertex_ai/gemini-2.5-pro")
    monkeypatch.setenv("ROOK_VERTEX_ACCEPTANCE_MARKER", "rook-vertex-marker-01234567")
    return calls


@pytest.mark.parametrize(
    ("port", "pid", "record"),
    [
        (None, None, SimpleNamespace(pid=7102, port=9951)),
        ("9951", "7102", SimpleNamespace(pid=7102, port=9952)),
    ],
)
def test_chirp_child_refuses_unowned_rhino_before_any_host_call(
    monkeypatch,
    port,
    pid,
    record,
):
    module = _load_harness()
    calls = _install_chirp_child_fakes(monkeypatch, module, record=record)
    if port is None:
        monkeypatch.delenv("ROOK_RHINO_PORT", raising=False)
        monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)
    else:
        monkeypatch.setenv("ROOK_RHINO_PORT", port)
        monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", pid)

    result = asyncio.run(module._run_chirp_child())

    assert result == 2
    assert not any(
        name in {"ensure_ready", "capture_state", "mutation"}
        for name, _ in calls
    )


@pytest.mark.parametrize(
    "first_response",
    [
        {"success": False, "data": "terminal failure"},
        None,
        {"success": True, "data": "malformed"},
        {"success": True, "data": {"preview": "not-a-list"}},
    ],
)
def test_chirp_inspection_stops_on_first_nontransient_failure(
    monkeypatch,
    first_response,
):
    module = _load_harness()
    record = SimpleNamespace(pid=7102, port=9951)
    calls = _install_chirp_child_fakes(
        monkeypatch,
        module,
        record=record,
        inspect_responses=[
            first_response,
            {"success": True, "data": {"preview": ["late-success"]}},
        ],
    )
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    result = asyncio.run(module._run_chirp_child())

    assert result == 1
    assert [name for name, _ in calls].count("gh_inspect_output") == 1


def test_chirp_inspection_retries_only_exact_callback_timeout(monkeypatch):
    module = _load_harness()
    record = SimpleNamespace(pid=7102, port=9951)
    calls = _install_chirp_child_fakes(
        monkeypatch,
        module,
        record=record,
        inspect_responses=[
            {"success": False, "data": "GH callback request timed out."},
            {"success": True, "data": {"preview": ["accepted"]}},
        ],
    )
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    result = asyncio.run(module._run_chirp_child())

    assert result == 0
    assert [name for name, _ in calls].count("gh_inspect_output") == 2
