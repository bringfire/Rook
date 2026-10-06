import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook import chirp_manager


@pytest.fixture(autouse=True)
def isolated_launch_store(monkeypatch, tmp_path):
    """Launcher tests must never write process metadata to the user's store."""
    import uuid
    from rook.providers.vertex_auth import VertexStore
    store = VertexStore(tmp_path / 'auth' / 'vertex.json', mutex_name='Local\\Rook.Chirp.Test.' + uuid.uuid4().hex)
    monkeypatch.setattr(VertexStore, 'production', lambda: store)
    # These tests fake Popen; real process tracking is covered by the integration tests.
    from rook import chirp_launch_tracking
    monkeypatch.setattr(chirp_launch_tracking, 'process_identity', lambda pid: {'pid':pid, 'created':1})
    monkeypatch.setattr(chirp_launch_tracking, 'ProcessJob', lambda _: SimpleNamespace(assign=lambda _: None, close=lambda: None))
    monkeypatch.setattr(chirp_launch_tracking, 'resume_process', lambda _: None)
    monkeypatch.setattr(chirp_launch_tracking, 'job_is_active', lambda _: False)
    monkeypatch.setattr(chirp_launch_tracking, 'keep_job_open', lambda *args: None)
    yield store


def _admit_synthetic_bootstrap(monkeypatch, generation):
    from rook.providers.vertex_auth import VertexMode
    import uuid
    store = SimpleNamespace(read=lambda: SimpleNamespace(mode=VertexMode.ADC, generation=generation), path=chirp_manager.VertexStore.production().path,
        _mutex_name='Local\\Rook.Chirp.Test.' + uuid.uuid4().hex, _mutex_timeout_ms=1000)
    monkeypatch.setattr(chirp_manager.VertexStore, 'production', lambda: store)


def test_start_chirp_marks_non_vertex_child_managed_without_secret_pipe(
    monkeypatch, tmp_path
):
    """A normal Rook launch is managed but carries no Vertex authorization."""
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    captured: dict = {}

    class _DummyProc:
        pid = 3210

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _DummyProc()

    monkeypatch.setattr(chirp_manager, "DISCOVERY_FOLDER", tmp_path / "discovery")
    monkeypatch.setattr(chirp_manager.subprocess, "Popen", fake_popen)

    proc = chirp_manager._start_chirp(chirp_home)

    assert isinstance(proc, _DummyProc)
    assert captured["args"] == (
        [str(python_exe), "-m", "chirp", "--rook-managed"],
    )
    assert captured["kwargs"]["cwd"] == str(chirp_home)
    # Override any installed .env value so a cold launch remains OS-assigned.
    assert captured["kwargs"]["env"]["CHIRP_PORT"] == "0"
    assert "PYTHONHOME" not in captured["kwargs"]["env"]
    assert "PYTHONPATH" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["env"]["CHIRP_HOME"] == str(chirp_home)
    assert captured["kwargs"]["env"]["CHIRP_DSPY_RESTRICT_PICKLE"] == "1"
    assert captured["kwargs"]["env"]["DSPY_CACHEDIR"] == str(
        chirp_home / "data" / "dspy-cache"
    )
    assert captured["kwargs"]["stdin"] is chirp_manager.subprocess.DEVNULL
    assert captured["kwargs"]["stdout"] is chirp_manager.subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] is chirp_manager.subprocess.DEVNULL
    assert captured["kwargs"]["close_fds"] is True
    assert (
        captured["kwargs"]["creationflags"]
        == chirp_manager.subprocess.CREATE_NO_WINDOW | 0x00000004
    )


