from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from rook.agent.chat.prime_runtime_contract import (
    RuntimeContractError,
    build_package_manifest,
    build_runtime_contract,
    canonical_json_bytes,
    parse_runtime_contract_bytes,
    stage_product_package,
    verify_package,
    verify_runtime_contract,
    write_package_manifest,
)


PRODUCT_PACKAGE_ROOT = (
    Path(__file__).parents[2] / "integrations" / "prime" / "skills" / "rook-full"
)


def _write_package(root: Path, *, body: str = "VALUE = 1\n") -> Path:
    (root / "src" / "rook_full").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("---\nname: rook-full\n---\nContract.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='rook-full'\n", encoding="utf-8")
    (root / "src" / "rook_full" / "__init__.py").write_text(body, encoding="utf-8")
    (root / "references" / "grasshopper.md").write_text("Grasshopper.\n", encoding="utf-8")
    return root


def test_manifest_is_recursive_closed_and_canonical(tmp_path: Path) -> None:
    root = _write_package(tmp_path / "rook-full")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "ignored").write_bytes(b"cache")
    (root / "build").mkdir()
    (root / "build" / "ignored.txt").write_text("build", encoding="utf-8")
    (root / "dist").mkdir()
    (root / "dist" / "ignored.txt").write_text("dist", encoding="utf-8")

    manifest = build_package_manifest(root)
    assert set(manifest) == {"files", "schemaVersion"}
    assert manifest["schemaVersion"] == 1
    assert [item["path"] for item in manifest["files"]] == [
        "SKILL.md",
        "pyproject.toml",
        "references/grasshopper.md",
        "src/rook_full/__init__.py",
    ]
    assert all(set(item) == {"path", "sha256", "size"} for item in manifest["files"])
    assert all(len(item["sha256"]) == 64 and item["sha256"].isupper() for item in manifest["files"])

    raw = canonical_json_bytes(manifest)
    assert raw == json.dumps(
        manifest,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not raw.endswith(b"\n")


def test_goal_and_rook_packages_use_the_same_manifest_algorithm(tmp_path: Path) -> None:
    rook = _write_package(tmp_path / "rook-full")
    goal = _write_package(tmp_path / "goal")

    assert canonical_json_bytes(build_package_manifest(rook)) == canonical_json_bytes(build_package_manifest(goal))


def test_checked_in_product_manifest_exactly_reproduces_package_bytes() -> None:
    manifest_path = PRODUCT_PACKAGE_ROOT / "package-manifest.json"
    expected = canonical_json_bytes(build_package_manifest(PRODUCT_PACKAGE_ROOT))

    assert manifest_path.read_bytes() == expected
    verified = verify_package(PRODUCT_PACKAGE_ROOT)
    assert verified.root == PRODUCT_PACKAGE_ROOT.resolve()


@pytest.mark.parametrize(
    "tamper",
    (
        "bom",
        "trailing_newline",
        "duplicate_root_key",
        "unknown_root_key",
        "unknown_member_key",
        "lowercase_hash",
        "wrong_size",
        "duplicate_path",
        "backslash_path",
        "unsorted_paths",
    ),
)
def test_manifest_verification_rejects_noncanonical_or_open_bytes(tmp_path: Path, tamper: str) -> None:
    root = _write_package(tmp_path / "rook-full")
    package = write_package_manifest(root)
    manifest_path = root / "package-manifest.json"
    value = json.loads(manifest_path.read_bytes())

    if tamper == "bom":
        raw = b"\xef\xbb\xbf" + manifest_path.read_bytes()
    elif tamper == "trailing_newline":
        raw = manifest_path.read_bytes() + b"\n"
    elif tamper == "duplicate_root_key":
        raw = manifest_path.read_bytes()[:-1] + b',"schemaVersion":1}'
    elif tamper == "unknown_root_key":
        value["extra"] = True
        raw = canonical_json_bytes(value)
    elif tamper == "unknown_member_key":
        value["files"][0]["extra"] = True
        raw = canonical_json_bytes(value)
    elif tamper == "lowercase_hash":
        value["files"][0]["sha256"] = value["files"][0]["sha256"].lower()
        raw = canonical_json_bytes(value)
    elif tamper == "wrong_size":
        value["files"][0]["size"] += 1
        raw = canonical_json_bytes(value)
    elif tamper == "duplicate_path":
        value["files"].append(dict(value["files"][0]))
        raw = canonical_json_bytes(value)
    elif tamper == "backslash_path":
        value["files"][0]["path"] = "references\\bad.md"
        raw = canonical_json_bytes(value)
    elif tamper == "unsorted_paths":
        value["files"] = list(reversed(value["files"]))
        raw = canonical_json_bytes(value)
    else:  # pragma: no cover
        raise AssertionError(tamper)

    manifest_path.write_bytes(raw)
    with pytest.raises(RuntimeContractError):
        verify_package(root, expected_manifest_sha256=package.manifest_sha256)


def test_manifest_verification_rejects_missing_unlisted_and_changed_files(tmp_path: Path) -> None:
    root = _write_package(tmp_path / "rook-full")
    package = write_package_manifest(root)

    (root / "references" / "grasshopper.md").unlink()
    with pytest.raises(RuntimeContractError, match="manifest|missing"):
        verify_package(root, expected_manifest_sha256=package.manifest_sha256)

    (root / "references" / "grasshopper.md").write_text("Grasshopper.\n", encoding="utf-8")
    (root / "unexpected.txt").write_text("unlisted", encoding="utf-8")
    with pytest.raises(RuntimeContractError, match="manifest|unlisted"):
        verify_package(root, expected_manifest_sha256=package.manifest_sha256)

    (root / "unexpected.txt").unlink()
    (root / "SKILL.md").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeContractError, match="manifest|hash|size"):
        verify_package(root, expected_manifest_sha256=package.manifest_sha256)


