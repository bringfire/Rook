from __future__ import annotations

import importlib.util
import builtins
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER_FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"
NON_R01_RECIPE = ROOT / "mcp_server" / "tests" / "fixtures" / "lm9b_p" / "non_r01_ready_recipe.json"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LM9B_C_SUPPORT = _load_script("lm9b_c_compiler_sufficiency_support")
LM9B_C_ARTIFACTS = _load_script("lm9b_c_compiler_sufficiency_artifacts")
LM9B_C_PROBE = _load_script("lm9b_c_compiler_sufficiency_probe")
SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")


def test_non_r01_recipe_reaches_unchanged_fake_compiler_provider(tmp_path: Path) -> None:
    authority = ARTIFACTS.load_planner_authority_context(PLANNER_FIXTURES)
    recipe_bytes = NON_R01_RECIPE.read_bytes()
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
    )
    assert gate.status == "mechanically_accepted"
    assert gate.final_recipe_bytes == recipe_bytes
    assert gate.ratified_recipe_fingerprint == gate.historical_recipe_fingerprint

    handoff = ARTIFACTS.build_lm9bc_handoff(
        accepted_recipe_bytes=recipe_bytes,
        accepted_recipe_fingerprint=gate.ratified_recipe_fingerprint,
        planner_fixture_dir=PLANNER_FIXTURES,
        compiler_fixture_dir=COMPILER_FIXTURES,
        destination=tmp_path / "handoff",
    )
    assert handoff.archived_recipe_bytes == recipe_bytes
    assert handoff.compiler_renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID
    assert handoff.attempt_context_fingerprint == authority.attempt_context[
        "context_fingerprint"
    ]
    assert handoff.manifest["probe_attempt_context"] == authority.attempt_context
    assert "r01_recipe" not in json.dumps(handoff.manifest).lower()

    loaded = LM9B_C_ARTIFACTS.load_frozen_inputs(handoff.fixture_dir)
    rendered = LM9B_C_ARTIFACTS.render_compiler_request(loaded)
    assert rendered.renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID

    calls: list[dict[str, object]] = []

    def fake_compiler(payload: dict[str, object]):
        calls.append(payload)
        raise LM9B_C_SUPPORT.ProviderCallFailure(
            failure_type="constructive_witness_stop",
            message="constructive witness stop",
            raw_request=b"",
            raw_error=b"constructive witness stop",
        )

    result = LM9B_C_PROBE.run_probe(
        run_root=tmp_path / "compiler-run",
        fixture_dir=handoff.fixture_dir,
        compiler_provider=fake_compiler,
        evaluator_provider=lambda payload: (_ for _ in ()).throw(
            AssertionError("evaluator must not run")
        ),
        compiler_identity={"provider": "fake", "model": "constructive-witness"},
        evaluator_identity={"provider": "fake", "model": "unused"},
        git_sha="constructivewitness",
    )
    assert len(calls) == 1
    assert result.decision.outcome == "inconclusive"


def test_handoff_never_reads_r01_or_its_source_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    forbidden = {
        (COMPILER_FIXTURES / "r01_recipe.json").resolve(),
        (COMPILER_FIXTURES / "input_manifest.json").resolve(),
    }
    observed: set[Path] = set()
    original_read_bytes = Path.read_bytes
    original_path_open = Path.open
    original_stat = Path.stat
    original_open = builtins.open

    def audited_read_bytes(path: Path):
        resolved = path.resolve()
        if resolved in forbidden:
            observed.add(resolved)
        return original_read_bytes(path)

    def audited_stat(path: Path, *args, **kwargs):
        resolved = Path(path).absolute()
        if resolved in forbidden:
            observed.add(resolved)
        return original_stat(path, *args, **kwargs)

    def audited_path_open(path: Path, *args, **kwargs):
        resolved = path.resolve()
        if resolved in forbidden:
            observed.add(resolved)
        return original_path_open(path, *args, **kwargs)

    def audited_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, Path)):
            resolved = Path(file).resolve()
            if resolved in forbidden:
                observed.add(resolved)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", audited_read_bytes)
    monkeypatch.setattr(Path, "open", audited_path_open)
    monkeypatch.setattr(Path, "stat", audited_stat)
    monkeypatch.setattr(builtins, "open", audited_open)

    authority = ARTIFACTS.load_planner_authority_context(PLANNER_FIXTURES)
    recipe_bytes = NON_R01_RECIPE.read_bytes()
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
    )
    ARTIFACTS.build_lm9bc_handoff(
        accepted_recipe_bytes=gate.final_recipe_bytes,
        accepted_recipe_fingerprint=gate.ratified_recipe_fingerprint,
        planner_fixture_dir=PLANNER_FIXTURES,
        compiler_fixture_dir=COMPILER_FIXTURES,
        destination=tmp_path / "audited-handoff",
    )
    assert observed == set()