def test_start_vertex_chirp_sends_one_bounded_envelope_only_through_stdin(
    monkeypatch, tmp_path
):
    """A managed Vertex launch keeps credentials out of argv and environment."""
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    writes = []
    captured = {}

    class _Stdin:
        closed = False

        def write(self, value):
            writes.append(value)
            return len(value)

        def flush(self):
            return None

        def close(self):
            self.closed = True

    class _DummyProc:
        pid = 3210
        stdin = _Stdin()

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _DummyProc()

    envelope = {
        "schema_version": 1,
        "generation": "0123456789abcdef0123456789abcdef",
        "mode": "oauth",
        "project_id": "company-ai-project",
        "region": "us-central1",
        "vertex_credentials": {
            "type": "authorized_user",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "refresh_token": "refresh-token-sentinel",
        },
    }
    monkeypatch.setattr(chirp_manager.subprocess, "Popen", fake_popen)

    _admit_synthetic_bootstrap(monkeypatch, envelope["generation"])
    proc = chirp_manager._start_chirp(
        chirp_home,
        vertex_bootstrap=envelope,
        requested_port=9123,
    )

    assert proc.pid == 3210
    assert captured["args"] == (
        [
            str(python_exe),
            "-m",
            "chirp",
            "--rook-managed",
            "--rook-vertex-bootstrap-stdin",
        ],
    )
    assert captured["kwargs"]["stdin"] is chirp_manager.subprocess.PIPE
    assert captured["kwargs"]["env"]["CHIRP_PORT"] == "9123"
    command_text = " ".join(captured["args"][0])
    environment_text = "\n".join(
        f"{key}={value}" for key, value in captured["kwargs"]["env"].items()
    )
    assert "refresh-token-sentinel" not in command_text
    assert "refresh-token-sentinel" not in environment_text
    assert len(writes) == 1
    assert writes[0].endswith(b"\n")
    assert len(writes[0]) <= 65_537
    assert json.loads(writes[0]) == envelope
    assert proc.stdin.closed is True


def test_bootstrap_write_failure_terminates_only_the_just_launched_child(
    monkeypatch,
    tmp_path,
):
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    actions = []

    class _Stdin:
        def write(self, _value):
            raise OSError("pipe failed")

        def flush(self):
            pytest.fail("flush must not follow a failed write")

        def close(self):
            actions.append("close")

    class _DummyProc:
        stdin = _Stdin()

        def terminate(self):
            actions.append("terminate")

    monkeypatch.setattr(
        chirp_manager.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _DummyProc(),
    )

    _admit_synthetic_bootstrap(monkeypatch, "0" * 32)
    with pytest.raises(OSError, match="pipe failed"):
        chirp_manager._start_chirp(
            chirp_home,
            vertex_bootstrap={"generation": "0" * 32},
        )

    assert actions == ["close", "terminate"]


def test_missing_bootstrap_pipe_terminates_only_the_just_launched_child(
    monkeypatch,
    tmp_path,
):
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    actions = []

    class _DummyProc:
        stdin = None

        def terminate(self):
            actions.append("terminate")

    monkeypatch.setattr(
        chirp_manager.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _DummyProc(),
    )

    _admit_synthetic_bootstrap(monkeypatch, "0" * 32)
    with pytest.raises(RuntimeError, match="stdin pipe"):
        chirp_manager._start_chirp(
            chirp_home,
            vertex_bootstrap={"generation": "0" * 32},
        )

    assert actions == ["terminate"]


def test_start_chirp_returns_none_when_no_venv(tmp_path):
    """_start_chirp returns None when the venv is missing."""
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    # No .venv created
    result = chirp_manager._start_chirp(chirp_home)
    assert result is None


def test_health_payload_classification_is_exact():
    healthy = chirp_manager._classify_health(
        "127.0.0.1", 9900, {"status": "ok", "version": "0.1.0"}
    )
    assert healthy == {
        "running": True,
        "host": "127.0.0.1",
        "port": 9900,
        "error": None,
    }

    disabled = chirp_manager._classify_health(
        "127.0.0.1",
        9900,
        {
            "status": "disabled",
            "version": "0.1.0",
            "error": {
                "code": "chirp_invalid_inference_timeout",
                "message": chirp_manager.INVALID_TIMEOUT_MESSAGE,
            },
        },
    )
    assert disabled == {
        "running": False,
        "host": "127.0.0.1",
        "port": 9900,
        "error": chirp_manager.INVALID_TIMEOUT_MESSAGE,
        "error_code": "chirp_invalid_inference_timeout",
    }

    assert chirp_manager._classify_health("127.0.0.1", 9900, None) is None
    assert chirp_manager._classify_health(
        "127.0.0.1", 9900, {"status": "starting"}
    ) is None
    assert chirp_manager._classify_health(
        "127.0.0.1",
        9900,
        {
            "status": "disabled",
            "error": {
                "code": "chirp_invalid_inference_timeout",
                "message": "different message",
            },
        },
    ) is None


