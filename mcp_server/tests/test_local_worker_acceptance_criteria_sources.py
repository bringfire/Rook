import ast
import copy
import importlib.util
import inspect
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

import rook.agent as agent_package
from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
    assemble_acceptance_criteria_packet,
)
from rook.agent import local_worker_acceptance_criteria_sources as module
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


def _expected_sources(**overrides):
    values = {
        "pin_contract": AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        "verifier_outcome": AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        "receipt_diagnostic": AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC],
        ),
        "convention": AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
        "unresolved_intent": (),
    }
    values.update(overrides)
    return AcceptanceCriteriaSources(**values)


def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5x", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_objects():
    probe = _load_lm5k_probe_script()
    _scaffold, result = probe.derive_probe_graph_state()
    return {
        "probe": probe,
        "workflow_contract": probe._probe_contract(),
        "graph": result.final_graph,
        "convention_packets": (probe._script_body_gotcha_packet(),),
    }


def _extract_from_fixture():
    fixture = _fixture_objects()
    return extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
    )


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _legacy_projection(packet):
    return [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in packet["criteria"]
    ]


def _import_names(source):
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
            if node.module:
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def _call_names(source):
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                calls.add(f"{node.func.value.id}.{node.func.attr}")
            calls.add(node.func.attr)
    return calls


def test_public_surface_exports_only_extractor():
    assert module.__all__ == ("extract_acceptance_criteria_sources",)


def test_source_module_import_boundary_stays_one_way_and_narrow():
    source = inspect.getsource(module)
    imports = _import_names(source)
    calls = _call_names(source)

    assert "rook.agent.local_worker_acceptance_criteria" in imports
    forbidden_source_fragments = (
        "BindStepSpec",
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "LiteLLM",
        "run_local_worker",
        "yaml",
        "base_params",
        "PROBE_REPAIR_CODE",
        "pathlib",
        "json",
        "builtins",
        "importlib.import_module",
        "import_module",
        "__import__",
    )
    for fragment in forbidden_source_fragments:
        assert fragment not in source
    assert not any(
        "local_worker_acceptance_criteria_sources" in imported
        for imported in _import_names(
            inspect.getsource(
                __import__(
                    "rook.agent.local_worker_acceptance_criteria",
                    fromlist=["dummy"],
                )
            )
        )
    )
    forbidden_import_fragments = (
        "BindStepSpec",
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "LiteLLM",
        "run_local_worker",
        "yaml",
        "pathlib",
        "json",
        "builtins",
        "open",
        "Path",
        "load",
        "import_module",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert {"open", "Path", "json.load", "import_module"}.isdisjoint(calls)


def test_agent_package_does_not_reexport_source_extractor():
    assert "local_worker_acceptance_criteria_sources" not in agent_package.__all__
    assert "extract_acceptance_criteria_sources" not in agent_package.__all__
    assert "local_worker_acceptance_criteria_sources" not in agent_package._EXPORT_MODULES
    assert "extract_acceptance_criteria_sources" not in agent_package._EXPORT_MODULES


def test_probe_scripts_do_not_import_acceptance_criteria_sources():
    root = Path(__file__).resolve().parents[2]
    for relative in ("scripts/lm5r_two_pass_publication_probe.py",):
        source = (root / relative).read_text(encoding="utf-8")
        assert "local_worker_acceptance_criteria_sources" not in source
        imports = _import_names(source)
        assert not any(
            "local_worker_acceptance_criteria_sources" in imported
            for imported in imports
        )


def test_lm5k_probe_is_the_only_probe_script_joining_acceptance_sources():
    root = Path(__file__).resolve().parents[2]
    lm5k_source = (root / "scripts" / "lm5k_worker_probe.py").read_text(
        encoding="utf-8"
    )
    lm5r_source = (
        root / "scripts" / "lm5r_two_pass_publication_probe.py"
    ).read_text(encoding="utf-8")

    assert "local_worker_acceptance_criteria import" in lm5k_source
    assert "local_worker_acceptance_criteria_sources import" in lm5k_source
    assert "local_worker_acceptance_criteria_sources" not in lm5r_source
    assert "local_worker_acceptance_criteria import" not in lm5r_source


def test_extracts_lm5u_fixture_sources():
    assert _extract_from_fixture() == _expected_sources()


def test_assemble_extracted_sources_matches_lm5w_expected_packet_fingerprint():
    extracted_packet = assemble_acceptance_criteria_packet(_extract_from_fixture())
    expected_packet = assemble_acceptance_criteria_packet(_expected_sources())

    assert extracted_packet["fingerprint"] == expected_packet["fingerprint"]
    assert extracted_packet == expected_packet


def test_extracted_sources_match_lm5u_legacy_acceptance_criteria_projection():
    fixture = _fixture_objects()
    lm5u_packet = _jsonable(
        fixture["probe"]._acceptance_criteria_evidence_packet(
            fixture["graph"]
        ).content
    )
    extracted_packet = assemble_acceptance_criteria_packet(
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )
    )

    assert _legacy_projection(extracted_packet) == (
        lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
    )


