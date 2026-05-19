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
    assert result["data"]["error_code"] == "run_script_safety_refusal"
    assert result["data"]["reason"] == reason
    assert result["data"]["verified"] is False
    assert result["data"]["retry_allowed"] is False
    assert result["data"]["safety_class"] == "good_refusal"
    if command is not None:
        assert result["data"]["command"] == command
        assert result["data"]["detected_command"] == command
    if mode is not None:
        assert result["data"]["mode"] == mode


def test_line_refusal_advises_existing_rhino_create_tool():
    result = preflight_rhino_command("_Line", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_Line")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_create",
            "reason": "Create lines through the typed creation schema with explicit start and end points.",
            "required_parameters": ["type", "start", "end"],
        }
    ]


def test_circle_refusal_advises_existing_rhino_create_tool():
    result = preflight_rhino_command("_Circle", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_Circle")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_create",
            "reason": "Create circles through the typed creation schema with explicit center and radius.",
            "required_parameters": ["type", "center", "radius"],
        }
    ]


def test_selection_refusal_advises_existing_selection_tool():
    result = preflight_rhino_command("_SelNone", None)

    assert_safety_refusal(result, "command_safety_unavailable", command="_SelNone")
    assert result["data"]["candidate_tools"] == [
        {
            "tool": "rhino_select_none",
            "reason": "Clear selection through the typed selection tool instead of a raw command.",
            "required_parameters": [],
        }
    ]


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


def test_rejects_unmatched_raw_values_even_when_command_marked_safe():
    parsed = {
        "command": "-Box",
        "mode": "default",
        "syntax": "_-Box <corner1> <corner2>",
        "parameters": {"corner1": "0,0,0", "corner2": "1,1,0"},
        "options_used": [],
        "raw_values": ["unexpected"],
    }

    result = preflight_rhino_command(
        "_-Box 0,0,0 1,1,0 unexpected",
        FakeKnowledgeStore(
            parsed=parsed,
            command_knowledge=command_knowledge(
                preconditions={"safe_non_interactive": True},
            ),
        ),
    )

    assert_safety_refusal(
        result,
        "unmatched_command_tokens",
        command="-Box",
        mode="default",
    )
    assert result["data"]["raw_values"] == ["unexpected"]


def test_rejects_missing_required_values_with_safety_refusal():
    parsed = {
        "command": "-Box",
        "mode": "default",
        "syntax": "_-Box <corner1> <corner2>",
        "parameters": {"corner1": "0,0,0"},
        "options_used": [],
    }

    result = preflight_rhino_command(
        "_-Box 0,0,0",
        FakeKnowledgeStore(
            parsed=parsed,
            command_knowledge=command_knowledge(
                preconditions={"safe_non_interactive": True},
            ),
        ),
    )

    assert_safety_refusal(
        result,
        "missing_required_command_values",
        command="-Box",
        mode="default",
    )
    assert result["data"]["missing_required"] == ["corner2"]
    assert result["data"]["expected_syntax"] == "_-Box <corner1> <corner2>"


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
