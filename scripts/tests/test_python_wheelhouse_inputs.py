"""Offline causal checks for the existing PowerShell builder's locked inputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/python-runtime/build-rook-python-wheelhouse.ps1"
LOCK = ROOT / "installer/python-runtime/requirements-third-party-lock.txt"
PYTHON = os.environ.get("ROOK_WHEELHOUSE_TEST_PYTHON")
PWSH = os.environ.get("ROOK_WHEELHOUSE_TEST_POWERSHELL", "pwsh")


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


class LockedInputs(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PYTHON and Path(PYTHON).is_file(), "Set ROOK_WHEELHOUSE_TEST_PYTHON to existing pip Python")
        self.temp = tempfile.TemporaryDirectory(prefix="rook-locked-inputs-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "accepted wheels"
        self.cache.mkdir()
        self.output = self.root / "output"
        self.lock = self.root / "inputs.txt"

    def wheel(self, name, version, requirements=()):
        normalized = name.replace("-", "_")
        path = self.cache / f"{normalized}-{version}-py3-none-any.whl"
        info = f"{normalized}-{version}.dist-info"
        with zipfile.ZipFile(path, "w") as wheel:
            metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            metadata += "".join(f"Requires-Dist: {r}\n" for r in requirements)
            wheel.writestr(f"{info}/METADATA", metadata)
            wheel.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: synthetic\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
            wheel.writestr(f"{info}/RECORD", "")
        return path

    def write_lock(self, *wheels):
        rows = []
        for wheel in wheels:
            name, version = wheel.name.split("-")[:2]
            rows.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}")
        self.lock.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def ps(self, tail):
        # Only the production functions are imported; the builder top-level never executes.
        script = f"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile({quote(BUILDER)},[ref]$tokens,[ref]$errors)
if ($errors.Count) {{ throw 'Builder syntax failed' }}
foreach ($name in @('Fail','Join-ProcessArguments','Invoke-CheckedProcess','Get-LockedDependencyArguments','Stage-LockedDependencies','Assert-DependencyCacheLocation')) {{
  $f=$ast.Find({{param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name}},$true)
  if ($null -eq $f) {{ throw "Missing locked-input implementation: $name" }}
  . ([scriptblock]::Create($f.Extent.Text))
}}
$CommandTimeoutSeconds=30
{tail}
"""
        result = subprocess.run([PWSH, "-NoProfile", "-Command", script], capture_output=True, timeout=45)
        self.assertLess(len(result.stdout) + len(result.stderr), 128 * 1024)
        return result

    def stage(self):
        return self.ps(f"Stage-LockedDependencies -PythonExe {quote(PYTHON)} -RequirementsLock {quote(self.lock)} -Wheelhouse {quote(self.output)} -DependencyWheelhouse {quote(self.cache)}")

    def test_accepted_old_version_wins_over_newer_and_transitives_are_locked(self):
        old = self.wheel("demo-leaf", "1.0", ["demo-transitive>=2"])
        self.wheel("demo-leaf", "2.0", ["demo-transitive>=3"])
        transitive = self.wheel("demo-transitive", "2.0")
        self.wheel("demo-transitive", "3.0")
        self.write_lock(old, transitive)
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual({p.name for p in self.output.iterdir()}, {old.name, transitive.name})
        self.assertEqual({p.name: p.read_bytes() for p in self.cache.iterdir()}, before)
        self.assertEqual((self.output / old.name).read_bytes(), old.read_bytes())

    def test_missing_accepted_wheel_refuses_without_substitution(self):
        old = self.wheel("demo-leaf", "1.0")
        self.write_lock(old)
        old.unlink()
        self.wheel("demo-leaf", "2.0")
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"No matching distribution", result.stderr)
        self.assertFalse(list(self.output.glob("*.whl")))

    def test_wrong_hash_refuses(self):
        old = self.wheel("demo-leaf", "1.0")
        self.write_lock(old)
        with old.open("ab") as stream:
            stream.write(b"changed bytes")
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"HASHES", result.stderr.upper())

    def test_unhashed_requirement_refuses(self):
        self.wheel("demo-leaf", "1.0")
        self.lock.write_text("demo-leaf==1.0\n", encoding="utf-8")
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"HASH", result.stderr.upper())

    def test_unpinned_requirement_refuses(self):
        wheel = self.wheel("demo-leaf", "1.0")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        self.lock.write_text(f"demo-leaf>=1 --hash=sha256:{digest}\n", encoding="utf-8")
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"pinned", result.stderr)

    def test_offline_resolution_rejects_incompatible_rebuilt_local_package(self):
        old = self.wheel("demo-leaf", "1.0")
        self.write_lock(old)
        staged = self.stage()
        self.assertEqual(staged.returncode, 0, staged.stderr.decode(errors="replace"))
        for required, success in (("demo-leaf==1.0", True), ("demo-leaf>=2", False), ("missing-transitive==1", False)):
            with self.subTest(required=required):
                rebuilt = self.wheel("local-app", "1.0", [required])
                result = subprocess.run(
                    [PYTHON, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-cache-dir",
                     "install", "--dry-run", "--ignore-installed", "--no-index", "--find-links", str(self.output), str(rebuilt)],
                    capture_output=True, timeout=30)
                self.assertLess(len(result.stdout) + len(result.stderr), 128 * 1024)
                self.assertEqual(result.returncode == 0, success, result.stderr.decode(errors="replace"))

    def test_cache_overlap_refuses_before_disposable_output_cleanup(self):
        sentinel = self.cache / "preserved.txt"
        sentinel.write_bytes(b"accepted bytes")
        for output in (self.cache, self.cache.parent, self.cache / "nested-output"):
            with self.subTest(output=output):
                result = self.ps(f"Assert-DependencyCacheLocation -DependencyWheelhouse {quote(self.cache)} -OutputPaths @({quote(output)})")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"must be separate", result.stderr)
                self.assertEqual(sentinel.read_bytes(), b"accepted bytes")
        separate = self.ps(f"Assert-DependencyCacheLocation -DependencyWheelhouse {quote(self.cache)} -OutputPaths @({quote(self.output)})")
        self.assertEqual(separate.returncode, 0, separate.stderr.decode(errors="replace"))

    def test_relative_cache_overlap_uses_powershell_location(self):
        sentinel = self.cache / "preserved.txt"
        sentinel.write_bytes(b"accepted bytes")
        other = self.root / "dotnet-location"
        other.mkdir()
        setup = f"""
[Environment]::CurrentDirectory={quote(other)}
Set-Location -LiteralPath {quote(self.root)}
if ([Environment]::CurrentDirectory -eq (Get-Location).Path) {{ throw 'Fixture requires distinct current directories' }}
"""
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        for output in ("accepted wheels", ".", "accepted wheels/nested-output", "unused/../accepted wheels"):
            with self.subTest(output=output):
                result = self.ps(setup + f"Assert-DependencyCacheLocation -DependencyWheelhouse 'accepted wheels' -OutputPaths @({quote(output)})")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"must be separate", result.stderr)
                self.assertEqual({p.name: p.read_bytes() for p in self.cache.iterdir()}, before)
        separate = self.ps(setup + "Assert-DependencyCacheLocation -DependencyWheelhouse 'accepted wheels' -OutputPaths @('separate-output')")
        self.assertEqual(separate.returncode, 0, separate.stderr.decode(errors="replace"))
        self.assertEqual({p.name: p.read_bytes() for p in self.cache.iterdir()}, before)

    def test_missing_lock_or_cache_refuses_without_output(self):
        result = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"input lock missing", result.stderr)
        self.write_lock(self.wheel("demo-leaf", "1.0"))
        result = self.ps(f"Stage-LockedDependencies -PythonExe {quote(PYTHON)} -RequirementsLock {quote(self.lock)} -Wheelhouse {quote(self.output)} -DependencyWheelhouse {quote(self.cache / 'missing')}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"wheelhouse missing", result.stderr)
        self.assertFalse(self.output.exists())

    def test_local_source_arguments_forbid_index_and_dependency_expansion(self):
        self.write_lock(self.wheel("demo-leaf", "1.0"))
        result = self.ps(f"@(Get-LockedDependencyArguments -RequirementsLock {quote(self.lock)} -Wheelhouse {quote(self.output)} -DependencyWheelhouse {quote(self.cache)}) | ConvertTo-Json -Compress")
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        args = json.loads(result.stdout)
        for expected in ("--require-hashes", "--no-deps", "--no-index", "--no-cache-dir", "--only-binary=:all:"):
            self.assertIn(expected, args)
        self.assertEqual(args[args.index("--find-links") + 1], str(self.cache))
        self.assertEqual(args[args.index("-r") + 1], str(self.lock))

    def test_default_acquisition_still_requires_pins_and_hashes(self):
        self.write_lock(self.wheel("demo-leaf", "1.0"))
        result = self.ps(f"@(Get-LockedDependencyArguments -RequirementsLock {quote(self.lock)} -Wheelhouse {quote(self.output)}) | ConvertTo-Json -Compress")
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        args = json.loads(result.stdout)
        self.assertIn("--require-hashes", args)
        self.assertIn("--no-deps", args)
        self.assertNotIn("--no-index", args)

    def test_production_download_has_no_unlocked_dependency_route(self):
        source = BUILDER.read_text(encoding="utf-8-sig")
        self.assertIn("Stage-LockedDependencies -PythonExe $buildPythonExe", source)
        self.assertNotIn("$rookWheel.FullName, $chirpWheel.FullName)", source)
        self.assertIn("requirements-third-party-lock.txt", source)
        self.assertIn("dependency_inputs", source)

    def test_committed_lock_keeps_accepted_multidict_and_excludes_local_wheels(self):
        self.assertTrue(LOCK.is_file(), "Approved input lock is missing")
        rows = [line for line in LOCK.read_text().splitlines() if line and not line.startswith("#")]
        self.assertTrue(rows)
        names = []
        for row in rows:
            self.assertRegex(row, r"^[a-z0-9-]+==[^ ]+ --hash=sha256:[a-f0-9]{64}$")
            names.append(row.split("==")[0])
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("rook-mcp", names)
        self.assertNotIn("chirp", names)
        self.assertIn("multidict==6.8.0 --hash=sha256:b03ca066b47b18b205cc080dca6f76cbd159f8cdd33a02a0700164c13b37e463", rows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
