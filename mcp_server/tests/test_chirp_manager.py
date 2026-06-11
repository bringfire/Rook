from pathlib import Path

from rook import chirp_manager


def test_start_chirp_detaches_stdio_no_port(monkeypatch, tmp_path):
    """_start_chirp does not pass CHIRP_PORT — Chirp uses port 0 (OS-assigned)."""
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    captured: dict = {}

    class _DummyProc:
        pass

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _DummyProc()

    monkeypatch.setattr(chirp_manager, "DISCOVERY_FOLDER", tmp_path / "discovery")
    monkeypatch.setattr(chirp_manager.subprocess, "Popen", fake_popen)

    proc = chirp_manager._start_chirp(chirp_home)

    assert isinstance(proc, _DummyProc)
    assert captured["args"] == ([str(python_exe), "-m", "chirp"],)
    assert captured["kwargs"]["cwd"] == str(chirp_home)
    # CHIRP_PORT must NOT be in env — let Chirp default to port 0
    assert "CHIRP_PORT" not in captured["kwargs"]["env"]
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
        == chirp_manager.subprocess.CREATE_NO_WINDOW
    )


def test_start_chirp_returns_none_when_no_venv(tmp_path):
    """_start_chirp returns None when the venv is missing."""
    chirp_home = tmp_path / "Chirp"
    chirp_home.mkdir()
    # No .venv created
    result = chirp_manager._start_chirp(chirp_home)
    assert result is None
