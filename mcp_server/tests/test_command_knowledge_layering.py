from __future__ import annotations

import json
from pathlib import Path

import pytest

from rook import runtime_paths
from rook.learning.command_knowledge_store import CommandKnowledgeStore
from rook.preflight import preflight_rhino_command


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _command_payload(commands: dict[str, dict]) -> dict:
    return {"version": "1.0", "commands": commands}


def _grasshopper_command(**overrides) -> dict:
    payload = {
        "command": "-Grasshopper",
        "description": "Bundled Grasshopper launcher",
        "modes": {
            "default": {
                "syntax": "_Grasshopper",
                "dialogue": "Open Grasshopper",
                "example": "_Grasshopper",
                "description": "Launch Grasshopper",
            }
        },
        "options": {},
        "preconditions": {
            "requires_selection": False,
            "selection_type": "none",
            "clear_pending": False,
            "safe_non_interactive": True,
        },
        "gotchas": ["bundled gotcha"],
        "related_commands": ["GrasshopperUnloadPlugin"],
        "observations_count": 2,
        "last_updated": "2026-05-24T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def installed_runtime(monkeypatch, tmp_path: Path):
    install_root = tmp_path / "Rook" / "app"
    data_root = tmp_path / "Rook" / "data"
    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("ROOK_DATA_DIR", str(data_root))
    monkeypatch.setenv("ROOK_MODE", "release")
    monkeypatch.setattr(runtime_paths, "_cached_runtime_paths", None)
    yield install_root, data_root
    monkeypatch.setattr(runtime_paths, "_cached_runtime_paths", None)


def test_default_store_keeps_single_file_semantics_when_bundled_and_mutable_paths_match(monkeypatch, tmp_path: Path):
    install_root = tmp_path / "Rook"
    shared_path = install_root / "knowledge" / "commands" / "command_knowledge.json"
    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("ROOK_DATA_DIR", str(install_root / "knowledge"))
    monkeypatch.setenv("ROOK_MODE", "dev")
    monkeypatch.setattr(runtime_paths, "_cached_runtime_paths", None)
    _write_json(
        shared_path,
        _command_payload({"-Sphere": _grasshopper_command(command="-Sphere", observations_count=12)}),
    )

    store = CommandKnowledgeStore()
    command = store.get_command("-Sphere")
    diagnostics = store.layering_diagnostics()

    assert command is not None
    assert diagnostics["layered"] is False
    assert store.get_command_source("-Sphere") == "mutable"
    assert command.observations_count == 12


def test_layered_default_store_keeps_bundled_grasshopper_when_mutable_is_stale(installed_runtime):
    install_root, data_root = installed_runtime
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )
    _write_json(
        data_root / "commands" / "command_knowledge.json",
        _command_payload({}),
    )

    store = CommandKnowledgeStore()

    assert store.get_command_source("-Grasshopper") == "bundled"
    assert preflight_rhino_command("_Grasshopper", store) is None


def test_layered_default_store_uses_bundled_safety_when_mutable_grasshopper_is_unsafe(installed_runtime):
    install_root, data_root = installed_runtime
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )
    _write_json(
        data_root / "commands" / "command_knowledge.json",
        _command_payload(
            {
                "-Grasshopper": _grasshopper_command(
                    description="stale mutable launcher",
                    modes={},
                    options={"_Bad": "stale"},
                    preconditions={},
                    gotchas=["mutable gotcha"],
                    related_commands=["MutableOnly"],
                    observations_count=3,
                )
            }
        ),
    )

    store = CommandKnowledgeStore()
    command = store.get_command("-Grasshopper")

    assert command is not None
    assert store.get_command_source("-Grasshopper") == "layered"
    assert command.description == "Bundled Grasshopper launcher"
    assert command.preconditions["safe_non_interactive"] is True
    assert "mutable gotcha" in command.gotchas
    assert command.observations_count == 5
    assert preflight_rhino_command("_Grasshopper", store) is None


