from __future__ import annotations

import copy
from pathlib import Path

import pytest

from rook.gh_csharp_preflight import (
    is_recognized_csharp_full_source,
    preflight_csharp_script,
    validate_rhinocode_csharp_full_source,
)


_FIXTURE_DIR = Path(__file__).with_name("fixtures")


def _pin(name: str, *, access: str = "item", type_name: str = "System.Object"):
    return {"name": name, "type": type_name, "access": access}


def _contract_result(code, pins_in=None, pins_out=None):
    return validate_rhinocode_csharp_full_source(
        code=code,
        pins_in=[] if pins_in is None else pins_in,
        pins_out=[] if pins_out is None else pins_out,
    )


def _result(code, pins_in=None, pins_out=None, mode="auto"):
    return preflight_csharp_script(
        code=code,
        pins_in=[] if pins_in is None else pins_in,
        pins_out=[] if pins_out is None else pins_out,
        mode=mode,
    )


def test_valid_body_style_code_with_valid_pins_passes():
    result = _result(
        "A = Convert.ToDouble(R);",
        pins_in=[{"name": "R", "type": "double"}],
        pins_out=[{"name": "A", "type": "double"}],
        mode="body",
    )

    assert result.ok is True
    assert result.message is None
    assert result.code is None


def test_valid_recognized_full_source_passes():
    code = (
        "using System;\n"
        "public class Script_Instance : GH_ScriptInstance {\n"
        "  private void RunScript(object R, ref object A) { A = R; }\n"
        "}\n"
    )

    result = _result(
        code,
        pins_in=[{"name": "R"}],
        pins_out=[{"name": "A"}],
        mode="full_source",
    )

    assert is_recognized_csharp_full_source(code) is True
    assert result.ok is True


