"""Behavioural tests for the Python wrapper behind POST /bim/run-transaction.

The wrapper lives in src/RookBim (the only place allowed to name Revit
namespaces) and is embedded in RookBim.dll. RevitPythonScriptRunner runs it in
Rhino's Python 3 engine by calling the engine directly, with one input:
``__rook__``, a RevitScriptChannel created by the host. The host decides commit
or rollback from two things together: its own engine call returned without
raising, and the wrapper called ``__rook__.Complete``.

These tests run the real wrapper text with a Python stand-in for that channel
and check both signals: what the wrapper told the channel, and whether running
it raised (which is what the host's engine call would see).
"""

from __future__ import annotations

import re
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
CHANNEL_SOURCE = WRAPPER_PATH.parents[1] / "RevitScriptChannel.cs"


class FakeChannel:
    """Mirrors the members of RookBim.Revit.RevitScriptChannel the wrapper uses."""

    STREAM_LIMIT = 20000

    def __init__(self, code, document):
        self.Code = code
        self.Document = document
        self.UIDocument = types.SimpleNamespace(Document=document)
        self.Application = types.SimpleNamespace(VersionNumber="2024")
        self.UIApplication = types.SimpleNamespace(Application=self.Application)
        self.BindRevitNamespaces = True
        self.MaxResultLength = 50000
        self.MaxResultDepth = 32
        self.MaxTracebackLength = 20000
        self.MaxErrorLength = 2000
        self.Stage = "none"
        self.Completed = False
        self.ScriptError = None
        self.ScriptTraceback = None
        self.ResultJson = None
        self.ResultOmittedReason = None
        self.Output = ""
        self.OutputTruncated = False
        self.Stderr = ""
        self.StderrTruncated = False
        self.write_calls = 0

    def SetStage(self, stage):
        self.Stage = stage

    def WriteOutput(self, text):
        self.write_calls += 1
        room = self.STREAM_LIMIT - len(self.Output)
        if len(text) > room:
            self.OutputTruncated = True
        self.Output += text[: max(room, 0)]

    def WriteError(self, text):
        room = self.STREAM_LIMIT - len(self.Stderr)
        if len(text) > room:
            self.StderrTruncated = True
        self.Stderr += text[: max(room, 0)]

    def Complete(self, result_json, result_omitted_reason):
        self.ResultJson = result_json
        self.ResultOmittedReason = result_omitted_reason
        self.Completed = True

    def Fail(self, error, traceback_text):
        self.ScriptError = error
        self.ScriptTraceback = traceback_text
        self.Completed = False


class _FakeDocument:
    Title = "Tower.rvt"

    def __init__(self):
        self.renamed = []