@pytest.mark.asyncio
async def test_discovered_terminal_timeout_config_short_circuits_without_polling(
    monkeypatch,
):
    sleeps = []
    health_calls = 0

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_health(_host, _port):
        nonlocal health_calls
        health_calls += 1
        return {
            "status": "disabled",
            "version": "0.1.0",
            "error": {
                "code": "chirp_invalid_inference_timeout",
                "message": chirp_manager.INVALID_TIMEOUT_MESSAGE,
            },
        }

    monkeypatch.setattr(chirp_manager.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_find_live_discovery",
        lambda: {"host": "127.0.0.1", "port": 9900, "pid": 1234},
    )
    result = await chirp_manager.ensure_chirp_running()
    assert result["running"] is False
    assert result["error_code"] == "chirp_invalid_inference_timeout"
    assert health_calls == 1
    assert sleeps == []


def test_retirement_never_signals_or_terminates_unmanaged_process(
    monkeypatch,
):
    signals = []
    process = SimpleNamespace(pid=4101, terminate=lambda: signals.append("terminate"))
    monkeypatch.setattr(chirp_manager, "_chirp_process", process)
    monkeypatch.setattr(
        chirp_manager,
        "_signal_retirement_event",
        lambda: signals.append("signal"),
    )

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._retire_discovered_process(
            {"host": "127.0.0.1", "port": 9123, "pid": 4101},
            {"status": "ok", "rook_managed": False, "vertex": {"status": "absent"}},
        )

    assert error.value.code == "vertex_restart_required"
    assert signals == []


def test_rediscovered_managed_process_is_signaled_but_never_force_terminated(
    monkeypatch,
):
    signals = []
    monkeypatch.setattr(chirp_manager, "_chirp_process", None)
    monkeypatch.setattr(
        chirp_manager,
        "_signal_retirement_event",
        lambda: signals.append("signal"),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_retirement",
        lambda _discovery, _timeout: False,
    )

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._retire_discovered_process(
            {"host": "127.0.0.1", "port": 9123, "pid": 4101},
            {"status": "ok", "rook_managed": True, "vertex": {"status": "stale"}},
        )

    assert error.value.code == "vertex_restart_required"
    assert signals == ["signal"]


def test_exact_owned_process_may_be_terminated_after_graceful_timeout(
    monkeypatch,
):
    actions = []

    class _OwnedProcess:
        pid = 4101

        def poll(self):
            return None

        def terminate(self):
            actions.append("terminate")

    process = _OwnedProcess()
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    waits = iter([False, True])
    monkeypatch.setattr(chirp_manager, "_chirp_process", process)
    monkeypatch.setattr(
        chirp_manager,
        "_signal_retirement_event",
        lambda: actions.append("signal"),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_retirement",
        lambda _discovery, _timeout: next(waits),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_read_discovery_for_port",
        lambda _port: dict(discovery),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_port_is_available",
        lambda _host, _port: True,
    )
    monkeypatch.setattr(
        chirp_manager,
        "_reset_retirement_event",
        lambda: actions.append("reset"),
    )

    retired = chirp_manager._retire_discovered_process(
        discovery,
        {"status": "ok", "rook_managed": True, "vertex": {"status": "stale"}},
    )

    assert retired == ("127.0.0.1", 9123)
    assert actions == ["signal", "terminate", "reset"]


def test_dead_exact_process_is_retired_without_deleting_discovery(monkeypatch, tmp_path):
    discovery_folder = tmp_path / "rook"
    discovery_folder.mkdir()
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    exact = discovery_folder / "chirp-service-9123.json"
    sibling = discovery_folder / "chirp-service-9124.json"
    exact.write_text(json.dumps(discovery), encoding="utf-8")
    sibling.write_text(
        json.dumps({"host": "127.0.0.1", "port": 9124, "pid": 4201}),
        encoding="utf-8",
    )
    monkeypatch.setattr(chirp_manager, "DISCOVERY_FOLDER", discovery_folder)
    monkeypatch.setattr(chirp_manager, "_is_pid_alive", lambda _pid: False)

    assert chirp_manager._wait_for_retirement(discovery, 0.2) is True
    assert exact.exists()
    assert sibling.exists()


