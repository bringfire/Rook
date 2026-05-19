from types import SimpleNamespace

from rook.preflight import preflight_rhino_command


class FakeKnowledgeStore:
    def __init__(self, command_knowledge=None, parsed=None):
        self.command_knowledge = command_knowledge
        self.parsed = parsed or {
            "command": "-Box",
            "mode": "default",
            "syntax": "_-Box <corner1> <corner2>",
            "parameters": {"corner1": "0,0,0", "corner2": "1,1,0"},
            "options_used": [],
        }

    def parse_command_string(self, command_string):
        return self.parsed

    def get_command(self, command):
        return self.command_knowledge


def command_knowledge(*, preconditions=None, modes=None, options=None):
    return SimpleNamespace(
        preconditions=preconditions or {},
        modes=modes or {
            "default": SimpleNamespace(syntax="_-Box <corner1> <corner2>"),
        },
        options=options or {},
    )


def assert_safety_refusal(result, reason, command=None, mode=None):
    assert result is not None
    assert result["success"] is False
    assert result["data"]["error"] == "run_script_safety_refusal"
    assert result["data"]["reason"] == reason
    assert result["data"]["verified"] is False
    assert (
        result["data"]["recovery"]
        == "Use a typed Rook tool or a known-safe fully scripted command."
    )
    if command is not None:
        assert result["data"]["command"] == command
    if mode is not None:
        assert result["data"]["mode"] == mode


def test_rejects_when_knowledge_store_unavailable():
    result = preflight_rhino_command("_-Box 0,0,0 1,1,0", None)

    assert_safety_refusal(
        result,
        "command_safety_unavailable",
        command="_-Box 0,0,0 1,1,0",
    )


def test_rejects_unknown_command_from_store():
    result = preflight_rhino_command(
        "_-Box 0,0,0 1,1,0",
        FakeKnowledgeStore(command_knowledge=None),
    )

    assert_safety_refusal(
        result,
        "unknown_command",
        command="-Box",
        mode="default",
    )


def test_rejects_known_command_without_explicit_safe_metadata():
    result = preflight_rhino_command(
        "_-Box 0,0,0 1,1,0",
        FakeKnowledgeStore(command_knowledge=command_knowledge()),
    )

    assert_safety_refusal(
        result,
        "command_not_marked_safe_non_interactive",
        command="-Box",
        mode="default",
    )


def test_allows_known_command_with_command_level_safe_metadata():
    result = preflight_rhino_command(
        "_-Box 0,0,0 1,1,0",
        FakeKnowledgeStore(
            command_knowledge=command_knowledge(
                preconditions={"safe_non_interactive": True},
            ),
        ),
    )

    assert result is None


def test_allows_dict_command_knowledge_with_command_level_safe_metadata():
    result = preflight_rhino_command(
        "_-Box 0,0,0 1,1,0",
        FakeKnowledgeStore(
            command_knowledge={
                "preconditions": {"safe_non_interactive": True},
                "modes": {
                    "default": {"syntax": "_-Box <corner1> <corner2>"},
                },
                "options": {},
            },
        ),
    )

    assert result is None


def test_allows_known_command_with_mode_safe_metadata():
    parsed = {
        "command": "-Box",
        "mode": "center",
        "syntax": "_-Box _Center <center> <corner>",
        "parameters": {"center": "0,0,0", "corner": "1,1,0"},
        "options_used": ["_Center"],
    }
    result = preflight_rhino_command(
        "_-Box _Center 0,0,0 1,1,0",
        FakeKnowledgeStore(
            parsed=parsed,
            command_knowledge=command_knowledge(
                preconditions={"safe_non_interactive_modes": ["center"]},
                modes={
                    "center": SimpleNamespace(
                        syntax="_-Box _Center <center> <corner>",
                    ),
                },
                options={"_Center": "Create box from center point"},
            ),
        ),
    )

    assert result is None
