from __future__ import annotations
import asyncio
from rook import server, work_units, targeting


def test_p7_tools_are_meta_no_rhino():
    for name in ("rhino_work_unit_register", "rhino_work_unit_link_artifact",
                 "rhino_merge_contract_record", "rhino_merge_contract_validate", "rhino_work_units"):
        assert name in targeting._ALL_KNOWN_TOOLS
        pol = targeting.policy_for_tool(name)
        assert pol.requires_rhino is False   # non-routed, works at 0/1/many Rhinos


def test_call_tool_dispatches_register(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()
    out = asyncio.run(server.call_tool("rhino_work_unit_register", {"label": "X"}))
    from rook.tool_result import parse_call_tool_data
    data = parse_call_tool_data(out)
    assert data["workUnitId"].startswith("wu-")
    work_units._reset_work_units_registry_singleton()
