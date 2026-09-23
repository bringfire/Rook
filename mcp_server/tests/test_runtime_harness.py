import json
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from rook.runtime_harness import (
    CleanupStatus,
    DiscoveryError,
    DiscoveryFailureReason,
    HarnessStatus,
    OwnedRhinoDiscovery,
    OwnedRhinoRecord,
    RhinoHarnessResult,
    SmokeCommandResult,
    classify_cleanup_status,
    close_windows_for_pid,
    copy_temp_rook_artifacts,
    request_external_graceful_close,
    run_rhino_runtime_harness,
    run_smoke_command,
    ping_native,
    _scoped_env_subset,
)
from rook import runtime_harness


def _load_harness_cli_module():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_rhino_runtime_harness.py"
    spec = importlib.util.spec_from_file_location("run_rhino_runtime_harness_cli", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeProcess:
    def __init__(self, pid: int, poll_results: list[int | None]):
        self.pid = pid
        self.returncode = None
        self._poll_results = poll_results

    def poll(self) -> int | None:
        if self._poll_results:
            self.returncode = self._poll_results.pop(0)
        return self.returncode


class PingRecorder:
    def __init__(self, results: list[bool]):
        self.results = results
        self.urls: list[tuple[str, int]] = []

    async def __call__(self, host: str, port: int) -> bool:
        self.urls.append((host, port))
        if self.results:
            return self.results.pop(0)
        return False


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeAsyncClient:
    response = httpx.Response(200, text="")
    urls: list[str] = []
    exception: Exception | None = None

    def __init__(self, timeout: float, headers: dict | None = None):
        # ping_native goes through bridge.native_client: the X-Rook-Client
        # header must be on the client, or the native server answers 403.
        assert headers and headers.get("X-Rook-Client"), headers
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url: str):
        self.urls.append(url)
        if self.exception is not None:
            raise self.exception
        return self.response


def _write_record(discovery_dir: Path, pid: int, record: dict) -> Path:
    path = discovery_dir / f"instance-{pid}-native.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _native_record(pid: int, **overrides) -> dict:
    record = {
        "processId": pid,
        "pluginType": "native",
        "host": "127.0.0.1",
        "port": 9010,
    }
    record.update(overrides)
    return record


def _pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_until_pid_exits(pid: int, timeout_seconds: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.05)
    return not _pid_is_running(pid)


def _smoke_result(returncode: int = 0, timed_out: bool = False) -> SmokeCommandResult:
    return SmokeCommandResult(
        command=["smoke"],
        scoped_env={},
        returncode=returncode,
        stdout="",
        stderr="",
        duration_seconds=0.01,
        timed_out=timed_out,
        timeout_seconds=None,
    )


def _harness_result(tmp_path: Path, *, smoke: SmokeCommandResult | None = None) -> RhinoHarnessResult:
    return RhinoHarnessResult(
        run_id="run-artifacts",
        artifact_dir=tmp_path / "artifacts",
        pid=1234,
        port=9010,
        smoke=smoke,
        run_started_at=100.0,
    )