@pytest.mark.parametrize("code", [None, 123, ["A = R;"]])
def test_non_string_code_fails(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "invalid_code"
    assert "code must be a non-empty string" in result.message


def test_empty_code_fails():
    result = _result("   \n\t", pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "invalid_code"
    assert "code must be a non-empty string" in result.message


@pytest.mark.parametrize("name", ["1A", "bad-name", "with space", "A.B"])
def test_invalid_pin_identifier_fails(name):
    result = _result("A = 1;", pins_out=[{"name": name}])

    assert result.ok is False
    assert result.code == "invalid_pin_name"
    assert name in result.message


@pytest.mark.parametrize("name", ["class", "namespace", "object", "ref"])
def test_reserved_keyword_pin_name_fails(name):
    result = _result("A = 1;", pins_out=[{"name": name}])

    assert result.ok is False
    assert result.code == "reserved_pin_name"
    assert name in result.message


def test_duplicate_pin_name_fails_case_sensitive_only():
    duplicate = _result(
        "A = R;",
        pins_in=[{"name": "A"}],
        pins_out=[{"name": "A"}],
    )
    distinct_by_case = _result(
        "a = A;",
        pins_in=[{"name": "A"}],
        pins_out=[{"name": "a"}],
    )

    assert duplicate.ok is False
    assert duplicate.code == "duplicate_pin_name"
    assert distinct_by_case.ok is True


@pytest.mark.parametrize(
    "code",
    [
        "public class MyComponent : GH_Component { }",
        "public class MyComponent:GH_Component { }",
        "public class MyComponent : Grasshopper.Kernel.GH_Component { }",
        "protected override void SolveInstance(IGH_DataAccess DA) { }",
        "protected override void RegisterInputParams(GH_InputParamManager pManager) { }",
        "protected override void RegisterOutputParams(GH_OutputParamManager pManager) { }",
    ],
)
def test_grasshopper_plugin_component_patterns_fail(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "wrong_component_category"
    assert "RhinoCode C# Script" in result.message


def test_plugin_component_pattern_fails_even_with_runscript_token():
    code = (
        "public class MyComponent : GH_Component {\n"
        "  private void RunScript(object R, ref object A) { A = R; }\n"
        "}\n"
    )

    result = _result(code, pins_in=[{"name": "R"}], pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "wrong_component_category"


def test_unrecognized_class_declaration_fails_in_body_mode():
    result = _result("public class Helper { }", pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "body_contains_class"
    assert "full source" in result.message


@pytest.mark.parametrize(
    "code",
    [
        "using Rhino.Geometry;\nA = new Point3d();",
        "using static System.Math;\nA = PI;",
        "using RG = Rhino.Geometry;\nA = new RG.Point3d();",
    ],
)
def test_top_level_using_fails_in_body_mode(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is False
    assert result.code == "body_contains_using"
    assert "body-style" in result.message


@pytest.mark.parametrize(
    "code",
    [
        "using (var stream = new System.IO.MemoryStream()) { A = stream.Length; }",
        "using var stream = new System.IO.MemoryStream();\nA = stream.Length;",
    ],
)
def test_using_statements_are_allowed_in_body_mode(code):
    result = _result(code, pins_out=[{"name": "A"}])

    assert result.ok is True


def test_top_level_using_allowed_in_recognized_full_source_mode():
    code = (
        "using Rhino.Geometry;\n"
        "public class Script_Instance : GH_ScriptInstance {\n"
        "  private void RunScript(ref object A) { A = Point3d.Origin; }\n"
        "}\n"
    )

    result = _result(code, pins_out=[{"name": "A"}], mode="auto")

    assert result.ok is True


def test_missing_output_assignment_is_not_a_hard_reject():
    result = _result(
        "var value = 1;",
        pins_out=[{"name": "A"}],
        mode="body",
    )

    assert result.ok is True


def test_helper_does_not_mutate_pin_inputs():
    pins_in = [{"name": "R", "type": "double"}]
    pins_out = [{"name": "A", "type": "double"}]
    before_in = copy.deepcopy(pins_in)
    before_out = copy.deepcopy(pins_out)

    result = _result("A = R;", pins_in=pins_in, pins_out=pins_out)

    assert result.ok is True
    assert pins_in == before_in
    assert pins_out == before_out


def test_exact_contract_accepts_generic_rhinocode_source():
    result = _contract_result(
        "public class Script_Instance : GH_ScriptInstance {\n"
        "  private void RunScript(object Input, ref object Result) { Result = Input; }\n"
        "}\n",
        pins_in=[_pin("Input")],
        pins_out=[_pin("Result", access="list")],
    )

    assert result.ok is True
    assert result.error_codes == ()


def test_exact_contract_rejects_preserved_first_candidate_for_both_defects():
    source = (_FIXTURE_DIR / "lm9b_c_first_candidate.cs").read_text(encoding="utf-8")

    result = _contract_result(source, pins_out=[_pin("Boxes", access="list")])

    assert result.ok is False
    assert result.error_codes == (
        "missing_gh_script_instance_base",
        "runscript_signature_mismatch",
    )


@pytest.mark.parametrize("visibility", ["public", "protected", "internal"])
def test_exact_contract_rejects_nonprivate_runscript(visibility):
    source = (
        "public class Script_Instance : GH_ScriptInstance { "
        f"{visibility} void RunScript(ref object A) {{ }} }}"
    )

    result = _contract_result(source, pins_out=[_pin("A")])

    assert "runscript_signature_mismatch" in result.error_codes


@pytest.mark.parametrize(
    "parameters,pins_in,pins_out",
    [
        ("ref object A", [_pin("R")], [_pin("A")]),
        ("object R, object X, ref object A", [_pin("R")], [_pin("A")]),
        ("ref object A, object R", [_pin("R")], [_pin("A")]),
        ("object Radius, ref object A", [_pin("R")], [_pin("A")]),
        ("object R, ref object Result", [_pin("R")], [_pin("A")]),
        ("object R, out object A", [_pin("R")], [_pin("A")]),
    ],
)
def test_exact_contract_binds_parameter_count_order_name_and_modifier(
    parameters, pins_in, pins_out
):
    source = (
        "public class Script_Instance : GH_ScriptInstance { "
        f"private void RunScript({parameters}) {{ }} }}"
    )

    result = _contract_result(source, pins_in=pins_in, pins_out=pins_out)

    assert result.error_codes == ("runscript_signature_mismatch",)


def test_exact_contract_requires_gh_script_instance_inheritance():
    result = _contract_result(
        "public class Script_Instance { private void RunScript(ref object A) { } }",
        pins_out=[_pin("A")],
    )

    assert result.error_codes == ("missing_gh_script_instance_base",)


def test_exact_contract_rejects_gh_component_subclass():
    result = _contract_result(
        "public class Script_Instance : GH_Component { "
        "private void RunScript(ref object A) { } }",
        pins_out=[_pin("A")],
    )

    assert result.error_codes == (
        "gh_component_subclass_forbidden",
        "missing_gh_script_instance_base",
    )


def test_exact_contract_rejects_duplicate_runscript_methods():
    result = _contract_result(
        "public class Script_Instance : GH_ScriptInstance { "
        "private void RunScript(ref object A) { } "
        "private void RunScript(ref object A, ref object B) { } }",
        pins_out=[_pin("A")],
    )

    assert result.error_codes == ("runscript_method_count_mismatch",)


@pytest.mark.parametrize(
    "pin",
    [
        {"name": "A", "type": "System.Object"},
        {"name": "A", "access": "item"},
        {"name": "A", "type": "System.Object", "access": "invalid"},
    ],
)
def test_exact_contract_requires_complete_pin_declarations(pin):
    result = _contract_result(
        "public class Script_Instance : GH_ScriptInstance { "
        "private void RunScript(ref object A) { } }",
        pins_out=[pin],
    )

    assert result.error_codes == ("invalid_pin_declaration",)
