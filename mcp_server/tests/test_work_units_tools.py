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


def test_p7_slice2_tools_are_meta_no_rhino():
    for name in ("rhino_declared_target_declare", "rhino_declared_target_promote", "rhino_declared_targets"):
        assert name in targeting._ALL_KNOWN_TOOLS
        assert name in targeting._META_TOOLS
        assert targeting.policy_for_tool(name).requires_rhino is False


def test_call_tool_dispatches_declare(tmp_path, monkeypatch):
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    work_units._reset_work_units_registry_singleton()
    out = asyncio.run(server.call_tool("rhino_declared_target_declare",
        {"intendedPath": str(tmp_path / "m.3dm"), "label": "M"}))
    from rook.tool_result import parse_call_tool_data
    data = parse_call_tool_data(out)
    assert data["declaredTargetId"].startswith("dt-")
    work_units._reset_work_units_registry_singleton()


def test_p7_slice3_tools_are_meta_no_rhino():
    for name in ("rhino_planned_contract_record", "rhino_planned_contract_activate", "rhino_planned_contracts"):
        assert name in targeting._ALL_KNOWN_TOOLS
        assert name in targeting._META_TOOLS
        assert targeting.policy_for_tool(name).requires_rhino is False


def test_call_tool_dispatches_planned_record(tmp_path, monkeypatch):
    from rook import artifacts
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    asyncio.run(server.call_tool("rhino_declared_target_declare", {"intendedPath": str(tmp_path / "M.3dm")}))
    asyncio.run(server.call_tool("rhino_declared_target_declare", {"intendedPath": str(tmp_path / "A.3dm")}))
    from rook.tool_result import parse_call_tool_data
    dts = [d["declaredTargetId"] for d in
           parse_call_tool_data(asyncio.run(server.call_tool("rhino_declared_targets", {})))["declaredTargets"]]
    out = asyncio.run(server.call_tool("rhino_planned_contract_record", {
        "target": {"kind": "declared_target", "id": dts[0]},
        "sources": [{"kind": "declared_target", "id": dts[1]}],
        "mergeKind": "import", "refreshPolicy": "refresh_on_demand"}))
    assert parse_call_tool_data(out)["plannedContractId"].startswith("pc-")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