def test_manifest_rejects_symlink_or_reparse_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _write_package(tmp_path / "rook-full")
    import rook.agent.chat.prime_runtime_contract as runtime_contract

    original = runtime_contract._is_reparse_point
    target = root / "references" / "grasshopper.md"
    monkeypatch.setattr(
        runtime_contract,
        "_is_reparse_point",
        lambda path: path == target or original(path),
    )

    with pytest.raises(RuntimeContractError, match="reparse"):
        build_package_manifest(root)


def _build_contract(
    *,
    package_root: Path,
    goal_root: Path,
    kernel_root: Path,
    profile: str,
):
    package = verify_package(package_root)
    return build_runtime_contract(
        prime_bundle_manifest_sha256="A" * 64,
        prime_git_commit_provenance="3e3c9da18911f3ecffd56fe99eb7bab552fcd81e",
        goal_skill_root=goal_root,
        goal_skill_path_identity="packages/coding-agent/skills/goal",
        rook_package=package,
        capability_profile=profile,
        kernel_root=kernel_root,
        runtime_compatibility_version=1,
    )


def test_runtime_contract_is_closed_profile_distinct_and_path_keyed(tmp_path: Path) -> None:
    package_root = _write_package(tmp_path / "source")
    write_package_manifest(package_root)
    goal_root = _write_package(tmp_path / "goal")
    kernels = tmp_path / "kernels"

    readonly = _build_contract(
        package_root=package_root,
        goal_root=goal_root,
        kernel_root=kernels,
        profile="readonly",
    )
    full = _build_contract(
        package_root=package_root,
        goal_root=goal_root,
        kernel_root=kernels,
        profile="full",
    )

    assert set(readonly.record) == {
        "capabilityProfile",
        "goalSkill",
        "prime",
        "rlmMaxDepth",
        "rookPackage",
        "runtimeCompatibilityVersion",
        "schemaVersion",
    }
    assert readonly.record["rlmMaxDepth"] == 0
    assert readonly.canonical_bytes == canonical_json_bytes(readonly.record)
    assert readonly.fingerprint != full.fingerprint
    assert readonly.kernel_environment_path == kernels.resolve() / readonly.fingerprint
    assert full.kernel_environment_path == kernels.resolve() / full.fingerprint
    assert readonly.goal_manifest_sha256 == full.goal_manifest_sha256
    assert readonly.rook_package.manifest_sha256 == full.rook_package.manifest_sha256
    assert parse_runtime_contract_bytes(readonly.canonical_bytes) == readonly.record


