import json
import subprocess
from pathlib import Path

import pytest


def test_validate_working_directory_defaults_to_executable_parent(tmp_path):
    from rook.mesh2splat.process import validate_working_directory

    exe = tmp_path / "bin" / "Mesh2Splat.exe"
    exe.parent.mkdir()
    exe.write_text("exe", encoding="utf-8")

    assert validate_working_directory(None, exe) == exe.parent.resolve()


def test_validate_working_directory_rejects_invalid_values(tmp_path):
    from rook.mesh2splat import process

    exe = tmp_path / "bin" / "Mesh2Splat.exe"
    exe.parent.mkdir()
    exe.write_text("exe", encoding="utf-8")
    missing = tmp_path / "missing"

    with pytest.raises(process.Mesh2SplatProcessError) as exc:
        process.validate_working_directory(str(missing), exe)

    assert exc.value.code == "invalid_working_directory"
    assert exc.value.diagnostics["path"] == str(missing)


def test_validate_working_directory_rejects_relative_values(tmp_path, monkeypatch):
    from rook.mesh2splat import process

    exe = tmp_path / "bin" / "Mesh2Splat.exe"
    exe.parent.mkdir()
    exe.write_text("exe", encoding="utf-8")
    relative = Path("relative-work")
    (tmp_path / relative).mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(process.Mesh2SplatProcessError) as exc:
        process.validate_working_directory(str(relative), exe)

    assert exc.value.code == "invalid_working_directory"
    assert exc.value.diagnostics["path"] == str(relative)


def test_sanitized_child_environment_keeps_only_safe_names_and_optional_path():
    from rook.mesh2splat.process import sanitized_child_environment

    parent_env = {
        "SystemRoot": "C:/Windows",
        "windir": "C:/Windows",
        "TEMP": "C:/Temp",
        "TMP": "C:/Tmp",
        "PATH": "C:/tools",
        "OPENAI_API_KEY": "secret",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "ROOK_TOKEN": "secret",
    }

    without_path = sanitized_child_environment(
        source_requires_path=False, parent_env=parent_env
    )
    with_path = sanitized_child_environment(
        source_requires_path=True, parent_env=parent_env
    )

    assert without_path == {
        "SystemRoot": "C:/Windows",
        "windir": "C:/Windows",
        "TEMP": "C:/Temp",
        "TMP": "C:/Tmp",
    }
    assert with_path == {**without_path, "PATH": "C:/tools"}
    assert "OPENAI_API_KEY" not in with_path
    assert "AWS_SECRET_ACCESS_KEY" not in with_path
    assert "ROOK_TOKEN" not in with_path


def test_run_mesh2splat_uses_argv_list_shell_false_and_no_command_string(
    tmp_path, monkeypatch
):
    from rook.mesh2splat import process

    captured = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.returncode = 0

        def communicate(self, timeout):
            captured["timeout"] = timeout
            return ('{"status":"ok"}\n', "")

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)

    result = process.run_mesh2splat(
        [str(tmp_path / "Mesh2Splat.exe"), "--input", "capture.glb"],
        cwd=tmp_path,
        env={"SystemRoot": "C:/Windows"},
        timeout_seconds=9,
    )

    assert captured["args"] == [
        str(tmp_path / "Mesh2Splat.exe"),
        "--input",
        "capture.glb",
    ]
    assert isinstance(captured["args"], list)
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["kwargs"]["env"] == {"SystemRoot": "C:/Windows"}
    assert captured["kwargs"]["text"] is True
    assert captured["timeout"] == 9
    assert result.success is True
    assert result.parsed_stdout == {"status": "ok"}


def test_timeout_returns_error_and_records_direct_child_termination(
    tmp_path, monkeypatch
):
    from rook.mesh2splat import process

    calls = []

    class FakePopen:
        pid = 4321
        returncode = None

        def communicate(self, timeout=None):
            calls.append(("communicate", timeout))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(cmd=["Mesh2Splat.exe"], timeout=timeout)
            return ("", "after terminate")

        def terminate(self):
            calls.append(("terminate", None))

        def kill(self):
            calls.append(("kill", None))

    monkeypatch.setattr(process.subprocess, "Popen", lambda *args, **kwargs: FakePopen())
    monkeypatch.setattr(process.os, "name", "posix")

    result = process.run_mesh2splat(
        ["Mesh2Splat.exe"],
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
    )

    assert result.success is False
    assert result.error_code == "mesh2splat_timeout"
    assert ("terminate", None) in calls
    assert result.diagnostics["processTreeTermination"] == "direct_child_only"


