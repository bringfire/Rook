from rook import server
from rook.agent import tool_groups
from rook.targeting import RhinoToolPolicy, policy_for_tool
from rook.targeting import (
    _ALL_KNOWN_TOOLS,
    _META_TOOLS,
    _RHINO_READ_TOOLS,
    _RHINO_INDEPENDENT_READ_TOOLS,
    _RHINO_INDEPENDENT_MUTATE_TOOLS,
)


def test_export_preset_schema_shape():
    schema = server._rookbim_export_preset_schema()
    props = schema["properties"]
    assert "preset" in props
    assert "output" in props
    assert "includeCategories" in props
    assert "excludeCategories" in props
    assert "layerPolicy" in props
    assert "namePolicy" in props
    assert "metadataProfile" in props
    assert "limitPerCategory" in props
    assert schema["required"] == ["preset", "output"]
    assert schema["additionalProperties"] is False


def test_export_preset_derives_mutate_policy():
    # The derived policy must be (True, "mutate") — achieved by membership in _ALL_KNOWN_TOOLS
    # and ABSENCE from every read/meta bucket (the user's plan note 1).
    assert policy_for_tool("rookbim_export_preset") == RhinoToolPolicy(True, "mutate")
    assert "rookbim_export_preset" in _ALL_KNOWN_TOOLS
    assert "rookbim_export_preset" not in _META_TOOLS
    assert "rookbim_export_preset" not in _RHINO_READ_TOOLS
    assert "rookbim_export_preset" not in _RHINO_INDEPENDENT_READ_TOOLS
    assert "rookbim_export_preset" not in _RHINO_INDEPENDENT_MUTATE_TOOLS


def test_export_preset_in_full_group_not_readonly():
    assert "rookbim_export_preset" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_preset" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]


def test_export_preset_to_rhino_derives_mutate_policy():
    assert policy_for_tool("rookbim_export_preset_to_rhino") == RhinoToolPolicy(True, "mutate")
    assert "rookbim_export_preset_to_rhino" in _ALL_KNOWN_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _META_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_READ_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_INDEPENDENT_READ_TOOLS
    assert "rookbim_export_preset_to_rhino" not in _RHINO_INDEPENDENT_MUTATE_TOOLS


def test_export_preset_to_rhino_in_full_group_not_readonly():
    assert "rookbim_export_preset_to_rhino" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_preset_to_rhino" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
