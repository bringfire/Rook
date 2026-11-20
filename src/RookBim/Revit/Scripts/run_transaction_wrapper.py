# RookBIM run-transaction wrapper (body).
#
# RevitTransactionService prepends a generated header to this file:
#     #! python 3
#     ROOK_CODE_PATH = '<file holding the caller's script>'
#     ROOK_RESULT_PATH = '<file this wrapper writes its JSON payload to>'
# and runs the result with Rhino's RunPythonScript while a Revit transaction is
# already open on the active document. This wrapper never starts, commits or
# rolls back a transaction: it runs the caller's script, captures what it
# printed, and reports success or the exception. The C# side decides commit or
# rollback from that payload alone.
#
# Names bound for the caller's script:
#     doc    Autodesk.Revit.DB.Document         the active document
#     uidoc  Autodesk.Revit.UI.UIDocument
#     uiapp  Autodesk.Revit.UI.UIApplication
#     app    Autodesk.Revit.ApplicationServices.Application
#     DB     the Autodesk.Revit.DB namespace
#     UI     the Autodesk.Revit.UI namespace
#     result None; assign a JSON-serializable value to return it to the caller
import io
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout

_rook_payload = {
    "success": False,
    "stage": "bind",
    "output": "",
    "stderr": "",
    "error": "",
    "traceback": "",
    "result": None,
    "resultOmittedReason": None,
}
_rook_stdout = io.StringIO()
_rook_stderr = io.StringIO()

try:
    import clr

    # The assemblies are already loaded in the Revit process; AddReference is
    # best effort and an import failure below reports the real problem.
    for _rook_assembly in ("RevitAPI", "RevitAPIUI", "RhinoInside.Revit"):
        try:
            clr.AddReference(_rook_assembly)
        except Exception:
            pass

    import Autodesk.Revit.DB as _rook_db
    import Autodesk.Revit.UI as _rook_ui
    from RhinoInside.Revit import Revit as _rook_revit

    _rook_uiapp = _rook_revit.ActiveUIApplication
    _rook_globals = {
        "__name__": "__main__",
        "__file__": ROOK_CODE_PATH,
        "DB": _rook_db,
        "UI": _rook_ui,
        "uiapp": _rook_uiapp,
        "app": _rook_uiapp.Application,
        "uidoc": _rook_revit.ActiveUIDocument,
        "doc": _rook_revit.ActiveDBDocument,
        "result": None,
    }

    _rook_payload["stage"] = "read"
    with open(ROOK_CODE_PATH, "r", encoding="utf-8") as _rook_code_file:
        _rook_code = _rook_code_file.read()

    _rook_payload["stage"] = "compile"
    _rook_compiled = compile(_rook_code, ROOK_CODE_PATH, "exec")

    _rook_payload["stage"] = "run"
    with redirect_stdout(_rook_stdout), redirect_stderr(_rook_stderr):
        exec(_rook_compiled, _rook_globals, _rook_globals)

    _rook_payload["stage"] = "result"
    _rook_value = _rook_globals.get("result")
    if _rook_value is not None:
        try:
            # Round-trip so the payload only ever holds plain JSON (no NaN,
            # no .NET objects); values json cannot encode fall back to str().
            _rook_payload["result"] = json.loads(
                json.dumps(_rook_value, default=str, allow_nan=False)
            )
        except Exception as _rook_result_err:
            # A result that cannot be returned must not undo a script that
            # ran correctly; say why it is missing instead.
            _rook_payload["resultOmittedReason"] = (
                "result could not be converted to JSON ("
                + type(_rook_result_err).__name__
                + ": "
                + str(_rook_result_err)
                + "). Assign plain numbers, strings, lists and dicts."
            )

    _rook_payload["success"] = True
    _rook_payload["stage"] = "done"
except BaseException as _rook_err:
    _rook_payload["success"] = False
    _rook_payload["error"] = type(_rook_err).__name__ + ": " + str(_rook_err)
    _rook_payload["traceback"] = traceback.format_exc()
finally:
    _rook_payload["output"] = _rook_stdout.getvalue()
    _rook_payload["stderr"] = _rook_stderr.getvalue()
    try:
        _rook_dir = os.path.dirname(ROOK_RESULT_PATH)
        if _rook_dir:
            os.makedirs(_rook_dir, exist_ok=True)
        with open(ROOK_RESULT_PATH, "w", encoding="utf-8") as _rook_result_file:
            json.dump(_rook_payload, _rook_result_file)
    except Exception:
        # No payload means the C# side rolls the transaction back.
        pass