def test_parse_last_stdout_json_uses_last_non_empty_json_line():
    from rook.mesh2splat.process import parse_last_stdout_json

    stdout = """
starting conversion
{"status":"intermediate","gaussians":1}

{"status":"complete","gaussians":2}
"""

    assert parse_last_stdout_json(stdout) == {
        "status": "complete",
        "gaussians": 2,
    }


def test_parse_last_stdout_json_ignores_trailing_non_json_lines():
    from rook.mesh2splat.process import parse_last_stdout_json

    assert parse_last_stdout_json('{"status":"ok"}\nnot json\n') == {"status": "ok"}


def test_parse_last_stdout_json_returns_last_json_object_not_last_json_value():
    from rook.mesh2splat.process import parse_last_stdout_json

    assert parse_last_stdout_json('{"status":"ok"}\n["not", "object"]\n') == {
        "status": "ok"
    }


@pytest.mark.parametrize(
    "returncode,stdout",
    [
        (4, "{}\n"),
        (1, json.dumps({"code": "GLB_PARSE_FAILED"}) + "\ncleanup complete\n"),
        (1, json.dumps({"error": {"code": "GLB_PARSE_FAILED"}}) + "\nlog tail\n"),
    ],
)
def test_glb_parse_failures_map_to_rook_error_code(
    tmp_path, monkeypatch, returncode, stdout
):
    from rook.mesh2splat import process

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = returncode

        def communicate(self, timeout):
            return (stdout, "")

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)

    result = process.run_mesh2splat(
        ["Mesh2Splat.exe"],
        cwd=tmp_path,
        env={},
        timeout_seconds=5,
    )

    assert result.success is False
    assert result.error_code == "mesh2splat_glb_parse_failed"


def test_capacity_exceeded_json_maps_to_rook_error_code(tmp_path, monkeypatch):
    from rook.mesh2splat import process

    class FakePopen:
        returncode = 1

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return (json.dumps({"code": "CAPACITY_EXCEEDED"}) + "\nlog tail\n", "")

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)

    result = process.run_mesh2splat(
        ["Mesh2Splat.exe"],
        cwd=tmp_path,
        env={},
        timeout_seconds=5,
    )

    assert result.success is False
    assert result.error_code == "mesh2splat_capacity_exceeded"


def test_gl_context_init_failed_json_maps_to_rook_error_code(tmp_path, monkeypatch):
    from rook.mesh2splat import process

    class FakePopen:
        returncode = 1

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return (
                json.dumps({"errorCode": "GL_CONTEXT_INIT_FAILED"}) + "\n",
                "failed to create OpenGL context",
            )

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)

    result = process.run_mesh2splat(
        ["Mesh2Splat.exe"],
        cwd=tmp_path,
        env={},
        timeout_seconds=5,
    )

    assert result.success is False
    assert result.error_code == "mesh2splat_gl_context_init_failed"


@pytest.mark.parametrize(
    "stdout,expected_error_code",
    [
        (
            json.dumps({"ok": False, "errorCode": "GLB_PARSE_FAILED"}) + "\n",
            "mesh2splat_glb_parse_failed",
        ),
        (
            json.dumps({"ok": False, "errorCode": "CAPACITY_EXCEEDED"}) + "\n",
            "mesh2splat_capacity_exceeded",
        ),
        (
            json.dumps({"ok": False, "errorCode": "GL_CONTEXT_INIT_FAILED"}) + "\n",
            "mesh2splat_gl_context_init_failed",
        ),
        (
            json.dumps({"ok": False, "errorCode": "SOME_FAILURE"}) + "\n",
            "mesh2splat_failed",
        ),
    ],
)
def test_ok_false_json_maps_to_failure_even_with_zero_returncode(
    tmp_path, monkeypatch, stdout, expected_error_code
):
    from rook.mesh2splat import process

    class FakePopen:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return (stdout, "")

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)

    result = process.run_mesh2splat(
        ["Mesh2Splat.exe"],
        cwd=tmp_path,
        env={},
        timeout_seconds=5,
    )

    assert result.success is False
    assert result.error_code == expected_error_code