def test_current_handle_cannot_terminate_mismatched_discovery(monkeypatch):
    actions = []

    class _OwnedProcess:
        pid = 4101

        def poll(self):
            return None

        def terminate(self):
            actions.append("terminate")

    monkeypatch.setattr(chirp_manager, "_chirp_process", _OwnedProcess())
    monkeypatch.setattr(
        chirp_manager,
        "_signal_retirement_event",
        lambda: actions.append("signal"),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_retirement",
        lambda _discovery, _timeout: False,
    )
    monkeypatch.setattr(
        chirp_manager,
        "_read_discovery_for_port",
        lambda _port: {"host": "127.0.0.1", "port": 9123, "pid": 9999},
    )

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._retire_discovered_process(
            {"host": "127.0.0.1", "port": 9123, "pid": 4101},
            {"status": "ok", "rook_managed": True, "vertex": {"status": "stale"}},
        )

    assert error.value.code == "vertex_restart_required"
    assert actions == ["signal"]


def test_rediscovered_managed_process_may_retire_gracefully(monkeypatch):
    actions = []
    monkeypatch.setattr(chirp_manager, "_chirp_process", None)
    monkeypatch.setattr(
        chirp_manager,
        "_signal_retirement_event",
        lambda: actions.append("signal"),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_retirement",
        lambda _discovery, _timeout: True,
    )
    monkeypatch.setattr(chirp_manager, "_port_is_available", lambda _host, _port: True)
    monkeypatch.setattr(
        chirp_manager,
        "_reset_retirement_event",
        lambda: actions.append("reset"),
    )

    assert chirp_manager._retire_discovered_process(
        {"host": "127.0.0.1", "port": 9123, "pid": 4101},
        {"status": "ok", "rook_managed": True, "vertex": {"status": "stale"}},
    ) == ("127.0.0.1", 9123)
    assert actions == ["signal", "reset"]


def test_effective_model_precedence_is_explicit_process_env_chirp_env_default(
    monkeypatch,
    tmp_path,
):
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    (chirp_home / ".env").write_text(
        "CHIRP_MODEL=vertex_ai/gemini-env-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHIRP_MODEL", "vertex_ai/gemini-process")

    assert (
        chirp_manager._resolve_effective_model(
            "vertex_ai/gemini-explicit", chirp_home
        )
        == "vertex_ai/gemini-explicit"
    )
    assert (
        chirp_manager._resolve_effective_model(None, chirp_home)
        == "vertex_ai/gemini-process"
    )
    monkeypatch.delenv("CHIRP_MODEL")
    assert (
        chirp_manager._resolve_effective_model(None, chirp_home)
        == "vertex_ai/gemini-env-file"
    )
    (chirp_home / ".env").unlink()
    assert (
        chirp_manager._resolve_effective_model(None, chirp_home)
        == "anthropic/claude-opus-5"
    )


def test_vertex_bootstrap_is_fresh_and_generation_bound(monkeypatch):
    generation = "0123456789abcdef0123456789abcdef"
    runtime = SimpleNamespace(
        generation=generation,
        project_id="company-ai-project",
        region="us-central1",
        vertex_credentials={
            "type": "authorized_user",
            "client_id": "client",
            "client_secret": "secret",
            "refresh_token": "refresh",
        },
    )
    record = SimpleNamespace(generation=generation, mode=SimpleNamespace(value="oauth"))
    store = SimpleNamespace(resolve_runtime=lambda: runtime, read=lambda: record)
    monkeypatch.setattr(
        chirp_manager.VertexStore,
        "production",
        classmethod(lambda _cls: store),
    )

    assert chirp_manager._resolve_vertex_bootstrap(generation) == {
        "schema_version": 1,
        "generation": generation,
        "mode": "oauth",
        "project_id": "company-ai-project",
        "region": "us-central1",
        "vertex_credentials": runtime.vertex_credentials,
    }

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._resolve_vertex_bootstrap("f" * 32)
    assert error.value.code == "vertex_restart_required"