@pytest.mark.parametrize("tamper", ("bom", "trailing_newline", "duplicate_key", "unknown_key"))
def test_runtime_contract_parser_rejects_noncanonical_or_open_bytes(tmp_path: Path, tamper: str) -> None:
    package_root = _write_package(tmp_path / "source")
    write_package_manifest(package_root)
    contract = _build_contract(
        package_root=package_root,
        goal_root=_write_package(tmp_path / "goal"),
        kernel_root=tmp_path / "kernels",
        profile="readonly",
    )
    if tamper == "bom":
        raw = b"\xef\xbb\xbf" + contract.canonical_bytes
    elif tamper == "trailing_newline":
        raw = contract.canonical_bytes + b"\n"
    elif tamper == "duplicate_key":
        raw = contract.canonical_bytes[:-1] + b',"schemaVersion":1}'
    elif tamper == "unknown_key":
        raw = canonical_json_bytes(contract.record | {"extra": True})
    else:  # pragma: no cover
        raise AssertionError(tamper)
    with pytest.raises(RuntimeContractError):
        parse_runtime_contract_bytes(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("capability_profile", "inspect"),
        ("prime_bundle_manifest_sha256", "a" * 64),
        ("prime_git_commit_provenance", ""),
        ("goal_skill_path_identity", ""),
        ("runtime_compatibility_version", 2),
    ),
)
def test_runtime_contract_rejects_invalid_inputs(tmp_path: Path, field: str, value: object) -> None:
    package_root = _write_package(tmp_path / "source")
    package = write_package_manifest(package_root)
    goal_root = _write_package(tmp_path / "goal")
    arguments = {
        "prime_bundle_manifest_sha256": "A" * 64,
        "prime_git_commit_provenance": "commit",
        "goal_skill_root": goal_root,
        "goal_skill_path_identity": "packages/coding-agent/skills/goal",
        "rook_package": package,
        "capability_profile": "readonly",
        "kernel_root": tmp_path / "kernels",
        "runtime_compatibility_version": 1,
    }
    arguments[field] = value
    with pytest.raises(RuntimeContractError):
        build_runtime_contract(**arguments)


def test_staging_is_immutable_atomic_and_reusable(tmp_path: Path) -> None:
    source = _write_package(tmp_path / "source")
    product_root = tmp_path / "installed"

    staged = stage_product_package(source, product_root=product_root)
    assert staged.root == product_root.resolve() / staged.manifest_sha256 / "rook-full"
    assert staged.root.is_dir()
    assert verify_package(staged.root, expected_manifest_sha256=staged.manifest_sha256) == staged

    reused = stage_product_package(source, product_root=product_root)
    assert reused == staged

    (staged.root / "SKILL.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeContractError):
        stage_product_package(source, product_root=product_root)


def test_same_contract_and_old_new_staging_are_isolated_under_concurrency(tmp_path: Path) -> None:
    first_source = _write_package(tmp_path / "first", body="VALUE = 1\n")
    second_source = _write_package(tmp_path / "second", body="VALUE = 2\n")
    product_root = tmp_path / "installed"

    with ThreadPoolExecutor(max_workers=4) as pool:
        same_results = list(pool.map(lambda _: stage_product_package(first_source, product_root=product_root), range(4)))
    assert len({result.root for result in same_results}) == 1
    assert len({result.manifest_sha256 for result in same_results}) == 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(stage_product_package, first_source, product_root=product_root)
        second_future = pool.submit(stage_product_package, second_source, product_root=product_root)
        first = first_future.result()
        second = second_future.result()
    assert first.root != second.root
    assert first.adapter_sha256 != second.adapter_sha256
    assert verify_package(first.root) == first
    assert verify_package(second.root) == second

    goal_root = _write_package(tmp_path / "goal")
    first_contract = _build_contract(
        package_root=first.root,
        goal_root=goal_root,
        kernel_root=tmp_path / "kernels",
        profile="full",
    )
    second_contract = _build_contract(
        package_root=second.root,
        goal_root=goal_root,
        kernel_root=tmp_path / "kernels",
        profile="full",
    )
    assert first_contract.kernel_environment_path != second_contract.kernel_environment_path


def test_runtime_verification_fails_closed_for_record_package_or_path_drift(tmp_path: Path) -> None:
    source = _write_package(tmp_path / "source")
    staged = stage_product_package(source, product_root=tmp_path / "installed")
    goal_root = _write_package(tmp_path / "goal")
    contract = _build_contract(
        package_root=staged.root,
        goal_root=goal_root,
        kernel_root=tmp_path / "kernels",
        profile="readonly",
    )
    assert verify_runtime_contract(
        contract,
        product_root=tmp_path / "installed",
        goal_skill_root=goal_root,
        kernel_root=tmp_path / "kernels",
    ) == contract

    with pytest.raises(RuntimeContractError):
        verify_runtime_contract(
            replace(contract, record=contract.record | {"extra": True}),
            product_root=tmp_path / "installed",
            goal_skill_root=goal_root,
            kernel_root=tmp_path / "kernels",
        )

    (staged.root / "SKILL.md").write_text("drift", encoding="utf-8")
    with pytest.raises(RuntimeContractError):
        verify_runtime_contract(
            contract,
            product_root=tmp_path / "installed",
            goal_skill_root=goal_root,
            kernel_root=tmp_path / "kernels",
        )