def test_default_owned_discovery_prefers_shared_localappdata_root(tmp_path: Path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    temp_root = tmp_path / "Temp"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(runtime_harness.tempfile, "gettempdir", lambda: str(temp_root))

    discovery_dir = runtime_harness.default_discovery_dir()

    assert discovery_dir == local_app_data / "Rook" / "discovery"


def test_default_temp_rook_artifacts_follow_shared_discovery_root(tmp_path: Path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    temp_root = tmp_path / "Temp"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(runtime_harness.tempfile, "gettempdir", lambda: str(temp_root))

    artifact_dir = runtime_harness.default_temp_rook_dir()

    assert artifact_dir == local_app_data / "Rook" / "discovery"


def test_default_artifact_roots_include_shared_and_legacy_temp(tmp_path: Path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    temp_root = tmp_path / "Temp"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(runtime_harness.tempfile, "gettempdir", lambda: str(temp_root))

    roots = runtime_harness.default_artifact_roots()

    assert roots == [
        runtime_harness.ArtifactRoot("shared-discovery", local_app_data / "Rook" / "discovery"),
        runtime_harness.ArtifactRoot("legacy-temp-rook", temp_root / "rook"),
    ]


class FakeExternalProcess:
    def __init__(self, pid: int, wait_results: list[object]):
        self.pid = pid
        self.wait_results = wait_results
        self.wait_timeouts: list[float | None] = []
        self.kill_calls = 0

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if not self.wait_results:
            return 0
        result = self.wait_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def kill(self):
        self.kill_calls += 1


class FakeHarnessProcess:
    def __init__(self, pid: int, poll_results: list[int | None] | None = None):
        self.pid = pid
        self.returncode: int | None = None
        self.poll_results = poll_results or [None]
        self.wait_calls: list[float | None] = []
        self.kill_calls = 0

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if self.poll_results:
            self.returncode = self.poll_results.pop(0)
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        self.returncode = 0
        return 0

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9


class FakeHarnessDiscovery:
    def __init__(
        self,
        *,
        pid: int = 4321,
        port: int = 9921,
        fail_ready: bool = False,
        leftover: bool = False,
        reread_port: int | None = None,
    ):
        self.pid = pid
        self.port = port
        self.fail_ready = fail_ready
        self.leftover = leftover
        self.reread_port = reread_port
        self.wait_calls: list[dict[str, object]] = []
        self.read_calls: list[int] = []
        self.snapshot_calls: list[Path] = []

    def owned_path(self, pid: int):
        class _OwnedPath:
            def __init__(self, exists_value: bool):
                self.exists_value = exists_value

            def exists(self) -> bool:
                return self.exists_value

        return _OwnedPath(self.leftover)

    def wait_for_ready(self, **kwargs):
        self.wait_calls.append(kwargs)
        if self.fail_ready:
            raise DiscoveryError("owned ready failed")
        return OwnedRhinoRecord(
            pid=self.pid,
            host="127.0.0.1",
            port=self.port,
            path=Path(f"instance-{self.pid}-native.json"),
            raw={
                "processId": self.pid,
                "pluginType": "native",
                "host": "127.0.0.1",
                "port": self.port,
            },
        )

    def read_owned_record(self, pid: int):
        self.read_calls.append(pid)
        port = self.port if self.reread_port is None else self.reread_port
        return OwnedRhinoRecord(
            pid=self.pid,
            host="127.0.0.1",
            port=port,
            path=Path(f"instance-{self.pid}-native.json"),
            raw={
                "processId": self.pid,
                "pluginType": "native",
                "host": "127.0.0.1",
                "port": port,
            },
        )

    def snapshot_owned_record(self, record, artifact_dir: Path) -> Path:
        self.snapshot_calls.append(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / f"owned-discovery-instance-{record.pid}-native.json"
        path.write_text(json.dumps(record.raw), encoding="utf-8")
        return path


def test_owned_discovery_accepts_exact_native_pid(tmp_path: Path):
    pid = 1234
    path = _write_record(tmp_path, pid, _native_record(pid, host="LOCALHOST", port=9876))

    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(pid)

    assert record.pid == pid
    assert record.host == "localhost"
    assert record.port == 9876
    assert record.path == path
    assert record.raw == _native_record(pid, host="LOCALHOST", port=9876)


def test_owned_discovery_accepts_whitespace_padded_loopback_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host=" LOCALHOST "))

    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)

    assert record.host == "localhost"


def test_owned_discovery_rejects_wrong_process_id(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(5678))

    with pytest.raises(DiscoveryError, match="wrong processId"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_boolean_process_id(tmp_path: Path):
    _write_record(tmp_path, 1, _native_record(True))

    with pytest.raises(DiscoveryError, match="processId"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1)


def test_owned_discovery_rejects_non_native_plugin_type(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, pluginType="managed"))

    with pytest.raises(DiscoveryError, match="pluginType"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


@pytest.mark.parametrize("port", [None, 0, -1, "abc", True])
def test_owned_discovery_rejects_invalid_port(tmp_path: Path, port):
    _write_record(tmp_path, 1234, _native_record(1234, port=port))

    with pytest.raises(DiscoveryError, match="port"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_missing_port(tmp_path: Path):
    record = _native_record(1234)
    del record["port"]
    _write_record(tmp_path, 1234, record)

    with pytest.raises(DiscoveryError, match="port"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "instance-1234-native.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="malformed JSON"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_top_level_non_object_json(tmp_path: Path):
    path = tmp_path / "instance-1234-native.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="object"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_non_loopback_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host="192.168.1.10"))

    with pytest.raises(DiscoveryError, match="loopback"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_non_string_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host=123))

    with pytest.raises(DiscoveryError, match="host|loopback"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_snapshots_json(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    _write_record(tmp_path, 1234, _native_record(1234, host=""))
    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)

    snapshot_path = OwnedRhinoDiscovery(tmp_path).snapshot_owned_record(record, artifact_dir)

    assert snapshot_path == artifact_dir / "owned-discovery-instance-1234-native.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == record.raw
    assert "\n  " in snapshot_path.read_text(encoding="utf-8")


def test_owned_discovery_never_reads_other_healthy_rhino(tmp_path: Path):
    _write_record(tmp_path, 1111, _native_record(1111, port=9011))
    discovery = OwnedRhinoDiscovery(tmp_path)

    with pytest.raises(DiscoveryError, match="not found"):
        discovery.read_owned_record(2222)


def test_wait_for_ready_reports_owned_process_exit_before_discovery(tmp_path: Path):
    pid = 1234
    process = FakeProcess(pid, [None, 17])
    ping = PingRecorder([True])

    with pytest.raises(
        DiscoveryError,
        match="Rhino exited with code 17 before RookNative discovery appeared",
    ):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            process,
            ping,
            timeout_seconds=1.0,
            poll_seconds=0,
        )

    assert ping.urls == []


def test_wait_for_ready_pings_exact_owned_port(tmp_path: Path):
    pid = 1234
    _write_record(tmp_path, pid, _native_record(pid, host="localhost", port=9821))
    ping = PingRecorder([False, True])

    record = OwnedRhinoDiscovery(tmp_path).wait_for_ready(
        pid,
        FakeProcess(pid, [None, None]),
        ping,
        timeout_seconds=1.0,
        poll_seconds=0,
    )

    assert record.pid == pid
    assert record.host == "localhost"
    assert record.port == 9821
    assert ping.urls == [("localhost", 9821), ("localhost", 9821)]


def test_wait_for_ready_times_out_when_ping_never_succeeds(tmp_path: Path):
    pid = 1234
    _write_record(tmp_path, pid, _native_record(pid, host="127.0.0.1", port=9821))
    ping = PingRecorder([False, False, False])

    with pytest.raises(DiscoveryError, match="did not become pingable"):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            FakeProcess(pid, [None, None, None]),
            ping,
            timeout_seconds=0.01,
            poll_seconds=0,
        )

    assert ping.urls
    assert set(ping.urls) == {("127.0.0.1", 9821)}


def test_wait_for_ready_yields_when_poll_seconds_is_zero(tmp_path: Path):
    pid = 1234
    clock = FakeClock()

    with pytest.raises(
        DiscoveryError,
        match="Rhino exited with code 9 before RookNative discovery appeared",
    ):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            FakeProcess(pid, [None, 9]),
            PingRecorder([True]),
            timeout_seconds=1.0,
            poll_seconds=0,
            _monotonic=clock.monotonic,
            _sleep=clock.sleep,
        )

    assert clock.sleeps == [pytest.approx(0.001)]


def test_wait_for_ready_reports_process_exit_after_discovery_before_ping(tmp_path: Path):
    pid = 1234
    _write_record(tmp_path, pid, _native_record(pid, host="127.0.0.1", port=9821))

    with pytest.raises(
        DiscoveryError,
        match="Rhino exited with code 9 before RookNative became pingable",
    ):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            FakeProcess(pid, [None, 9]),
            PingRecorder([False]),
            timeout_seconds=1.0,
            poll_seconds=0,
        )


def test_wait_for_ready_reason_exited_before_bind(tmp_path: Path):
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, 17]), PingRecorder([True]),
            timeout_seconds=1.0, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.EXITED_BEFORE_BIND


def test_wait_for_ready_reason_exited_before_ready(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, port=9821))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, 9]), PingRecorder([False]),
            timeout_seconds=1.0, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.EXITED_BEFORE_READY


def test_wait_for_ready_reason_bind_timeout_no_discovery(tmp_path: Path):
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY


def test_wait_for_ready_reason_invalid_discovery_record(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, processId=999))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.INVALID_DISCOVERY_RECORD


def test_wait_for_ready_reason_bind_timeout_no_ping(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, port=9821))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([False, False, False]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_PING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="pong"),
        httpx.Response(200, json={"data": "pong"}),
        httpx.Response(200, json={"success": True}),
    ],
)
async def test_ping_native_accepts_supported_pong_shapes(monkeypatch, response):
    FakeAsyncClient.response = response
    FakeAsyncClient.urls = []
    FakeAsyncClient.exception = None
    monkeypatch.setattr("rook.runtime_harness.httpx.AsyncClient", FakeAsyncClient)

    assert await ping_native("localhost", 9821) is True

    assert FakeAsyncClient.urls == ["http://localhost:9821/ping"]


@pytest.mark.asyncio
async def test_ping_native_returns_false_when_endpoint_not_listening(monkeypatch):
    FakeAsyncClient.urls = []
    FakeAsyncClient.exception = httpx.ConnectError("connection refused")
    monkeypatch.setattr("rook.runtime_harness.httpx.AsyncClient", FakeAsyncClient)

    assert await ping_native("localhost", 9821) is False

    assert FakeAsyncClient.urls == ["http://localhost:9821/ping"]


def test_run_smoke_command_captures_output_and_scoped_env(tmp_path: Path):
    script = (
        "import os, sys\n"
        "print(os.environ['ROOK_RHINO_PORT'])\n"
        "print(os.environ['ROOK_RHINO_PROCESS_ID'])\n"
        "print(os.environ['NATIVE_PORT'])\n"
        "print(os.environ.get('IGNORED_FOR_MANIFEST'))\n"
        "print('err-line', file=sys.stderr)\n"
    )

    result = run_smoke_command(
        [sys.executable, "-c", script],
        env_additions={
            "ROOK_RHINO_PORT": "9001",
            "ROOK_RHINO_PROCESS_ID": "1234",
            "NATIVE_PORT": "9001",
            "IGNORED_FOR_MANIFEST": "ambient-ok",
        },
        cwd=tmp_path,
        timeout_seconds=5,
    )

    assert result.command == [sys.executable, "-c", script]
    assert result.scoped_env == {
        "ROOK_RHINO_PORT": "9001",
        "ROOK_RHINO_PROCESS_ID": "1234",
        "NATIVE_PORT": "9001",
    }
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["9001", "1234", "9001", "ambient-ok"]
    assert result.stderr.strip() == "err-line"
    assert result.duration_seconds >= 0
    assert result.succeeded is True