@pytest.mark.asyncio
async def test_required_vertex_recycles_managed_absent_child_on_same_port(
    monkeypatch,
    tmp_path,
):
    chirp_home = tmp_path / "Chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    discovery = {
        "host": "127.0.0.1",
        "port": 9123,
        "pid": 4101,
        "home": str(chirp_home),
    }
    health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "absent"},
    }
    envelope = {"generation": "0" * 32}
    restarts = []

    async def fake_health(_host, _port):
        return health

    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_resolve_vertex_bootstrap",
        lambda _expected=None: envelope,
    )
    monkeypatch.setattr(
        chirp_manager,
        "_restart_discovered_process",
        lambda found, payload, bootstrap: restarts.append(
            (found, payload, bootstrap)
        )
        or {"running": True, "host": "127.0.0.1", "port": 9123, "error": None},
    )

    result = await chirp_manager.ensure_chirp_running(
        "vertex_ai/gemini-2.5-pro"
    )

    assert result["running"] is True
    assert restarts == [(discovery, health, envelope)]


@pytest.mark.asyncio
async def test_required_vertex_never_adopts_unmanaged_child(monkeypatch):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}

    async def fake_health(_host, _port):
        return {
            "status": "ok",
            "rook_managed": False,
            "vertex": {"status": "absent"},
        }

    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_start_chirp",
        lambda *_args, **_kwargs: pytest.fail("must not launch another port"),
    )

    result = await chirp_manager.ensure_chirp_running(
        "vertex_ai/gemini-2.5-pro"
    )

    assert result["running"] is False
    assert result["error_code"] == "vertex_restart_required"
    assert result["port"] == 9123


@pytest.mark.asyncio
async def test_explicit_non_vertex_uses_managed_child_disabled_only_for_vertex(
    monkeypatch,
):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}

    async def fake_health(_host, _port):
        return {
            "status": "disabled",
            "rook_managed": True,
            "vertex": {"status": "absent"},
            "error": {
                "code": "vertex_signed_out",
                "message": "Vertex AI is not configured for this managed Chirp process.",
            },
        }

    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)

    result = await chirp_manager.ensure_chirp_running("anthropic/claude-sonnet-5")

    assert result == {
        "running": True,
        "host": "127.0.0.1",
        "port": 9123,
        "error": None,
    }


def test_post_commit_restarts_prior_vertex_child_with_new_generation(
    monkeypatch,
):
    generation = "fedcba9876543210fedcba9876543210"
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "ready"},
    }
    envelope = {"generation": generation}
    restarts = []
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_read_health_sync", lambda _host, _port: health)
    monkeypatch.setattr(
        chirp_manager,
        "_resolve_vertex_bootstrap",
        lambda expected=None: envelope if expected == generation else pytest.fail(),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_restart_discovered_process",
        lambda found, payload, bootstrap: restarts.append(
            (found, payload, bootstrap)
        ),
    )

    chirp_manager.recycle_after_vertex_commit(generation)

    assert restarts == [(discovery, health, envelope)]


def test_post_commit_preserves_configured_vertex_bootstrap_when_health_is_absent(
    monkeypatch,
    tmp_path,
):
    generation = "fedcba9876543210fedcba9876543210"
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "absent"},
    }
    chirp_home = tmp_path / "Chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    (chirp_home / ".env").write_text(
        "CHIRP_MODEL=vertex_ai/gemini-2.5-pro\n",
        encoding="utf-8",
    )
    envelope = {"generation": generation}
    restarts = []
    monkeypatch.delenv("CHIRP_MODEL", raising=False)
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_find_chirp_home", lambda: chirp_home)
    monkeypatch.setattr(chirp_manager, "_read_health_sync", lambda _host, _port: health)
    monkeypatch.setattr(
        chirp_manager,
        "_resolve_vertex_bootstrap",
        lambda expected=None: envelope if expected == generation else pytest.fail(),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_restart_discovered_process",
        lambda found, payload, bootstrap: restarts.append(
            (found, payload, bootstrap)
        ),
    )

    chirp_manager.recycle_after_vertex_commit(generation)

    assert restarts == [(discovery, health, envelope)]


