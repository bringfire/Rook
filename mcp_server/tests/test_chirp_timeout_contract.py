from pathlib import Path

from rook import local_testing_proof


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def _tree_bytes(relative: str) -> dict[str, bytes]:
    root = ROOT / relative
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_active_chirp_contract_uses_component_errors_only():
    server_source = _source("mcp_server/src/rook/server.py")
    chirp_block = _slice(server_source, 'case "chirp_create":', 'case "gh_errors":')
    create_script_block = _slice(
        server_source,
        "async def _execute_gh_create_script(",
        "async def _execute_gh_set_script_pins(",
    )

    assert "component_errors" in chirp_block
    assert "compilation_errors" not in chirp_block
    assert "compilation_errors" in create_script_block

    proof_source = _source("mcp_server/src/rook/local_testing_proof.py")
    validation_block = _slice(
        proof_source,
        "def _chirp_validation_failure(",
        "async def run_live_smoke(",
    )
    assert 'chirp_data.get("component_errors")' in validation_block
    assert "compilation_errors" not in validation_block


def test_chirp_skill_mirrors_are_byte_identical_and_describe_timeout_contract():
    for skill_name in ("chirp", "chirp-cascade"):
        agent_tree = _tree_bytes(f".agents/skills/{skill_name}")
        assert agent_tree == _tree_bytes(f".claude/skills/{skill_name}")
        assert agent_tree == _tree_bytes(
            f"installer/agent-assets/codex-skills/{skill_name}"
        )

        skill_body = agent_tree["SKILL.md"].decode("utf-8")
        for token in (
            "chirp_invalid_inference_timeout",
            "chirp_inference_timeout",
            "chirp_transport_timeout",
            "component_errors",
        ):
            assert token in skill_body
        assert "retry the whole" not in skill_body.lower()
        assert "retry only missing" in skill_body.lower()


def test_chirp_validation_failure_runtime_contract_is_component_error():
    failure, component_guid = local_testing_proof._chirp_validation_failure(
        {
            "success": True,
            "data": {
                "component_guid": "11111111-1111-4111-8111-111111111111",
                "component_errors": ["runtime message"],
            },
        }
    )
    assert component_guid == "11111111-1111-4111-8111-111111111111"
    assert failure is not None
    assert failure.failure_label == "chirp_component_error"