def test_failing_smoke_command_is_non_green_and_manifest_records_output(tmp_path: Path):
    smoke = run_smoke_command(
        [
            sys.executable,
            "-c",
            "import sys; print('partial out'); print('partial err', file=sys.stderr); sys.exit(7)",
        ],
        env_additions={"ROOK_RHINO_PORT": "9002"},
        timeout_seconds=5,
    )
    harness = RhinoHarnessResult(
        run_id="run-failure",
        artifact_dir=tmp_path,
        pid=1234,
        port=9002,
        ready_record_path=tmp_path / "owned-discovery-instance-1234-native.json",
        smoke=smoke,
    )

    manifest_path = harness.write_manifest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert smoke.returncode == 7
    assert smoke.succeeded is False
    assert harness.status == HarnessStatus.NON_GREEN
    assert harness.success is False
    assert manifest["status"] == "non_green"
    assert manifest["success"] is False
    assert manifest["smoke"]["returncode"] == 7
    assert manifest["smoke"]["stdout"] == "partial out\n"
    assert manifest["smoke"]["stderr"] == "partial err\n"


def test_run_smoke_command_timeout_returns_result_without_throwing():
    result = run_smoke_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        env_additions={},
        timeout_seconds=0.01,
    )

    assert result.returncode != 0
    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()
    assert result.succeeded is False


def test_run_smoke_command_timeout_kills_descendant_holding_output_pipes(tmp_path: Path):
    child_pid_path = tmp_path / "child.pid"
    script = (
        "from pathlib import Path\n"
        "import subprocess, sys, time\n"
        f"child_pid_path = {str(child_pid_path)!r}\n"
        "child = subprocess.Popen([\n"
        "    sys.executable,\n"
        "    '-c',\n"
        "    'import sys, time; print(\"child-start\"); sys.stdout.flush(); time.sleep(3)',\n"
        "])\n"
        "Path(child_pid_path).write_text(str(child.pid), encoding='utf-8')\n"
        "print('parent-start')\n"
        "sys.stdout.flush()\n"
        "time.sleep(3)\n"
    )

    started = time.monotonic()
    try:
        result = run_smoke_command(
            [sys.executable, "-c", script],
            env_additions={},
            timeout_seconds=1.0,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert result.returncode != 0
        assert "timed out" in result.stderr.lower()
        assert elapsed < 1.5
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        assert _wait_until_pid_exits(child_pid)
    finally:
        if child_pid_path.exists():
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            if _pid_is_running(child_pid):
                subprocess.run(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )


def test_run_smoke_command_timeout_kills_descendant_after_parent_exits(tmp_path: Path):
    child_pid_path = tmp_path / "child-after-parent-exit.pid"
    script = (
        "from pathlib import Path\n"
        "import subprocess, sys\n"
        f"child_pid_path = {str(child_pid_path)!r}\n"
        "child = subprocess.Popen([\n"
        "    sys.executable,\n"
        "    '-c',\n"
        "    'import time; time.sleep(3)',\n"
        "])\n"
        "Path(child_pid_path).write_text(str(child.pid), encoding='utf-8')\n"
        "print('parent-exiting')\n"
        "sys.stdout.flush()\n"
    )

    started = time.monotonic()
    try:
        result = run_smoke_command(
            [sys.executable, "-c", script],
            env_additions={},
            timeout_seconds=1.0,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert result.returncode != 0
        assert "timed out" in result.stderr.lower()
        assert "parent-exiting" in result.stdout
        assert elapsed < 1.5
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        assert _wait_until_pid_exits(child_pid)
    finally:
        if child_pid_path.exists():
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            if _pid_is_running(child_pid):
                subprocess.run(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )


def test_runtime_harness_keep_rhino_on_failure_skips_cleanup(monkeypatch, tmp_path: Path):
    fake_process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    fake_discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    cleanup_calls = []
    (tmp_path / "Rhino.exe").write_text("fake", encoding="utf-8")

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda *args, **kwargs: fake_process)
    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", lambda *args, **kwargs: _smoke_result(returncode=7))
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda *args, **kwargs: cleanup_calls.append(args) or False,
    )
    monkeypatch.setattr("rook.runtime_harness.ping_native", lambda host, port: True)

    result = run_rhino_runtime_harness(
        rhino_exe=tmp_path / "Rhino.exe",
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        smoke_kind="installed-live-smoke",
        discovery=fake_discovery,
        keep_rhino_on_failure=True,
    )

    assert result.success is False
    assert cleanup_calls == []
    assert result.cleanup_status == CleanupStatus.NOT_ATTEMPTED
    assert any("KeepRhinoOnFailure" in warning for warning in result.warnings)


def test_run_smoke_command_timeout_recovery_never_uses_unbounded_final_drain(monkeypatch):
    class AlwaysTimingOutProcess:
        pid = 4242
        returncode = None

        def __init__(self):
            self.communicate_timeouts: list[float | None] = []
            self.kill_called = False

        def communicate(self, timeout=None):
            self.communicate_timeouts.append(timeout)
            if timeout is None:
                raise AssertionError("communicate called without a timeout")
            raise subprocess.TimeoutExpired(
                cmd=["fake-smoke"],
                timeout=timeout,
                output="partial stdout",
                stderr="partial stderr",
            )

        def kill(self):
            self.kill_called = True
            self.returncode = -9

        def poll(self):
            return self.returncode

    fake_process = AlwaysTimingOutProcess()
    monkeypatch.setattr(
        "rook.runtime_harness.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr("rook.runtime_harness._create_windows_job_for_process", lambda process: None)
    monkeypatch.setattr("rook.runtime_harness._terminate_smoke_process_tree", lambda process, job: None)
    monkeypatch.setattr("rook.runtime_harness._close_windows_job", lambda job: None)

    result = run_smoke_command(
        ["fake-smoke"],
        env_additions={},
        timeout_seconds=0.2,
    )

    assert result.timed_out is True
    assert result.returncode != 0
    assert result.stdout == "partial stdout"
    assert "partial stderr" in result.stderr
    assert "timed out" in result.stderr.lower()
    assert "could not drain" in result.stderr.lower()
    assert fake_process.kill_called is True
    assert fake_process.communicate_timeouts == [0.2, 5, 1]


def test_request_external_graceful_close_targets_owned_pid_and_does_not_kill():
    process = FakeExternalProcess(pid=4242, wait_results=[0])
    closed_pids: list[int] = []
    diagnostics: list[str] = []

    forced = request_external_graceful_close(
        process,
        timeout_seconds=2.5,
        close_windows_for_pid_fn=lambda pid: closed_pids.append(pid) or 1,
        diagnostics=diagnostics,
    )

    assert forced is False
    assert diagnostics == []
    assert closed_pids == [4242]
    assert process.kill_calls == 0
    assert process.wait_timeouts == [2.5]


def test_request_external_graceful_close_force_kills_owned_process_after_timeout():
    process = FakeExternalProcess(
        pid=5252,
        wait_results=[
            subprocess.TimeoutExpired(cmd=["rhino"], timeout=0.1),
            0,
        ],
    )
    closed_pids: list[int] = []

    forced = request_external_graceful_close(
        process,
        timeout_seconds=0.1,
        close_windows_for_pid_fn=lambda pid: closed_pids.append(pid) or 2,
    )

    assert forced is True
    assert closed_pids == [5252]
    assert process.kill_calls == 1
    assert process.wait_timeouts == [0.1, pytest.approx(1.0)]


def test_request_external_graceful_close_force_kills_owned_process_when_no_windows_close():
    process = FakeExternalProcess(
        pid=6262,
        wait_results=[
            subprocess.TimeoutExpired(cmd=["rhino"], timeout=0.2),
            0,
        ],
    )
    closed_pids: list[int] = []

    forced = request_external_graceful_close(
        process,
        timeout_seconds=0.2,
        close_windows_for_pid_fn=lambda pid: closed_pids.append(pid) or 0,
    )

    assert forced is True
    assert closed_pids == [6262]
    assert process.kill_calls == 1
    assert process.wait_timeouts == [0.2, pytest.approx(1.0)]


def test_force_owned_process_cleanup_falls_back_to_process_kill_when_taskkill_fails(monkeypatch):
    import rook.runtime_harness as runtime_harness

    process = FakeHarnessProcess(pid=7272, poll_results=[None])
    diagnostics: list[str] = []

    monkeypatch.setattr(runtime_harness.os, "name", "nt")
    monkeypatch.setattr(
        runtime_harness.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=128,
            stdout="",
            stderr="taskkill failed",
        ),
    )

    assert runtime_harness.force_owned_process_cleanup(process, diagnostics) is True
    assert process.kill_calls == 1
    assert any("taskkill returned 128" in warning for warning in diagnostics)


