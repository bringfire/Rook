"""Windows storage admission. All paths and credentials are disposable fixtures."""
import ctypes
import importlib
import os
import json
import sys
import subprocess
from pathlib import Path

import pytest


def storage():
    name = 'rook.agent.chat.configuration_storage'
    assert importlib.util.find_spec(name) is not None, 'storage admission helper is missing'
    return importlib.import_module(name)


def test_owned_object_rejects_untrusted_access():
    s = storage()
    trusted = {'user', 'system', 'admin'}
    for right in (0x120089, 0x10000, 0x40000, 0x80000, 0x40, 0x2, 0x10000000, 0x40000000):
        with pytest.raises(s.ConfigurationStorageRefused):
            s._admit_aces([('other', right, 0)], trusted)


def set_acl(path, sddl):
    """Fixture-only ACL setup, never called on installed/user configuration."""
    from ctypes import wintypes as w
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(w.LPVOID), w.LPVOID]
    adv.GetSecurityDescriptorDacl.argtypes = [w.LPVOID, ctypes.POINTER(w.BOOL), ctypes.POINTER(w.LPVOID), ctypes.POINTER(w.BOOL)]
    adv.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, w.LPVOID, w.LPVOID, w.LPVOID, w.LPVOID]
    kernel.LocalFree.argtypes = [w.LPVOID]
    sd = w.LPVOID()
    assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None)
    try:
        present, defaulted, acl = w.BOOL(), w.BOOL(), w.LPVOID()
        assert adv.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted))
        assert adv.SetNamedSecurityInfoW(str(path), 1, 4 | 0x80000000, None, None, acl, None) == 0
    finally:
        kernel.LocalFree(sd)


@pytest.fixture
def private_parent(tmp_path):
    if os.name != 'nt':
        pytest.skip('requires Windows discretionary ACLs')
    s = storage()
    sid = s._Windows().user_sid
    parent = tmp_path / 'data'
    parent.mkdir()
    acl = f'D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    set_acl(parent, acl + '(A;OICI;FR;;;WD)')
    return s, parent, acl


@pytest.mark.parametrize('rights', ['FR', 'DC', 'FA'])
def test_fresh_private_directory_under_broad_ancestors(private_parent, monkeypatch, rights):
    s, parent, acl = private_parent
    # Only disposable fixture ACLs are changed. The ordinary Temp/profile
    # ancestors are neither inspected nor altered by the product admission.
    set_acl(parent, acl + f'(A;OICI;{rights};;;WD)')
    root = parent / 'prime-config'
    original = s._Windows.open
    opened = []
    def observe_open(windows, path, **kwargs):
        opened.append(path)
        return original(windows, path, **kwargs)
    monkeypatch.setattr(s._Windows, 'open', observe_open)
    s.admit_configuration_storage(root)
    assert root.is_dir()
    assert not list(root.iterdir())  # admission does not manufacture auth/settings
    s.admit_configuration_storage(root)
    assert set(opened) == {root, *(root / name for name in ('auth.json', 'settings.json', 'models.json'))}