def test_disconnect_restarts_live_child_without_vertex_bootstrap(monkeypatch):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "ready"},
    }
    restarts = []
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_read_health_sync", lambda _host, _port: health)
    monkeypatch.setattr(
        chirp_manager,
        "_resolve_vertex_bootstrap",
        lambda _expected=None: pytest.fail("disconnect must not resolve credentials"),
    )
    monkeypatch.setattr(
        chirp_manager,
        "_restart_discovered_process",
        lambda found, payload, bootstrap: restarts.append(
            (found, payload, bootstrap)
        ),
    )

    chirp_manager.recycle_after_vertex_commit(None)

    assert restarts == [(discovery, health, None)]


def test_post_commit_without_live_child_starts_nothing(monkeypatch):
    monkeypatch.setattr(chirp_manager, "_chirp_process", None)
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: None)
    monkeypatch.setattr(
        chirp_manager,
        "_start_chirp",
        lambda *_args, **_kwargs: pytest.fail("no prior child means no replacement"),
    )

    assert chirp_manager.recycle_after_vertex_commit("0" * 32) is None


def test_post_commit_fails_closed_for_owned_child_without_discovery(monkeypatch):
    process = SimpleNamespace(pid=4101, poll=lambda: None)
    monkeypatch.setattr(chirp_manager, "_chirp_process", process)
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: None)

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager.recycle_after_vertex_commit("0" * 32)

    assert error.value.code == "vertex_restart_required"


def test_restart_proves_replacement_home_before_retiring_child(monkeypatch):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 4101}
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(chirp_manager, "_find_managed_chirp_home", lambda: None)
    monkeypatch.setattr(
        chirp_manager,
        "_retire_discovered_process",
        lambda *_args: pytest.fail("must not retire without replacement prerequisites"),
    )

    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._restart_discovered_process(
            discovery,
            {"status": "ok", "rook_managed": True, "vertex": {"status": "ready"}},
            {"generation": "0" * 32},
        )

    assert error.value.code == "vertex_restart_required"


def test_restart_uses_manager_owned_home_not_discovery_home(monkeypatch, tmp_path):
    canonical_home = tmp_path / "installed" / "Chirp"
    stale_home = tmp_path / "stale-worktree" / "Chirp"
    for chirp_home in (canonical_home, stale_home):
        (chirp_home / "src" / "chirp").mkdir(parents=True)
        python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
        python_exe.parent.mkdir(parents=True)
        python_exe.write_text("", encoding="utf-8")

    discovery = {
        "host": "127.0.0.1",
        "port": 9123,
        "pid": 4101,
        "home": str(stale_home),
    }
    health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "stale"},
    }
    started_homes = []
    monkeypatch.setenv("CHIRP_HOME", str(canonical_home))
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", lambda: discovery)
    monkeypatch.setattr(
        chirp_manager,
        "_retire_discovered_process",
        lambda *_args: ("127.0.0.1", 9123),
    )

    def fake_start(chirp_home, **_kwargs):
        started_homes.append(chirp_home)
        return SimpleNamespace(pid=4201, poll=lambda: None)

    monkeypatch.setattr(chirp_manager, "_start_chirp", fake_start)
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_started_process_sync",
        lambda *_args, **_kwargs: {
            "running": True,
            "host": "127.0.0.1",
            "port": 9123,
            "error": None,
        },
    )

    _admit_synthetic_bootstrap(monkeypatch, "0" * 32)
    result = chirp_manager._restart_discovered_process(
        discovery,
        health,
        {"generation": "0" * 32},
    )

    assert result["running"] is True
    assert started_homes == [canonical_home]