def test_close_windows_for_pid_posts_close_only_to_visible_top_level_owned_windows(monkeypatch):
    import rook.runtime_harness as runtime_harness

    hwnds = [1001, 1002, 1003, 1004]
    visible = {1001: True, 1002: False, 1003: True, 1004: True}
    pids = {1001: 42, 1002: 42, 1003: 99, 1004: 42}
    posted: list[tuple[int, int, int, int]] = []

    class FakeUser32:
        def EnumWindows(self, callback, lparam):
            for hwnd in hwnds:
                if not callback(hwnd, lparam):
                    return 0
            return 1

        def IsWindowVisible(self, hwnd):
            return bool(visible[hwnd])

        def GetWindowThreadProcessId(self, hwnd, pid_pointer):
            pid_pointer._obj.value = pids[hwnd]
            return 1

        def PostMessageW(self, hwnd, message, wparam, lparam):
            posted.append((hwnd, message, wparam, lparam))
            return 1

    monkeypatch.setattr(runtime_harness.os, "name", "nt")
    monkeypatch.setattr(runtime_harness, "_windows_user32", lambda: FakeUser32())

    assert close_windows_for_pid(42) == 2
    assert posted == [
        (1001, runtime_harness.WM_CLOSE, 0, 0),
        (1004, runtime_harness.WM_CLOSE, 0, 0),
    ]


def test_harness_manifest_contains_future_cleanup_and_readiness_fields(tmp_path: Path):
    ready_path = tmp_path / "owned-discovery-instance-2222-native.json"
    ready_path.write_text('{"processId":2222}', encoding="utf-8")
    smoke = run_smoke_command(
        [sys.executable, "-c", "print('ok')"],
        env_additions={
            "ROOK_RHINO_PORT": "9010",
            "ROOK_RHINO_PROCESS_ID": "2222",
            "NATIVE_PORT": "9010",
            "ROOK_HARNESS_ARTIFACT_DIR": str(tmp_path),
        },
        timeout_seconds=5,
    )
    harness = RhinoHarnessResult(
        run_id="run-success",
        artifact_dir=tmp_path,
        pid=2222,
        port=9010,
        ready_record_path=ready_path,
        smoke=smoke,
        cleanup_status=CleanupStatus.NOT_ATTEMPTED,
        warnings=["artifact copy skipped"],
    )

    manifest_path = harness.write_manifest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_path == tmp_path / "manifest.json"
    assert manifest == {
        "run_id": "run-success",
        "artifact_dir": str(tmp_path),
        "pid": 2222,
        "port": 9010,
        "ready": {
            "record_snapshot_path": str(ready_path),
            "record_available": True,
        },
        "smoke": {
            "command": [sys.executable, "-c", "print('ok')"],
            "scoped_env": {
                "ROOK_RHINO_PORT": "9010",
                "ROOK_RHINO_PROCESS_ID": "2222",
                "NATIVE_PORT": "9010",
                "ROOK_HARNESS_ARTIFACT_DIR": str(tmp_path),
            },
            "returncode": 0,
            "stdout": "ok\n",
            "stderr": "",
            "duration_seconds": smoke.duration_seconds,
            "timed_out": False,
            "timeout_seconds": 5,
        },
        "cleanup": {
            "status": "not_attempted",
            "path": "not_attempted",
        },
        "runscript_safety": {
            "unrecovered": False,
            "sentinel_path": None,
        },
        "warnings": ["artifact copy skipped"],
        "launch_outcome": None,
        "status": "non_green",
        "success": False,
    }


def test_harness_success_requires_graceful_cleanup(tmp_path: Path):
    result = RhinoHarnessResult(
        run_id="run-no-cleanup",
        artifact_dir=tmp_path,
        pid=2222,
        port=9010,
        smoke=_smoke_result(0),
        cleanup_status=CleanupStatus.NOT_ATTEMPTED,
    )

    assert result.success is False
    assert result.status == HarnessStatus.NON_GREEN


def test_copy_temp_rook_artifacts_missing_temp_dir_warns_and_returns_empty(tmp_path: Path):
    harness = _harness_result(tmp_path)

    copied = copy_temp_rook_artifacts(harness, tmp_path / "missing-temp-rook", "temp-rook")

    assert copied == []
    assert harness.warnings
    assert "missing" in harness.warnings[0].lower()


def test_copy_temp_rook_artifacts_preserves_relative_paths_and_contents(tmp_path: Path):
    temp_rook = tmp_path / "temp-rook-source"
    (temp_rook / "nested").mkdir(parents=True)
    (temp_rook / "root.log").write_text("root", encoding="utf-8")
    (temp_rook / "nested" / "trace.json").write_text('{"ok":true}', encoding="utf-8")
    harness = _harness_result(tmp_path)

    copied = copy_temp_rook_artifacts(harness, temp_rook, "copied")

    assert copied == [
        harness.artifact_dir / "copied" / "nested" / "trace.json",
        harness.artifact_dir / "copied" / "root.log",
    ]
    assert (harness.artifact_dir / "copied" / "root.log").read_text(encoding="utf-8") == "root"
    assert (
        harness.artifact_dir / "copied" / "nested" / "trace.json"
    ).read_text(encoding="utf-8") == '{"ok":true}'
    assert harness.warnings == []