@pytest.mark.parametrize('name', ['auth.json', 'settings.json', 'models.json'])
def test_existing_unsafe_file_refuses_without_repair(private_parent, name):
    s, parent, acl = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    file = root / name
    file.write_text('synthetic-only', encoding='utf8')
    set_acl(file, acl.replace('OICI', '') + '(A;;FR;;;WD)')
    before = file.read_bytes()
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert file.read_bytes() == before
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_existing_unsafe_root_refuses_unchanged(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    root.mkdir()  # inherits extra read
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert root.is_dir() and not list(root.iterdir())


def test_hardlinked_file_refuses(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    file = root / 'auth.json'
    file.write_text('synthetic-only')
    os.link(file, parent / 'alias')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_regular_file_cannot_stand_in_for_directory(private_parent):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    root.write_text('synthetic-only')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


def test_reparse_directory_refuses_without_following_target(private_parent, tmp_path):
    s, parent, _ = private_parent
    target = tmp_path / 'target'
    target.mkdir()
    root = parent / 'prime-config'
    env = dict(os.environ, STORAGE_TEST_LINK=str(root), STORAGE_TEST_TARGET=str(target))
    result = subprocess.run(['C:/Program Files/PowerShell/7/pwsh.exe','-NoProfile','-NonInteractive','-Command',
        "$ErrorActionPreference='Stop';New-Item -ItemType Junction -Path $env:STORAGE_TEST_LINK -Target $env:STORAGE_TEST_TARGET | Out-Null"],
        env=env,capture_output=True,timeout=10)
    assert result.returncode == 0 and not result.stderr
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)
    assert not list(target.iterdir())


def test_relative_path_refuses():
    s = storage()
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(Path('relative/prime-config'))


def test_unknown_owner_refuses_from_real_security_read(private_parent, monkeypatch):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    w = s._Windows()
    # Substitute only the owner SID result; real handle/descriptor acquisition
    # runs. Changing an object's owner to another user requires extra privilege.
    monkeypatch.setattr(w, 'sid', lambda pointer: 'S-1-5-21-1-2-3-9999')
    with w.open(root) as handle, pytest.raises(s.ConfigurationStorageRefused):
        w.inspect(handle, directory=True)


def test_creation_is_protected_before_admission_readback(private_parent, monkeypatch):
    s, parent, _ = private_parent
    original = s._Windows.create
    checked = []
    def observe_created(windows, path):
        original(windows, path)
        with windows.open(path) as handle:
            windows.inspect(handle, directory=True)
        checked.append(path)
    monkeypatch.setattr(s._Windows, 'create', observe_created)
    s.admit_configuration_storage(parent / 'prime-config')
    assert checked == [parent / 'prime-config']


def test_privacy_error_has_safe_http_classification():
    from rook.agent.chat import server
    error = storage().ConfigurationStorageRefused()
    response = server._exception_response(error)
    assert response.status == 409
    value = json.loads(response.text)
    assert value['error']['code'] == 'configuration_storage_refused'
    assert 'Operation not started' in value['error']['message']


@pytest.mark.parametrize('policy', ['missing_inheritance', 'inherit_only_read'])
def test_root_must_protect_future_files(private_parent, policy):
    s, parent, acl = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    set_acl(root, acl.replace('OICI','') if policy == 'missing_inheritance' else acl + '(A;OIIO;FR;;;WD)')
    with pytest.raises(s.ConfigurationStorageRefused):
        s.admit_configuration_storage(root)


@pytest.mark.asyncio
@pytest.mark.parametrize('runtime', ['node', 'bun'])
async def test_real_prime_writes_refresh_and_replacement_preserve_acl(private_parent, tmp_path, runtime):
    s, parent, _ = private_parent
    root = parent / 'prime-config'
    s.admit_configuration_storage(root)
    prime = Path('D:/prime-agent/.worktrees/rookchat-configuration')
    fixture = Path(__file__).parent / 'fixtures/prime_configuration_storage.mjs'
    common_path = Path(__file__).parents[2] / 'scripts/qualification/rookchat_prime_acp_common.py'
    spec = importlib.util.spec_from_file_location('storage_test_common', common_path)
    common = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = common
    spec.loader.exec_module(common)
    if runtime == 'node':
        argv = ('C:/Program Files/nodejs/node.exe','--import',(prime/'node_modules/tsx/dist/loader.mjs').as_uri(),str(fixture))
    else:
        argv = ('C:/Users/bring/.bun/bin/bun.exe','--no-install','--no-env-file',str(fixture))
    env = {'SystemRoot':os.environ['SystemRoot'], 'WINDIR':os.environ['SystemRoot'], 'PATH':'',
           'HOME':str(tmp_path),'USERPROFILE':str(tmp_path),'TEMP':str(tmp_path),'TMP':str(tmp_path),
           'ROOK_STORAGE_PRIME_SOURCE':str(prime),'PRIME_AGENT_CODING_AGENT_DIR':str(root),
           'TSX_TSCONFIG_PATH':str(prime/'tsconfig.json'),'TSX_DISABLE_CACHE':'1','DO_NOT_TRACK':'1',
           'ESBUILD_BINARY_PATH':str(prime/'node_modules/@esbuild/win32-x64/esbuild.exe')}
    result = await common.run_bounded_process(common.ProcessSpec(argv,tmp_path,env,90,10,65536))
    assert result.direct_child_exit_observed and not result.timed_out and not result.output_overflow
    assert result.exit_code == 0 and not result.stderr, result.stderr.decode(errors='replace')
    report = json.loads(result.stdout)
    assert report['outcome'] == 'passed' and report['contacts'] == 0
    sid = s._Windows().user_sid
    phases = set()
    temporary = set()
    for observation in report['reports']:
        phases.add(observation['phase'])
        acl = observation['acl']
        assert acl['aces']
        assert all(ace['type'] == 'Allow' and ace['sid'] in {sid,'S-1-5-18','S-1-5-32-544'} for ace in acl['aces'])
        assert any(ace['sid'] == sid and ace['rights'] & 0x1F01FF == 0x1F01FF for ace in acl['aces'])
        if observation['name'].endswith('.tmp'):
            temporary.add(observation['phase'])
    assert {'sync-create','async-replace','oauth-refresh','settings-replace','models-replace'} <= phases
    assert temporary == {'settings-replace','models-replace'}
    s.admit_configuration_storage(root)