@pytest.fixture
def revit(monkeypatch):
    """Stub the Revit namespaces the wrapper imports inside the Revit process."""
    autodesk = types.ModuleType("Autodesk")
    autodesk_revit = types.ModuleType("Autodesk.Revit")
    db = types.ModuleType("Autodesk.Revit.DB")
    db.ElementId = lambda value: ("ElementId", value)
    ui = types.ModuleType("Autodesk.Revit.UI")
    autodesk.Revit = autodesk_revit
    autodesk_revit.DB = db
    autodesk_revit.UI = ui
    for name, module in {
        "Autodesk": autodesk,
        "Autodesk.Revit": autodesk_revit,
        "Autodesk.Revit.DB": db,
        "Autodesk.Revit.UI": ui,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return types.SimpleNamespace(document=_FakeDocument(), db=db, ui=ui)


def _run(revit, code, configure=None):
    """Runs the wrapper as the host does. Returns (channel, host_error):
    host_error is None when running the wrapper returned normally."""
    channel = FakeChannel(code, revit.document)
    if configure is not None:
        configure(channel)
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    host_error = None
    try:
        exec(compile(wrapper, str(WRAPPER_PATH), "exec"), {"__name__": "__main__", "__rook__": channel})
    except BaseException as error:  # the engine call sees SystemExit too
        host_error = error
    return channel, host_error


def test_wrapper_file_is_where_the_csproj_embeds_it_from():
    assert WRAPPER_PATH.is_file()


def test_fake_channel_has_every_member_the_real_channel_exposes_to_the_wrapper():
    source = CHANNEL_SOURCE.read_text(encoding="utf-8")
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    used = set(re.findall(r"__rook__\.([A-Za-z_]\w*)", wrapper))
    assert used, "the wrapper must talk to the channel"
    for name in used:
        assert hasattr(FakeChannel("", None), name), name
        assert re.search(
            r"public [\w?<>\[\]]+ " + re.escape(name) + r"\b", source
        ), f"RevitScriptChannel has no public member {name}"


def test_successful_script_reports_completion_output_and_result(revit):
    channel, host_error = _run(
        revit,
        "print('renaming', doc.Title)\n"
        "doc.renamed.append('Level 02')\n"
        "result = {'renamed': 311, 'names': ['Level 02']}\n",
    )

    assert host_error is None
    assert channel.Completed is True
    assert channel.Stage == "done"
    assert channel.Output == "renaming Tower.rvt\n"
    assert channel.ScriptError is None
    assert channel.ResultJson == '{"renamed": 311, "names": ["Level 02"]}'
    assert channel.ResultOmittedReason is None
    assert revit.document.renamed == ["Level 02"]


def test_script_sees_the_documented_bound_names(revit):
    channel, host_error = _run(
        revit,
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

    assert host_error is None
    assert channel.ResultJson == (
        '{"doc": "Tower.rvt", "uidoc_doc_is_doc": true, "app": "2024", "uiapp_app_is_app": true, '
        '"db": "Autodesk.Revit.DB", "ui": "Autodesk.Revit.UI", "name": "__main__"}'
    )


def test_script_without_result_completes_with_no_result(revit):
    channel, host_error = _run(revit, "x = 1 + 1\n")

    assert host_error is None
    assert channel.Completed is True
    assert channel.ResultJson is None
    assert channel.ResultOmittedReason is None


def test_exception_is_reported_to_the_channel_and_raised_to_the_host(revit):
    channel, host_error = _run(
        revit,
        "print('before the error')\n"
        "doc.renamed.append('half done')\n"
        "def inner():\n"
        "    raise ValueError('wall type not found')\n"
        "inner()\n",
    )

    # Both signals say failure: the host's call raised, and the wrapper said so.
    assert isinstance(host_error, ValueError)
    assert channel.Completed is False
    assert channel.Stage == "run"
    assert channel.ScriptError == "ValueError: wall type not found"
    assert channel.ScriptTraceback.rstrip().endswith("ValueError: wall type not found")
    # The traceback shows the caller's own line, not just a line number.
    assert "raise ValueError('wall type not found')" in channel.ScriptTraceback
    assert 'File "<rookbim_run_transaction>", line 4, in inner' in channel.ScriptTraceback
    assert channel.Output == "before the error\n"


def test_syntax_error_fails_at_compile_before_any_line_runs(revit):
    channel, host_error = _run(revit, "doc.renamed.append('ran')\ndef broken(:\n    pass\n")

    assert isinstance(host_error, SyntaxError)
    assert channel.Completed is False
    assert channel.Stage == "compile"
    assert channel.ScriptError.startswith("SyntaxError")
    assert revit.document.renamed == []


def test_sys_exit_is_a_failure_on_both_signals(revit):
    channel, host_error = _run(revit, "import sys\nsys.exit(0)\n")

    assert isinstance(host_error, SystemExit)
    assert channel.Completed is False
    assert channel.ScriptError.startswith("SystemExit")


def test_stderr_is_forwarded_separately(revit):
    channel, host_error = _run(revit, "import sys\nprint('to stderr', file=sys.stderr)\nprint('to stdout')\n")

    assert host_error is None
    assert channel.Output == "to stdout\n"
    assert channel.Stderr == "to stderr\n"


def test_output_is_forwarded_as_it_is_written_not_buffered_in_python(revit):
    channel, host_error = _run(revit, "for _ in range(50):\n    print('x' * 999)\n")

    assert host_error is None
    assert len(channel.Output) == FakeChannel.STREAM_LIMIT
    assert channel.OutputTruncated is True
    # print() writes the text and the newline separately: 100 forwards, each
    # handed to the host at once; empty writes are not forwarded at all.
    assert channel.write_calls == 100


def test_empty_writes_are_not_forwarded(revit):
    channel, host_error = _run(revit, "import sys\nfor _ in range(1000):\n    sys.stdout.write('')\n")

    assert host_error is None
    assert channel.write_calls == 0


@pytest.mark.parametrize(
    "code,reason",
    [
        ("result = {'id': 311, 'element': object()}\n", "result contains a object, which is not a plain JSON value"),
        ("result = {1: 'first', '1': 'second'}\n", "result has a dict key of type int; use string keys"),
        ("result = float('nan')\n", "result contains NaN or infinity"),
        ("r = []\nfor _ in range(80):\n    r = [r]\nresult = r\n", "result is nested more than 32 levels deep"),
        ("result = 'r' * 60000\n", "result is larger than 50000 characters"),
        ("result = ['ab'] * 20000\n", "result is larger than 50000 characters"),
    ],
)
def test_unreturnable_result_is_omitted_with_the_reason_and_the_script_still_succeeds(revit, code, reason):
    channel, host_error = _run(revit, "doc.renamed.append('done')\n" + code)

    # The edit stands; only the return value is left out, and it is never
    # replaced by something the caller could mistake for it.
    assert host_error is None
    assert channel.Completed is True
    assert channel.Stage == "done"
    assert channel.ResultJson is None
    assert reason in channel.ResultOmittedReason
    assert "The script's changes are not affected." in channel.ResultOmittedReason
    assert revit.document.renamed == ["done"]


def test_oversized_result_is_refused_before_it_is_encoded(revit, monkeypatch):
    import json

    encoded = []
    real_dumps = json.dumps
    monkeypatch.setattr(json, "dumps", lambda *a, **k: encoded.append(1) or real_dumps(*a, **k))

    channel, host_error = _run(revit, "result = ['ab'] * 200000\n")

    assert host_error is None
    assert channel.ResultJson is None
    assert encoded == [], "the size check must come before json.dumps"


def test_long_traceback_keeps_its_end_where_the_error_is(revit):
    channel, host_error = _run(
        revit,
        "def deep(n):\n"
        "    if n == 0:\n"
        "        raise RuntimeError('bottom of the stack')\n"
        "    deep(n - 1)\n"
        "deep(400)\n",
    )

    assert isinstance(host_error, RuntimeError)
    assert len(channel.ScriptTraceback) <= 20000
    assert channel.ScriptTraceback.rstrip().endswith("RuntimeError: bottom of the stack")
    # Only the innermost frames are formatted at all.
    assert channel.ScriptTraceback.count("deep(n - 1)") <= 30


def test_missing_revit_namespaces_fail_at_bind_without_running_the_script(revit, monkeypatch):
    # None in sys.modules makes the import raise ImportError.
    monkeypatch.setitem(sys.modules, "Autodesk.Revit.DB", None)

    channel, host_error = _run(revit, "doc.renamed.append('ran')\n")

    assert isinstance(host_error, ImportError)
    assert channel.Completed is False
    assert channel.Stage == "bind"
    assert revit.document.renamed == []


def test_wrapper_does_not_need_revit_namespaces_when_the_host_says_so(revit, monkeypatch):
    monkeypatch.setitem(sys.modules, "Autodesk.Revit.DB", None)

    channel, host_error = _run(
        revit,
        "result = 'DB' in dir()\n",
        configure=lambda c: setattr(c, "BindRevitNamespaces", False),
    )

    assert host_error is None
    assert channel.ResultJson == "false"


def test_wrapper_leaves_no_script_source_behind_in_linecache(revit):
    import linecache

    _run(revit, "x = 1\n")
    _run(revit, "raise ValueError('x')\n")

    assert "<rookbim_run_transaction>" not in linecache.cache