@pytest.mark.asyncio
async def test_concurrent_vertex_admission_restarts_stale_child_once(
    monkeypatch,
    tmp_path,
):
    chirp_home = tmp_path / "Chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    old_discovery = {
        "host": "127.0.0.1",
        "port": 9123,
        "pid": 4101,
        "home": str(chirp_home),
    }
    new_discovery = {
        "host": "127.0.0.1",
        "port": 9123,
        "pid": 4201,
        "home": str(chirp_home),
    }
    stale_health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "stale"},
    }
    ready_health = {
        "status": "ok",
        "rook_managed": True,
        "vertex": {"status": "ready"},
    }
    state = {"discovery": old_discovery}
    retire_barrier = threading.Barrier(2)
    retirements = []
    starts = []

    monkeypatch.setenv("CHIRP_HOME", str(chirp_home))
    monkeypatch.setattr(
        chirp_manager,
        "_find_live_discovery",
        lambda: dict(state["discovery"]),
    )

    async def fake_health(_host, _port):
        return (
            stale_health
            if state["discovery"]["pid"] == old_discovery["pid"]
            else ready_health
        )

    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_read_health_sync",
        lambda _host, _port: ready_health,
    )
    monkeypatch.setattr(
        chirp_manager,
        "_resolve_vertex_bootstrap",
        lambda _expected=None: {"generation": "0" * 32},
    )

    def fake_retire(discovery, _health):
        retirements.append(discovery["pid"])
        try:
            retire_barrier.wait(timeout=0.25)
        except threading.BrokenBarrierError:
            pass
        return "127.0.0.1", 9123

    def fake_start(_chirp_home, **_kwargs):
        starts.append(4201)
        state["discovery"] = new_discovery
        return SimpleNamespace(pid=4201, poll=lambda: None)

    monkeypatch.setattr(chirp_manager, "_retire_discovered_process", fake_retire)
    monkeypatch.setattr(chirp_manager, "_start_chirp", fake_start)
    monkeypatch.setattr(
        chirp_manager,
        "_wait_for_started_process_sync",
        lambda *_args, **_kwargs: {
            "running": True,
            "host": "127.0.0.1",
            "port": 9123,
            "error": None,
        },
    )

    _admit_synthetic_bootstrap(monkeypatch, "0" * 32)
    results = await asyncio.gather(
        chirp_manager.ensure_chirp_running("vertex_ai/gemini-2.5-pro"),
        chirp_manager.ensure_chirp_running("vertex_ai/gemini-2.5-pro"),
    )

    assert all(result["running"] is True for result in results)
    assert retirements == [4101]
    assert starts == [4201]

@pytest.mark.parametrize('live', [False, True, 'unowned', 'alive'])
def test_workforce_activation_retires_without_resolving_bootstrap(monkeypatch, live, isolated_launch_store):
    import time
    from rook.providers.vertex_auth import VertexMode
    snapshot = SimpleNamespace(mode=VertexMode.WORKFORCE, generation='a' * 32, chirp_retirement_pending=True)
    monkeypatch.setattr(isolated_launch_store, 'read', lambda: snapshot)
    discovery = {'host': '127.0.0.1', 'port': 9123, 'pid': 4101}
    monkeypatch.setattr(chirp_manager, '_find_live_discovery', lambda: discovery if live else None)
    monkeypatch.setattr(chirp_manager, '_chirp_process', None)
    monkeypatch.setattr(chirp_manager, '_read_health_sync', lambda *args, **kwargs: {'rook_managed': live != 'unowned'})
    calls = []
    monkeypatch.setattr(chirp_manager, '_resolve_vertex_bootstrap', lambda *args: pytest.fail('Stop before credential resolution'))
    monkeypatch.setattr(chirp_manager, '_start_chirp', lambda *args, **kwargs: pytest.fail('No replacement start'))
    monkeypatch.setattr(chirp_manager, '_signal_retirement_event', lambda: calls.append('signal'))
    monkeypatch.setattr(chirp_manager, '_wait_for_retirement', lambda *args: live != 'alive')
    monkeypatch.setattr(chirp_manager, '_port_is_available', lambda *args: True)
    monkeypatch.setattr(chirp_manager, '_reset_retirement_event', lambda: calls.append('reset'))
    if live in ('unowned', 'alive'):
        with pytest.raises(chirp_manager.VertexAuthError):
            chirp_manager.retire_after_workforce_commit('a' * 32, time.monotonic() + 30, lambda: None)
    else:
        chirp_manager.retire_after_workforce_commit('a' * 32, time.monotonic() + 30, lambda: None)
    assert calls == (['signal', 'reset'] if live is True else ['signal'] if live == 'alive' else [])


