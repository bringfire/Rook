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
# rollback from that payload alone, and only accepts success at stage "done".
#
# Names bound for the caller's script:
#     doc    Autodesk.Revit.DB.Document         the active document
#     uidoc  Autodesk.Revit.UI.UIDocument
#     uiapp  Autodesk.Revit.UI.UIApplication
#     app    Autodesk.Revit.ApplicationServices.Application
#     DB     the Autodesk.Revit.DB namespace
#     UI     the Autodesk.Revit.UI namespace
#     result None; assign a JSON value (numbers, strings, lists, dicts) to
#            return it to the caller
import io
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout

# Keep in step with BimTransactionScriptResult (MaxStreamLength,
# MaxResultJsonLength, MaxTracebackLength, MaxErrorLength).
_ROOK_STREAM_LIMIT = 20000
_ROOK_RESULT_LIMIT = 50000
_ROOK_TRACEBACK_LIMIT = 20000
_ROOK_ERROR_LIMIT = 2000


class _RookBoundedText(io.TextIOBase):
    """Text sink that stops storing at a limit, so a script that prints a
    huge report cannot grow memory inside the Revit process."""

    def __init__(self, limit):
        super().__init__()
        self._limit = limit
        self._parts = []
        self._size = 0
        self.truncated = False

    def writable(self):
        return True

    def write(self, text):
        text = str(text)
        room = self._limit - self._size
        if room > 0:
            kept = text[:room]
            self._parts.append(kept)
            self._size += len(kept)
        if len(text) > max(room, 0):
            self.truncated = True
        return len(text)

    def getvalue(self):
        return "".join(self._parts)


_rook_payload = {
    "success": False,
    "stage": "bind",
    "output": "",
    "outputTruncated": False,
    "stderr": "",
    "stderrTruncated": False,
    "error": "",
    "traceback": "",
    "result": None,
    "resultOmittedReason": None,
}
_rook_stdout = _RookBoundedText(_ROOK_STREAM_LIMIT)
_rook_stderr = _RookBoundedText(_ROOK_STREAM_LIMIT)

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
        # A result that cannot be returned must not undo a script that ran
        # correctly, and must not be silently replaced by something else:
        # it is omitted and the reason is given.
        try:
            # Strict: no str() fallback for Revit objects, no NaN.
            _rook_text = json.dumps(_rook_value, allow_nan=False)
            if len(_rook_text) > _ROOK_RESULT_LIMIT:
                _rook_payload["resultOmittedReason"] = (
                    "result was "
                    + str(len(_rook_text))
                    + " characters of JSON; the limit is "
                    + str(_ROOK_RESULT_LIMIT)
                    + ". Return a smaller value, for example ids and counts."
                )
            else:
                _rook_payload["result"] = json.loads(_rook_text)
        except Exception as _rook_result_err:
            _rook_payload["resultOmittedReason"] = (
                "result could not be converted to JSON ("
                + type(_rook_result_err).__name__
                + ": "
                + str(_rook_result_err)[:300]
                + "). Assign plain numbers, strings, lists and dicts; "
                + "return Revit elements as their ids, for example element.Id.Value."
            )

    _rook_payload["success"] = True
    _rook_payload["stage"] = "done"
except BaseException as _rook_err:
    _rook_payload["success"] = False
    _rook_payload["error"] = (type(_rook_err).__name__ + ": " + str(_rook_err))[:_ROOK_ERROR_LIMIT]
    _rook_payload["traceback"] = traceback.format_exc()[-_ROOK_TRACEBACK_LIMIT:]
finally:
    _rook_payload["output"] = _rook_stdout.getvalue()
    _rook_payload["outputTruncated"] = _rook_stdout.truncated
    _rook_payload["stderr"] = _rook_stderr.getvalue()
    _rook_payload["stderrTruncated"] = _rook_stderr.truncated
    try:
        _rook_dir = os.path.dirname(ROOK_RESULT_PATH)
        if _rook_dir:
            os.makedirs(_rook_dir, exist_ok=True)
        with open(ROOK_RESULT_PATH, "w", encoding="utf-8") as _rook_result_file:
            json.dump(_rook_payload, _rook_result_file)
    except Exception:
        # No payload means the C# side rolls the transaction back.
        pass