def test_copy_temp_rook_artifacts_skips_files_before_run_start_window(tmp_path: Path):
    temp_rook = tmp_path / "temp-rook-source"
    temp_rook.mkdir()
    old_file = temp_rook / "old.log"
    new_file = temp_rook / "new.log"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    os.utime(old_file, (89.0, 89.0))
    os.utime(new_file, (96.0, 96.0))
    harness = _harness_result(tmp_path)

    copied = copy_temp_rook_artifacts(
        harness,
        temp_rook,
        "copied",
        mtime_slop_seconds=5.0,
    )

    assert copied == [harness.artifact_dir / "copied" / "new.log"]
    assert not (harness.artifact_dir / "copied" / "old.log").exists()
    assert (harness.artifact_dir / "copied" / "new.log").read_text(encoding="utf-8") == "new"


def test_copy_temp_rook_artifacts_continues_after_individual_copy_failure(
    tmp_path: Path,
    monkeypatch,
):
    temp_rook = tmp_path / "temp-rook-source"
    temp_rook.mkdir()
    bad_file = temp_rook / "bad.log"
    good_file = temp_rook / "good.log"
    bad_file.write_text("bad", encoding="utf-8")
    good_file.write_text("good", encoding="utf-8")
    harness = _harness_result(tmp_path)

    import rook.runtime_harness as runtime_harness

    original_copy2 = runtime_harness.shutil.copy2

    def fail_for_bad(src: Path, dst: Path):
        if Path(src).name == "bad.log":
            raise OSError("permission denied")
        return original_copy2(src, dst)

    monkeypatch.setattr(runtime_harness.shutil, "copy2", fail_for_bad)

    copied = copy_temp_rook_artifacts(harness, temp_rook, "copied")

    assert copied == [harness.artifact_dir / "copied" / "good.log"]
    assert (harness.artifact_dir / "copied" / "good.log").read_text(encoding="utf-8") == "good"
    assert harness.warnings
    assert "bad.log" in harness.warnings[0]
    assert "permission denied" in harness.warnings[0]


def test_copy_temp_rook_artifacts_rejects_parent_traversal_label(tmp_path: Path):
    temp_rook = tmp_path / "temp-rook-source"
    temp_rook.mkdir()
    (temp_rook / "root.log").write_text("root", encoding="utf-8")
    harness = _harness_result(tmp_path)

    copied = copy_temp_rook_artifacts(harness, temp_rook, str(Path("..") / "escaped"))

    assert copied == []
    assert not (tmp_path / "escaped" / "root.log").exists()
    assert not (harness.artifact_dir / ".." / "escaped" / "root.log").resolve().exists()
    assert harness.warnings
    assert "unsafe" in harness.warnings[0].lower()


def test_copy_temp_rook_artifacts_rejects_absolute_label(tmp_path: Path):
    temp_rook = tmp_path / "temp-rook-source"
    temp_rook.mkdir()
    (temp_rook / "root.log").write_text("root", encoding="utf-8")
    harness = _harness_result(tmp_path)
    outside_dir = tmp_path / "absolute-output"

    copied = copy_temp_rook_artifacts(harness, temp_rook, str(outside_dir))

    assert copied == []
    assert not (outside_dir / "root.log").exists()
    assert harness.warnings
    assert "unsafe" in harness.warnings[0].lower()


@pytest.mark.parametrize(
    (
        "kwargs",
        "expected_status",
        "expected_green_with_successful_smoke",
    ),
    [
        (
            {"already_exited_before_cleanup": True},
            CleanupStatus.ALREADY_EXITED_BEFORE_CLEANUP,
            False,
        ),
        (
            {"force_failed": True},
            CleanupStatus.FORCE_KILL_FAILED,
            False,
        ),
        (
            {"process_exited_after_cleanup": False},
            CleanupStatus.FORCE_KILL_FAILED,
            False,
        ),
        (
            {"forced": True},
            CleanupStatus.GRACEFUL_TIMEOUT_FORCED_KILL,
            False,
        ),
        (
            {"discovery_leftover": True},
            CleanupStatus.GRACEFUL_EXIT_DISCOVERY_LEFTOVER,
            False,
        ),
        (
            {},
            CleanupStatus.GRACEFUL_EXIT,
            True,
        ),
    ],
)
def test_cleanup_classification_priority_and_green_status(
    tmp_path: Path,
    kwargs,
    expected_status,
    expected_green_with_successful_smoke,
):
    inputs = {
        "already_exited_before_cleanup": False,
        "process_exited_after_cleanup": True,
        "discovery_leftover": False,
        "forced": False,
        "force_failed": False,
    }
    inputs.update(kwargs)

    cleanup_status = classify_cleanup_status(**inputs)
    harness = RhinoHarnessResult(
        run_id="run-cleanup",
        artifact_dir=tmp_path,
        pid=1234,
        port=9010,
        smoke=_smoke_result(returncode=0),
        cleanup_status=cleanup_status,
    )

    assert cleanup_status == expected_status
    assert harness.success is expected_green_with_successful_smoke
    if expected_green_with_successful_smoke:
        assert harness.status == HarnessStatus.SUCCESS
    else:
        assert harness.status == HarnessStatus.NON_GREEN


def test_graceful_cleanup_is_non_green_when_smoke_failed(tmp_path: Path):
    harness = RhinoHarnessResult(
        run_id="run-failed-smoke",
        artifact_dir=tmp_path,
        pid=1234,
        port=9010,
        smoke=_smoke_result(returncode=7),
        cleanup_status=CleanupStatus.GRACEFUL_EXIT,
    )

    assert harness.success is False
    assert harness.status == HarnessStatus.NON_GREEN


def test_request_external_graceful_close_records_window_diagnostics_before_force_kill():
    process = FakeExternalProcess(
        pid=4321,
        wait_results=[subprocess.TimeoutExpired(cmd="Rhino.exe", timeout=0.1), 0],
    )
    diagnostics: list[str] = []

    forced = request_external_graceful_close(
        process,
        timeout_seconds=0.1,
        close_windows_for_pid_fn=lambda pid: 2,
        describe_windows_for_pid_fn=lambda pid: [
            {"hwnd": "0x123", "visible": True, "title": "Untitled - Rhino 8"},
        ],
        diagnostics=diagnostics,
    )

    assert forced is True
    assert process.kill_calls == 1
    assert any("WM_CLOSE posted to 2 window(s) for pid 4321" in item for item in diagnostics)
    assert any("Untitled - Rhino 8" in item for item in diagnostics)
    assert any("timed out" in item for item in diagnostics)


def test_manifest_records_cleanup_path_status_and_warnings(tmp_path: Path):
    harness = RhinoHarnessResult(
        run_id="run-warning",
        artifact_dir=tmp_path,
        pid=1234,
        port=9010,
        smoke=_smoke_result(),
        cleanup_status=CleanupStatus.GRACEFUL_EXIT_DISCOVERY_LEFTOVER,
        warnings=["could not copy C:/Temp/rook/bad.log: permission denied"],
    )

    manifest = json.loads(harness.write_manifest().read_text(encoding="utf-8"))

    assert manifest["cleanup"] == {
        "status": "graceful_exit_discovery_leftover",
        "path": "graceful_exit_discovery_leftover",
    }
    assert manifest["warnings"] == ["could not copy C:/Temp/rook/bad.log: permission denied"]
    assert manifest["status"] == "non_green"
    assert manifest["success"] is False