@pytest.mark.asyncio
async def test_workforce_refusal_precedes_live_chirp_reuse(monkeypatch):
    from rook.providers.vertex_auth import VertexMode
    snapshot = SimpleNamespace(mode=VertexMode.WORKFORCE, generation='a' * 32, chirp_retirement_pending=False)
    monkeypatch.setattr(chirp_manager.VertexStore, 'production', lambda: SimpleNamespace(read=lambda: snapshot))
    monkeypatch.setattr(chirp_manager, '_find_chirp_home', lambda: None)
    monkeypatch.setattr(chirp_manager, '_find_live_discovery', lambda: pytest.fail('Refuse before reuse'))
    result = await chirp_manager.ensure_chirp_running('vertex_ai/gemini-2.5-pro')
    assert result['error_code'] == 'vertex_text_federation_unsupported' and not result['running']


def test_vertex_startup_racing_activation_cannot_reinstall_child(monkeypatch, tmp_path):
    from rook.providers.vertex_auth import VertexMode
    snapshot = SimpleNamespace(mode=VertexMode.WORKFORCE, generation='a' * 32, chirp_retirement_pending=True)
    monkeypatch.setattr(chirp_manager.VertexStore, 'production', lambda: SimpleNamespace(read=lambda: snapshot, _mutex_name='Local\\Rook.Workforce.Launch.Test', _mutex_timeout_ms=1000))
    monkeypatch.setattr(chirp_manager.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('No stale launch'))
    with pytest.raises(chirp_manager.VertexAuthError) as error:
        chirp_manager._start_chirp(tmp_path, vertex_bootstrap={'generation': 'b' * 32})
    assert error.value.code == 'vertex_text_federation_unsupported'



def test_pre_activation_launch_waiter_rechecks_under_replacement_lock(monkeypatch, tmp_path):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from .test_vertex_workforce_store import Protector
    from rook.providers.vertex_auth import VertexStore, VertexRecord, VertexMode
    from rook.providers.vertex_workforce_store import VertexWorkforceStore
    from rook.providers.vertex_workforce_contract import FirmSettings, PrivatePrincipal, VerifiedEntraAssertion, EntraSessionCandidate, WorkforceExchangeResult
    import uuid
    base = VertexStore(tmp_path / 'vertex.json', protector=Protector(), mutex_name='Local\\Rook.Chirp.Race.' + uuid.uuid4().hex)
    prior = base.replace(VertexRecord(1, '0' * 32, VertexMode.ADC, 'synthetic-firm-project', 'us-central1', None, None))
    monkeypatch.setattr(chirp_manager.VertexStore, 'production', lambda: base)
    monkeypatch.setattr(chirp_manager.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('No pre-activation bootstrap after activation'))
    store = VertexWorkforceStore(base)
    settings = FirmSettings(2, 'Synthetic firm', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '123456789', 'synthetic-pool', 'synthetic-provider', 'synthetic-firm-project', 'synthetic-firm-project', None, 'us-central1')
    principal = PrivatePrincipal(settings.entra_tenant_id, '33333333-3333-3333-3333-333333333333', 'bound-account')
    candidate = EntraSessionCandidate(principal, '{}', VerifiedEntraAssertion('synthetic', principal, int(time.time()) + 60))
    exchange = WorkforceExchangeResult('synthetic', int(time.time()) + 60, settings.project_id, settings.workforce_pool_user_project, None)
    ticket = store.import_pending(settings)
    entered = threading.Event()
    def launch():
        entered.set()
        return chirp_manager._launch_registered_chirp(tmp_path, {'generation': prior.generation}, True)
    with ThreadPoolExecutor() as pool:
        with chirp_manager._replacement_lock:
            waiter = pool.submit(launch)
            assert entered.wait(2)
            store.activate(ticket, candidate, exchange, cancel_check=lambda: None)
        with pytest.raises(chirp_manager.VertexAuthError) as error:
            waiter.result(timeout=2)
        assert error.value.code == 'vertex_text_federation_unsupported'
