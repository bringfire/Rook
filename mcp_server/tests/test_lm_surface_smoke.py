from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm_surface_smoke.py"
    spec = importlib.util.spec_from_file_location("lm_surface_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SMOKE = _load_script()


def test_pythonpath_clean():
    assert SMOKE.pythonpath_clean("") is True
    assert SMOKE.pythonpath_clean("   ") is True
    assert SMOKE.pythonpath_clean("C:/repo/src") is False
    assert SMOKE.pythonpath_clean(" C:/x ") is False


def test_module_origin_ok_under_site_packages():
    root = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages"
    under = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages\rook\__init__.py"
    repo = r"C:\UDEV\Rook\mcp_server\src\rook\__init__.py"
    assert SMOKE.module_origin_ok(under, root) is True
    # case + separator insensitivity
    assert SMOKE.module_origin_ok(under.lower().replace("\\", "/"), root) is True
    assert SMOKE.module_origin_ok(repo, root) is False


def test_module_origin_ok_rejects_sibling_path():
    # Real containment, not string startswith: a sibling whose name shares the
    # root as a prefix must NOT pass.
    root = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages"
    sibling = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages2\rook\__init__.py"
    assert SMOKE.module_origin_ok(sibling, root) is False


def test_classify_cache():
    required = {"gh_snapshot", "gh_errors"}
    assert SMOKE.classify_cache(None, {"a"}, required) == "absent"
    assert SMOKE.classify_cache({"a", "b"}, {"a", "b"}, required) == "current"
    # benign drift (not in required) -> warning
    assert SMOKE.classify_cache({"a", "b"}, {"a"}, required) == "warning"
    # required-touching drift -> fail
    assert SMOKE.classify_cache({"a"}, {"a", "gh_snapshot"}, required) == "fail"


def test_degenerate_activation_failures():
    catalog_groups = {"gh_canvas", "rhino_geometry"}
    # gh_canvas present in catalog but failed -> degenerate
    assert SMOKE.degenerate_activation_failures(
        {"gh_canvas", "absent_group"}, catalog_groups
    ) == ("gh_canvas",)
    # a group absent from the catalog failing is allowed (not flagged)
    assert SMOKE.degenerate_activation_failures({"absent_group"}, catalog_groups) == ()


def test_format_surface_evidence_is_deterministic():
    out = SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"active_not_intended": 3, "group_activation_failed": 1},
        profile_findings_count=76,
    )
    assert "catalog tools: 300" in out
    assert "profile: readonly" in out
    # histogram rendered in sorted code order
    assert out.index("active_not_intended") < out.index("group_activation_failed")
    assert out == SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"group_activation_failed": 1, "active_not_intended": 3},
        profile_findings_count=76,
    )