def test_layered_default_store_preserves_mutable_only_commands(installed_runtime):
    install_root, data_root = installed_runtime
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({}),
    )
    _write_json(
        data_root / "commands" / "command_knowledge.json",
        _command_payload(
            {
                "-UserCommand": {
                    "command": "-UserCommand",
                    "description": "User learned command",
                    "modes": {"default": {"syntax": "_UserCommand"}},
                    "options": {},
                    "preconditions": {"safe_non_interactive": True},
                    "gotchas": [],
                    "related_commands": [],
                    "observations_count": 1,
                    "last_updated": "2026-05-24T00:00:00+00:00",
                }
            }
        ),
    )

    store = CommandKnowledgeStore()

    assert store.get_command("-UserCommand") is not None
    assert store.get_command_source("-UserCommand") == "mutable"


def test_layered_save_writes_only_mutable_overlay_for_bundled_commands(installed_runtime):
    install_root, data_root = installed_runtime
    mutable_path = data_root / "commands" / "command_knowledge.json"
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )

    store = CommandKnowledgeStore()

    assert store.add_gotcha("-Grasshopper", "user gotcha") is True
    assert store.increment_observations("-Grasshopper") is True
    assert store.save() is True

    mutable = json.loads(mutable_path.read_text(encoding="utf-8"))
    command = mutable["commands"]["-Grasshopper"]
    assert command["gotchas"] == ["user gotcha"]
    assert command["observations_count"] == 1
    assert "modes" not in command
    assert "options" not in command
    assert "preconditions" not in command
    assert "description" not in command


def test_layered_save_prunes_stale_full_mutable_records_for_bundled_commands(installed_runtime):
    install_root, data_root = installed_runtime
    mutable_path = data_root / "commands" / "command_knowledge.json"
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )
    _write_json(
        mutable_path,
        _command_payload(
            {
                "-Grasshopper": _grasshopper_command(
                    description="stale mutable launcher",
                    modes={},
                    options={"_Bad": "stale"},
                    preconditions={},
                    gotchas=["mutable gotcha"],
                    related_commands=["MutableOnly"],
                    observations_count=3,
                )
            }
        ),
    )

    store = CommandKnowledgeStore()

    assert store.add_gotcha("-Grasshopper", "new gotcha") is True
    assert store.save() is True

    mutable = json.loads(mutable_path.read_text(encoding="utf-8"))
    command = mutable["commands"]["-Grasshopper"]
    assert command["gotchas"] == ["mutable gotcha", "new gotcha"]
    assert command["related_commands"] == ["MutableOnly"]
    assert command["observations_count"] == 3
    assert "modes" not in command
    assert "options" not in command
    assert "preconditions" not in command
    assert "description" not in command


def test_custom_path_store_keeps_single_file_semantics(tmp_path: Path, installed_runtime):
    install_root, _data_root = installed_runtime
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )
    custom_path = tmp_path / "custom" / "command_knowledge.json"
    _write_json(custom_path, _command_payload({}))

    store = CommandKnowledgeStore(path=custom_path)

    assert store.get_command("-Grasshopper") is None
    assert store.get_command_source("-Grasshopper") == "missing"


def test_layered_store_reports_provenance_diagnostics(installed_runtime):
    install_root, data_root = installed_runtime
    _write_json(
        install_root / "knowledge" / "commands" / "command_knowledge.json",
        _command_payload({"-Grasshopper": _grasshopper_command()}),
    )
    _write_json(
        data_root / "commands" / "command_knowledge.json",
        _command_payload({"-UserCommand": {"command": "-UserCommand", "modes": {}}}),
    )

    store = CommandKnowledgeStore()
    diagnostics = store.layering_diagnostics()

    assert diagnostics["bundled_path"].endswith("app\\knowledge\\commands\\command_knowledge.json") or diagnostics["bundled_path"].endswith("app/knowledge/commands/command_knowledge.json")
    assert diagnostics["mutable_path"].endswith("data\\commands\\command_knowledge.json") or diagnostics["mutable_path"].endswith("data/commands/command_knowledge.json")
    assert diagnostics["bundled_count"] == 1
    assert diagnostics["mutable_only_count"] == 1
    assert diagnostics["effective_count"] == 2