def test_runtime_harness_missing_rhino_exe_writes_manifest_and_does_not_launch(
    tmp_path: Path,
    monkeypatch,
):
    popen_calls: list[object] = []
    monkeypatch.setattr(
        "rook.runtime_harness.subprocess.Popen",
        lambda *args, **kwargs: popen_calls.append((args, kwargs)),
    )

    result = run_rhino_runtime_harness(
        rhino_exe=tmp_path / "missing" / "Rhino.exe",
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert popen_calls == []
    assert result.success is False
    assert result.status == HarnessStatus.NON_GREEN
    assert any("Rhino executable not found" in warning for warning in result.warnings)
    assert manifest["warnings"] == result.warnings
    assert manifest["status"] == "non_green"


def test_runtime_harness_launch_failure_writes_manifest_without_cleanup(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    cleanup_calls: list[object] = []

    def fail_launch(command, **kwargs):
        raise OSError("not a valid executable")

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", fail_launch)
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda *args: cleanup_calls.append(args),
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert cleanup_calls == []
    assert result.success is False
    assert result.status == HarnessStatus.NON_GREEN
    assert result.pid == 0
    assert result.cleanup_status == CleanupStatus.NOT_ATTEMPTED
    assert any("Rhino launch failed" in warning for warning in result.warnings)
    assert any("not a valid executable" in warning for warning in result.warnings)
    assert manifest["warnings"] == result.warnings
    assert manifest["smoke"] is None
    assert manifest["status"] == "non_green"


def test_runtime_harness_successful_flow_uses_exact_owned_discovery_and_scoped_smoke(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    popen_calls: list[list[str]] = []
    smoke_calls: list[tuple[list[str], dict[str, str], Path | None, float | None]] = []
    artifact_labels: list[str] = []
    close_calls: list[tuple[FakeHarnessProcess, float]] = []

    monkeypatch.setattr(
        "rook.runtime_harness.subprocess.Popen",
        lambda command, **kwargs: popen_calls.append(command) or process,
    )

    def fake_smoke(command, env_additions, cwd=None, timeout_seconds=None):
        smoke_calls.append((command, env_additions, cwd, timeout_seconds))
        return SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", fake_smoke)
    monkeypatch.setattr(
        "rook.runtime_harness.copy_temp_rook_artifacts",
        lambda result, temp_rook_dir, label: artifact_labels.append(label) or [],
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: close_calls.append(
            (cleanup_process, timeout_seconds)
        )
        or cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        smoke_cwd=tmp_path,
        discovery=discovery,
        cleanup_timeout_seconds=2.5,
    )

    assert popen_calls == [[str(rhino_exe), "/nosplash"]]
    assert len(discovery.wait_calls) == 1
    assert discovery.wait_calls[0]["pid"] == 4321
    assert discovery.wait_calls[0]["process"] is process
    assert discovery.wait_calls[0]["ping"] is ping_native
    assert discovery.snapshot_calls == [result.artifact_dir]
    assert smoke_calls == [
        (
            ["smoke"],
            {
                "ROOK_RHINO_PORT": "9921",
                "ROOK_RHINO_PROCESS_ID": "4321",
                "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
            },
            tmp_path,
            None,
        )
    ]
    assert artifact_labels == [
        "before-shutdown-shared-discovery",
        "before-shutdown-legacy-temp-rook",
        "after-shutdown-shared-discovery",
        "after-shutdown-legacy-temp-rook",
    ]
    assert close_calls == [(process, 2.5)]
    assert result.cleanup_status == CleanupStatus.GRACEFUL_EXIT
    assert result.success is True
    assert result.ready_record_path is not None
    assert result.ready_record_path.exists()
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["success"] is True
    assert manifest["ready"]["record_snapshot_path"] == str(result.ready_record_path)


def test_runtime_harness_passes_artifact_dir_and_timeout_to_smoke(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    original_popen = subprocess.Popen
    launch_calls: list[tuple[list[str], dict[str, object]]] = []
    smoke_script = (
        "import os\n"
        "print(os.environ['ROOK_RHINO_PORT'])\n"
        "print(os.environ['ROOK_RHINO_PROCESS_ID'])\n"
        "print(os.environ['ROOK_HARNESS_ARTIFACT_DIR'])\n"
    )

    def fake_popen(command, **kwargs):
        if command == [str(rhino_exe), "/nosplash"]:
            launch_calls.append((command, kwargs))
            return process
        return original_popen(command, **kwargs)

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", fake_popen)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout, headers: httpx.Response(200, json={"success": True}),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=[sys.executable, "-c", smoke_script],
        smoke_timeout_seconds=8.5,
        discovery=discovery,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert launch_calls
    assert result.smoke is not None
    assert result.smoke.scoped_env == {
        "ROOK_RHINO_PORT": "9921",
        "ROOK_RHINO_PROCESS_ID": "4321",
        "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
    }
    assert result.smoke.stdout.splitlines() == ["9921", "4321", str(result.artifact_dir)]
    assert result.smoke.timeout_seconds == 8.5
    assert manifest["smoke"]["timeout_seconds"] == 8.5


def test_runtime_harness_applies_rhino_launch_env_overrides(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    launch_envs: list[dict[str, str]] = []
    monkeypatch.setenv("ROOK_NATIVE_RUNSCRIPT_SAFETY", "ambient")
    monkeypatch.setenv("ROOK_KEEP_ME", "ambient")

    def fake_popen(command, **kwargs):
        launch_envs.append(kwargs["env"])
        return process

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout, headers: httpx.Response(200, json={"success": True}),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
        launch_env_overrides={
            "ROOK_NATIVE_RUNSCRIPT_SAFETY": None,
            "ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE": "smoke",
        },
    )

    assert result.success is True
    assert len(launch_envs) == 1
    assert "ROOK_NATIVE_RUNSCRIPT_SAFETY" not in launch_envs[0]
    assert launch_envs[0]["ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE"] == "smoke"
    assert launch_envs[0]["ROOK_KEEP_ME"] == "ambient"


def test_runtime_harness_applies_overrides_before_build_launch_env(
    tmp_path: Path,
    monkeypatch,
):
    from types import SimpleNamespace

    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4322, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4322, port=9922)
    received_base_envs: list[dict[str, str]] = []
    popen_envs: list[dict[str, str]] = []
    report = {
        "authoritative": {
            "SystemDrive": "C:",
            "SystemRoot": r"C:\Windows",
            "windir": r"C:\Windows",
        },
        "backfilled": {"ProgramData": r"C:\ProgramData"},
        "inherited": {"ROOK_KEEP_ME": "ambient"},
        "missing_unresolved": [],
        "fallback_used": [],
    }
    fake_env = SimpleNamespace(
        env={"windir": r"C:\Windows", "SystemRoot": r"C:\Windows", "SystemDrive": "C:", "ROOK_KEEP_ME": "ambient"},
        report=report,
    )

    monkeypatch.setenv("ROOK_NATIVE_RUNSCRIPT_SAFETY", "ambient")
    monkeypatch.setenv("ROOK_KEEP_ME", "ambient")
    monkeypatch.setattr(
        "rook.runtime_harness.build_launch_env",
        lambda base_env: received_base_envs.append(dict(base_env)) or fake_env,
    )
    monkeypatch.setattr(
        "rook.runtime_harness.subprocess.Popen",
        lambda command, **kwargs: popen_envs.append(kwargs["env"]) or process,
    )
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout, headers: httpx.Response(200, json={"success": True}),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
        launch_env_overrides={
            "ROOK_NATIVE_RUNSCRIPT_SAFETY": None,
            "ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE": "smoke",
        },
    )

    assert result.success is True
    assert len(received_base_envs) == 1
    assert "ROOK_NATIVE_RUNSCRIPT_SAFETY" not in received_base_envs[0]
    assert received_base_envs[0]["ROOK_NATIVE_RUNSCRIPT_SAFETY_MODE"] == "smoke"
    assert received_base_envs[0]["ROOK_KEEP_ME"] == "ambient"
    assert popen_envs == [fake_env.env]
    assert result.launch_outcome["evidence"]["launchEnv"] == report

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["launch_outcome"]["evidence"]["launchEnv"] == report


def test_runtime_harness_unrecovered_sentinel_forces_owned_cleanup(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    save_calls: list[object] = []
    graceful_calls: list[FakeHarnessProcess] = []
    force_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)

    def fake_smoke(command, env_additions, cwd=None, timeout_seconds=None):
        sentinel_path = Path(env_additions["ROOK_HARNESS_ARTIFACT_DIR"]) / "runscript_safety_unrecovered.json"
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text('{"unrecovered": true}', encoding="utf-8")
        return SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", fake_smoke)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda *args, **kwargs: save_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: graceful_calls.append(cleanup_process)
        or False,
    )

    def fake_force_cleanup(cleanup_process, diagnostics):
        force_calls.append(cleanup_process)
        cleanup_process.kill()
        return True

    monkeypatch.setattr("rook.runtime_harness.force_owned_process_cleanup", fake_force_cleanup)

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
        keep_rhino_on_failure=True,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    sentinel_path = result.artifact_dir / "runscript_safety_unrecovered.json"
    assert result.success is False
    assert result.runscript_safety_unrecovered_path == sentinel_path
    assert manifest["runscript_safety"] == {
        "unrecovered": True,
        "sentinel_path": str(sentinel_path),
    }
    assert save_calls == []
    assert graceful_calls == []
    assert force_calls == [process]
    assert any("runscript safety unrecovered" in warning.lower() for warning in result.warnings)


def test_runtime_harness_unrecovered_sentinel_forces_cleanup_after_smoke_exception(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    graceful_calls: list[FakeHarnessProcess] = []
    force_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)

    def fake_smoke(command, env_additions, cwd=None, timeout_seconds=None):
        sentinel_path = Path(env_additions["ROOK_HARNESS_ARTIFACT_DIR"]) / "runscript_safety_unrecovered.json"
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text('{"unrecovered": true}', encoding="utf-8")
        raise OSError("smoke crashed after sentinel")

    monkeypatch.setattr("rook.runtime_harness.run_smoke_command", fake_smoke)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: graceful_calls.append(cleanup_process)
        or False,
    )

    def fake_force_cleanup(cleanup_process, diagnostics):
        force_calls.append(cleanup_process)
        cleanup_process.kill()
        return True

    monkeypatch.setattr("rook.runtime_harness.force_owned_process_cleanup", fake_force_cleanup)

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    sentinel_path = result.artifact_dir / "runscript_safety_unrecovered.json"
    assert result.success is False
    assert result.runscript_safety_unrecovered_path == sentinel_path
    assert graceful_calls == []
    assert force_calls == [process]
    assert any("smoke crashed after sentinel" in warning for warning in result.warnings)
    assert any("runscript safety unrecovered" in warning.lower() for warning in result.warnings)


