# RookBIM run-transaction wrapper.
#
# RevitPythonScriptRunner runs this text in Rhino's Python 3 engine by calling
# the engine directly, with one input: __rook__, a RevitScriptChannel created
# by the host. A Revit transaction is already open on the active document.
#
# This wrapper never starts, commits or rolls back a transaction. It runs the
# caller's script, forwards what it prints to the host as it is printed, and
# tells the host how it ended. The host decides commit or rollback from two
# things together: its own engine call returned without raising, and this
# wrapper called __rook__.Complete. An exception is re-raised so that the
# host sees it as well.
#
# Names bound for the caller's script:
#     doc    Autodesk.Revit.DB.Document         the active document
#     uidoc  Autodesk.Revit.UI.UIDocument
#     uiapp  Autodesk.Revit.UI.UIApplication
#     app    Autodesk.Revit.ApplicationServices.Application
#     DB     the Autodesk.Revit.DB namespace
#     UI     the Autodesk.Revit.UI namespace
#     result None; assign a plain JSON value (numbers, strings, lists, dicts
#            with string keys) to return it to the caller
import io
import json
import linecache
import math
import traceback
from contextlib import redirect_stderr, redirect_stdout

_ROOK_SCRIPT_NAME = "<rookbim_run_transaction>"


class _RookStream(io.TextIOBase):
    """Forwards text to a host method as it is written. The host keeps a
    bounded amount, so nothing accumulates on the Python side."""

    def __init__(self, forward):
        super().__init__()
        self._forward = forward

    def writable(self):
        return True

    def write(self, text):
        text = str(text)
        if text:
            self._forward(text)
        return len(text)


def _rook_check_result(value, max_depth, budget):
    """Refuses a result the caller could not get back intact, before any of
    it is encoded: wrong types, non-string keys (JSON would merge 1 and "1"),
    NaN, nesting too deep, or simply too much. Returns nothing; raises
    ValueError with the reason."""
    remaining = [budget]

    def spend(amount):
        remaining[0] -= amount
        if remaining[0] < 0:
            raise ValueError(
                "result is larger than "
                + str(budget)
                + " characters; return a smaller value, for example ids and counts"
            )

    def walk(item, depth):
        if depth > max_depth:
            raise ValueError("result is nested more than " + str(max_depth) + " levels deep")
        if item is None or isinstance(item, bool):
            spend(5)
        elif isinstance(item, int):
            spend(len(str(item)))
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("result contains NaN or infinity, which JSON cannot carry")
            spend(24)
        elif isinstance(item, str):
            spend(len(item) + 2)
        elif isinstance(item, (list, tuple)):
            spend(2)
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, dict):
            spend(2)
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError(
                        "result has a dict key of type "
                        + type(key).__name__
                        + "; use string keys"
                    )
                spend(len(key) + 3)
                walk(child, depth + 1)
        else:
            raise ValueError(
                "result contains a "
                + type(item).__name__
                + ", which is not a plain JSON value; return Revit elements as their ids, "
                + "for example element.Id.Value"
            )

    walk(value, 1)


__rook__.SetStage("bind")
try:
    _rook_globals = {
        "__name__": "__main__",
        "doc": __rook__.Document,
        "uidoc": __rook__.UIDocument,
        "uiapp": __rook__.UIApplication,
        "app": __rook__.Application,
        "result": None,
    }
    if __rook__.BindRevitNamespaces:
        import Autodesk.Revit.DB as _rook_db
        import Autodesk.Revit.UI as _rook_ui

        _rook_globals["DB"] = _rook_db
        _rook_globals["UI"] = _rook_ui

    __rook__.SetStage("compile")
    _rook_code = __rook__.Code
    # Lets a traceback show the caller's own source lines.
    linecache.cache[_ROOK_SCRIPT_NAME] = (
        len(_rook_code),
        None,
        _rook_code.splitlines(True),
        _ROOK_SCRIPT_NAME,
    )
    _rook_compiled = compile(_rook_code, _ROOK_SCRIPT_NAME, "exec")

    __rook__.SetStage("run")
    with redirect_stdout(_RookStream(__rook__.WriteOutput)), redirect_stderr(
        _RookStream(__rook__.WriteError)
    ):
        exec(_rook_compiled, _rook_globals, _rook_globals)

    __rook__.SetStage("result")
    _rook_value = _rook_globals.get("result")
    _rook_json = None
    _rook_omitted = None
    if _rook_value is not None:
        # A result that cannot be returned must not undo a script that ran
        # correctly, and must not be silently replaced by something else:
        # it is omitted and the reason is given.
        try:
            _rook_check_result(_rook_value, __rook__.MaxResultDepth, __rook__.MaxResultLength)
            _rook_json = json.dumps(_rook_value, allow_nan=False)
            if len(_rook_json) > __rook__.MaxResultLength:
                raise ValueError(
                    "result is "
                    + str(len(_rook_json))
                    + " characters of JSON; the limit is "
                    + str(__rook__.MaxResultLength)
                )
        except Exception as _rook_result_err:
            _rook_json = None
            _rook_omitted = (
                "result was not returned: "
                + str(_rook_result_err)[:300]
                + ". The script's changes are not affected."
            )

    __rook__.SetStage("done")
    __rook__.Complete(_rook_json, _rook_omitted)
except BaseException as _rook_err:
    __rook__.Fail(
        (type(_rook_err).__name__ + ": " + str(_rook_err))[: __rook__.MaxErrorLength],
        # limit=-30 formats only the innermost frames, where the error is.
        traceback.format_exc(limit=-30)[-__rook__.MaxTracebackLength :],
    )
    raise
finally:
    linecache.cache.pop(_ROOK_SCRIPT_NAME, None)
