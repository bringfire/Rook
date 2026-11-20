"""Behavioural tests for the Python wrapper behind POST /bim/run-transaction.

The wrapper body lives in src/RookBim (it is the only place allowed to name
Revit assemblies) and is embedded in RookBim.dll. RevitTransactionService
prepends a three-line header and runs it inside Revit with a transaction
already open. Its payload is the only thing the C# side reads to decide commit
or rollback, so these tests run the real wrapper text against stub Revit
modules and check that payload.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

WRAPPER_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "RookBim"
    / "Revit"
    / "Scripts"
    / "run_transaction_wrapper.py"
)


def _escape_python_string(value: str) -> str:
    # Mirrors RevitTransactionService.EscapePythonString.
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _build_wrapper(code_path: Path, result_path: Path) -> str:
    # Mirrors RevitTransactionService.BuildWrapper.
    return (
        "#! python 3\n"
        "ROOK_CODE_PATH = '" + _escape_python_string(str(code_path)) + "'\n"
        "ROOK_RESULT_PATH = '" + _escape_python_string(str(result_path)) + "'\n"
        + WRAPPER_PATH.read_text(encoding="utf-8")
    )


class _FakeDocument:
    Title = "Tower.rvt"

    def __init__(self):
        self.renamed = []


@pytest.fixture
def revit(monkeypatch):
    """Stub the modules the wrapper imports inside the Revit process."""
    document = _FakeDocument()
    application = types.SimpleNamespace(VersionNumber="2024")
    ui_application = types.SimpleNamespace(Application=application)
    ui_document = types.SimpleNamespace(Document=document)

    added_references = []
    clr = types.ModuleType("clr")
    clr.AddReference = added_references.append

    autodesk = types.ModuleType("Autodesk")
    autodesk_revit = types.ModuleType("Autodesk.Revit")
    db = types.ModuleType("Autodesk.Revit.DB")
    db.ElementId = lambda value: ("ElementId", value)
    ui = types.ModuleType("Autodesk.Revit.UI")
    autodesk.Revit = autodesk_revit
    autodesk_revit.DB = db
    autodesk_revit.UI = ui

    rhino_inside = types.ModuleType("RhinoInside")
    rhino_inside_revit = types.ModuleType("RhinoInside.Revit")
    rhino_inside_revit.Revit = types.SimpleNamespace(
        ActiveUIApplication=ui_application,
        ActiveUIDocument=ui_document,
        ActiveDBDocument=document,
    )
    rhino_inside.Revit = rhino_inside_revit

    for name, module in {
        "clr": clr,
        "Autodesk": autodesk,
        "Autodesk.Revit": autodesk_revit,
        "Autodesk.Revit.DB": db,
        "Autodesk.Revit.UI": ui,
        "RhinoInside": rhino_inside,
        "RhinoInside.Revit": rhino_inside_revit,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    return types.SimpleNamespace(
        document=document,
        application=application,
        ui_application=ui_application,
        ui_document=ui_document,
        db=db,
        ui=ui,
        added_references=added_references,
    )


def _run(tmp_path: Path, code: str) -> dict:
    code_path = tmp_path / "bimtx_1_1_code.py"
    result_path = tmp_path / "bimtx_1_1_result.json"
    code_path.write_text(code, encoding="utf-8")
    wrapper = _build_wrapper(code_path, result_path)

    # RunPythonScript executes the file as a top-level script.
    exec(compile(wrapper, str(tmp_path / "bimtx_1_1_wrapper.py"), "exec"), {"__name__": "__main__"})

    assert result_path.exists(), "the wrapper must always write a payload"
    return json.loads(result_path.read_text(encoding="utf-8"))


def test_wrapper_file_is_where_the_csproj_embeds_it_from():
    assert WRAPPER_PATH.is_file()


def test_successful_script_reports_output_and_result(tmp_path, revit):
    payload = _run(
        tmp_path,
        "print('renaming', doc.Title)\n"
        "doc.renamed.append('Level 02')\n"
        "result = {'renamed': 311, 'names': ['Level 02']}\n",
    )

    assert payload["success"] is True
    assert payload["stage"] == "done"
    assert payload["output"] == "renaming Tower.rvt\n"
    assert payload["error"] == ""
    assert payload["traceback"] == ""
    assert payload["result"] == {"renamed": 311, "names": ["Level 02"]}
    assert payload["resultOmittedReason"] is None
    assert revit.document.renamed == ["Level 02"]


def test_script_sees_the_documented_bound_names(tmp_path, revit):
    payload = _run(
        tmp_path,
        "result = {\n"
        "    'doc': doc.Title,\n"
        "    'uidoc_doc_is_doc': uidoc.Document is doc,\n"
        "    'app': app.VersionNumber,\n"
        "    'uiapp_app_is_app': uiapp.Application is app,\n"
        "    'db': DB.__name__,\n"
        "    'ui': UI.__name__,\n"
        "    'name': __name__,\n"
        "}\n",
    )

    assert payload["success"] is True
    assert payload["result"] == {
        "doc": "Tower.rvt",
        "uidoc_doc_is_doc": True,
        "app": "2024",
        "uiapp_app_is_app": True,
        "db": "Autodesk.Revit.DB",
        "ui": "Autodesk.Revit.UI",
        "name": "__main__",
    }
    assert revit.added_references == ["RevitAPI", "RevitAPIUI", "RhinoInside.Revit"]


def test_script_without_result_returns_null_result(tmp_path, revit):
    payload = _run(tmp_path, "x = 1 + 1\n")

    assert payload["success"] is True
    assert payload["result"] is None
    assert payload["resultOmittedReason"] is None


def test_exception_reports_failure_with_traceback_and_partial_output(tmp_path, revit):
    payload = _run(
        tmp_path,
        "print('before the error')\n"
        "doc.renamed.append('half done')\n"
        "raise ValueError('wall type not found')\n",
    )

    assert payload["success"] is False
    assert payload["stage"] == "run"
    assert payload["error"] == "ValueError: wall type not found"
    assert "ValueError: wall type not found" in payload["traceback"]
    assert "line 3" in payload["traceback"]
    assert payload["output"] == "before the error\n"
    assert payload["result"] is None


def test_syntax_error_fails_at_compile_before_any_line_runs(tmp_path, revit):
    payload = _run(tmp_path, "doc.renamed.append('ran')\ndef broken(:\n    pass\n")

    assert payload["success"] is False
    assert payload["stage"] == "compile"
    assert payload["error"].startswith("SyntaxError")
    assert revit.document.renamed == []


def test_sys_exit_is_a_failure_so_the_transaction_rolls_back(tmp_path, revit):
    payload = _run(tmp_path, "import sys\nsys.exit(0)\n")

    assert payload["success"] is False
    assert payload["stage"] == "run"
    assert payload["error"].startswith("SystemExit")


def test_stderr_is_captured_separately(tmp_path, revit):
    payload = _run(tmp_path, "import sys\nprint('to stderr', file=sys.stderr)\nprint('to stdout')\n")

    assert payload["success"] is True
    assert payload["output"] == "to stdout\n"
    assert payload["stderr"] == "to stderr\n"


def test_non_json_values_fall_back_to_their_string_form(tmp_path, revit):
    payload = _run(tmp_path, "result = {'id': DB.ElementId(311), 'doc': object}\n")

    assert payload["success"] is True
    assert payload["result"] == {"id": ["ElementId", 311], "doc": "<class 'object'>"}


def test_unreturnable_result_is_omitted_with_a_reason_but_does_not_fail_the_script(tmp_path, revit):
    payload = _run(tmp_path, "doc.renamed.append('done')\nresult = float('nan')\n")

    # The model change is valid; only the return value could not be sent.
    assert payload["success"] is True
    assert payload["result"] is None
    assert "result could not be converted to JSON" in payload["resultOmittedReason"]
    assert revit.document.renamed == ["done"]


def test_missing_revit_modules_fail_at_bind_without_running_the_script(tmp_path, revit, monkeypatch):
    # None in sys.modules makes the import raise ImportError.
    monkeypatch.setitem(sys.modules, "RhinoInside.Revit", None)

    payload = _run(tmp_path, "doc.renamed.append('ran')\n")

    assert payload["success"] is False
    assert payload["stage"] == "bind"
    assert "RhinoInside" in payload["error"]
    assert revit.document.renamed == []


def test_add_reference_failure_alone_does_not_stop_a_script_whose_imports_work(tmp_path, revit, monkeypatch):
    def refuse(_name):
        raise FileNotFoundError("assembly already loaded from another path")

    monkeypatch.setattr(sys.modules["clr"], "AddReference", refuse)

    payload = _run(tmp_path, "result = doc.Title\n")

    assert payload["success"] is True
    assert payload["result"] == "Tower.rvt"


def test_paths_with_quotes_and_backslashes_survive_the_generated_header(tmp_path, revit):
    folder = tmp_path / "it's a temp"
    folder.mkdir()

    payload = _run(folder, "result = __file__\n")

    assert payload["success"] is True
    assert payload["result"] == str(folder / "bimtx_1_1_code.py")