def test_runtime_harness_validation_smoke_receives_native_port(tmp_path: Path, monkeypatch):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    smoke_envs: list[dict[str, str]] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: smoke_envs.append(
            env_additions
        )
        or SmokeCommandResult(command, _scoped_env_subset(env_additions), 0, "", "", 0.01),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        smoke_kind="rhino-operational",
        discovery=discovery,
    )

    assert result.success is True
    assert smoke_envs == [
        {
            "ROOK_RHINO_PORT": "9921",
            "ROOK_RHINO_PROCESS_ID": "4321",
            "NATIVE_PORT": "9921",
            "ROOK_HARNESS_ARTIFACT_DIR": str(result.artifact_dir),
        }
    ]


def test_runtime_harness_saves_owned_document_before_external_close(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    save_calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout, headers: save_calls.append((url, json))
        or httpx.Response(200, json={"success": True, "data": {"path": json["path"]}}),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert result.success is True
    assert len(save_calls) == 1
    save_url, save_payload = save_calls[0]
    assert save_url == "http://127.0.0.1:9921/document/save"
    assert save_payload["small"] is True
    assert Path(str(save_payload["path"])).parent == result.artifact_dir / "cleanup"
    assert str(save_payload["path"]).endswith("owned-rhino-4321-cleanup.3dm")


def test_runtime_harness_ping_only_does_not_save_owned_document_before_close(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    save_calls: list[object] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr("rook.runtime_harness.ping_native", lambda host, port: True)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda *args, **kwargs: save_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["unused-smoke"],
        smoke_kind="ping-only",
        discovery=discovery,
    )

    assert result.success is True
    assert save_calls == []


def test_runtime_harness_warns_when_cleanup_document_save_fails_but_still_closes(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    close_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.httpx.post",
        lambda url, json, timeout, headers: httpx.Response(
            200,
            json={"success": False, "error": "save rejected"},
        ),
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: close_calls.append(cleanup_process)
        or cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert close_calls == [process]
    assert result.cleanup_status == CleanupStatus.GRACEFUL_EXIT
    assert any("cleanup document save failed" in warning for warning in result.warnings)


def test_runtime_harness_ping_only_smoke_reuses_owned_ping_without_native_port(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    ping_calls: list[tuple[str, int]] = []
    smoke_calls: list[object] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda *args, **kwargs: smoke_calls.append(args),
    )

    async def fake_ping(host: str, port: int) -> bool:
        ping_calls.append((host, port))
        return True

    monkeypatch.setattr("rook.runtime_harness.ping_native", fake_ping)
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, diagnostics=None: cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["unused-smoke"],
        smoke_kind="ping-only",
        discovery=discovery,
    )

    assert result.success is True
    assert result.smoke is not None
    assert result.smoke.command == ["ping-only"]
    assert result.smoke.scoped_env == {
        "ROOK_RHINO_PORT": "9921",
        "ROOK_RHINO_PROCESS_ID": "4321",
    }
    assert "NATIVE_PORT" not in result.smoke.scoped_env
    assert ping_calls == [("127.0.0.1", 9921)]
    assert smoke_calls == []


def test_runtime_harness_fails_if_discovery_changes_after_ping_before_smoke(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921, reread_port=9922)
    smoke_calls: list[object] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda *args, **kwargs: smoke_calls.append(args),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert discovery.read_calls == [4321]
    assert smoke_calls == []
    assert result.smoke is None
    assert result.success is False
    assert any("changed after ping" in warning for warning in result.warnings)
    assert manifest["warnings"] == result.warnings


def test_runtime_harness_run_started_at_covers_rhino_launch(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    monotonic_times = iter([10.0, 10.5])
    copied_started_at: list[float] = []

    monkeypatch.setattr("rook.runtime_harness.time.time", lambda: next(monotonic_times))
    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
        ),
    )

    def record_artifact_copy(result, temp_rook_dir, label):
        if label.startswith("before-shutdown-"):
            copied_started_at.append(result.run_started_at)
        return []

    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", record_artifact_copy)
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert result.success is True
    assert result.run_started_at == 10.0
    assert copied_started_at == [10.0, 10.0]


