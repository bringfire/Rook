"""Dev manifest handoff: checkout Python with installed ACP payload/data roots."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from .test_chat_prime_runtime import _write_runtime

REPO = Path(__file__).resolve().parents[2]
DRIVER = r"""
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $env:TEST_REPO 'scripts/deploy-local-testing.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Deployment syntax failure' }
foreach ($name in @('Resolve-DevPythonRuntime','New-DeployRuntimeEnvironment',
    'Resolve-DeployRuntimeContract','Write-ChatServiceManifests','Test-ChatServiceManifest',
    'Test-ChatServiceManifestAtPath','Normalize-PathForCompare')) {
    $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    if (-not $fn) { throw "Missing deployment owner: $name" }
    . ([scriptblock]::Create($fn.Extent.Text))
}
$RepoRoot=$env:TEST_REPO
$InstallRoot=Join-Path $env:TEST_ROOT 'app'
$DataRoot=Join-Path $env:TEST_ROOT 'data'
$VenvPython=Join-Path $env:TEST_ROOT 'release-venv/Scripts/python.exe'
$ChirpInstallRoot=Join-Path $InstallRoot 'chirp'
$PluginDir=Join-Path $env:TEST_ROOT 'plugin'
$ManagedCompanionRuntimes=@('net8.0','net7.0','net48')
$UseRepoVenv=$env:TEST_MODE -eq 'repo'
$DevPythonRuntime=if ($env:TEST_MODE -eq 'explicit') { $env:TEST_PYTHON } elseif ($env:TEST_MODE -eq 'missing') { Join-Path $env:TEST_ROOT 'absent/python.exe' } else { '' }
$contract=Resolve-DeployRuntimeContract
Write-ChatServiceManifests -Contract $contract
Test-ChatServiceManifest -Contract $contract
"""

PROBE = r"""
import json, sys
def forbid_contact(event, args):
    if event in {'subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind'}:
        raise AssertionError('Runtime/network contact is forbidden in this test')
sys.addaudithook(forbid_contact)
import rook
from rook.runtime_paths import resolve_runtime_paths, get_acp_data_paths
from rook.agent.chat.service_main import build_acp_manager
paths = resolve_runtime_paths()
manager, available = build_acp_manager({})
print(json.dumps({'origin': rook.__file__, 'install': str(paths.install_root),
                  'data': str(paths.data_root), 'sessions': str(get_acp_data_paths(paths).sessions_root),
                  'runtimeAvailable': available}))
"""


def manifest(tmp_path, mode):
    for runtime in ('net8.0', 'net7.0', 'net48'):
        (tmp_path / 'plugin' / runtime).mkdir(parents=True)
    result = subprocess.run(
        ['C:/Program Files/PowerShell/7/pwsh.exe', '-NoProfile', '-Command', DRIVER],
        env=os.environ | {'TEST_REPO': str(REPO), 'TEST_ROOT': str(tmp_path),
                          'TEST_MODE': mode, 'TEST_PYTHON': sys.executable},
        capture_output=True, text=True, timeout=30,
    )
    return result


@pytest.mark.parametrize('mode', ['repo', 'explicit'])
@pytest.mark.parametrize('tampered', [False, True])
def test_dev_manifest_loads_checkout_code_and_verifies_installed_runtime(tmp_path, mode, tampered):
    prime = tmp_path / 'app/prime'
    runtime_id, runtime = _write_runtime(prime)
    (prime / 'current.json').write_bytes((json.dumps({'runtimeId': runtime_id}, separators=(',', ':')) + '\n').encode())
    if tampered:
        (runtime / 'pi.exe').write_bytes(b'changed fixture bytes')
    before = {p.relative_to(prime): p.read_bytes() for p in prime.rglob('*') if p.is_file()}
    result = manifest(tmp_path, mode)
    assert result.returncode == 0, result.stdout + result.stderr
    paths = [tmp_path / 'plugin' / part / 'RookChatService.json'
             for part in ('', 'net8.0', 'net7.0', 'net48')]
    values = [json.loads(path.read_text(encoding='utf-8-sig')) for path in paths]
    assert all(value == values[0] for value in values)
    value = values[0]
    assert Path(value['workingDirectory']) == REPO / 'mcp_server'
    assert [Path(p) for p in value['pythonPathEntries']] == [REPO / 'mcp_server/src']
    expected_python = REPO / 'mcp_server/.venv/Scripts/python.exe' if mode == 'repo' else Path(sys.executable)
    assert Path(value['pythonPath']) == expected_python
    assert Path(value['environment']['ROOK_PROJECT_ROOT']) == REPO
    assert Path(value['environment']['ROOK_INSTALL_ROOT']) == tmp_path / 'app'
    assert Path(value['environment']['ROOK_DATA_DIR']) == tmp_path / 'data'
    assert value['environment']['ROOK_MODE'] == 'dev'
    # Project only the emitted manifest environment and import paths, as the
    # panel does; do not inherit credentials or point any data root at the user.
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
    env.update(value['environment'])
    env.update({'PYTHONPATH': os.pathsep.join(value['pythonPathEntries']),
                'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'})
    probe = subprocess.run([value['pythonPath'], '-B', '-c', PROBE], env=env,
                           cwd=value['workingDirectory'], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    observed = json.loads(probe.stdout)
    assert Path(observed['origin']).is_relative_to(REPO / 'mcp_server/src/rook')
    assert Path(observed['install']) == tmp_path / 'app'
    assert Path(observed['data']) == tmp_path / 'data'
    assert Path(observed['sessions']) == tmp_path / 'data/rookchat/acp/v1/sessions'
    assert observed['runtimeAvailable'] is (not tampered)
    assert {p.relative_to(prime): p.read_bytes() for p in prime.rglob('*') if p.is_file()} == before


def test_release_manifest_still_uses_installed_python_and_no_source_override(tmp_path):
    result = manifest(tmp_path, 'release')
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads((tmp_path / 'plugin/RookChatService.json').read_text(encoding='utf-8-sig'))
    assert Path(value['pythonPath']) == tmp_path / 'release-venv/Scripts/python.exe'
    assert Path(value['workingDirectory']) == tmp_path / 'app/mcp_server'
    assert value['pythonPathEntries'] == []
    assert value['environment']['ROOK_MODE'] == 'release'
    assert value['environment']['PYTHONPATH'] == ''
    assert 'ROOK_PROJECT_ROOT' not in value['environment']


def test_missing_explicit_interpreter_refuses_before_manifest_write(tmp_path):
    result = manifest(tmp_path, 'missing')
    assert result.returncode != 0
    assert 'Dev Python runtime not found' in result.stderr
    assert not list((tmp_path / 'plugin').rglob('RookChatService.json'))
