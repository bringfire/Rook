from rook.agent import tool_groups
from rook import targeting


def test_export_tool_in_full_group_not_readonly():
    assert "rookbim_export_elements" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_elements" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]


def test_export_tool_policy_is_rhino_mutate():
    policy = targeting.policy_for_tool("rookbim_export_elements")
    assert policy.requires_rhino is True
    assert policy.risk == "mutate"


def test_export_tool_in_all_known_tools():
    assert "rookbim_export_elements" in targeting._ALL_KNOWN_TOOLS