def test_runtime_harness_readiness_failure_captures_artifacts_and_cleans_owned_process(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, fail_ready=True)
    artifact_labels: list[str] = []
    close_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.copy_temp_rook_artifacts",
        lambda result, temp_rook_dir, label: artifact_labels.append(label) or [],
    )
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: close_calls.append(cleanup_process)
        or cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert artifact_labels == [
        "readiness-failure-shared-discovery",
        "readiness-failure-legacy-temp-rook",
        "before-shutdown-shared-discovery",
        "before-shutdown-legacy-temp-rook",
        "after-shutdown-shared-discovery",
        "after-shutdown-legacy-temp-rook",
    ]
    assert close_calls == [process]
    assert result.smoke is None
    assert result.success is False
    assert any("owned ready failed" in warning for warning in result.warnings)
    assert manifest["smoke"] is None
    assert manifest["status"] == "non_green"


def test_runtime_harness_smoke_exception_warns_and_still_cleans_owned_process(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    close_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("smoke command missing")),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: close_calls.append(cleanup_process)
        or cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["missing-smoke"],
        discovery=discovery,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert close_calls == [process]
    assert result.smoke is None
    assert result.success is False
    assert result.cleanup_status == CleanupStatus.GRACEFUL_EXIT
    assert any("Rhino smoke command failed before result" in warning for warning in result.warnings)
    assert any("smoke command missing" in warning for warning in result.warnings)
    assert manifest["smoke"] is None
    assert manifest["warnings"] == result.warnings
    assert manifest["status"] == "non_green"


def test_runtime_harness_non_oserror_smoke_exception_warns_and_returns_result(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)
    close_calls: list[FakeHarnessProcess] = []

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad smoke")),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: close_calls.append(cleanup_process)
        or cleanup_process.wait(timeout_seconds)
        or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["bad-smoke"],
        discovery=discovery,
    )

    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert close_calls == [process]
    assert result.smoke is None
    assert result.success is False
    assert any("Rhino smoke command failed before result" in warning for warning in result.warnings)
    assert any("bad smoke" in warning for warning in result.warnings)
    assert manifest["warnings"] == result.warnings
    assert manifest["smoke"] is None
    assert manifest["status"] == "non_green"


def test_runtime_harness_forced_cleanup_is_non_green(tmp_path: Path, monkeypatch):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921)

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.kill() or True,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert result.cleanup_status == CleanupStatus.GRACEFUL_TIMEOUT_FORCED_KILL
    assert result.success is False
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cleanup"]["status"] == "graceful_timeout_forced_kill"
    assert manifest["status"] == "non_green"


def test_runtime_harness_discovery_leftover_after_graceful_exit_is_non_green(
    tmp_path: Path,
    monkeypatch,
):
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_text("fake", encoding="utf-8")
    process = FakeHarnessProcess(pid=4321, poll_results=[None, None])
    discovery = FakeHarnessDiscovery(pid=4321, port=9921, leftover=True)

    monkeypatch.setattr("rook.runtime_harness.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr(
        "rook.runtime_harness.run_smoke_command",
        lambda command, env_additions, cwd=None, timeout_seconds=None: SmokeCommandResult(
            command,
            _scoped_env_subset(env_additions),
            0,
            "",
            "",
            0.01,
        ),
    )
    monkeypatch.setattr("rook.runtime_harness.copy_temp_rook_artifacts", lambda *args: [])
    monkeypatch.setattr(
        "rook.runtime_harness.request_external_graceful_close",
        lambda cleanup_process, timeout_seconds, **kwargs: cleanup_process.wait(timeout_seconds) or False,
    )

    result = run_rhino_runtime_harness(
        rhino_exe=rhino_exe,
        artifact_root=tmp_path / "artifacts",
        smoke_command=["smoke"],
        discovery=discovery,
    )

    assert result.cleanup_status == CleanupStatus.GRACEFUL_EXIT_DISCOVERY_LEFTOVER
    assert result.success is False
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cleanup"]["status"] == "graceful_exit_discovery_leftover"
    assert manifest["status"] == "non_green"


def test_runtime_harness_cli_help_works():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_rhino_runtime_harness.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    assert "--rhino-exe" in result.stdout
    assert "--artifact-root" in result.stdout
    assert "--readiness-timeout" in result.stdout
    assert "--smoke" in result.stdout
    assert "ping-only" in result.stdout
    assert "gh-readiness" in result.stdout
    assert "gh-python-geometry-output" in result.stdout
    assert "command-control-saturation" in result.stdout


def test_runtime_harness_maps_gh_python_geometry_output_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_harness_cli_module()

    command, cwd = module._smoke_command("gh-python-geometry-output", repo_root)

    assert command == [
        sys.executable,
        "mcp_server/tools/gh_python_geometry_output_live_harness.py",
    ]
    assert cwd == repo_root


def test_runtime_harness_maps_runscript_safety_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_harness_cli_module()

    command, cwd = module._smoke_command("runscript-safety", repo_root)

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_runscript_safety_live.py",
        "-m",
        "requires_rhino and runscript_safety_live and not runscript_safety_hooks",
        "-v",
    ]
    assert cwd == repo_root / "mcp_server"
    assert module._smoke_timeout_seconds("runscript-safety") == 120.0
    assert module._readiness_timeout_seconds("runscript-safety", None) == 90.0
    assert module._readiness_timeout_seconds("runscript-safety", 45.0) == 45.0
    assert module._launch_env_overrides("runscript-safety") == {
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
        "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": None,
    }


def test_runtime_harness_maps_runscript_safety_hooks_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_harness_cli_module()

    command, cwd = module._smoke_command("runscript-safety-hooks", repo_root)

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_runscript_safety_live.py",
        "-m",
        "requires_rhino and runscript_safety_live and runscript_safety_hooks",
        "-v",
    ]
    assert cwd == repo_root / "mcp_server"
    assert module._smoke_timeout_seconds("runscript-safety-hooks") == 120.0
    assert module._readiness_timeout_seconds("runscript-safety-hooks", None) == 90.0
    assert module._launch_env_overrides("runscript-safety-hooks") == {
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
        "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": "1",
    }


def test_runtime_harness_maps_command_control_saturation_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_harness_cli_module()

    command, cwd = module._smoke_command("command-control-saturation", repo_root)

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_native_command_control_live.py",
        "-m",
        "requires_rhino and command_control_live",
        "-v",
    ]
    assert cwd == repo_root / "mcp_server"
    assert module._smoke_timeout_seconds("command-control-saturation") == 45.0
    assert module._readiness_timeout_seconds("command-control-saturation", None) == 45.0
    assert module._launch_env_overrides("command-control-saturation") == {
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": "1",
    }


def test_runtime_harness_router_plane_smokes_use_cold_start_readiness_ceiling():
    module = _load_harness_cli_module()

    for smoke in (
        "p2-bridge-diagnosis",
        "p3-session-mutation",
        "p4-workbench-lifecycle",
        "p5-registry-reclaim",
        "p6-artifact-perception",
    ):
        assert module._readiness_timeout_seconds(smoke, None) == 90.0
        assert module._readiness_timeout_seconds(smoke, 12.5) == 12.5


def test_runtime_harness_uses_legacy_default_readiness_for_other_smoke():
    module = _load_harness_cli_module()

    assert module._readiness_timeout_seconds("ping-only", None) == 30.0
    assert module._readiness_timeout_seconds("ping-only", 12.5) == 12.5
