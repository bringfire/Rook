import json
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
    HarnessStatus,
    OwnedRhinoDiscovery,
    RhinoHarnessResult,
    run_smoke_command,
    ping_native,
)


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

    def __init__(self, timeout: float):
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
            timeout_seconds=0.2,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert result.returncode != 0
        assert "timed out" in result.stderr.lower()
        assert "parent-start" in result.stdout
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
            timeout_seconds=0.2,
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


def test_harness_manifest_contains_future_cleanup_and_readiness_fields(tmp_path: Path):
    ready_path = tmp_path / "owned-discovery-instance-2222-native.json"
    ready_path.write_text('{"processId":2222}', encoding="utf-8")
    smoke = run_smoke_command(
        [sys.executable, "-c", "print('ok')"],
        env_additions={
            "ROOK_RHINO_PORT": "9010",
            "ROOK_RHINO_PROCESS_ID": "2222",
            "NATIVE_PORT": "9010",
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
            },
            "returncode": 0,
            "stdout": "ok\n",
            "stderr": "",
            "duration_seconds": smoke.duration_seconds,
            "timed_out": False,
        },
        "cleanup": {
            "status": "not_attempted",
        },
        "status": "success",
        "success": True,
    }