def _replace_contract_initial_params(workflow_contract, initial_params):
    from dataclasses import replace

    return replace(workflow_contract, initial_params=tuple(initial_params))


def _replace_contract_rules(workflow_contract, rules):
    from dataclasses import replace

    return replace(workflow_contract, rules=tuple(rules))


def _replace_graph_create_receipt(graph, receipt):
    graph_copy = copy.deepcopy(graph)
    graph_copy.nodes["create_script"].evidence.receipt = receipt
    return graph_copy


def test_missing_create_initial_params_fails_with_pin_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_initial_params(fixture["workflow_contract"], ())

    with pytest.raises(ValueError, match="create_script.initial_execution_params.pins_out"):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_missing_verify_repair_rule_fails_with_verifier_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_rules(
        fixture["workflow_contract"],
        [
            rule
            for rule in fixture["workflow_contract"].rules
            if rule.node_id != "verify_repair"
        ],
    )

    with pytest.raises(
        ValueError,
        match="workflow_contract.rules.verify_repair.expected_outcome",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_target_errors_wrong_shape_fails_with_diagnostic_source_path():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = "not-a-list"
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    with pytest.raises(
        ValueError,
        match="create_script.receipt.script_receipt.repair_anchor.target_errors",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=graph,
            convention_packets=fixture["convention_packets"],
        )


def test_missing_script_body_gotcha_fails_with_packet_id():
    fixture = _fixture_objects()

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(),
        )


def test_duplicate_script_body_gotcha_candidates_fail():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(packet, packet),
        )


def test_malformed_convention_packet_fails_with_packet_id():
    fixture = _fixture_objects()

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(object(),),
        )


def test_script_body_gotcha_wrong_kind_fails_after_id_selection():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]
    wrong_kind = type(packet)(
        packet_id=packet.packet_id,
        kind="evidence",
        title=packet.title,
        content=packet.content,
    )

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(wrong_kind,),
        )


def test_script_body_gotcha_wrong_title_fails_after_id_selection():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]
    wrong_title = type(packet)(
        packet_id=packet.packet_id,
        kind=packet.kind,
        title="Different gotcha",
        content=packet.content,
    )

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(wrong_title,),
        )


def test_extracted_values_are_copied_from_contract_and_receipt():
    fixture = _fixture_objects()
    sources = extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
    )

    contract_pins_out = fixture["workflow_contract"].initial_params[
        0
    ].execution_params["pins_out"]
    receipt_target_errors = fixture["graph"].nodes[
        "create_script"
    ].evidence.receipt["repair_anchor"]["target_errors"]

    contract_pins_out.append("B:int")
    receipt_target_errors.append("CS9999: extra")
    sources.pin_contract.value["pins_out"].append("C:string")
    sources.receipt_diagnostic.value.append("CS8888: source mutation")

    assert sources.pin_contract.value["pins_out"] == ["A:double", "C:string"]
    assert sources.receipt_diagnostic.value == [
        TARGET_DIAGNOSTIC,
        "CS8888: source mutation",
    ]
    assert fixture["workflow_contract"].initial_params[0].execution_params[
        "pins_out"
    ] == ["A:double", "B:int"]
    assert fixture["graph"].nodes["create_script"].evidence.receipt[
        "repair_anchor"
    ]["target_errors"] == [TARGET_DIAGNOSTIC, "CS9999: extra"]


def test_wrong_diagnostic_shape_extracts_but_assembler_rejects_semantics():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = ["CS0000: Different diagnostic"]
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    sources = extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=graph,
        convention_packets=fixture["convention_packets"],
    )

    assert sources.receipt_diagnostic.value == ["CS0000: Different diagnostic"]
    with pytest.raises(ValueError, match="DefinitelyMissingSymbol"):
        assemble_acceptance_criteria_packet(sources)
